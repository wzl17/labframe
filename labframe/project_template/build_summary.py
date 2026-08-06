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


def _completed_run_data(run_dir: Path) -> tuple[dict, dict] | None:
    try:
        config_text = (run_dir / "config.yaml").read_text(encoding="utf-8")
        meta_text = (run_dir / "meta.json").read_text(encoding="utf-8")
        config = yaml.safe_load(config_text)
        meta = json.loads(meta_text)
    except (OSError, UnicodeError, json.JSONDecodeError, yaml.YAMLError):
        return None
    if not isinstance(config, dict) or not isinstance(meta, dict) or meta.get("status") != "completed":
        return None
    return config, meta


def _read_notes(run_dir: Path) -> str:
    notes_path = run_dir / "notes.md"
    if notes_path.is_file():
        return notes_path.read_text(encoding="utf-8")
    notes = _legacy_notes(run_dir / "summary.md")
    _write_text(notes_path, notes)
    return notes


def _run_type(config: dict) -> str:
    workflow = config.get("workflow")
    if isinstance(workflow, dict):
        value = workflow.get("type")
        if value is not None:
            return str(value)

    value = config.get("run_type", config.get("type"))
    return str(value) if value is not None else "unknown"


def _relative_href(path: Path, start: Path) -> str:
    relative = Path(os.path.relpath(path, start)).as_posix()
    return quote(relative, safe="/")


def rebuild_index(project_root: Path, runs_dir: Path | None = None) -> Path:
    """Create the run-directory home page from completed per-run HTML summaries."""
    project_root = project_root.resolve()
    runs_dir = runs_dir.resolve() if runs_dir is not None else project_root / "runs"
    grouped_entries: dict[str, list[dict]] = {}

    if runs_dir.is_dir():
        for run_dir in sorted(runs_dir.iterdir(), key=lambda path: path.name, reverse=True):
            summary_path = run_dir / "summary.html"
            if not run_dir.is_dir() or not summary_path.is_file():
                continue
            saved_data = _completed_run_data(run_dir)
            if saved_data is None:
                continue
            config, meta = saved_data
            run_type = _run_type(config)
            grouped_entries.setdefault(run_type, []).append(
                {
                    "name": run_dir.name,
                    "href": _relative_href(summary_path, runs_dir),
                    "started_at": meta.get("started_at"),
                    "runtime_seconds": meta.get("runtime_seconds"),
                    "status": meta.get("status", "unknown"),
                }
            )

    group_documents = []
    for run_type, entries in grouped_entries.items():
        entry_documents = []
        for entry in entries:
            details = [str(entry["status"])]
            if entry["started_at"]:
                details.append(str(entry["started_at"]))
            if entry["runtime_seconds"] is not None:
                details.append(f"{entry['runtime_seconds']} s")
            entry_documents.append(
                f'<li><a href="{html.escape(entry["href"], quote=True)}">'
                f'<span class="run-name">{html.escape(entry["name"])}</span>'
                f'<span class="run-details">{html.escape(" · ".join(details))}</span>'
                "</a></li>"
            )
        count = len(entries)
        group_documents.append(
            f'<section class="run-group" data-run-type="{html.escape(run_type, quote=True)}">'
            '<h2><span class="group-label">Run type</span> '
            f"<code>{html.escape(run_type)}</code> "
            f'<span class="run-count">{count} run{"s" if count != 1 else ""}</span></h2>'
            f'<ul class="run-list">{"".join(entry_documents)}</ul></section>'
        )

    groups = "".join(group_documents) or '<div class="panel muted">No run summaries are available yet.</div>'
    project_name = html.escape(project_root.name)
    document = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>{project_name} runs · Labframe</title>
<style>
:root{{color-scheme:light dark;--background:#f4f6f8;--surface:#fff;--text:#17202a;--muted:#667085;--border:#d8dee6;--accent:#2457a7}}
@media(prefers-color-scheme:dark){{:root{{--background:#11151a;--surface:#191f26;--text:#e7edf3;--muted:#a5b0bd;--border:#35404c;--accent:#8bb8ff}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--background);color:var(--text);font:16px/1.55 system-ui}}
main{{width:min(64rem,calc(100% - 2rem));margin:0 auto;padding:3rem 0 5rem}}h1{{margin:0 0 .35rem}}h2{{display:flex;flex-wrap:wrap;align-items:baseline;gap:.55rem}}
.lede,.muted,.group-label,.run-count,.run-details{{color:var(--muted)}}.run-group{{margin-top:2.2rem}}.group-label{{font-size:.82rem;text-transform:uppercase;letter-spacing:.04em}}
.run-count{{font-size:.85rem;font-weight:400}}.run-list{{display:grid;gap:.8rem;padding:0;list-style:none}}.run-list a{{display:block;padding:1rem 1.1rem;border:1px solid var(--border);border-radius:.65rem;background:var(--surface);text-decoration:none}}
.run-list a:hover{{border-color:var(--accent)}}.run-name{{display:block;color:var(--text);font-weight:650}}.run-details{{display:block;margin-top:.25rem;font-size:.9rem}}.panel{{margin-top:1.5rem;padding:1.25rem;border:1px solid var(--border);border-radius:.75rem;background:var(--surface)}}
</style></head><body><main><h1>{project_name} runs</h1>
<p class="lede">Static summaries grouped by run type.</p>{groups}</main></body></html>
"""
    index_path = runs_dir / "index.html"
    _write_text(index_path, document)
    return index_path


def build_summary(run_dir: Path) -> None:
    """Create summary.md and summary.html without rerunning earlier stages."""
    run_dir = run_dir.resolve()
    config = yaml.safe_load((run_dir / "config.yaml").read_text(encoding="utf-8"))
    meta = json.loads((run_dir / "meta.json").read_text(encoding="utf-8"))
    configured_project_root = meta.get("project_root")
    project_root = (
        Path(configured_project_root).resolve()
        if isinstance(configured_project_root, str) and configured_project_root
        else run_dir.parent.parent
    )
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
    rebuild_index(project_root, runs_dir)
