"""Reusable lmfit models for common one-dimensional fitting problems."""

from pathlib import Path

import numpy as np
from lmfit import Model
from lmfit.models import ExponentialModel, GaussianModel, LinearModel, PowerLawModel, update_param_vals


def sine(
    x: np.ndarray,
    amplitude: float,
    frequency: float,
    phase: float,
    offset: float,
) -> np.ndarray:
    """Return a sinusoid whose frequency is measured in cycles per x unit."""
    return offset + amplitude * np.sin(2.0 * np.pi * frequency * x + phase)


class SineModel(Model):
    """Sinusoid model with an FFT-based initial-parameter guess."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(sine, *args, **kwargs)
        self.set_param_hint("amplitude", min=0.0)
        self.set_param_hint("frequency", min=0.0)
        self.set_param_hint("phase", min=-np.pi, max=np.pi)

    def guess(self, data, x, **kwargs):
        """Estimate parameters from finite samples and apply keyword overrides."""
        x_values = np.asarray(x, dtype=float).reshape(-1)
        y_values = np.asarray(data, dtype=float).reshape(-1)
        if x_values.shape != y_values.shape:
            raise ValueError("x and data must have the same shape")

        finite = np.isfinite(x_values) & np.isfinite(y_values)
        if finite.sum() < 4:
            raise ValueError("At least four finite samples are required for a sine guess")

        order = np.argsort(x_values[finite])
        sorted_x = x_values[finite][order]
        sorted_y = y_values[finite][order]
        if np.any(np.diff(sorted_x) <= 0.0):
            raise ValueError("x values must be distinct for a sine guess")

        sample_x = np.linspace(sorted_x[0], sorted_x[-1], sorted_x.size)
        sample_y = np.interp(sample_x, sorted_x, sorted_y)
        centered_y = sample_y - np.mean(sample_y)
        frequencies = np.fft.rfftfreq(sample_x.size, d=sample_x[1] - sample_x[0])
        spectrum = np.abs(np.fft.rfft(centered_y))
        spectrum[0] = 0.0
        frequency = float(frequencies[np.argmax(spectrum)])
        if frequency <= 0.0:
            frequency = 1.0 / (sample_x[-1] - sample_x[0])

        angle = 2.0 * np.pi * frequency * sorted_x
        design = np.column_stack((np.sin(angle), np.cos(angle), np.ones_like(angle)))
        sine_coefficient, cosine_coefficient, offset = np.linalg.lstsq(design, sorted_y, rcond=None)[0]
        amplitude = float(np.hypot(sine_coefficient, cosine_coefficient))
        phase = float(np.arctan2(cosine_coefficient, sine_coefficient))

        parameters = self.make_params(
            amplitude=amplitude,
            frequency=frequency,
            phase=phase,
            offset=float(offset),
        )
        return update_param_vals(parameters, self.prefix, **kwargs)


sine_model = SineModel()
linear_model = LinearModel()
gaussian_model = GaussianModel()
exponential_model = ExponentialModel()
power_law_model = PowerLawModel()


def fit_results(config: dict, results_dir: Path) -> None:
    """Select and run the example fit named by ``simulation.type``."""
    simulation = config["simulation"]
    simulation_type = simulation.get(
        "type",
        simulation.get("model", "rabi_flop"),
    )

    if simulation_type == "rabi_flop":
        fit_rabi_flop(results_dir)
    else:
        raise ValueError(f"No example fit for simulation type: {simulation_type!r}")


def fit_rabi_flop(results_dir: Path) -> None:
    """Fit the saved Rabi result and save the fitted curve as another result."""
    with np.load(results_dir / "rabi_flop.npz", allow_pickle=False) as data:
        time_s = np.asarray(data["time_s"], dtype=float)
        probability = np.asarray(data["excited_state_probability"], dtype=float)

    parameters = sine_model.guess(probability, x=time_s)
    fit = sine_model.fit(probability, parameters, x=time_s)
    np.savez(
        results_dir / "rabi_flop_fit.npz",
        time_s=time_s,
        excited_state_probability=np.asarray(fit.best_fit, dtype=float),
    )
    print(fit.fit_report())


__all__ = [
    "SineModel",
    "exponential_model",
    "fit_rabi_flop",
    "fit_results",
    "gaussian_model",
    "linear_model",
    "power_law_model",
    "sine",
    "sine_model",
]
