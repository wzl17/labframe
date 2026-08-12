"""Regenerate a completed run's figures from its saved results."""

import tempfile
from pathlib import Path

from labframe.project import is_project_root, project_runs_dir
from labframe.rebuild import _load_summary_module, _read_completed_run
from labframe.runner import _load_hook, _project_on_path


def _resolve_run_dir(project_root: Path, requested: Path) -> Path:
    """Resolve a run name or path and require a direct child of the configured runs directory."""
    runs_dir = project_runs_dir(project_root)
    if requested.is_absolute():
        run_dir = requested.resolve()
    else:
        project_relative = (project_root / requested).resolve()
        run_dir = project_relative if project_relative.parent == runs_dir else (runs_dir / requested).resolve()

    if run_dir.parent != runs_dir:
        raise ValueError(f"Run must be a direct child of the configured runs directory: {runs_dir}")
    if not run_dir.is_dir():
        raise FileNotFoundError(f"Run directory not found: {run_dir}")
    return run_dir


def _replace_figures(run_dir: Path, staged_figures: Path, staging_dir: Path) -> None:
    figures_dir = run_dir / "figures"
    previous_figures = staging_dir / "previous_figures"
    if figures_dir.is_symlink():
        raise ValueError(f"Figures path must not be a symlink: {figures_dir}")
    had_previous_figures = figures_dir.exists()
    if had_previous_figures:
        if not figures_dir.is_dir():
            raise ValueError(f"Figures path must be a directory, not a file: {figures_dir}")
        figures_dir.replace(previous_figures)

    try:
        staged_figures.replace(figures_dir)
    except BaseException:
        if had_previous_figures and previous_figures.exists() and not figures_dir.exists():
            previous_figures.replace(figures_dir)
        raise


def regenerate_plots(project_root: Path, requested_run: Path) -> tuple[Path, Path]:
    """Replace one completed run's figures and refresh its summary and index.

    The current project's plotting hook reads a staged view of the saved
    ``results/`` directory. New figures are installed only after that hook
    succeeds, so a plotting error leaves the existing figures untouched.
    """
    project_root = project_root.resolve()
    if not is_project_root(project_root):
        raise ValueError(f"Not a Labframe project: {project_root}")
    run_dir = _resolve_run_dir(project_root, requested_run)
    problem = _read_completed_run(run_dir, require_figures=False)
    if problem is not None:
        raise ValueError(f"Cannot regenerate plots for {run_dir.name}: {problem}")

    runs_dir = project_runs_dir(project_root)
    with tempfile.TemporaryDirectory(prefix=f".{run_dir.name}-plots-", dir=runs_dir) as temporary_directory:
        staging_dir = Path(temporary_directory)
        (staging_dir / "results").symlink_to(run_dir / "results", target_is_directory=True)
        staged_figures = staging_dir / "figures"
        staged_figures.mkdir()
        with _project_on_path(project_root):
            plot = _load_hook(project_root, "plot")
            plot(staging_dir)
        _replace_figures(run_dir, staged_figures, staging_dir)

    summary_module = _load_summary_module(project_root)
    with _project_on_path(project_root):
        summary_module.build_summary(run_dir)
        index_path = summary_module.rebuild_index(project_root, runs_dir)
    return run_dir, index_path
