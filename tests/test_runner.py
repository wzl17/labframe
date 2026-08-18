import contextlib
import importlib.util
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from lmfit import Model

from labframe.project import initialize_project
from labframe.runner import _collect_notes, _run_summary, run_project


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
    def _project(self, parent: Path, *, runs_dir: Path | None = None) -> Path:
        project_root = parent / "rabi-test"
        initialize_project(project_root, sync=False, initialize_git=False, runs_dir=runs_dir)
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
                notes=(
                    "A **useful** result.\n\n- repeat scan\n- [open docs](https://example.com)"
                    "\n\n<script>alert('unsafe')</script>"
                ),
            )

            meta = json.loads((run_dir / "meta.json").read_text(encoding="utf-8"))
            self.assertEqual(meta["status"], "completed")
            self.assertEqual(meta["git_commit"], starting_commit)
            data_path = run_dir / "results" / "rabi_flop.npz"
            fit_path = run_dir / "results" / "rabi_flop_fit.npz"
            self.assertTrue(data_path.is_file())
            self.assertTrue(fit_path.is_file())
            self.assertTrue((run_dir / "figures" / "combined_results.png").is_file())
            self.assertTrue((run_dir / "summary.md").is_file())
            self.assertTrue((run_dir / "summary.html").is_file())
            self.assertEqual(
                (run_dir / "notes.md").read_text(encoding="utf-8"),
                "A **useful** result.\n\n- repeat scan\n- [open docs](https://example.com)"
                "\n\n<script>alert('unsafe')</script>",
            )
            self.assertTrue((project_root / "runs" / "index.html").is_file())
            self.assertTrue((project_root / "runs" / "catalog.sqlite3").is_file())
            self.assertFalse((project_root / "index.html").exists())

            with (
                np.load(data_path, allow_pickle=False) as data,
                np.load(fit_path, allow_pickle=False) as fitted,
            ):
                self.assertEqual(data.files, ["time_s", "excited_state_probability"])
                self.assertEqual(fitted.files, data.files)
                self.assertGreater(fitted["time_s"].size, data["time_s"].size)
                self.assertEqual(float(fitted["time_s"][0]), float(data["time_s"][0]))
                self.assertEqual(float(fitted["time_s"][-1]), float(data["time_s"][-1]))
                time_s = data["time_s"]
                probability = data["excited_state_probability"]
                fitted_time_s = fitted["time_s"]
                fitted_probability = fitted["excited_state_probability"]
            self.assertGreater(fitted_probability.size, probability.size)
            interpolated_fit = np.interp(time_s, fitted_time_s, fitted_probability)
            residual_sum_squares = np.sum((probability - interpolated_fit) ** 2)
            total_sum_squares = np.sum((probability - probability.mean()) ** 2)
            self.assertGreater(1.0 - residual_sum_squares / total_sum_squares, 0.999)

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
            self.assertNotIn(".guess(", (project_root / "workflow.py").read_text(encoding="utf-8"))
            summary = (run_dir / "summary.md").read_text(encoding="utf-8")
            self.assertIn("results/rabi_flop.npz", summary)
            self.assertIn("results/rabi_flop_fit.npz", summary)
            self.assertIn("# Notes\n\nA **useful** result.\n\n- repeat scan", summary)
            summary_html = (run_dir / "summary.html").read_text(encoding="utf-8")
            self.assertIn('href="../index.html"', summary_html)
            self.assertIn("<strong>useful</strong>", summary_html)
            self.assertIn("<li>repeat scan</li>", summary_html)
            self.assertIn('<a href="https://example.com">open docs</a>', summary_html)
            self.assertNotIn("<script>", summary_html)
            self.assertIn("&lt;script&gt;alert", summary_html)
            index_html = (project_root / "runs" / "index.html").read_text(encoding="utf-8")
            self.assertIn('id="workflow-type"', index_html)
            self.assertIn(f'"run_id":"{run_dir.name}"', index_html)
            self.assertIn('"workflow_type":"rabi_flop"', index_html)
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

    def test_run_supports_spawned_process_pool_tasks_defined_in_workflow(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project_root = self._project(Path(temporary_directory))
            (project_root / "workflow.py").write_text(
                '''"""Workflow exercising spawn-based Python task parallelism."""

from concurrent.futures import ProcessPoolExecutor
import multiprocessing
from pathlib import Path

import numpy as np


def square(value: int) -> int:
    """Return one independently computed result."""
    return value * value


def run_workflow(config: dict, results_dir: Path) -> None:
    """Run importable task functions in spawned Python workers."""
    values = list(range(8))
    context = multiprocessing.get_context("spawn")
    with ProcessPoolExecutor(max_workers=2, mp_context=context) as executor:
        squared = list(executor.map(square, values))

    results_dir.mkdir(parents=True, exist_ok=True)
    np.savez(
        results_dir / "parallel_tasks.npz",
        value=np.asarray(values, dtype=float),
        squared=np.asarray(squared, dtype=float),
    )
    print(f"parallel results: {squared}")
''',
                encoding="utf-8",
            )

            run_dir = run_project(
                project_root,
                Path("configs/smoke.yaml"),
                commit=True,
                message="Test parallel workflow",
                yes=True,
                notes="",
            )

            with np.load(run_dir / "results" / "parallel_tasks.npz", allow_pickle=False) as results:
                np.testing.assert_array_equal(results["value"], np.arange(8, dtype=float))
                np.testing.assert_array_equal(results["squared"], np.arange(8, dtype=float) ** 2)
            output = (run_dir / "output.log").read_text(encoding="utf-8")
            self.assertIn("parallel results: [0, 1, 4, 9, 16, 25, 36, 49]", output)
            self.assertTrue((run_dir / "figures" / "combined_results.png").is_file())
            meta = json.loads((run_dir / "meta.json").read_text())
            self.assertEqual(meta["status"], "completed")
            with contextlib.closing(sqlite3.connect(project_root / "runs" / "catalog.sqlite3")) as connection:
                catalog_commit = connection.execute(
                    "SELECT git_commit FROM runs WHERE run_id = ?", (run_dir.name,)
                ).fetchone()[0]
            self.assertEqual(catalog_commit, meta["git_commit"])

    def test_run_uses_external_directory_configured_during_initialization(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            parent = Path(temporary_directory)
            external_runs_dir = parent / "run-artifacts"
            project_root = self._project(parent, runs_dir=external_runs_dir)

            run_dir = run_project(
                project_root,
                Path("configs/smoke.yaml"),
                commit=False,
                message=None,
                yes=False,
            )

            self.assertEqual(run_dir.parent, external_runs_dir.resolve())
            self.assertFalse((project_root / "runs").exists())
            meta = json.loads((run_dir / "meta.json").read_text(encoding="utf-8"))
            self.assertEqual(meta["project_root"], str(project_root.resolve()))
            self.assertEqual(meta["runs_dir"], str(external_runs_dir.resolve()))

            summary_html = (run_dir / "summary.html").read_text(encoding="utf-8")
            index_href = Path(os.path.relpath((external_runs_dir / "index.html").resolve(), run_dir)).as_posix()
            self.assertIn(f'href="{index_href}"', summary_html)

            index_html = (external_runs_dir / "index.html").read_text(encoding="utf-8")
            self.assertIn(f'"summary_href":"{run_dir.name}/summary.html"', index_html)

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
            (project_root / "workflow.py").write_text(
                (project_root / "workflow.py").read_text(encoding="utf-8") + "\n# dirty\n",
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

    def test_interactive_notes_preserve_multiline_markdown(self) -> None:
        class InteractiveInput:
            @staticmethod
            def isatty() -> bool:
                return True

        with (
            patch("labframe.runner.sys.stdin", InteractiveInput()),
            patch("builtins.input", side_effect=["First paragraph", "", "```python", "x = 1", "```", "."]),
        ):
            notes = _collect_notes(None, prompt=True)

        self.assertEqual(notes, "First paragraph\n\n```python\nx = 1\n```")

    def test_noninteractive_and_suppressed_notes_never_read_input(self) -> None:
        with patch("builtins.input") as read:
            self.assertEqual(_collect_notes(None, prompt=True), "")
            self.assertEqual(_collect_notes(None, prompt=False), "")
        read.assert_not_called()

    def test_eof_and_interruption_skip_optional_notes(self) -> None:
        class InteractiveInput:
            @staticmethod
            def isatty() -> bool:
                return True

        for error in (EOFError(), KeyboardInterrupt()):
            with self.subTest(error=type(error).__name__):
                with (
                    patch("labframe.runner.sys.stdin", InteractiveInput()),
                    patch("builtins.input", side_effect=error),
                ):
                    self.assertEqual(_collect_notes(None, prompt=True), "")

    def test_interrupted_notes_prompt_does_not_fail_a_successful_pipeline(self) -> None:
        class InteractiveInput:
            @staticmethod
            def isatty() -> bool:
                return True

        with tempfile.TemporaryDirectory() as temporary_directory:
            project_root = self._project(Path(temporary_directory))
            with (
                patch("labframe.runner.sys.stdin", InteractiveInput()),
                patch("builtins.input", side_effect=KeyboardInterrupt()),
                patch("labframe.runner._run_data_pipeline"),
                patch("labframe.runner._run_summary"),
            ):
                run_dir = run_project(
                    project_root,
                    Path("configs/smoke.yaml"),
                    commit=False,
                    message=None,
                    yes=False,
                )

            meta = json.loads((run_dir / "meta.json").read_text(encoding="utf-8"))
            self.assertEqual(meta["status"], "completed")
            self.assertEqual((run_dir / "notes.md").read_text(encoding="utf-8"), "")

    def test_commit_mode_collects_notes_once_and_preserves_them_across_summaries(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project_root = self._project(Path(temporary_directory))
            workflow_path = project_root / "workflow.py"
            workflow_path.write_text(
                workflow_path.read_text(encoding="utf-8") + "\n# launch change\n", encoding="utf-8"
            )

            with (
                patch("labframe.runner._collect_notes", return_value="Commit-mode **note**") as collect,
                patch("labframe.runner._run_summary", wraps=_run_summary) as summarize,
            ):
                run_dir = run_project(
                    project_root,
                    Path("configs/smoke.yaml"),
                    commit=True,
                    message="Test notes",
                    yes=True,
                )

            collect.assert_called_once_with(None, prompt=True)
            self.assertEqual(summarize.call_count, 2)
            self.assertEqual((run_dir / "notes.md").read_text(encoding="utf-8"), "Commit-mode **note**")
            self.assertIn("Commit-mode **note**", (run_dir / "summary.md").read_text(encoding="utf-8"))

    def test_legacy_summary_notes_are_migrated_when_notes_file_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project_root = Path(temporary_directory) / "legacy-notes"
            initialize_project(project_root, sync=False, initialize_git=False)
            run_dir = project_root / "runs" / "20260806-100000_aaaaaaaa"
            (run_dir / "results").mkdir(parents=True)
            (run_dir / "figures").mkdir()
            (run_dir / "config.yaml").write_text("workflow:\n  type: legacy\n", encoding="utf-8")
            (run_dir / "meta.json").write_text(
                json.dumps({"status": "completed", "runtime_seconds": 1.0, "project_root": str(project_root)}),
                encoding="utf-8",
            )
            (run_dir / "output.log").write_text("saved output\n", encoding="utf-8")
            legacy_notes = "Legacy paragraph.\n\n- preserve this\n"
            (run_dir / "summary.md").write_text(f"# Old summary\n\n# Notes\n\n{legacy_notes}", encoding="utf-8")

            summary_module = _load_module("generated_legacy_summary", project_root / "build_summary.py")
            summary_module.build_summary(run_dir)

            self.assertEqual((run_dir / "notes.md").read_text(encoding="utf-8"), legacy_notes)
            self.assertIn(legacy_notes, (run_dir / "summary.md").read_text(encoding="utf-8"))
            self.assertIn("<li>preserve this</li>", (run_dir / "summary.html").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
