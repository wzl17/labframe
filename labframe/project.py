"""Project discovery and initialization."""

import os
import re
import shutil
import subprocess
import tomllib
from pathlib import Path

PROJECT_FILE = "pyproject.toml"
_TEMPLATE_SUFFIX = ".tmpl"


def load_project_settings(project_root: Path) -> dict[str, str]:
    """Load and validate the small ``[tool.labframe]`` hook table."""
    path = project_root / PROJECT_FILE
    try:
        document = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise FileNotFoundError(f"Labframe project file not found: {path}") from error
    settings = document.get("tool", {}).get("labframe")
    if not isinstance(settings, dict):
        raise ValueError(f"Missing [tool.labframe] table in {path}")
    return settings


def find_project_root(start: Path) -> Path:
    """Find the nearest parent containing a Labframe-enabled pyproject.toml."""
    candidate = start.resolve()
    for directory in (candidate, *candidate.parents):
        try:
            load_project_settings(directory)
        except (FileNotFoundError, ValueError, tomllib.TOMLDecodeError):
            continue
        return directory
    raise FileNotFoundError(f"No Labframe-enabled {PROJECT_FILE} found at or above {candidate}")


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


def _copy_template(template_root: Path, target: Path, context: dict[str, str]) -> None:
    for source in sorted(template_root.rglob("*")):
        if "__pycache__" in source.parts or source.suffix in {".pyc", ".pyo"}:
            continue
        relative = source.relative_to(template_root)
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
    initialize_git: bool = True,
) -> Path:
    """Create an editable Labframe project and optionally prepare uv and Git."""
    target = directory.resolve()
    if target.exists() and any(target.iterdir()):
        raise FileExistsError(f"Project directory is not empty: {target}")
    target.mkdir(parents=True, exist_ok=True)

    project_name = _normalized_name(target, name)
    template_root = Path(__file__).resolve().parent / "project_template"
    if not template_root.is_dir():
        raise RuntimeError(f"Bundled project template is missing: {template_root}")
    _copy_template(template_root, target, _template_context(target, project_name))

    if sync:
        _run(["uv", "sync"], target)

    if initialize_git:
        _run(["git", "init"], target)
        _run(["git", "add", "-A"], target)
        _initial_commit(target)

    return target
