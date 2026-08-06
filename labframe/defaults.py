"""Convenience command defaults for projects using Labframe as a dependency."""

import argparse
import subprocess
import sys
from pathlib import Path

from labframe.project import _normalized_name


def _project_defaults(arguments: list[str]) -> list[str]:
    """Return shortcut defaults without replacing an explicit runs directory."""
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("directory", nargs="?", type=Path)
    parser.add_argument("--name")
    parser.add_argument("--runs-dir", type=Path)
    parser.add_argument("--no-venv", action="store_true")
    parser.add_argument("--no-sync", action="store_true")
    parser.add_argument("--no-git", action="store_true")
    parsed, _ = parser.parse_known_args(arguments)

    defaults = ["--no-venv", "--no-git"]
    if parsed.runs_dir is None and parsed.directory is not None:
        project_name = _normalized_name(parsed.directory, parsed.name)
        defaults.extend(["--runs-dir", str(Path.home() / "data" / "labframe" / project_name)])
    return defaults


def new_project() -> None:
    """Initialize a project in the containing environment with project-scoped run storage."""
    arguments = sys.argv[1:]
    command = [
        "labframe",
        "init",
        *_project_defaults(arguments),
        *arguments,
    ]
    raise SystemExit(subprocess.call(command))
