"""Editable fitting hook for saved run data."""

import json
from pathlib import Path

import numpy as np
from scipy.optimize import curve_fit


def rabi_model(time_s: np.ndarray, frequency_hz: float, contrast: float, offset: float) -> np.ndarray:
    """Return a Rabi probability model parameterized by oscillation frequency."""
    return offset + 0.5 * contrast * (1.0 - np.cos(2.0 * np.pi * frequency_hz * time_s))


def _frequency_guess(time_s: np.ndarray, probability: np.ndarray) -> float:
    spacing = float(np.mean(np.diff(time_s)))
    spectrum = np.abs(np.fft.rfft(probability - np.mean(probability)))
    frequencies = np.fft.rfftfreq(time_s.size, d=spacing)
    spectrum[0] = 0.0
    return float(frequencies[np.argmax(spectrum)])


def fit_results(config: dict, results_dir: Path) -> None:
    """Fit saved Rabi data and write numerical fit products into results_dir."""
    del config  # The saved data, rather than the launch parameters, drives the fit.
    with np.load(results_dir / "rabi_data.npz", allow_pickle=False) as data:
        time_s = np.asarray(data["time_s"], dtype=float)
        probability = np.asarray(data["excited_state_probability"], dtype=float)

    initial_frequency = _frequency_guess(time_s, probability)
    initial_offset = float(np.percentile(probability, 5))
    initial_contrast = float(np.percentile(probability, 95) - initial_offset)
    parameters, covariance = curve_fit(
        rabi_model,
        time_s,
        probability,
        p0=(initial_frequency, initial_contrast, initial_offset),
        bounds=((0.0, 0.0, -0.5), (np.inf, 2.0, 1.5)),
        maxfev=20_000,
    )
    frequency_hz, contrast, offset = (float(value) for value in parameters)
    fitted_probability = rabi_model(time_s, frequency_hz, contrast, offset)
    residual = probability - fitted_probability
    standard_errors = np.sqrt(np.diag(covariance))

    np.savez(
        results_dir / "rabi_fit.npz",
        time_s=time_s,
        fitted_excited_state_probability=fitted_probability,
    )
    fit_summary = {
        "oscillation_frequency_hz": frequency_hz,
        "oscillation_frequency_standard_error_hz": float(standard_errors[0]),
        "contrast": contrast,
        "offset": offset,
        "rmse": float(np.sqrt(np.mean(residual**2))),
    }
    (results_dir / "fit.json").write_text(json.dumps(fit_summary, indent=2) + "\n", encoding="utf-8")
    print(
        "Fit Rabi oscillation: "
        f"frequency={frequency_hz:.6g} ± {standard_errors[0]:.2g} Hz, "
        f"contrast={contrast:.4f}, rmse={fit_summary['rmse']:.4g}"
    )
