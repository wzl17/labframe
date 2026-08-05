"""Command line interface for Labframe."""

import argparse
from pathlib import Path

from labframe.project import find_project_root, initialize_project
from labframe.runner import run_project


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="labframe",
        description="Initialize and run reproducible simulation or experiment projects.",
    )
    parser.add_argument("--version", action="version", version="%(prog)s 0.1.0")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="create a project from the bundled template")
    init_parser.add_argument("directory", type=Path, help="new project directory")
    init_parser.add_argument("--name", help="project name written to pyproject.toml")
    init_parser.add_argument(
        "--no-sync",
        action="store_true",
        help="create the uv project without resolving and installing dependencies",
    )
    init_parser.add_argument(
        "--no-git",
        action="store_true",
        help="create files without initializing and committing the Git repository",
    )

    run_parser = subparsers.add_parser("run", help="run simulation, fit, plot, and summary hooks")
    run_parser.add_argument(
        "config",
        nargs="?",
        type=Path,
        default=Path("configs/default.yaml"),
        help="configuration relative to the project root (default: configs/default.yaml)",
    )
    run_parser.add_argument(
        "--project",
        type=Path,
        help="project root; otherwise search upward from the current directory",
    )
    run_parser.add_argument(
        "--commit",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="commit the launch source after a successful run (default: enabled)",
    )
    run_parser.add_argument("--message", help="commit message for the launch source")
    run_parser.add_argument(
        "--yes",
        action="store_true",
        help="skip confirmation before commit mode captures dirty source files",
    )
    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    if args.command == "init":
        project_root = initialize_project(
            args.directory,
            name=args.name,
            sync=not args.no_sync,
            initialize_git=not args.no_git,
        )
        print(project_root)
        return

    if args.command == "run":
        if (args.message or args.yes) and not args.commit:
            parser.error("--message and --yes cannot be used with --no-commit")
        project_root = args.project.resolve() if args.project else find_project_root(Path.cwd())
        run_dir = run_project(
            project_root,
            args.config,
            commit=args.commit,
            message=args.message,
            yes=args.yes,
        )
        print(run_dir.relative_to(project_root))
        return

    parser.error(f"unknown command: {args.command}")
