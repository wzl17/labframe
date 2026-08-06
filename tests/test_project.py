import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from labframe.cli import _build_parser, main
from labframe.defaults import new_project
from labframe.project import find_project_root, initialize_project, project_commit_default, project_runs_dir


class ProjectTest(unittest.TestCase):
    def test_new_project_command_uses_containing_environment_defaults(self) -> None:
        with (
            patch("labframe.defaults.subprocess.call", return_value=23) as call,
            patch("sys.argv", ["labframe-new-project", "my-simulation", "--name", "Rabi scan"]),
        ):
            with self.assertRaisesRegex(SystemExit, "23"):
                new_project()

        self.assertEqual(
            call.call_args.args[0],
            [
                "labframe",
                "init",
                "--no-venv",
                "--no-git",
                "--runs-dir",
                str(Path.home() / "data" / "labframe"),
                "my-simulation",
                "--name",
                "Rabi scan",
            ],
        )

    def test_init_parser_accepts_runs_directory(self) -> None:
        args = _build_parser().parse_args(["init", "example", "--runs-dir", "../run-artifacts"])

        self.assertEqual(args.runs_dir, Path("../run-artifacts"))

    def test_run_parser_leaves_commit_unspecified_until_project_settings_are_loaded(self) -> None:
        parser = _build_parser()

        self.assertIsNone(parser.parse_args(["run"]).commit)
        self.assertTrue(parser.parse_args(["run", "--commit"]).commit)
        self.assertFalse(parser.parse_args(["run", "--no-commit"]).commit)

    def test_initializer_materializes_editable_rabi_project(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project_root = Path(temporary_directory) / "microwave-experiment"
            initialize_project(project_root, sync=False, initialize_git=False)

            expected = {
                ".labframe.yaml",
                "workflow.py",
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
            self.assertFalse(project_commit_default(project_root))

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
                "runs_dir: ../run-artifacts\ncommit: false\n",
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

    def test_project_commit_default_reads_and_validates_settings(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project_root = Path(temporary_directory) / "commit-settings"
            initialize_project(project_root, sync=False, initialize_git=False)
            settings_path = project_root / ".labframe.yaml"

            settings_path.write_text("runs_dir: runs\ncommit: false\n", encoding="utf-8")
            self.assertFalse(project_commit_default(project_root))

            settings_path.write_text("runs_dir: runs\ncommit: sometimes\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "commit must be true or false"):
                project_commit_default(project_root)

    def test_cli_uses_project_commit_default_unless_overridden(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project_root = Path(temporary_directory) / "commit-settings"
            initialize_project(project_root, sync=False, initialize_git=False)
            (project_root / ".labframe.yaml").write_text(
                "runs_dir: runs\ncommit: false\n", encoding="utf-8"
            )
            run_dir = project_root / "runs" / "test-run"

            with patch("labframe.cli.run_project", return_value=run_dir) as run:
                with patch("sys.argv", ["labframe", "run", "--project", str(project_root), "configs/smoke.yaml"]):
                    main()
            self.assertFalse(run.call_args.kwargs["commit"])

            with patch("labframe.cli.run_project", return_value=run_dir) as run:
                with patch(
                    "sys.argv",
                    ["labframe", "run", "--project", str(project_root), "--commit", "configs/smoke.yaml"],
                ):
                    main()
            self.assertTrue(run.call_args.kwargs["commit"])


if __name__ == "__main__":
    unittest.main()
