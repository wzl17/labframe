import tempfile
import unittest
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from plot_results import _create_figure, _load_dataset, plot_results


class PlotResultsTest(unittest.TestCase):
    def test_multiple_result_files_share_one_labeled_figure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            run_dir = Path(temporary_directory)
            results_dir = run_dir / "results"
            results_dir.mkdir()
            x_values = np.linspace(0.0, 1.0, 21)
            np.savez(results_dir / "alpha.npz", time=x_values, signal=x_values)
            np.savez(results_dir / "beta.npz", time=x_values, signal=x_values**2)

            datasets = [
                _load_dataset(results_dir / "alpha.npz"),
                _load_dataset(results_dir / "beta.npz"),
            ]
            figure, axis = _create_figure(datasets)
            try:
                _, labels = axis.get_legend_handles_labels()
                self.assertEqual(labels, ["alpha.npz", "beta.npz"])
            finally:
                plt.close(figure)

            plot_results(run_dir)

            self.assertTrue((run_dir / "figures" / "combined_results.png").is_file())
            self.assertEqual(
                list((run_dir / "figures").glob("*.png")),
                [run_dir / "figures" / "combined_results.png"],
            )

    def test_single_result_keeps_stem_figure_name(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            run_dir = Path(temporary_directory)
            results_dir = run_dir / "results"
            results_dir.mkdir()
            x_values = np.linspace(0.0, 1.0, 21)
            np.savez(results_dir / "signal.npz", time=x_values, value=x_values)

            plot_results(run_dir)

            self.assertTrue((run_dir / "figures" / "signal.png").is_file())


if __name__ == "__main__":
    unittest.main()
