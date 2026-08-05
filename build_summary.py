"""Build static per-run summaries and the root run index."""

import argparse
import json
from pathlib import Path
from urllib.parse import quote

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
DEFAULT_NOTES = "Add interpretation and follow-up notes here."


def _existing_notes(summary_path: Path) -> str:
    if not summary_path.exists():
        return DEFAULT_NOTES
    text = summary_path.read_text(encoding="utf-8")
    marker = "\n# Notes\n"
    if marker not in text:
        return DEFAULT_NOTES
    notes = text.split(marker, maxsplit=1)[1].strip()
    return notes or DEFAULT_NOTES


def _environment() -> Environment:
    return Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        autoescape=select_autoescape(enabled_extensions=("html", "j2"), default=True),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )


def _write_text(path: Path, text: str) -> None:
    temporary_path = path.with_name(f".{path.name}.tmp")
    temporary_path.write_text(text, encoding="utf-8")
    temporary_path.replace(path)


def _url(path: Path) -> str:
    return quote(path.as_posix(), safe="/")


def _read_metadata(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _read_output(path: Path) -> str:
    try:
        output = path.read_text(encoding="utf-8").rstrip()
    except FileNotFoundError:
        output = ""
    return output or "No output captured."


def _load_config(path: Path) -> dict:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Configuration root must be a mapping: {path}")
    return value


def _read_index_config(path: Path) -> dict:
    try:
        return _load_config(path)
    except (FileNotFoundError, ValueError, yaml.YAMLError):
        return {}


def _simulation_type(config: dict) -> str:
    simulation = config.get("simulation", {})
    if not isinstance(simulation, dict):
        return "unknown"
    value = simulation.get("type", simulation.get("model", "unknown"))
    return str(value) if value is not None else "unknown"


def rebuild_index(project_root: Path) -> Path:
    """Regenerate index.html from run folders that contain summary.html."""
    project_root = project_root.resolve()
    runs_dir = project_root / "runs"
    grouped_entries = {}

    if runs_dir.exists():
        for run_dir in sorted(runs_dir.iterdir(), key=lambda path: path.name, reverse=True):
            summary_html = run_dir / "summary.html"
            if not run_dir.is_dir() or not summary_html.is_file():
                continue
            meta = _read_metadata(run_dir / "meta.json")
            simulation_type = _simulation_type(_read_index_config(run_dir / "config.yaml"))
            grouped_entries.setdefault(simulation_type, []).append(
                {
                    "name": run_dir.name,
                    "href": _url(summary_html.relative_to(project_root)),
                    "simulation_type": simulation_type,
                    "started_at": meta.get("started_at"),
                    "runtime_seconds": meta.get("runtime_seconds"),
                    "status": meta.get("status", "unknown"),
                }
            )

    groups = [{"simulation_type": simulation_type, "entries": entries} for simulation_type, entries in grouped_entries.items()]
    rendered = _environment().get_template("index.html.j2").render(groups=groups)
    index_path = project_root / "index.html"
    _write_text(index_path, rendered)
    return index_path


def build_summary(run_dir: Path) -> None:
    """Create summary.md and render summary.html with Jinja2."""
    run_dir = run_dir.resolve()
    project_root = run_dir.parent.parent
    config = _load_config(run_dir / "config.yaml")
    simulation_type = _simulation_type(config)
    meta = _read_metadata(run_dir / "meta.json")
    output_text = _read_output(run_dir / "output")
    summary_path = run_dir / "summary.md"
    notes = _existing_notes(summary_path)

    result_files = sorted(path.name for path in (run_dir / "results").iterdir() if path.is_file())
    figure_files = sorted(path.name for path in (run_dir / "figures").iterdir() if path.is_file())
    config_yaml = yaml.safe_dump(config, sort_keys=False).rstrip()
    result_lines = "\n".join(f"- `{name}`" for name in result_files) or "- No results found."
    figure_blocks = "\n\n".join(f"![{name}](figures/{name})" for name in figure_files if name.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp")))

    summary = f"""# Simulation summary

Git commit: `{meta.get("git_commit") or "pending"}`  
Status: `{meta.get("status", "unknown")}`

# Parameters

```yaml
{config_yaml}
```

# Results

{result_lines}

{figure_blocks}

# Output

```text
{output_text}
```

# Notes

{notes}
"""
    _write_text(summary_path, summary)

    image_extensions = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp")
    rendered = (
        _environment()
        .get_template("summary.html.j2")
        .render(
            run_name=run_dir.name,
            simulation_type=simulation_type,
            meta=meta,
            config_yaml=config_yaml,
            notes=notes,
            output_text=output_text,
            results=[{"name": name, "href": _url(Path("results") / name)} for name in result_files],
            figures=[{"name": name, "src": _url(Path("figures") / name)} for name in figure_files if name.lower().endswith(image_extensions)],
            index_href="../../index.html",
        )
    )
    _write_text(run_dir / "summary.html", rendered)
    rebuild_index(project_root)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    args = parser.parse_args()
    build_summary(args.run_dir)


if __name__ == "__main__":
    main()
