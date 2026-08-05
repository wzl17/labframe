"""Example simulations selected by the configuration."""

from pathlib import Path

import numpy as np
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

    results_dir.mkdir(parents=True, exist_ok=True)
    np.savez(
        results_dir / "rabi_flop.npz",
        time_s=time_s,
        excited_state_probability=np.asarray(result.expect[0], dtype=float),
    )
