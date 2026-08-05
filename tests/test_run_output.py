import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from build_summary import build_summary
from run import _run_core


class RunOutputTest(unittest.TestCase):
    def test_core_output_is_saved_for_summary_use(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            run_dir = Path(temporary_directory)
            (run_dir / "results").mkdir()
            (run_dir / "figures").mkdir()
            (run_dir / "config.yaml").write_text("simulation: {}\n", encoding="utf-8")

            with (
                patch("simulation.run_simulation", side_effect=lambda *_: print("fit report")),
                patch("plot_results.plot_results"),
            ):
                _run_core(run_dir)

            self.assertEqual((run_dir / "output").read_text(encoding="utf-8"), "fit report\n")

    def test_summary_contains_output_section(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            run_dir = Path(temporary_directory) / "runs" / "test-run"
            (run_dir / "results").mkdir(parents=True)
            (run_dir / "figures").mkdir()
            (run_dir / "config.yaml").write_text(
                "simulation:\n  type: test\n",
                encoding="utf-8",
            )
            (run_dir / "meta.json").write_text("{}\n", encoding="utf-8")
            (run_dir / "output").write_text("fit report\n", encoding="utf-8")

            build_summary(run_dir)

            summary_markdown = (run_dir / "summary.md").read_text(encoding="utf-8")
            summary_html = (run_dir / "summary.html").read_text(encoding="utf-8")
            self.assertIn("# Output\n\n```text\nfit report\n```", summary_markdown)
            self.assertIn("<h2>Output</h2>", summary_html)
            self.assertIn("<pre>fit report</pre>", summary_html)


if __name__ == "__main__":
    unittest.main()
