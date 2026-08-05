import json
import tempfile
import unittest
from pathlib import Path

import yaml
from fit_results import fit_results
from simulation import run_simulation


class RabiWorkflowTest(unittest.TestCase):
    def test_simulation_and_fit_recover_frequency(self) -> None:
        config = yaml.safe_load((Path(__file__).parents[1] / "configs" / "smoke.yaml").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as temporary_directory:
            results_dir = Path(temporary_directory)
            run_simulation(config, results_dir)
            fit_results(config, results_dir)

            fit = json.loads((results_dir / "fit.json").read_text(encoding="utf-8"))
            expected_hz = float(config["simulation"]["rabi_frequency_hz"])
            self.assertLess(abs(fit["oscillation_frequency_hz"] - expected_hz) / expected_hz, 0.01)
            self.assertTrue((results_dir / "rabi_data.npz").is_file())
            self.assertTrue((results_dir / "rabi_fit.npz").is_file())


if __name__ == "__main__":
    unittest.main()
