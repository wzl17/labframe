"""Run the complete configuration-to-summary simulation workflow."""

import argparse
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent


class _Tee:
    """Write text to every supplied stream."""

    def __init__(self, *streams) -> None:
        self.streams = streams

    def write(self, text: str) -> int:
        for stream in self.streams:
            stream.write(text)
        return len(text)

    def flush(self) -> None:
        for stream in self.streams:
            stream.flush()


def _git(*args: str, env: dict[str, str] | None = None) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=PROJECT_ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _write_meta(run_dir: Path, meta: dict) -> None:
    (run_dir / "meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")


def _config_relative_path(config_path: Path) -> Path:
    resolved = config_path.resolve()
    try:
        return resolved.relative_to(PROJECT_ROOT)
    except ValueError as error:
        raise ValueError("The configuration must be inside the project directory") from error


def _new_run_dir(config_bytes: bytes) -> Path:
    timestamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    config_hash = hashlib.sha256(config_bytes).hexdigest()[:8]
    base = PROJECT_ROOT / "runs" / f"{timestamp}_{config_hash}"
    candidate = base
    counter = 1
    while candidate.exists():
        candidate = Path(f"{base}_{counter:02d}")
        counter += 1
    candidate.mkdir(parents=True)
    (candidate / "results").mkdir()
    (candidate / "figures").mkdir()
    return candidate


