import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from labframe.project import initialize_project
from labframe.rebuild import _build_parser, rebuild_project, update_index


class RebuildTest(unittest.TestCase):
    def _run(self, project_root: Path, runs_dir: Path, name: str, run_type: str, notes: str) -> Path:
        run_dir = runs_dir / name
        (run_dir / "results").mkdir(parents=True)
        (run_dir / "figures").mkdir()
        (run_dir / "config.yaml").write_text(f"workflow:\n  type: {run_type}\n", encoding="utf-8")
        (run_dir / "meta.json").write_text(
            json.dumps(
                {
                    "status": "completed",
                    "started_at": "2026-08-06T10:00:00+02:00",
                    "runtime_seconds": 1.5,
                    "project_root": str(project_root),
                    "runs_dir": str(runs_dir),
                }
            ),
            encoding="utf-8",
        )
        (run_dir / "output.log").write_text("saved output\n", encoding="utf-8")
        (run_dir / "notes.md").write_text(notes, encoding="utf-8")
        return run_dir

    def test_parser_accepts_optional_project(self) -> None:
        self.assertIsNone(_build_parser().parse_args([]).project)
        self.assertEqual(_build_parser().parse_args(["--project", "example"]).project, Path("example"))

    def test_rebuild_refreshes_notes_without_loading_computation_hooks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project_root = Path(temporary_directory) / "rebuild-project"
            initialize_project(project_root, sync=False, initialize_git=False)
            runs_dir = project_root / "runs"
            older = self._run(project_root, runs_dir, "20260806-100000_aaaaaaaa", "rabi", "Old note")
            newer = self._run(project_root, runs_dir, "20260806-120000_bbbbbbbb", "rabi", "New note")
            (project_root / "workflow.py").write_text("raise AssertionError('workflow loaded')\n", encoding="utf-8")
            (project_root / "plot_results.py").write_text("raise AssertionError('plot loaded')\n", encoding="utf-8")

            index_path, refreshed, skipped = rebuild_project(project_root)
            self.assertEqual((refreshed, skipped), (2, 0))
            self.assertEqual(index_path, (runs_dir / "index.html").resolve())
            (older / "notes.md").write_text("Edited **after** the run.\n\n- inspect", encoding="utf-8")
            rebuild_project(project_root)

            self.assertIn("Edited **after** the run.", (older / "summary.md").read_text(encoding="utf-8"))
            self.assertIn("<strong>after</strong>", (older / "summary.html").read_text(encoding="utf-8"))
            index_html = index_path.read_text(encoding="utf-8")
            self.assertLess(index_html.index(newer.name), index_html.index(older.name))
            self.assertIn('"workflow_type":"rabi"', index_html)

    def test_external_runs_links_zero_runs_and_malformed_entries(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            parent = Path(temporary_directory)
            project_root = parent / "external-project"
            runs_dir = parent / "external run artifacts"
            initialize_project(project_root, sync=False, initialize_git=False, runs_dir=runs_dir)

            index_path, refreshed, skipped = rebuild_project(project_root)
            self.assertEqual((refreshed, skipped), (0, 0))
            self.assertTrue(index_path.is_file())
            self.assertIn("No completed runs", index_path.read_text(encoding="utf-8"))

            valid = self._run(project_root, runs_dir, "20260806-100000_valid run", "scan", "External")
            malformed = runs_dir / "20260806-110000_malformed"
            malformed.mkdir()
            (malformed / "summary.html").write_text("stale", encoding="utf-8")
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                index_path, refreshed, skipped = rebuild_project(project_root)

            self.assertEqual((refreshed, skipped), (1, 1))
            self.assertIn("warning: skipping 20260806-110000_malformed", stderr.getvalue())
            summary_html = (valid / "summary.html").read_text(encoding="utf-8")
            expected_index_href = Path(os.path.relpath(index_path, valid.resolve())).as_posix().replace(" ", "%20")
            self.assertIn(f'href="{expected_index_href}"', summary_html)
            index_html = index_path.read_text(encoding="utf-8")
            self.assertIn("20260806-100000_valid run", index_html)
            self.assertNotIn("20260806-110000_malformed", index_html)
            self.assertIn("valid%20run/summary.html", index_html)

    def test_console_entrypoint_searches_upward_and_reports_counts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project_root = Path(temporary_directory) / "entrypoint-project"
            initialize_project(project_root, sync=False, initialize_git=False)
            nested = project_root / "nested"
            nested.mkdir()
            stdout = io.StringIO()
            with (
                patch("sys.argv", ["labframe-update-index"]),
                patch("pathlib.Path.cwd", return_value=nested),
                contextlib.redirect_stdout(stdout),
            ):
                update_index()

            self.assertIn(str(project_root / "runs" / "index.html"), stdout.getvalue())
            self.assertIn("refreshed 0, skipped 0", stdout.getvalue())

    def test_packaging_registers_console_entrypoint(self) -> None:
        pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
        self.assertIn(
            'labframe-update-index = "labframe.rebuild:update_index"',
            pyproject.read_text(encoding="utf-8"),
        )


if __name__ == "__main__":
    unittest.main()
