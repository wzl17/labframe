import contextlib
import io
import json
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

import yaml

from labframe.catalog import CATALOG_FILENAME, SCHEMA_VERSION, synchronize_catalog


class CatalogTest(unittest.TestCase):
    def _run(
        self,
        runs_dir: Path,
        run_id: str,
        workflow: dict,
        *,
        git_commit: str = "abc123",
        started_at: str = "2026-08-18T10:00:00+02:00",
        runtime_seconds: float = 1.25,
        status: str = "completed",
    ) -> Path:
        run_dir = runs_dir / run_id
        run_dir.mkdir(parents=True)
        (run_dir / "config.yaml").write_text(
            yaml.safe_dump({"workflow": workflow}, sort_keys=False),
            encoding="utf-8",
        )
        (run_dir / "meta.json").write_text(
            json.dumps(
                {
                    "git_commit": git_commit,
                    "started_at": started_at,
                    "runtime_seconds": runtime_seconds,
                    "status": status,
                }
            ),
            encoding="utf-8",
        )
        (run_dir / "summary.html").write_text("summary", encoding="utf-8")
        return run_dir

    @staticmethod
    def _rows(runs_dir: Path) -> list[tuple]:
        with contextlib.closing(sqlite3.connect(runs_dir / CATALOG_FILENAME)) as connection:
            return connection.execute(
                "SELECT run_id, git_commit, workflow_type, started_at, runtime_seconds, parameters_json "
                "FROM runs ORDER BY run_id"
            ).fetchall()

    @staticmethod
    def _embedded_records(index_path: Path) -> list[dict]:
        document = index_path.read_text(encoding="utf-8")
        start = document.index('<script type="application/json" id="run-data">')
        start = document.index(">", start) + 1
        end = document.index("</script>", start)
        return json.loads(document[start:end])

    def test_initial_catalog_stores_typed_scalar_parameters_and_escapes_embedded_data(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project_root = Path(temporary_directory) / "catalog-project"
            runs_dir = Path(temporary_directory) / "external runs"
            project_root.mkdir()
            self._run(
                runs_dir,
                "20260818-100000_run with space",
                {
                    "type": "rabi</script><b>",
                    "points": 101,
                    "frequency": 5.5,
                    "enabled": True,
                    "label": "alpha</script><i>",
                    "optional": None,
                    "nested": {"not": "a scalar"},
                    "sequence": [1, 2],
                },
                git_commit="deadbeef",
            )

            result = synchronize_catalog(project_root, runs_dir)

            self.assertEqual((result.added, result.removed, result.skipped), (1, 0, 0))
            self.assertEqual(result.index_path, (runs_dir / "index.html").resolve())
            rows = self._rows(runs_dir)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0][0:3], ("20260818-100000_run with space", "deadbeef", "rabi</script><b>"))
            self.assertEqual(
                json.loads(rows[0][5]),
                {
                    "enabled": True,
                    "frequency": 5.5,
                    "label": "alpha</script><i>",
                    "optional": None,
                    "points": 101,
                },
            )
            with contextlib.closing(sqlite3.connect(runs_dir / CATALOG_FILENAME)) as connection:
                self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], SCHEMA_VERSION)
                columns = [row[1:3] for row in connection.execute("PRAGMA table_info(runs)")]
            self.assertEqual(
                columns,
                [
                    ("run_id", "TEXT"),
                    ("git_commit", "TEXT"),
                    ("workflow_type", "TEXT"),
                    ("started_at", "TEXT"),
                    ("runtime_seconds", "REAL"),
                    ("parameters_json", "TEXT"),
                ],
            )

            document = result.index_path.read_text(encoding="utf-8")
            self.assertNotIn("rabi</script>", document)
            self.assertIn(r"rabi\u003c/script>", document)
            records = self._embedded_records(result.index_path)
            self.assertEqual(records[0]["workflow_type"], "rabi</script><b>")
            self.assertEqual(records[0]["summary_href"], "20260818-100000_run%20with%20space/summary.html")

    def test_known_ids_are_not_reopened_and_new_stale_and_renamed_folders_are_synchronized(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project_root = Path(temporary_directory) / "project"
            runs_dir = project_root / "runs"
            project_root.mkdir()
            original = self._run(runs_dir, "20260818-100000_old", {"type": "scan", "points": 5})
            synchronize_catalog(project_root, runs_dir)

            with patch("labframe.catalog._read_run_record") as read_run:
                repeated = synchronize_catalog(project_root, runs_dir)
            read_run.assert_not_called()
            self.assertEqual((repeated.added, repeated.removed, repeated.skipped), (0, 0, 0))

            renamed = original.with_name("20260818-110000_renamed")
            original.rename(renamed)
            self._run(runs_dir, "20260818-120000_new", {"type": "scan", "points": 8})
            changed = synchronize_catalog(project_root, runs_dir)

            self.assertEqual((changed.added, changed.removed), (2, 1))
            self.assertEqual(
                [row[0] for row in self._rows(runs_dir)],
                ["20260818-110000_renamed", "20260818-120000_new"],
            )

    def test_schema_version_change_rebuilds_from_authoritative_run_folders(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project_root = Path(temporary_directory) / "project"
            runs_dir = project_root / "runs"
            project_root.mkdir()
            self._run(runs_dir, "20260818-100000_real", {"type": "scan", "points": 7})
            synchronize_catalog(project_root, runs_dir)
            with contextlib.closing(sqlite3.connect(runs_dir / CATALOG_FILENAME)) as connection:
                connection.execute(
                    "INSERT INTO runs VALUES (?, ?, ?, ?, ?, ?)",
                    ("stale", None, "old", None, None, "{}"),
                )
                connection.execute("PRAGMA user_version = 999")
                connection.commit()

            result = synchronize_catalog(project_root, runs_dir)

            self.assertEqual((result.added, result.removed), (1, 0))
            self.assertEqual([row[0] for row in self._rows(runs_dir)], ["20260818-100000_real"])

    def test_explicit_refresh_warns_and_skips_malformed_workflow_types(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project_root = Path(temporary_directory) / "project"
            runs_dir = project_root / "runs"
            project_root.mkdir()
            self._run(runs_dir, "missing-type", {"points": 5})
            self._run(runs_dir, "wrong-type", {"type": 123, "points": 5})
            self._run(runs_dir, "incomplete", {"type": "scan"}, status="running")
            stderr = io.StringIO()

            with contextlib.redirect_stderr(stderr):
                result = synchronize_catalog(project_root, runs_dir, warn=True)

            self.assertEqual((result.added, result.skipped), (0, 3))
            self.assertEqual(self._rows(runs_dir), [])
            self.assertIn("workflow.type is missing", stderr.getvalue())
            self.assertIn("status is 'running'", stderr.getvalue())

    def test_concurrent_synchronization_serializes_writes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project_root = Path(temporary_directory) / "project"
            runs_dir = project_root / "runs"
            project_root.mkdir()
            for index in range(20):
                self._run(
                    runs_dir,
                    f"20260818-{index:06d}_run",
                    {"type": "scan", "index": index},
                )

            with ThreadPoolExecutor(max_workers=4) as executor:
                results = list(executor.map(lambda _: synchronize_catalog(project_root, runs_dir), range(4)))

            self.assertEqual(len(self._rows(runs_dir)), 20)
            self.assertTrue(all(result.index_path.is_file() for result in results))
            with contextlib.closing(sqlite3.connect(runs_dir / CATALOG_FILENAME)) as connection:
                self.assertEqual(connection.execute("PRAGMA integrity_check").fetchone()[0], "ok")

    def test_index_contains_typed_and_missing_filters_expansion_and_pagination(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project_root = Path(temporary_directory) / "project"
            runs_dir = project_root / "runs"
            project_root.mkdir()
            self._run(runs_dir, "20260818-100000_old", {"type": "older", "points": 1})
            self._run(runs_dir, "20260818-120000_new", {"type": "newer", "label": "latest"})

            index_path = synchronize_catalog(project_root, runs_dir).index_path
            document = index_path.read_text(encoding="utf-8")
            records = self._embedded_records(index_path)

            self.assertEqual([record["run_id"] for record in records], ["20260818-120000_new", "20260818-100000_old"])
            self.assertIn("const pageSize = 100;", document)
            self.assertIn('["present", "is present"]', document)
            self.assertIn('["missing", "is missing"]', document)
            self.assertIn("filters.every", document)
            self.assertIn("parameterPaths = [...new Set", document)
            self.assertIn('show.textContent = "Show"', document)
            self.assertIn("function savedState()", document)
            self.assertIn("history.replaceState", document)
            self.assertIn("selectType(initialState)", document)


if __name__ == "__main__":
    unittest.main()