def _run_core(run_dir: Path) -> None:
    from plot_results import plot_results
    from simulation import run_simulation

    config = yaml.safe_load((run_dir / "config.yaml").read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise ValueError("The configuration root must be a mapping")
    with (run_dir / "output").open("w", encoding="utf-8", buffering=1) as output_stream:
        with (
            redirect_stdout(_Tee(sys.stdout, output_stream)),
            redirect_stderr(_Tee(sys.stderr, output_stream)),
        ):
            run_simulation(config, run_dir / "results")
            plot_results(run_dir)


def _render_summary(run_dir: Path) -> None:
    from build_summary import build_summary

    build_summary(run_dir)


def _snapshot_tree(starting_commit: str) -> tuple[str, str, Path]:
    if _git("ls-files", "-u"):
        raise RuntimeError("Unresolved merge conflicts must be resolved before --commit")
    branch = _git("symbolic-ref", "--quiet", "--short", "HEAD")
    temp_dir = Path(tempfile.mkdtemp(prefix="simulation-snapshot-"))
    index_path = temp_dir / "index"
    env = os.environ.copy()
    env["GIT_INDEX_FILE"] = str(index_path)
    _git("read-tree", starting_commit, env=env)
    _git("add", "-A", "--", ".", env=env)
    tree = _git("write-tree", env=env)
    return branch, tree, temp_dir


def _materialize_tree(tree: str, destination: Path) -> None:
    archive = subprocess.run(
        ["git", "archive", "--format=tar", tree],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
    ).stdout
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as tar:
        tar.extractall(destination, filter="data")


def _create_snapshot_commit(tree: str, starting_commit: str, message: str) -> str:
    starting_tree = _git("rev-parse", f"{starting_commit}^{{tree}}")
    if tree == starting_tree:
        return starting_commit

    return _git("commit-tree", tree, "-p", starting_commit, "-m", message)


def _commit_run_outputs(run_dir: Path, source_commit: str, starting_commit: str, branch: str, message: str) -> str:
    temp_dir = Path(tempfile.mkdtemp(prefix="simulation-results-"))
    try:
        index_path = temp_dir / "index"
        env = os.environ.copy()
        env["GIT_INDEX_FILE"] = str(index_path)
        _git("read-tree", source_commit, env=env)
        _git(
            "add",
            "-A",
            "--",
            str(run_dir.relative_to(PROJECT_ROOT)),
            "index.html",
            env=env,
        )
        results_tree = _git("write-tree", env=env)
    finally:
        shutil.rmtree(temp_dir)

    source_tree = _git("rev-parse", f"{source_commit}^{{tree}}")
    final_commit = source_commit
    if results_tree != source_tree:
        final_commit = _git("commit-tree", results_tree, "-p", source_commit, "-m", message)

    branch_ref = f"refs/heads/{branch}"
    _git("update-ref", branch_ref, final_commit, starting_commit)
    _git("read-tree", final_commit)
    return final_commit


def _snapshot_worker() -> None:
    action = sys.argv[2]
    run_dir = Path(sys.argv[3]).resolve()
    if action == "core":
        _run_core(run_dir)
    elif action == "summary":
        _render_summary(run_dir)
    else:
        raise ValueError(f"Unknown snapshot worker action: {action}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "config",
        nargs="?",
        type=Path,
        default=Path("configs/default.yaml"),
        help="YAML configuration (default: configs/default.yaml)",
    )
    parser.add_argument(
        "--commit",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="commit the launch snapshot and generated artifacts after success (default: enabled)",
    )
    parser.add_argument("--message", help="message for the generated-run commit")
    parser.add_argument(
        "--yes",
        action="store_true",
        help="skip confirmation when commit mode will capture project changes",
    )
    args = parser.parse_args()
    if (args.message or args.yes) and not args.commit:
        parser.error("--message and --yes cannot be used with --no-commit")
    return args


def main() -> None:
    args = _parse_args()
    config_relative = _config_relative_path(args.config)
    config_path = PROJECT_ROOT / config_relative
    if not config_path.is_file():
        raise FileNotFoundError(f"Configuration not found: {config_relative}")

    starting_commit = _git("rev-parse", "HEAD")
    dirty = _git("status", "--porcelain")
    if dirty and not args.commit:
        raise RuntimeError("The working tree is dirty. Commit manually or rerun without --no-commit.")

    started = time.monotonic()
    started_at = datetime.now().astimezone().isoformat(timespec="seconds")
    run_dir: Path | None = None
    snapshot_temp: Path | None = None
    snapshot_branch: str | None = None
    snapshot_tree: str | None = None
    git_commit: str | None = starting_commit if not args.commit else None

    try:
        if args.commit:
            snapshot_branch, snapshot_tree, active_snapshot_temp = _snapshot_tree(starting_commit)
            snapshot_temp = active_snapshot_temp
            source_dir = active_snapshot_temp / "source"
            source_dir.mkdir()
            _materialize_tree(snapshot_tree, source_dir)
            snapshot_config = source_dir / config_relative
            if not snapshot_config.is_file():
                raise RuntimeError("The selected configuration is ignored by Git and absent from the launch snapshot")
            config_bytes = snapshot_config.read_bytes()
            starting_tree = _git("rev-parse", f"{starting_commit}^{{tree}}")
            if snapshot_tree != starting_tree and not args.yes:
                if not sys.stdin.isatty():
                    raise RuntimeError("Use --yes to confirm commit mode in a non-interactive shell")
                answer = input("Commit the launch snapshot after a successful run? [y/N] ")
                if answer.strip().lower() not in {"y", "yes"}:
                    raise RuntimeError("Commit-mode run cancelled")
        else:
            source_dir = PROJECT_ROOT
            config_bytes = config_path.read_bytes()

        active_run_dir = _new_run_dir(config_bytes)
        run_dir = active_run_dir
        (active_run_dir / "config.yaml").write_bytes(config_bytes)
        _write_meta(
            active_run_dir,
            {
                "git_commit": git_commit,
                "started_at": started_at,
                "runtime_seconds": 0.0,
                "status": "running",
            },
        )

        if args.commit:
            if snapshot_branch is None or snapshot_tree is None:
                raise RuntimeError("Commit snapshot state was not initialized")
            subprocess.run(
                [
                    sys.executable,
                    str(source_dir / "run.py"),
                    "__snapshot_worker__",
                    "core",
                    str(active_run_dir),
                ],
                cwd=source_dir,
                check=True,
            )
            git_commit = _create_snapshot_commit(
                snapshot_tree,
                starting_commit,
                f"simulation source: {config_relative.stem}",
            )
        else:
            _run_core(active_run_dir)

        runtime_seconds = round(time.monotonic() - started, 3)
        _write_meta(
            active_run_dir,
            {
                "git_commit": git_commit,
                "started_at": started_at,
                "runtime_seconds": runtime_seconds,
                "status": "completed",
            },
        )
        if args.commit:
            subprocess.run(
                [
                    sys.executable,
                    str(source_dir / "run.py"),
                    "__snapshot_worker__",
                    "summary",
                    str(active_run_dir),
                ],
                cwd=source_dir,
                check=True,
            )
            if snapshot_branch is None or git_commit is None:
                raise RuntimeError("Commit snapshot state was not initialized")
            _commit_run_outputs(
                active_run_dir,
                git_commit,
                starting_commit,
                snapshot_branch,
                args.message or f"simulation run: {config_relative.stem}",
            )
        else:
            _render_summary(active_run_dir)
        print(active_run_dir.relative_to(PROJECT_ROOT))
    except BaseException:
        if run_dir is None:
            print(
                "Run failed before the run directory was created.",
                file=sys.stderr,
            )
        else:
            _write_meta(
                run_dir,
                {
                    "git_commit": git_commit,
                    "started_at": started_at,
                    "runtime_seconds": round(time.monotonic() - started, 3),
                    "status": "failed",
                },
            )
        raise
    finally:
        if snapshot_temp is not None:
            shutil.rmtree(snapshot_temp)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "__snapshot_worker__":
        _snapshot_worker()
    else:
        main()
