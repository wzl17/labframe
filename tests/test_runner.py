import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from lmfit import Model

from labframe.project import initialize_project
from labframe.runner import run_project


def _git(project_root: Path, *arguments: str) -> None:
    subprocess.run(["git", *arguments], cwd=project_root, check=True, capture_output=True)


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class RunnerTest(unittest.TestCase):
    def _project(self, parent: Path) -> Path:
        project_root = parent / "rabi-test"
        initialize_project(project_root, sync=False, initialize_git=False)
        _git(project_root, "init")
        _git(project_root, "add", "-A")
        subprocess.run(
            [
                "git",
                "-c",
                "user.name=Labframe Tests",
                "-c",
                "user.email=labframe-tests@example.invalid",
                "commit",
                "-m",
                "Initial test project",
            ],
            cwd=project_root,
            check=True,
            capture_output=True,
        )
        return project_root

    def test_no_commit_run_executes_rabi_plot_and_summary_and_supports_lmfit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project_root = self._project(Path(temporary_directory))
            starting_commit = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=project_root,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()

            run_dir = run_project(
                project_root,
                Path("configs/smoke.yaml"),
                commit=False,
                message=None,
                yes=False,
            )

            meta = json.loads((run_dir / "meta.json").read_text(encoding="utf-8"))
            self.assertEqual(meta["status"], "completed")
            self.assertEqual(meta["git_commit"], starting_commit)
            simulation_path = run_dir / "results" / "rabi_flop.npz"
            fit_path = run_dir / "results" / "rabi_flop_fit.npz"
            self.assertTrue(simulation_path.is_file())
            self.assertTrue(fit_path.is_file())
            self.assertTrue((run_dir / "figures" / "combined_results.png").is_file())
            self.assertTrue((run_dir / "summary.md").is_file())
            self.assertTrue((run_dir / "summary.html").is_file())
            self.assertTrue((project_root / "index.html").is_file())

            with (
                np.load(simulation_path, allow_pickle=False) as simulation,
                np.load(fit_path, allow_pickle=False) as fitted,
            ):
                self.assertEqual(simulation.files, ["time_s", "excited_state_probability"])
                self.assertEqual(fitted.files, simulation.files)
                self.assertGreater(fitted["time_s"].size, simulation["time_s"].size)
                self.assertEqual(float(fitted["time_s"][0]), float(simulation["time_s"][0]))
                self.assertEqual(float(fitted["time_s"][-1]), float(simulation["time_s"][-1]))
                probability = simulation["excited_state_probability"]
                fitted_probability = fitted["excited_state_probability"]
            self.assertGreater(fitted_probability.size, probability.size)

            fit_models = _load_module("generated_fit_models", project_root / "fit_models.py")
            for name in (
                "sine_offset_model",
                "linear_model",
                "gaussian_model",
                "exponential_model",
                "power_law_model",
            ):
                self.assertTrue(hasattr(fit_models, name))
                self.assertIsInstance(getattr(fit_models, name), Model)
            self.assertNotIn(".guess(", (project_root / "simulation.py").read_text(encoding="utf-8"))
            summary = (run_dir / "summary.md").read_text(encoding="utf-8")
            self.assertIn("results/rabi_flop.npz", summary)
            self.assertIn("results/rabi_flop_fit.npz", summary)
            summary_html = (run_dir / "summary.html").read_text(encoding="utf-8")
            self.assertIn('href="../../index.html"', summary_html)
            index_html = (project_root / "index.html").read_text(encoding="utf-8")
            self.assertIn('data-run-type="rabi_flop"', index_html)
            self.assertIn(f'href="runs/{run_dir.name}/summary.html"', index_html)
            self.assertIn('<span class="run-count">1 run</span>', index_html)
            self.assertEqual(
                subprocess.run(
                    ["git", "rev-parse", "HEAD"],
                    cwd=project_root,
                    check=True,
                    capture_output=True,
                    text=True,
                ).stdout.strip(),
                starting_commit,
            )
            self.assertEqual(
                subprocess.run(
                    ["git", "status", "--porcelain"],
                    cwd=project_root,
                    check=True,
                    capture_output=True,
                    text=True,
                ).stdout,
                "",
            )

    def test_index_groups_existing_summaries_by_run_type_newest_first(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project_root = Path(temporary_directory) / "grouped-runs"
            initialize_project(project_root, sync=False, initialize_git=False)
            summary_module = _load_module("generated_grouped_summary", project_root / "build_summary.py")
            self.assertEqual(summary_module._run_type({"simulation": {"type": "rabi_flop"}}), "rabi_flop")
            self.assertEqual(summary_module._run_type({"experiment": {"type": "ramsey"}}), "ramsey")
            self.assertEqual(summary_module._run_type({"acquisition": {"type": "scan"}}), "unknown")

            runs = (
                ("20260806-100000_aaaaaaaa", "rabi_flop"),
                ("20260806-110000_bbbbbbbb", "ramsey"),
                ("20260806-120000_cccccccc", "rabi_flop"),
            )
            for position, (name, run_type) in enumerate(runs):
                run_dir = project_root / "runs" / name
                run_dir.mkdir()
                (run_dir / "config.yaml").write_text(
                    f"simulation:\n  type: {run_type}\n",
                    encoding="utf-8",
                )
                (run_dir / "meta.json").write_text(
                    json.dumps(
                        {
                            "status": "completed",
                            "started_at": f"2026-08-06T1{position}:00:00+02:00",
                            "runtime_seconds": position + 0.5,
                        }
                    ),
                    encoding="utf-8",
                )
                (run_dir / "summary.html").write_text("summary", encoding="utf-8")

            incomplete_run = project_root / "runs" / "20260806-130000_dddddddd"
            incomplete_run.mkdir()
            (incomplete_run / "config.yaml").write_text(
                "simulation:\n  type: ignored\n",
                encoding="utf-8",
            )

            index_path = summary_module.rebuild_index(project_root)
            index_html = index_path.read_text(encoding="utf-8")

            self.assertEqual(index_html.count('class="run-group"'), 2)
            self.assertIn('data-run-type="rabi_flop"', index_html)
            self.assertIn('data-run-type="ramsey"', index_html)
            self.assertNotIn("ignored", index_html)
            self.assertIn('<span class="run-count">2 runs</span>', index_html)
            newest_rabi = index_html.index("20260806-120000_cccccccc")
            older_rabi = index_html.index("20260806-100000_aaaaaaaa")
            self.assertLess(newest_rabi, older_rabi)

    def test_plot_accepts_results_with_different_x_coordinates(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project_root = Path(temporary_directory)
            initialize_project(project_root, sync=False, initialize_git=False)
            run_dir = project_root / "runs" / "test"
            results_dir = run_dir / "results"
            results_dir.mkdir(parents=True)
            x_values = np.linspace(0.0, 1.0, 11)
            np.savez(
                results_dir / "first.npz",
                time_s=x_values,
                excited_state_probability=x_values,
            )
            np.savez(
                results_dir / "second.npz",
                time_s=x_values + 0.1,
                excited_state_probability=x_values,
            )

            plot_module = _load_module("generated_plot_results", project_root / "plot_results.py")
            plot_module.plot_results(run_dir)
            self.assertTrue((run_dir / "figures" / "combined_results.png").is_file())

    def test_plot_rejects_results_with_different_axis_names(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project_root = Path(temporary_directory)
            initialize_project(project_root, sync=False, initialize_git=False)
            run_dir = project_root / "runs" / "test"
            results_dir = run_dir / "results"
            results_dir.mkdir(parents=True)
            x_values = np.linspace(0.0, 1.0, 11)
            np.savez(results_dir / "first.npz", time_s=x_values, probability=x_values)
            np.savez(results_dir / "second.npz", delay_s=x_values, probability=x_values)

            plot_module = _load_module("generated_plot_axis_check", project_root / "plot_results.py")
            with self.assertRaisesRegex(ValueError, "array names"):
                plot_module.plot_results(run_dir)

    def test_no_commit_run_rejects_dirty_project(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project_root = self._project(Path(temporary_directory))
            (project_root / "simulation.py").write_text(
                (project_root / "simulation.py").read_text(encoding="utf-8") + "\n# dirty\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(RuntimeError, "working tree is dirty"):
                run_project(
                    project_root,
                    Path("configs/smoke.yaml"),
                    commit=False,
                    message=None,
                    yes=False,
                )


if __name__ == "__main__":
    unittest.main()
