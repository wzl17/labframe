"""Generate figures strictly from saved numerical results."""

import argparse
from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np

from plot_style import FIGURE_SIZE, RC_PARAMS, SAVE_DPI


@dataclass(frozen=True)
class Dataset:
    """One saved x-y dataset and its presentation metadata."""

    filename: str
    x_values: np.ndarray
    y_values: np.ndarray
    x_label: str
    y_label: str
    title: str
    is_rabi_oscillation: bool


def _load_dataset(result_path: Path) -> Dataset:
    with np.load(result_path, allow_pickle=False) as data:
        if len(data.files) != 2:
            raise ValueError(f"Expected exactly two arrays in {result_path.name}, found {len(data.files)}: {data.files}")
        x_name, y_name = data.files
        x_values = data[x_name]
        y_values = data[y_name]

    if x_values.shape != y_values.shape:
        raise ValueError(f"Saved arrays {x_name!r} and {y_name!r} in {result_path.name} have different shapes")
    if x_values.ndim != 1:
        raise ValueError(f"Saved arrays in {result_path.name} must be one-dimensional")

    is_rabi_oscillation = {x_name, y_name} == {
        "time_s",
        "excited_state_probability",
    }
    if is_rabi_oscillation:
        x_values = x_values * 1e6
        x_label = "Time (µs)"
        y_label = "Excited-state probability"
        title = "Two-level-system Rabi oscillation"
    else:
        x_label = x_name
        y_label = y_name
        title = f"{y_name} vs {x_name}"

    return Dataset(
        filename=result_path.name,
        x_values=x_values,
        y_values=y_values,
        x_label=x_label,
        y_label=y_label,
        title=title,
        is_rabi_oscillation=is_rabi_oscillation,
    )


def _create_figure(datasets: list[Dataset]):
    figure, axis = plt.subplots(figsize=FIGURE_SIZE)
    for dataset in datasets:
        axis.plot(dataset.x_values, dataset.y_values, label=dataset.filename)

    common_x_label = len({dataset.x_label for dataset in datasets}) == 1
    common_y_label = len({dataset.y_label for dataset in datasets}) == 1
    common_title = len({dataset.title for dataset in datasets}) == 1
    axis.set(
        xlabel=datasets[0].x_label if common_x_label else "x",
        ylabel=datasets[0].y_label if common_y_label else "y",
        title=datasets[0].title if common_title else "Simulation results",
    )
    if all(dataset.is_rabi_oscillation for dataset in datasets):
        axis.set_ylim(-0.05, 1.05)
    axis.grid(alpha=0.25)
    axis.legend()
    return figure, axis


def plot_results(run_dir: Path) -> None:
    """Read saved results and write figures without rerunning the simulation."""
    result_paths = sorted((run_dir / "results").glob("*.npz"))
    if not result_paths:
        raise ValueError("No .npz result files found")

    figures_dir = run_dir / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)
    datasets = [_load_dataset(path) for path in result_paths]
    output_name = f"{result_paths[0].stem}.png" if len(result_paths) == 1 else "combined_results.png"

    with plt.rc_context(RC_PARAMS):
        figure, _ = _create_figure(datasets)
        figure.savefig(figures_dir / output_name, dpi=SAVE_DPI)
        plt.close(figure)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    args = parser.parse_args()
    plot_results(args.run_dir.resolve())


if __name__ == "__main__":
    main()
