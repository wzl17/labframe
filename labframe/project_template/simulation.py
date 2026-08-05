"""Editable simulation or experiment-acquisition hook."""

from pathlib import Path

import numpy as np


def run_simulation(config: dict, results_dir: Path) -> None:
    """Generate noisy Rabi data and save it in the supplied results directory."""
    settings = config["simulation"]
    duration_s = float(settings["duration_s"])
    points = int(settings["points"])
    rabi_frequency_hz = float(settings["rabi_frequency_hz"])
    detuning_hz = float(settings.get("detuning_hz", 0.0))
    contrast = float(settings.get("contrast", 1.0))
    offset = float(settings.get("offset", 0.0))
    noise_std = float(settings.get("noise_std", 0.0))
    random_seed = int(config.get("random_seed", 0))

    if duration_s <= 0.0:
        raise ValueError("simulation.duration_s must be positive")
    if points < 4:
        raise ValueError("simulation.points must be at least 4")
    if rabi_frequency_hz <= 0.0:
        raise ValueError("simulation.rabi_frequency_hz must be positive")
    if not 0.0 < contrast <= 1.0:
        raise ValueError("simulation.contrast must be in (0, 1]")
    if noise_std < 0.0:
        raise ValueError("simulation.noise_std must be non-negative")

    time_s = np.linspace(0.0, duration_s, points)
    effective_frequency_hz = np.hypot(rabi_frequency_hz, detuning_hz)
    driven_fraction = rabi_frequency_hz**2 / effective_frequency_hz**2
    probability = offset + 0.5 * contrast * driven_fraction * (
        1.0 - np.cos(2.0 * np.pi * effective_frequency_hz * time_s)
    )

    if noise_std:
        probability += np.random.default_rng(random_seed).normal(0.0, noise_std, size=points)
    probability = np.clip(probability, 0.0, 1.0)

    results_dir.mkdir(parents=True, exist_ok=True)
    np.savez(
        results_dir / "rabi_data.npz",
        time_s=time_s,
        excited_state_probability=probability,
    )
    print(f"Saved {points} Rabi samples; expected oscillation frequency {effective_frequency_hz:.6g} Hz")
