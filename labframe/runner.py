"""Configuration-driven run orchestration for generated projects."""

import hashlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from datetime import datetime
from pathlib import Path

import yaml

from labframe.catalog import synchronize_catalog
from labframe.project import PROJECT_HOOKS, is_project_root, project_runs_dir


class _Tee:
    def __init__(self, *streams) -> None:
        self.streams = streams

    def write(self, text: str) -> int:
        for stream in self.streams:
            stream.write(text)
        return len(text)

    def flush(self) -> None:
        for stream in self.streams:
            stream.flush()


def _git(project_root: Path, *args: str, env: dict[str, str] | None = None) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=project_root,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _git_config(project_root: Path, key: str) -> str:
    completed = subprocess.run(
        ["git", "config", key],
        cwd=project_root,
        check=False,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _write_meta(run_dir: Path, meta: dict) -> None:
    temporary = run_dir / ".meta.json.tmp"
    temporary.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    temporary.replace(run_dir / "meta.json")


def _write_notes(run_dir: Path, notes: str) -> None:
    temporary = run_dir / ".notes.md.tmp"
    temporary.write_text(notes, encoding="utf-8")
    temporary.replace(run_dir / "notes.md")


def _collect_notes(notes: str | None, *, prompt: bool) -> str:
    if notes is not None:
        return notes
    if not prompt or not sys.stdin.isatty():
        return ""

    print("Optional Markdown notes (enter a line containing only . to finish):")
    lines = []
    try:
        while True:
            line = input()
            if line == ".":
                return "\n".join(lines)
            lines.append(line)
    except (EOFError, KeyboardInterrupt):
        print("\nNotes skipped.", file=sys.stderr)
        return ""


def _load_config(path: Path) -> dict:
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise ValueError("The configuration root must be a mapping")
    return config


def _new_run_dir(runs_dir: Path, config_bytes: bytes) -> Path:
    timestamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    config_hash = hashlib.sha256(config_bytes).hexdigest()[:8]
    base = runs_dir / f"{timestamp}_{config_hash}"
    candidate = base
    counter = 1
    while candidate.exists():
        candidate = Path(f"{base}_{counter:02d}")
        counter += 1
    (candidate / "results").mkdir(parents=True)
    (candidate / "figures").mkdir()
    return candidate


@contextmanager
def _project_on_path(project_root: Path):
    original = list(sys.path)
    hook_module_names = {Path(filename).stem for filename, _ in PROJECT_HOOKS.values()}
    displaced_hook_modules = {name: sys.modules.pop(name) for name in hook_module_names if name in sys.modules}
    sys.path.insert(0, str(project_root))
    try:
        yield
    finally:
        sys.path[:] = original
        for name, module in list(sys.modules.items()):
            module_file = getattr(module, "__file__", None)
            if module_file is None:
                continue
            try:
                Path(module_file).resolve().relative_to(project_root)
            except ValueError:
                continue
            sys.modules.pop(name, None)
        sys.modules.update(displaced_hook_modules)


def _load_hook(project_root: Path, hook_name: str):
    filename, function_name = PROJECT_HOOKS[hook_name]
    path = project_root / filename
    if not path.is_file():
        raise FileNotFoundError(f"Missing {hook_name} hook file: {path}")
    module_name = path.stem
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    previous_module = sys.modules.get(module_name)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        if previous_module is None:
            sys.modules.pop(module_name, None)
        else:
            sys.modules[module_name] = previous_module
        raise
    function = getattr(module, function_name, None)
    if not callable(function):
        raise TypeError(f"{filename} must define callable {function_name}()")
    return function


def _run_data_pipeline(source_root: Path, run_dir: Path) -> None:
    config = _load_config(run_dir / "config.yaml")
    with _project_on_path(source_root):
        workflow = _load_hook(source_root, "workflow")
        plot = _load_hook(source_root, "plot")
        workflow(config, run_dir / "results")
        plot(run_dir)


def _run_summary(source_root: Path, run_dir: Path) -> None:
    with _project_on_path(source_root):
        summary = _load_hook(source_root, "summary")
        summary(run_dir)


def _snapshot_tree(project_root: Path, starting_commit: str) -> tuple[str, str, Path]:
    if _git(project_root, "ls-files", "-u"):
        raise RuntimeError("Unresolved merge conflicts must be resolved before --commit")
    branch = _git(project_root, "symbolic-ref", "--quiet", "--short", "HEAD")
    temp_dir = Path(tempfile.mkdtemp(prefix="labframe-snapshot-"))
    index_path = temp_dir / "index"
    env = os.environ.copy()
    env["GIT_INDEX_FILE"] = str(index_path)
    _git(project_root, "read-tree", starting_commit, env=env)
    _git(project_root, "add", "-A", "--", ".", env=env)
    tree = _git(project_root, "write-tree", env=env)
    return branch, tree, temp_dir


def _materialize_tree(project_root: Path, tree: str, destination: Path) -> None:
    archive = subprocess.run(
        ["git", "archive", "--format=tar", tree],
        cwd=project_root,
        check=True,
        capture_output=True,
    ).stdout
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as tar:
        tar.extractall(destination, filter="data")


def _create_snapshot_commit(project_root: Path, tree: str, starting_commit: str, message: str) -> str:
    starting_tree = _git(project_root, "rev-parse", f"{starting_commit}^{{tree}}")
    if tree == starting_tree:
        return starting_commit
    env = os.environ.copy()
    name = _git_config(project_root, "user.name")
    email = _git_config(project_root, "user.email")
    if not name:
        env.setdefault("GIT_AUTHOR_NAME", "Labframe")
        env.setdefault("GIT_COMMITTER_NAME", "Labframe")
    if not email:
        env.setdefault("GIT_AUTHOR_EMAIL", "labframe@localhost")
        env.setdefault("GIT_COMMITTER_EMAIL", "labframe@localhost")
    return _git(project_root, "commit-tree", tree, "-p", starting_commit, "-m", message, env=env)


def _advance_branch(project_root: Path, branch: str, commit: str, starting_commit: str) -> None:
    _git(project_root, "update-ref", f"refs/heads/{branch}", commit, starting_commit)
    _git(project_root, "read-tree", commit)


def _config_path(project_root: Path, requested: Path) -> tuple[Path, Path]:
    path = requested if requested.is_absolute() else project_root / requested
    resolved = path.resolve()
    try:
        relative = resolved.relative_to(project_root)
    except ValueError as error:
        raise ValueError("The configuration must be inside the project directory") from error
    if not resolved.is_file():
        raise FileNotFoundError(f"Configuration not found: {relative}")
    return resolved, relative


def run_project(
    project_root: Path,
    config: Path,
    *,
    commit: bool,
    message: str | None,
    yes: bool,
    notes: str | None = None,
    prompt_for_notes: bool = True,
) -> Path:
    """Execute the pipeline and return the completed run folder; only notes.md stays editable."""
    project_root = project_root.resolve()
    if not is_project_root(project_root):
        raise ValueError(f"Not a Labframe project: {project_root}")
    runs_dir = project_runs_dir(project_root)
    config_path, config_relative = _config_path(project_root, config)
    starting_commit = _git(project_root, "rev-parse", "HEAD")
    dirty = _git(project_root, "status", "--porcelain")
    if dirty and not commit:
        raise RuntimeError("The working tree is dirty. Commit manually or rerun without --no-commit.")

    started = time.monotonic()
    started_at = datetime.now().astimezone().isoformat(timespec="seconds")
    run_dir: Path | None = None
    snapshot_temp: Path | None = None
    git_commit: str | None = starting_commit if not commit else None

    try:
        if commit:
            branch, tree, snapshot_temp = _snapshot_tree(project_root, starting_commit)
            source_root = snapshot_temp / "source"
            source_root.mkdir()
            _materialize_tree(project_root, tree, source_root)
            snapshot_config = source_root / config_relative
            if not snapshot_config.is_file():
                raise RuntimeError("The selected configuration is absent from the launch snapshot")
            config_bytes = snapshot_config.read_bytes()
            starting_tree = _git(project_root, "rev-parse", f"{starting_commit}^{{tree}}")
            if tree != starting_tree and not yes:
                if not sys.stdin.isatty():
                    raise RuntimeError("Use --yes to confirm commit mode in a non-interactive shell")
                answer = input("Commit the launch source after a successful run? [y/N] ")
                if answer.strip().lower() not in {"y", "yes"}:
                    raise RuntimeError("Commit-mode run cancelled")
        else:
            source_root = project_root
            config_bytes = config_path.read_bytes()

        run_dir = _new_run_dir(runs_dir, config_bytes)
        (run_dir / "config.yaml").write_bytes(config_bytes)
        meta = {
            "git_commit": git_commit,
            "project_root": str(project_root),
            "runs_dir": str(runs_dir),
            "started_at": started_at,
            "runtime_seconds": 0.0,
            "status": "running",
        }
        _write_meta(run_dir, meta)

        with (run_dir / "output.log").open("w", encoding="utf-8", buffering=1) as output:
            with redirect_stdout(_Tee(sys.stdout, output)), redirect_stderr(_Tee(sys.stderr, output)):
                _run_data_pipeline(source_root, run_dir)

        meta.update(
            runtime_seconds=round(time.monotonic() - started, 3),
            status="completed",
        )
        _write_meta(run_dir, meta)
        _write_notes(run_dir, _collect_notes(notes, prompt=prompt_for_notes))
        _run_summary(source_root, run_dir)

        if commit:
            git_commit = _create_snapshot_commit(
                project_root,
                tree,
                starting_commit,
                message or f"labframe run: {config_relative.stem}",
            )
            meta["git_commit"] = git_commit
            _write_meta(run_dir, meta)
            _run_summary(source_root, run_dir)
            _advance_branch(project_root, branch, git_commit, starting_commit)

    except BaseException:
        if run_dir is not None:
            _write_meta(
                run_dir,
                {
                    "git_commit": git_commit,
                    "project_root": str(project_root),
                    "runs_dir": str(runs_dir),
                    "started_at": started_at,
                    "runtime_seconds": round(time.monotonic() - started, 3),
                    "status": "failed",
                },
            )
        raise
    finally:
        if snapshot_temp is not None:
            shutil.rmtree(snapshot_temp)

    assert run_dir is not None
    try:
        synchronize_catalog(project_root, runs_dir)
    except Exception as error:
        print(f"warning: run completed but catalog refresh failed ({error})", file=sys.stderr)
    return run_dir
