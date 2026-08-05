import numpy as np

from qutip import Qobj
from scipy.constants import atomic_mass, hbar
from scipy.sparse import dia_matrix
from scipy.special import eval_genlaguerre as laguerre


def coupling_func_ld(n):
    """coupling strength under the Lamb Dicke approximation, between n and n+1"""
    return np.sqrt(n + 1)


def coupling_func_full(n, eta):
    """coupling strength beyond the Lamb Dicke approximation, between n and n+1"""
    return np.exp(-1.0 / 2 * eta**2) * (1.0 / (n + 1.0)) ** 0.5 * laguerre(n, 1, eta**2)


def carrier_coupling_func_full(n, eta):
    """coupling strength beyond the Lamb Dicke approximation, between n and n"""
    return np.exp(-1.0 / 2 * eta**2) * laguerre(n, 0, eta**2)


def get_eta(w_t, angle):
    """Calculate the Lamb-Dicke parameter from the trap frequency and angle

    Parameters
    ----------
    w_t : float, Trap frequency in 1/s (angular frequency)
    angle : float, Angle of the trap in radian
    """
    wl = 729.15e-9
    k = 2 * np.pi / wl * np.cos(angle)
    x0 = np.sqrt(hbar / (2 * 40.0 * atomic_mass * w_t))
    return k * x0


def get_eta_two_ion_mixed(mass_ratio, w_t, angle):
    """Calculate the Lamb-Dicke parameter of ion 1 in the mixed species two ion crystal

    Parameters
    ----------
    mass_ratio : float, Mass ratio of the two species, m1/m2
    w_t : float, Trap frequency in 1/s (angular frequency) of a single ion 1
    angle : float, Angle of the trap in radian
    """
    mu = mass_ratio
    w_t_1 = w_t * np.sqrt(1 + mu - np.sqrt(1 - mu + mu**2))
    eta0 = get_eta(w_t_1, angle)
    mode_comp = (-1 + mu + np.sqrt(1 - mu + mu**2)) / np.sqrt((-1 + mu + np.sqrt(1 - mu + mu**2)) ** 2 + mu)
    return eta0 * mode_comp


def get_eta_ir(wl, mass, w_t, angle):
    """Calculate the Lamb-Dicke parameter for the molecular transition

    Parameters
    ----------
    wl : float, Wavelength of the molecular transition in meters
    mass : float, Mass of the molecular ion in atomic mass unit
    w_t : float, Trap frequency in 1/s (angular frequency)
    angle : float, Angle of the trap in radian
    """
    k = 2 * np.pi / wl * np.cos(angle)
    x0 = np.sqrt(hbar / (2 * mass * atomic_mass * w_t))
    return k * x0


def get_eta_ir_two_ion_mixed(wl, mass_ratio, w_t, angle):
    """
    Calculate the Lamb-Dicke parameter for the molecular transition of ion 2 in the mixed species two ion crystal

    Parameters
    ----------
    wl : float, Wavelength of the molecular transition in meters
    mass_ratio : float, Mass ratio of the two species, m1/m2
    w_t : float, Trap frequency in 1/s (angular frequency) of a single ion 1
    angle : float, Angle of the trap in radian
    """
    mu = mass_ratio
    w_t_1 = w_t * np.sqrt(1 + mu - np.sqrt(1 - mu + mu**2))
    eta0 = get_eta_ir(wl, 40.0 / mu, w_t_1, angle)
    mode_comp = np.sqrt(mu) / np.sqrt((-1 + mu + np.sqrt(1 - mu + mu**2)) ** 2 + mu)
    return eta0 * mode_comp


def create_not_ld(eta: float, N_motional_states: int = 500) -> Qobj:
    """Creation operator beyond the Lamb-Dicke approximation, between n and n+1

    Parameters
    ----------
    eta : float, Lamb-Dicke parameter
    N_motional_states : int, Number of simulated motional states
    """
    ad_data = dia_matrix(
            (np.array([[coupling_func_full(n, eta) for n in range(N_motional_states - 1)]]), np.array([-1])),
            shape=(N_motional_states, N_motional_states),
    )
    return Qobj(ad_data)

def carrier_not_ld(eta: float, N_motional_states: int = 500) -> Qobj:
    """Carrier transition operator beyond the Lamb-Dicke approximation, between n and n

    Parameters
    ----------
    eta : float, Lamb-Dicke parameter
    N_motional_states : int, Number of simulated motional states
    """
    _data = dia_matrix(
            (np.array([[carrier_coupling_func_full(n, eta) for n in range(N_motional_states)]]), np.array([0])),
            shape=(N_motional_states, N_motional_states),
    )
    return Qobj(_data)