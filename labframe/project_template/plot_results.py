"""Editable plotting hook that reads only saved results."""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from plot_style import FIGURE_SIZE, RC_PARAMS, SAVE_DPI


def plot_results(run_dir: Path) -> None:
    """Plot measured/simulated Rabi samples together with the saved fit."""
    with np.load(run_dir / "results" / "rabi_data.npz", allow_pickle=False) as data:
        time_us = np.asarray(data["time_s"]) * 1e6
        probability = np.asarray(data["excited_state_probability"])
    with np.load(run_dir / "results" / "rabi_fit.npz", allow_pickle=False) as data:
        fit_time_us = np.asarray(data["time_s"]) * 1e6
        fitted_probability = np.asarray(data["fitted_excited_state_probability"])

    figures_dir = run_dir / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)
    with plt.rc_context(RC_PARAMS):
        figure, axis = plt.subplots(figsize=FIGURE_SIZE)
        axis.plot(time_us, probability, linestyle="none", marker="o", markersize=3.2, label="saved data")
        axis.plot(fit_time_us, fitted_probability, label="Rabi fit")
        axis.set(
            xlabel="Time (µs)",
            ylabel="Excited-state probability",
            title="Rabi oscillation",
            ylim=(-0.05, 1.05),
        )
        axis.grid(alpha=0.25)
        axis.legend()
        figure.savefig(figures_dir / "rabi_fit.png", dpi=SAVE_DPI)
        plt.close(figure)
