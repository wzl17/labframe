"""Plot every compatible saved result in one figure."""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np

RC_PARAMS = {
    "axes.labelsize": 11,
    "axes.titlesize": 12,
    "font.size": 10,
    "legend.fontsize": 9,
    "lines.linewidth": 1.8,
    "savefig.bbox": "tight",
    "xtick.labelsize": 9,
    "ytick.labelsize": 9,
}


def _load_result(path: Path) -> tuple[str, str, np.ndarray, np.ndarray]:
    with np.load(path, allow_pickle=False) as data:
        if len(data.files) != 2:
            raise ValueError(f"{path.name} must contain exactly one x array and one y array")
        x_name, y_name = data.files
        x_values = np.asarray(data[x_name], dtype=float)
        y_values = np.asarray(data[y_name], dtype=float)

    if x_values.ndim != 1 or y_values.ndim != 1:
        raise ValueError(f"The x/y arrays in {path.name} must be one-dimensional")
    if x_values.shape != y_values.shape:
        raise ValueError(f"The x/y arrays in {path.name} must have the same shape")
    return x_name, y_name, x_values, y_values


def plot_results(run_dir: Path) -> None:
    """Plot all NPZ results after verifying that their axes match."""
    result_paths = sorted((run_dir / "results").glob("*.npz"))
    if not result_paths:
        raise ValueError("No NPZ results found")

    loaded = [(path, *_load_result(path)) for path in result_paths]
    _, reference_x_name, reference_y_name, reference_x, _ = loaded[0]
    for path, x_name, y_name, x_values, _ in loaded[1:]:
        if (x_name, y_name) != (reference_x_name, reference_y_name):
            raise ValueError(f"The x/y array names in {path.name} do not match the other results")
        if x_values.shape != reference_x.shape or not np.array_equal(x_values, reference_x):
            raise ValueError(f"The x coordinates in {path.name} do not match the other results")

    x_scale = 1e6 if reference_x_name == "time_s" else 1.0
    x_label = "Time (µs)" if reference_x_name == "time_s" else reference_x_name
    y_label = "Excited-state probability" if reference_y_name == "excited_state_probability" else reference_y_name

    figures_dir = run_dir / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)
    with plt.rc_context(RC_PARAMS):
        figure, axis = plt.subplots(figsize=(7.0, 4.2))
        for path, _, _, x_values, y_values in loaded:
            axis.plot(x_values * x_scale, y_values, label=path.stem)
        axis.set(
            xlabel=x_label,
            ylabel=y_label,
            title="Rabi flop",
        )
        if reference_y_name == "excited_state_probability":
            axis.set_ylim(-0.05, 1.05)
        axis.grid(alpha=0.25)
        axis.legend()
        figure.savefig(figures_dir / "combined_results.png", dpi=180)
        plt.close(figure)
