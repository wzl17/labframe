"""Command line interface for Labframe."""

import argparse
from pathlib import Path

from labframe import __version__
from labframe.project import find_project_root, initialize_project, project_commit_default
from labframe.replot import regenerate_plots
from labframe.runner import run_project


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="labframe",
        description="Initialize and run reproducible simulation or experiment projects.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="create a project from the bundled template")
    init_parser.add_argument("directory", type=Path, help="new project directory")
    init_parser.add_argument("--name", help="project name used in generated files")
    init_parser.add_argument(
        "--runs-dir",
        type=Path,
        metavar="PATH",
        help="directory for run folders; relative paths use the project root (default: runs)",
    )
    dependency_group = init_parser.add_mutually_exclusive_group()
    dependency_group.add_argument(
        "--no-venv",
        action="store_true",
        help="use a containing project's environment and omit the standalone pyproject.toml",
    )
    dependency_group.add_argument(
        "--no-sync",
        action="store_true",
        help="write standalone project files without invoking uv",
    )
    init_parser.add_argument(
        "--no-git",
        action="store_true",
        help="create files without initializing and committing the Git repository",
    )

    run_parser = subparsers.add_parser("run", help="run workflow, plot, and summary hooks")
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
        default=None,
        help="override the .labframe.yaml commit setting for this run",
    )
    run_parser.add_argument("--message", help="commit message for the launch source")
    run_parser.add_argument(
        "--yes",
        action="store_true",
        help="skip confirmation before commit mode captures dirty source files",
    )
    notes_group = run_parser.add_mutually_exclusive_group()
    notes_group.add_argument(
        "--notes",
        metavar="TEXT",
        help="save Markdown notes without prompting",
    )
    notes_group.add_argument(
        "--no-notes-prompt",
        action="store_true",
        help="skip the optional interactive notes prompt",
    )

    plot_parser = subparsers.add_parser("plot", help="regenerate one completed run's figures from saved results")
    plot_parser.add_argument(
        "run",
        type=Path,
        help="run name or path inside the configured runs directory",
    )
    plot_parser.add_argument(
        "--project",
        type=Path,
        help="project root; otherwise search upward from the current directory",
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
            create_venv=not args.no_venv,
            initialize_git=not args.no_git,
            runs_dir=args.runs_dir,
        )
        print(project_root)
        return

    if args.command == "run":
        project_root = args.project.resolve() if args.project else find_project_root(Path.cwd())
        commit = args.commit if args.commit is not None else project_commit_default(project_root)
        if (args.message or args.yes) and not commit:
            parser.error("--message and --yes require commit mode; use --commit to override the project setting")
        run_dir = run_project(
            project_root,
            args.config,
            commit=commit,
            message=args.message,
            yes=args.yes,
            notes=args.notes,
            prompt_for_notes=not args.no_notes_prompt,
        )
        try:
            displayed_run_dir = run_dir.relative_to(project_root)
        except ValueError:
            displayed_run_dir = run_dir
        print(displayed_run_dir)
        return

    if args.command == "plot":
        project_root = args.project.resolve() if args.project else find_project_root(Path.cwd())
        run_dir, index_path = regenerate_plots(project_root, args.run)
        try:
            displayed_run_dir = run_dir.relative_to(project_root)
        except ValueError:
            displayed_run_dir = run_dir
        print(f"Regenerated plots in {displayed_run_dir}")
        print(f"Rebuilt {index_path}")
        return

    parser.error(f"unknown command: {args.command}")
