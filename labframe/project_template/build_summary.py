"""Build Markdown and HTML summaries from saved run artifacts."""

import html
import json
import os
from pathlib import Path
from urllib.parse import quote

import yaml
from markdown import markdown


def _legacy_notes(summary_path: Path) -> str:
    if not summary_path.is_file():
        return ""
    lines = summary_path.read_text(encoding="utf-8").splitlines(keepends=True)
    for index, line in enumerate(lines):
        if line.rstrip("\r\n") == "# Notes":
            notes = "".join(lines[index + 1 :])
            return notes.removeprefix("\r\n").removeprefix("\n")
    return ""


def _write_text(path: Path, text: str) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def _read_notes(run_dir: Path) -> str:
    notes_path = run_dir / "notes.md"
    if notes_path.is_file():
        return notes_path.read_text(encoding="utf-8")
    notes = _legacy_notes(run_dir / "summary.md")
    _write_text(notes_path, notes)
    return notes


def _relative_href(path: Path, start: Path) -> str:
    relative = Path(os.path.relpath(path, start)).as_posix()
    return quote(relative, safe="/")


def build_summary(run_dir: Path) -> None:
    """Create summary.md and summary.html without rerunning earlier stages."""
    run_dir = run_dir.resolve()
    config = yaml.safe_load((run_dir / "config.yaml").read_text(encoding="utf-8"))
    meta = json.loads((run_dir / "meta.json").read_text(encoding="utf-8"))
    runs_dir = run_dir.parent
    output = (run_dir / "output.log").read_text(encoding="utf-8").rstrip() or "No output captured."
    summary_path = run_dir / "summary.md"
    notes = _read_notes(run_dir)
    config_yaml = yaml.safe_dump(config, sort_keys=False).rstrip()
    result_files = sorted(path.name for path in (run_dir / "results").glob("*.npz"))
    result_lines = "\n".join(f"- `results/{name}`" for name in result_files)

    summary = f"""# Run summary

Git commit: `{meta.get("git_commit") or "pending"}`  
Status: `{meta.get("status", "unknown")}`  
Runtime: `{meta.get("runtime_seconds", "unknown")} s`

# Parameters

```yaml
{config_yaml}
```

# Results

{result_lines}

![Combined results](figures/combined_results.png)

# Output

```text
{output}
```

# Notes

{notes}
"""
    _write_text(summary_path, summary)

    result_items = "".join(f"<li><code>results/{html.escape(name)}</code></li>" for name in result_files)
    index_href = html.escape(_relative_href(runs_dir / "index.html", run_dir), quote=True)
    document = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>{html.escape(run_dir.name)} · Labframe</title>
<style>body{{font:16px/1.55 system-ui;max-width:64rem;margin:3rem auto;padding:0 1rem;color:#17202a}}pre{{overflow:auto;background:#f3f5f7;padding:1rem;border-radius:.5rem}}img{{max-width:100%}}</style></head>
<body><p><a href="{index_href}">← All runs</a></p><h1>Run summary</h1>
<p>Status: <code>{html.escape(str(meta.get("status", "unknown")))}</code> · Git: <code>{html.escape(str(meta.get("git_commit") or "pending"))}</code></p>
<h2>Parameters</h2><pre>{html.escape(config_yaml)}</pre>
<h2>Results</h2><ul>{result_items}</ul>
<figure><img src="figures/combined_results.png" alt="Combined results"></figure>
<h2>Output</h2><pre>{html.escape(output)}</pre><h2>Notes</h2>{markdown(html.escape(notes))}</body></html>
"""
    _write_text(run_dir / "summary.html", document)
