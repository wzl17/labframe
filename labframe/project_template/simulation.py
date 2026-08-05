"""Example simulations selected by the configuration."""

from pathlib import Path

import numpy as np
from fit_models import sine_offset_model
from qutip import basis, mesolve, sigmax, sigmaz


def run_simulation(config: dict, results_dir: Path) -> None:
    """Select and run the simulation named by ``simulation.type``."""
    simulation = config["simulation"]
    simulation_type = simulation.get(
        "type",
        simulation.get("model", "rabi_flop"),
    )

    if simulation_type == "rabi_flop":
        rabi_flop(simulation, results_dir)
    else:
        raise ValueError(f"Unknown simulation type: {simulation_type!r}")


def rabi_flop(simulation: dict, results_dir: Path) -> None:
    """Simulate a coherently driven two-level system and save the result."""
    duration_s = float(simulation["duration_s"])
    points = int(simulation["points"])
    rabi_frequency_hz = float(simulation["rabi_frequency_Hz"])
    detuning_hz = float(simulation.get("detuning_Hz", 0.0))

    angular_rabi_frequency = 2.0 * np.pi * rabi_frequency_hz
    angular_detuning = 2.0 * np.pi * detuning_hz
    hamiltonian = 0.5 * (angular_rabi_frequency * sigmax() + angular_detuning * sigmaz())
    initial_state = basis(2, 0)
    excited_state_projector = basis(2, 1).proj()
    time_s = np.linspace(0.0, duration_s, points)

    result = mesolve(
        hamiltonian,
        initial_state,
        time_s,
        c_ops=[],
        e_ops=[excited_state_projector],
    )
    excited_state_probability = np.asarray(result.expect[0], dtype=float)

    results_dir.mkdir(parents=True, exist_ok=True)
    np.savez(
        results_dir / "rabi_flop.npz",
        time_s=time_s,
        excited_state_probability=excited_state_probability,
    )
    fit_rabi_flop(results_dir, angular_rabi_frequency)


def fit_rabi_flop(
    results_dir: Path,
    angular_rabi_frequency: float,
) -> None:
    """Read the saved Rabi result and save a smooth fitted curve."""
    with np.load(results_dir / "rabi_flop.npz", allow_pickle=False) as data:
        time_s = np.asarray(data["time_s"], dtype=float)
        excited_state_probability = np.asarray(data["excited_state_probability"], dtype=float)

    parameters = sine_offset_model.make_params()
    parameters["amplitude"].set(value=0.5, min=0.0, max=1.0, vary=True)
    parameters["frequency"].set(
        value=angular_rabi_frequency,
        min=0.5 * angular_rabi_frequency,
        max=1.5 * angular_rabi_frequency,
        vary=True,
    )
    parameters["shift"].set(value=-0.5 * np.pi, min=-np.pi, max=np.pi, vary=True)
    parameters["c"].set(value=0.5, min=0.0, max=1.0, vary=True)

    fit = sine_offset_model.fit(excited_state_probability, parameters, x=time_s)
    fit_points = max(1000, min(5000, 5 * time_s.size))
    fit_time_s = np.linspace(float(time_s[0]), float(time_s[-1]), fit_points)
    fitted_probability = np.asarray(fit.eval(x=fit_time_s), dtype=float)
    np.savez(
        results_dir / "rabi_flop_fit.npz",
        time_s=fit_time_s,
        excited_state_probability=fitted_probability,
    )
    print(fit.fit_report())
