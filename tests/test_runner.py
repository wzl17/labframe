import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from labframe.project import initialize_project
from labframe.runner import run_project


def _git(project_root: Path, *arguments: str) -> None:
    subprocess.run(["git", *arguments], cwd=project_root, check=True, capture_output=True)


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

    def test_no_commit_run_executes_simulation_fit_plot_and_summary(self) -> None:
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
            fit = json.loads((run_dir / "results" / "fit.json").read_text(encoding="utf-8"))
            self.assertEqual(meta["status"], "completed")
            self.assertEqual(meta["git_commit"], starting_commit)
            self.assertAlmostEqual(fit["oscillation_frequency_hz"], 50_000.0, delta=500.0)
            self.assertTrue((run_dir / "results" / "rabi_data.npz").is_file())
            self.assertTrue((run_dir / "results" / "rabi_fit.npz").is_file())
            self.assertTrue((run_dir / "figures" / "rabi_fit.png").is_file())
            self.assertTrue((run_dir / "summary.md").is_file())
            self.assertTrue((run_dir / "summary.html").is_file())
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
