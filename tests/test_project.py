import tempfile
import unittest
from pathlib import Path

from labframe.project import find_project_root, initialize_project


class ProjectTest(unittest.TestCase):
    def test_initializer_materializes_editable_rabi_project(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project_root = Path(temporary_directory) / "microwave-experiment"
            initialize_project(project_root, sync=False, initialize_git=False)

            expected = {
                "simulation.py",
                "fit_results.py",
                "plot_results.py",
                "plot_style.py",
                "build_summary.py",
                "labframe.yaml",
                "configs/default.yaml",
                "configs/smoke.yaml",
                "tests/test_rabi_workflow.py",
            }
            for relative_path in expected:
                with self.subTest(path=relative_path):
                    self.assertTrue((project_root / relative_path).is_file())

            pyproject = (project_root / "pyproject.toml").read_text(encoding="utf-8")
            self.assertIn('name = "microwave-experiment"', pyproject)
            self.assertIn('labframe = { path = "', pyproject)
            self.assertEqual(find_project_root(project_root / "configs"), project_root.resolve())

    def test_initializer_refuses_nonempty_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project_root = Path(temporary_directory)
            (project_root / "keep.txt").write_text("user data", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                initialize_project(project_root, sync=False, initialize_git=False)


if __name__ == "__main__":
    unittest.main()
