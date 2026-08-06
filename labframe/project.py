"""Project discovery and initialization."""

import os
import re
import shutil
import subprocess
from pathlib import Path

import yaml

PROJECT_HOOKS = {
    "workflow": ("workflow.py", "run_workflow"),
    "plot": ("plot_results.py", "plot_results"),
    "summary": ("build_summary.py", "build_summary"),
}
PROJECT_SETTINGS = ".labframe.yaml"
_TEMPLATE_SUFFIX = ".tmpl"


def is_project_root(directory: Path) -> bool:
    """Return whether a directory contains the conventional Labframe hooks."""
    return all((directory / filename).is_file() for filename, _ in PROJECT_HOOKS.values())


def find_project_root(start: Path) -> Path:
    """Find the nearest parent containing the conventional Labframe hooks."""
    candidate = start.resolve()
    for directory in (candidate, *candidate.parents):
        if is_project_root(directory):
            return directory
    raise FileNotFoundError(f"No Labframe project found at or above {candidate}")


def _project_settings(project_root: Path) -> dict:
    """Load a project's optional Labframe settings."""
    project_root = project_root.resolve()
    settings_path = project_root / PROJECT_SETTINGS
    if not settings_path.is_file():
        return {}

    settings = yaml.safe_load(settings_path.read_text(encoding="utf-8"))
    if not isinstance(settings, dict):
        raise ValueError(f"The settings root must be a mapping: {settings_path}")
    return settings


def project_runs_dir(project_root: Path) -> Path:
    """Return the configured directory that contains a project's run folders."""
    project_root = project_root.resolve()
    settings_path = project_root / PROJECT_SETTINGS
    settings = _project_settings(project_root)
    configured = settings.get("runs_dir", "runs")
    if not isinstance(configured, str) or not configured.strip():
        raise ValueError(f"runs_dir must be a non-empty path string: {settings_path}")

    path = Path(configured)
    return (path if path.is_absolute() else project_root / path).resolve()


def project_commit_default(project_root: Path) -> bool:
    """Return whether runs should commit launch source unless the CLI overrides it."""
    project_root = project_root.resolve()
    settings_path = project_root / PROJECT_SETTINGS
    configured = _project_settings(project_root).get("commit", True)
    if not isinstance(configured, bool):
        raise ValueError(f"commit must be true or false: {settings_path}")
    return configured


def _normalized_name(target: Path, requested_name: str | None) -> str:
    name = requested_name or target.name
    normalized = re.sub(r"[^a-zA-Z0-9._-]+", "-", name).strip("-_.").lower()
    if not normalized:
        raise ValueError("The project name must contain a letter or number")
    return normalized


def _local_labframe_source() -> Path | None:
    source_root = Path(__file__).resolve().parents[1]
    pyproject = source_root / "pyproject.toml"
    if pyproject.is_file() and 'name = "labframe"' in pyproject.read_text(encoding="utf-8"):
        return source_root
    return None


def _template_context(target: Path, project_name: str) -> dict[str, str]:
    source = _local_labframe_source()
    uv_source = ""
    if source is not None:
        relative_source = Path(os.path.relpath(source, target)).as_posix()
        uv_source = f'\n[tool.uv.sources]\nlabframe = {{ path = "{relative_source}", editable = true }}\n'
    return {
        "PROJECT_NAME": project_name,
        "UV_SOURCE_BLOCK": uv_source,
    }


def _render_template(text: str, context: dict[str, str]) -> str:
    for key, value in context.items():
        text = text.replace(f"{{{{{key}}}}}", value)
    return text


def _copy_template(
    template_root: Path,
    target: Path,
    context: dict[str, str],
    *,
    include_pyproject: bool,
    include_default_runs: bool,
) -> None:
    for source in sorted(template_root.rglob("*")):
        if "__pycache__" in source.parts or source.suffix in {".pyc", ".pyo"}:
            continue
        relative = source.relative_to(template_root)
        if not include_default_runs and relative.parts[0] == "runs":
            continue
        if not include_pyproject and relative == Path("pyproject.toml.tmpl"):
            continue
        destination_relative = relative.with_suffix("") if source.name.endswith(_TEMPLATE_SUFFIX) else relative
        destination = target / destination_relative
        if source.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
        elif source.name.endswith(_TEMPLATE_SUFFIX):
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(_render_template(source.read_text(encoding="utf-8"), context), encoding="utf-8")
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)


def _run(command: list[str], project_root: Path) -> None:
    subprocess.run(command, cwd=project_root, check=True)


def _initial_commit(project_root: Path) -> None:
    name = subprocess.run(
        ["git", "config", "user.name"],
        cwd=project_root,
        check=False,
        capture_output=True,
        text=True,
    ).stdout.strip()
    email = subprocess.run(
        ["git", "config", "user.email"],
        cwd=project_root,
        check=False,
        capture_output=True,
        text=True,
    ).stdout.strip()
    command = ["git"]
    if not name:
        command.extend(["-c", "user.name=Labframe"])
    if not email:
        command.extend(["-c", "user.email=labframe@localhost"])
    command.extend(["commit", "-m", "Initialize Labframe project"])
    _run(command, project_root)


def initialize_project(
    directory: Path,
    *,
    name: str | None = None,
    sync: bool = True,
    create_venv: bool = True,
    initialize_git: bool = True,
    runs_dir: Path | None = None,
) -> Path:
    """Create a Labframe project and optionally prepare uv and Git.

    ``create_venv=False`` omits the standalone ``pyproject.toml`` and leaves
    dependency and environment management to a containing project.
    """
    target = directory.resolve()
    if target.exists() and any(target.iterdir()):
        raise FileExistsError(f"Project directory is not empty: {target}")

    requested_runs_dir = runs_dir or Path("runs")
    resolved_runs_dir = (
        requested_runs_dir
        if requested_runs_dir.is_absolute()
        else target / requested_runs_dir
    ).resolve()
    if resolved_runs_dir == target:
        raise ValueError("The runs directory cannot be the project root")
    target.mkdir(parents=True, exist_ok=True)

    if requested_runs_dir.is_absolute():
        stored_runs_dir = str(resolved_runs_dir)
    else:
        stored_runs_dir = Path(os.path.relpath(resolved_runs_dir, target)).as_posix()

    project_name = _normalized_name(target, name)
    template_root = Path(__file__).resolve().parent / "project_template"
    if not template_root.is_dir():
        raise RuntimeError(f"Bundled project template is missing: {template_root}")
    _copy_template(
        template_root,
        target,
        _template_context(target, project_name),
        include_pyproject=create_venv,
        include_default_runs=resolved_runs_dir == target / "runs",
    )
    (target / PROJECT_SETTINGS).write_text(
        yaml.safe_dump({"runs_dir": stored_runs_dir, "commit": True}, sort_keys=False),
        encoding="utf-8",
    )
    resolved_runs_dir.mkdir(parents=True, exist_ok=True)
    try:
        resolved_runs_dir.relative_to(target)
    except ValueError:
        pass
    else:
        if resolved_runs_dir != target / "runs":
            (resolved_runs_dir / ".gitignore").write_text("*\n!.gitignore\n", encoding="utf-8")

    if sync and create_venv:
        _run(["uv", "sync"], target)

    if initialize_git:
        _run(["git", "init"], target)
        _run(["git", "add", "-A"], target)
        _initial_commit(target)

    return target
