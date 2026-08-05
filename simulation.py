from pathlib import Path

import numpy as np
from qutip import (
    basis,
    expect,
    mesolve,
    num,
    qeye,
    sigmam,
    sigmap,
    sigmax,
    sigmaz,
    tensor,
)

from utils import create_not_ld, get_eta

eta = get_eta(w_t=2 * np.pi * 1e6, angle=0.0)  # single ion


def run_simulation(config: dict, results_dir: Path) -> None:
    """Run the configured simulation and write numerical output into results_dir."""
    simulation = config["simulation"]
    simulation_type = simulation.get(
        "type",
        simulation.get("model", "cat_generation"),
    )

    if simulation_type == "rabi_oscillation":
        rabi_oscillation(simulation, results_dir)
    elif simulation_type == "cat_generation":
        cat_generation(simulation, results_dir)
    else:
        raise ValueError(f"Unknown simulation type: {simulation_type!r}")


def rabi_oscillation(simulation: dict, results_dir: Path) -> None:
    """Simulate a coherently driven two-level system with QuTiP."""
    duration_s = float(simulation["duration_s"])
    points = int(simulation["points"])
    rabi_frequency_hz = float(simulation["rabi_frequency_Hz"])
    detuning_hz = float(simulation.get("detuning_Hz", 0.0))

    if duration_s <= 0.0:
        raise ValueError("simulation.duration_s must be positive")
    if points < 2:
        raise ValueError("simulation.points must be at least 2")
    if rabi_frequency_hz <= 0.0:
        raise ValueError("simulation.rabi_frequency_Hz must be positive")

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
        results_dir / "rabi_oscillation.npz",
        time_s=time_s,
        excited_state_probability=excited_state_probability,
    )


def cat_generation(simulation: dict, results_dir: Path) -> None:
    """Cat generation simulation.

    parameters:
        n_motion: number of motional states
        omega: Rabi frequency (scaled by eta)
        delta_c: common detuning
        delta_d: differential detuning
        bichro_amp_ratio: ratio of red tone amplitude
    """

    # Parameters
    n_motion = int(simulation["n_motion"])
    omega = eta * 2 * np.pi * float(simulation["carrier_rabi_Hz"])
    delta_c = 2 * np.pi * float(simulation["comm_detuning_Hz"])
    delta_d = 2 * np.pi * float(simulation["diff_detuning_Hz"])
    bichro_amp_ratio = float(simulation["bichro_amp_ratio"])
    omega_r = omega * bichro_amp_ratio / np.sqrt(bichro_amp_ratio**2 + (1 - bichro_amp_ratio) ** 2)
    omega_b = omega * (1 - bichro_amp_ratio) / np.sqrt(bichro_amp_ratio**2 + (1 - bichro_amp_ratio) ** 2)

    # Operators
    sz = tensor(sigmaz(), qeye(n_motion))
    sp = tensor(sigmap(), qeye(n_motion))
    sm = tensor(sigmam(), qeye(n_motion))
    p0 = tensor(basis(2, 0).proj(), qeye(n_motion))
    n = tensor(qeye(2), num(n_motion))
    ad_not_ld = tensor(qeye(2), create_not_ld(eta, n_motion))
    a_not_ld = ad_not_ld.dag()
    # they follow the same transformation(e^{-ivt}) as normal a/ad since [n, ad]=ad

    # Scan
    t_pulse_list = np.array([0, 50, 100, 150, 200, 250, 300, 350, 400]) * 1e-6
    n_sqrt_list = []

    for t_pulse in t_pulse_list:
        H_cat = -delta_c * sz - delta_d * n + omega_b / 2 * (sp * ad_not_ld + sm * a_not_ld) + omega_r / 2 * (sm * ad_not_ld + sp * a_not_ld)
        psi0 = tensor(basis(2, 0), basis(n_motion, 0))
        times = np.linspace(0, t_pulse, 2)
        c_ops = []
        result = mesolve(H_cat, psi0, times, c_ops=c_ops, options={"nsteps": 1e5})
        print(f"Pulse duration: {float(t_pulse) * 1e6:.1f} µs, P(|0>): {expect(p0, result.states[-1]):.3f}")
        n_expect = expect(n, result.states[-1])
        n2_expect = expect(n * n, result.states[-1])
        print(f"n: {n_expect:.3f}")
        print(f"delta_n: {np.sqrt(n2_expect - n_expect**2):.3f}")

        n_sqrt_list.append(np.sqrt(n_expect))
    n_sqrt_list = np.array(n_sqrt_list)

    results_dir.mkdir(parents=True, exist_ok=True)
    np.savez(results_dir / "scan_results.npz", t_pulse_list=t_pulse_list, n_sqrt_list=n_sqrt_list)
