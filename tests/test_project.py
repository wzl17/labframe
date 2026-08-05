import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from labframe.cli import _build_parser
from labframe.project import find_project_root, initialize_project, project_runs_dir


class ProjectTest(unittest.TestCase):
    def test_init_parser_accepts_runs_directory(self) -> None:
        args = _build_parser().parse_args(["init", "example", "--runs-dir", "../run-artifacts"])

        self.assertEqual(args.runs_dir, Path("../run-artifacts"))

    def test_initializer_materializes_editable_rabi_project(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project_root = Path(temporary_directory) / "microwave-experiment"
            initialize_project(project_root, sync=False, initialize_git=False)

            expected = {
                ".labframe.yaml",
                "simulation.py",
                "fit_models.py",
                "plot_results.py",
                "build_summary.py",
                "configs/default.yaml",
                "configs/smoke.yaml",
            }
            for relative_path in expected:
                with self.subTest(path=relative_path):
                    self.assertTrue((project_root / relative_path).is_file())

            pyproject = (project_root / "pyproject.toml").read_text(encoding="utf-8")
            self.assertIn('name = "microwave-experiment"', pyproject)
            self.assertIn('labframe = { path = "', pyproject)
            self.assertNotIn("[tool.labframe]", pyproject)
            readme = (project_root / "README.md").read_text(encoding="utf-8")
            self.assertIn("# microwave-experiment", readme)
            self.assertNotIn("{{PROJECT_NAME}}", readme)
            self.assertEqual(find_project_root(project_root / "configs"), project_root.resolve())
            self.assertEqual(project_runs_dir(project_root), (project_root / "runs").resolve())

    def test_initializer_configures_an_external_runs_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            parent = Path(temporary_directory)
            project_root = parent / "microwave-experiment"
            runs_dir = parent / "run-artifacts"

            initialize_project(
                project_root,
                sync=False,
                initialize_git=False,
                runs_dir=Path("../run-artifacts"),
            )

            self.assertEqual(
                (project_root / ".labframe.yaml").read_text(encoding="utf-8"),
                "runs_dir: ../run-artifacts\n",
            )
            self.assertEqual(project_runs_dir(project_root), runs_dir.resolve())
            self.assertTrue(runs_dir.is_dir())
            self.assertFalse((project_root / "runs").exists())

    def test_initializer_ignores_a_custom_runs_directory_inside_the_project(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project_root = Path(temporary_directory) / "microwave-experiment"

            initialize_project(
                project_root,
                sync=False,
                initialize_git=False,
                runs_dir=Path("artifacts/runs"),
            )

            custom_gitignore = project_root / "artifacts" / "runs" / ".gitignore"
            self.assertEqual(custom_gitignore.read_text(encoding="utf-8"), "*\n!.gitignore\n")

    def test_initializer_refuses_nonempty_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project_root = Path(temporary_directory)
            (project_root / "keep.txt").write_text("user data", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                initialize_project(project_root, sync=False, initialize_git=False)

    def test_initializer_can_use_containing_environment_without_pyproject(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project_root = Path(temporary_directory) / "contained-project"
            with patch("labframe.project._run") as run:
                initialize_project(project_root, create_venv=False, initialize_git=False)

            run.assert_not_called()
            self.assertFalse((project_root / "pyproject.toml").exists())
            self.assertFalse((project_root / "uv.lock").exists())
            self.assertFalse((project_root / ".venv").exists())
            self.assertEqual(find_project_root(project_root / "configs"), project_root.resolve())


if __name__ == "__main__":
    unittest.main()
