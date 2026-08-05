"""Editable Markdown/HTML summary hook built from saved artifacts."""

import html
import json
from pathlib import Path

import yaml

DEFAULT_NOTES = "Add interpretation and follow-up notes here."


def _existing_notes(summary_path: Path) -> str:
    if not summary_path.is_file():
        return DEFAULT_NOTES
    marker = "\n# Notes\n"
    text = summary_path.read_text(encoding="utf-8")
    if marker not in text:
        return DEFAULT_NOTES
    return text.split(marker, maxsplit=1)[1].strip() or DEFAULT_NOTES


def _read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else {}


def _write_index(project_root: Path) -> None:
    entries = []
    for run_dir in sorted((project_root / "runs").glob("*"), reverse=True):
        if (run_dir / "summary.html").is_file():
            entries.append(
                f'<li><a href="runs/{html.escape(run_dir.name)}/summary.html">{html.escape(run_dir.name)}</a></li>'
            )
    listing = "\n".join(entries) or "<li>No completed runs yet.</li>"
    document = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Labframe runs</title><style>body{{font:16px/1.5 system-ui;max-width:56rem;margin:3rem auto;padding:0 1rem}}li{{margin:.5rem 0}}</style></head>
<body><h1>Labframe runs</h1><ul>{listing}</ul></body></html>
"""
    (project_root / "index.html").write_text(document, encoding="utf-8")


def build_summary(run_dir: Path) -> None:
    """Create summary.md and summary.html without rerunning earlier stages."""
    run_dir = run_dir.resolve()
    project_root = run_dir.parent.parent
    config = yaml.safe_load((run_dir / "config.yaml").read_text(encoding="utf-8"))
    meta = _read_json(run_dir / "meta.json")
    fit = _read_json(run_dir / "results" / "fit.json")
    output = (run_dir / "output.log").read_text(encoding="utf-8").rstrip()
    summary_path = run_dir / "summary.md"
    notes = _existing_notes(summary_path)
    config_yaml = yaml.safe_dump(config, sort_keys=False).rstrip()

    summary = f"""# Run summary

Git commit: `{meta.get("git_commit") or "pending"}`  
Status: `{meta.get("status", "unknown")}`  
Runtime: `{meta.get("runtime_seconds", "unknown")} s`

# Parameters

```yaml
{config_yaml}
```

# Fit results

- Oscillation frequency: `{fit["oscillation_frequency_hz"]:.8g} Hz`
- Frequency standard error: `{fit["oscillation_frequency_standard_error_hz"]:.3g} Hz`
- Contrast: `{fit["contrast"]:.6g}`
- Offset: `{fit["offset"]:.6g}`
- RMSE: `{fit["rmse"]:.6g}`

![Rabi data and fit](figures/rabi_fit.png)

# Output

```text
{output}
```

# Notes

{notes}
"""
    summary_path.write_text(summary, encoding="utf-8")

    fit_rows = "".join(f"<tr><th>{html.escape(key)}</th><td>{value:.8g}</td></tr>" for key, value in fit.items())
    document = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>{html.escape(run_dir.name)} · Labframe</title>
<style>body{{font:16px/1.55 system-ui;max-width:64rem;margin:3rem auto;padding:0 1rem;color:#17202a}}pre{{overflow:auto;background:#f3f5f7;padding:1rem;border-radius:.5rem}}img{{max-width:100%}}th{{text-align:left;padding-right:1.5rem}}td,th{{padding-top:.35rem}}</style></head>
<body><a href="../../index.html">← All runs</a><h1>Run summary</h1>
<p>Status: <code>{html.escape(str(meta.get("status", "unknown")))}</code> · Git: <code>{html.escape(str(meta.get("git_commit") or "pending"))}</code></p>
<h2>Parameters</h2><pre>{html.escape(config_yaml)}</pre>
<h2>Fit results</h2><table>{fit_rows}</table>
<figure><img src="figures/rabi_fit.png" alt="Rabi data and fit"><figcaption>Saved data and fitted model.</figcaption></figure>
<h2>Output</h2><pre>{html.escape(output)}</pre><h2>Notes</h2><p>{html.escape(notes)}</p></body></html>
"""
    (run_dir / "summary.html").write_text(document, encoding="utf-8")
    _write_index(project_root)
