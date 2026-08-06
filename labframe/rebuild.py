"""Rebuild run summaries and the configured run-directory index."""

import argparse
import importlib.util
import json
import sys
import uuid
from contextlib import contextmanager
from pathlib import Path

import yaml

from labframe.project import PROJECT_HOOKS, find_project_root, is_project_root, project_runs_dir


@contextmanager
def _project_on_path(project_root: Path):
    original = list(sys.path)
    sys.path.insert(0, str(project_root))
    try:
        yield
    finally:
        sys.path[:] = original


def _load_summary_module(project_root: Path):
    filename, _ = PROJECT_HOOKS["summary"]
    path = project_root / filename
    module_name = f"_labframe_rebuild_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    with _project_on_path(project_root):
        spec.loader.exec_module(module)
    if not callable(getattr(module, "build_summary", None)):
        raise TypeError(f"{filename} must define callable build_summary()")
    if not callable(getattr(module, "rebuild_index", None)):
        raise TypeError(f"{filename} must define callable rebuild_index()")
    return module


def _read_completed_run(run_dir: Path) -> str | None:
    required_files = ("config.yaml", "meta.json", "output.log")
    missing = [name for name in required_files if not (run_dir / name).is_file()]
    required_directories = ("results", "figures")
    missing.extend(name for name in required_directories if not (run_dir / name).is_dir())
    if missing:
        return f"missing {', '.join(missing)}"

    try:
        config = yaml.safe_load((run_dir / "config.yaml").read_text(encoding="utf-8"))
        meta = json.loads((run_dir / "meta.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, yaml.YAMLError) as error:
        return f"unreadable saved data ({error})"
    if not isinstance(config, dict):
        return "config.yaml is not a mapping"
    if not isinstance(meta, dict):
        return "meta.json is not an object"
    if meta.get("status") != "completed":
        return f"status is {meta.get('status', 'missing')!r}"
    return None


def rebuild_project(project_root: Path) -> tuple[Path, int, int]:
    """Refresh completed summaries and return index path and run counts."""
    project_root = project_root.resolve()
    if not is_project_root(project_root):
        raise ValueError(f"Not a Labframe project: {project_root}")
    runs_dir = project_runs_dir(project_root)
    runs_dir.mkdir(parents=True, exist_ok=True)
    module = _load_summary_module(project_root)
    refreshed = 0
    skipped = 0

    for run_dir in sorted(runs_dir.iterdir(), key=lambda path: path.name):
        if not run_dir.is_dir():
            continue
        problem = _read_completed_run(run_dir)
        if problem is not None:
            print(f"warning: skipping {run_dir.name}: {problem}", file=sys.stderr)
            skipped += 1
            continue
        try:
            with _project_on_path(project_root):
                module.build_summary(run_dir)
        except Exception as error:
            print(f"warning: skipping {run_dir.name}: summary rebuild failed ({error})", file=sys.stderr)
            skipped += 1
            continue
        refreshed += 1

    with _project_on_path(project_root):
        index_path = module.rebuild_index(project_root, runs_dir)
    return index_path, refreshed, skipped


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="labframe-update-index",
        description="Rebuild saved run summaries and the configured runs index without rerunning computation.",
    )
    parser.add_argument(
        "--project",
        type=Path,
        help="project root; otherwise search upward from the current directory",
    )
    return parser


def update_index() -> None:
    """Console entry point for rebuilding derived reports and the run index."""
    args = _build_parser().parse_args()
    project_root = args.project.resolve() if args.project else find_project_root(Path.cwd())
    index_path, refreshed, skipped = rebuild_project(project_root)
    print(f"Rebuilt {index_path} (refreshed {refreshed}, skipped {skipped}).")
