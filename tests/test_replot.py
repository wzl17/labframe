import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from labframe.cli import _build_parser, main
from labframe.project import initialize_project
from labframe.replot import regenerate_plots


class ReplotTest(unittest.TestCase):
    def _completed_run(self, project_root: Path, runs_dir: Path, name: str = "test-run") -> Path:
        run_dir = runs_dir / name
        (run_dir / "results").mkdir(parents=True)
        (run_dir / "figures").mkdir()
        (run_dir / "results" / "saved.txt").write_text("saved result\n", encoding="utf-8")
        (run_dir / "figures" / "stale.png").write_text("stale\n", encoding="utf-8")
        (run_dir / "config.yaml").write_text("workflow:\n  type: test\n", encoding="utf-8")
        (run_dir / "meta.json").write_text(
            json.dumps(
                {
                    "status": "completed",
                    "started_at": "2026-08-12T10:00:00+02:00",
                    "runtime_seconds": 1.0,
                    "project_root": str(project_root),
                    "runs_dir": str(runs_dir),
                }
            ),
            encoding="utf-8",
        )
        (run_dir / "output.log").write_text("original workflow output\n", encoding="utf-8")
        (run_dir / "notes.md").write_text("keep this note\n", encoding="utf-8")
        return run_dir

    def _write_plot_hook(self, project_root: Path, body: str) -> None:
        (project_root / "plot_results.py").write_text(
            f"from pathlib import Path\n\ndef plot_results(run_dir: Path) -> None:\n{body}",
            encoding="utf-8",
        )

    def test_parser_accepts_run_and_optional_project(self) -> None:
        args = _build_parser().parse_args(["plot", "runs/example", "--project", "project"])

        self.assertEqual(args.run, Path("runs/example"))
        self.assertEqual(args.project, Path("project"))

    def test_regenerates_from_saved_results_without_loading_workflow(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project_root = Path(temporary_directory) / "plot-project"
            initialize_project(project_root, sync=False, initialize_git=False)
            runs_dir = project_root / "runs"
            run_dir = self._completed_run(project_root, runs_dir)
            (project_root / "workflow.py").write_text("raise AssertionError('workflow loaded')\n", encoding="utf-8")
            self._write_plot_hook(
                project_root,
                "    saved = (run_dir / 'results' / 'saved.txt').read_text(encoding='utf-8')\n"
                "    (run_dir / 'figures' / 'combined_results.png').write_text(saved, encoding='utf-8')\n",
            )

            regenerated_run, index_path = regenerate_plots(project_root, Path("runs/test-run"))

            self.assertEqual(regenerated_run, run_dir.resolve())
            self.assertEqual(index_path, (runs_dir / "index.html").resolve())
            self.assertEqual((run_dir / "results" / "saved.txt").read_text(encoding="utf-8"), "saved result\n")
            self.assertFalse((run_dir / "figures" / "stale.png").exists())
            self.assertEqual(
                (run_dir / "figures" / "combined_results.png").read_text(encoding="utf-8"),
                "saved result\n",
            )
            self.assertIn("keep this note", (run_dir / "summary.md").read_text(encoding="utf-8"))
            self.assertTrue(index_path.is_file())

    def test_plot_failure_preserves_existing_figures(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project_root = Path(temporary_directory) / "plot-project"
            initialize_project(project_root, sync=False, initialize_git=False)
            run_dir = self._completed_run(project_root, project_root / "runs")
            self._write_plot_hook(
                project_root,
                "    (run_dir / 'figures' / 'partial.png').write_text('partial', encoding='utf-8')\n"
                "    raise RuntimeError('plot failed')\n",
            )

            with self.assertRaisesRegex(RuntimeError, "plot failed"):
                regenerate_plots(project_root, Path("test-run"))

            self.assertEqual((run_dir / "figures" / "stale.png").read_text(encoding="utf-8"), "stale\n")
            self.assertFalse((run_dir / "figures" / "partial.png").exists())

    def test_rejects_noncompleted_or_outside_run_directories(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project_root = Path(temporary_directory) / "plot-project"
            initialize_project(project_root, sync=False, initialize_git=False)
            run_dir = self._completed_run(project_root, project_root / "runs")
            meta_path = run_dir / "meta.json"
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            meta["status"] = "failed"
            meta_path.write_text(json.dumps(meta), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "status is 'failed'"):
                regenerate_plots(project_root, Path("test-run"))
            with self.assertRaisesRegex(ValueError, "direct child"):
                regenerate_plots(project_root, project_root / "not-a-run")

    def test_external_runs_and_cli_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            parent = Path(temporary_directory)
            project_root = parent / "plot-project"
            runs_dir = parent / "external-runs"
            initialize_project(project_root, sync=False, initialize_git=False, runs_dir=runs_dir)
            run_dir = self._completed_run(project_root, runs_dir, "external-run")
            self._write_plot_hook(
                project_root,
                "    (run_dir / 'figures' / 'combined_results.png').write_text('new', encoding='utf-8')\n",
            )
            stdout = io.StringIO()

            with (
                patch(
                    "sys.argv",
                    [
                        "labframe",
                        "plot",
                        "external-run",
                        "--project",
                        str(project_root),
                    ],
                ),
                contextlib.redirect_stdout(stdout),
            ):
                main()

            self.assertIn(f"Regenerated plots in {run_dir.resolve()}", stdout.getvalue())
            self.assertIn(f"Rebuilt {(runs_dir / 'index.html').resolve()}", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
