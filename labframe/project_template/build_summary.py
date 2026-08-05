"""Build Markdown and HTML summaries from saved run artifacts."""

import html
import json
from pathlib import Path
from urllib.parse import quote

import yaml

DEFAULT_NOTES = "Add interpretation and follow-up notes here."


def _existing_notes(summary_path: Path) -> str:
    if not summary_path.is_file():
        return DEFAULT_NOTES
    text = summary_path.read_text(encoding="utf-8")
    marker = "\n# Notes\n"
    if marker not in text:
        return DEFAULT_NOTES
    return text.split(marker, maxsplit=1)[1].strip() or DEFAULT_NOTES


def _write_text(path: Path, text: str) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def _read_mapping(path: Path, *, yaml_document: bool = False) -> dict:
    try:
        text = path.read_text(encoding="utf-8")
        value = yaml.safe_load(text) if yaml_document else json.loads(text)
    except (FileNotFoundError, json.JSONDecodeError, yaml.YAMLError):
        return {}
    return value if isinstance(value, dict) else {}


def _run_type(config: dict) -> str:
    for section_name in ("simulation", "experiment"):
        section = config.get(section_name)
        if not isinstance(section, dict):
            continue
        value = section.get("type", section.get("model"))
        if value is not None:
            return str(value)

    value = config.get("run_type", config.get("type"))
    return str(value) if value is not None else "unknown"


def rebuild_index(project_root: Path) -> Path:
    """Create the project home page from completed per-run HTML summaries."""
    project_root = project_root.resolve()
    grouped_entries: dict[str, list[dict]] = {}
    runs_dir = project_root / "runs"

    if runs_dir.is_dir():
        for run_dir in sorted(runs_dir.iterdir(), key=lambda path: path.name, reverse=True):
            summary_path = run_dir / "summary.html"
            if not run_dir.is_dir() or not summary_path.is_file():
                continue
            meta = _read_mapping(run_dir / "meta.json")
            run_type = _run_type(_read_mapping(run_dir / "config.yaml", yaml_document=True))
            grouped_entries.setdefault(run_type, []).append(
                {
                    "name": run_dir.name,
                    "href": quote(summary_path.relative_to(project_root).as_posix(), safe="/"),
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
    index_path = project_root / "index.html"
    _write_text(index_path, document)
    return index_path


def build_summary(run_dir: Path) -> None:
    """Create summary.md and summary.html without rerunning earlier stages."""
    run_dir = run_dir.resolve()
    project_root = run_dir.parent.parent
    config = yaml.safe_load((run_dir / "config.yaml").read_text(encoding="utf-8"))
    meta = json.loads((run_dir / "meta.json").read_text(encoding="utf-8"))
    output = (run_dir / "output.log").read_text(encoding="utf-8").rstrip() or "No output captured."
    summary_path = run_dir / "summary.md"
    notes = _existing_notes(summary_path)
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
    document = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>{html.escape(run_dir.name)} · Labframe</title>
<style>body{{font:16px/1.55 system-ui;max-width:64rem;margin:3rem auto;padding:0 1rem;color:#17202a}}pre{{overflow:auto;background:#f3f5f7;padding:1rem;border-radius:.5rem}}img{{max-width:100%}}</style></head>
<body><p><a href="../../index.html">← All runs</a></p><h1>Run summary</h1>
<p>Status: <code>{html.escape(str(meta.get("status", "unknown")))}</code> · Git: <code>{html.escape(str(meta.get("git_commit") or "pending"))}</code></p>
<h2>Parameters</h2><pre>{html.escape(config_yaml)}</pre>
<h2>Results</h2><ul>{result_items}</ul>
<figure><img src="figures/combined_results.png" alt="Combined results"></figure>
<h2>Output</h2><pre>{html.escape(output)}</pre><h2>Notes</h2><p>{html.escape(notes)}</p></body></html>
"""
    _write_text(run_dir / "summary.html", document)
    rebuild_index(project_root)
