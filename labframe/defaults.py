"""Convenience command defaults for projects using Labframe as a dependency."""

import subprocess
import sys
from pathlib import Path


def new_project() -> None:
    """Initialize a project in the containing environment with shared run storage."""
    command = [
        "labframe",
        "init",
        "--no-venv",
        "--no-git",
        "--runs-dir",
        str(Path.home() / "data" / "labframe"),
        *sys.argv[1:],
    ]
    raise SystemExit(subprocess.call(command))
