"""Incrementally catalog completed runs and build their static index."""

import html
import json
import math
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

import yaml

CATALOG_FILENAME = "catalog.sqlite3"
INDEX_FILENAME = "index.html"
SCHEMA_VERSION = 1


@dataclass(frozen=True)
class CatalogSyncResult:
    index_path: Path
    added: int
    removed: int
    skipped: int


def _write_text(path: Path, text: str) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def _json_scalar(value):
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float) and math.isfinite(value):
        return value
    return None


def _read_run_record(run_dir: Path) -> tuple[dict | None, str | None]:
    required = ("config.yaml", "meta.json", "summary.html")
    missing = [name for name in required if not (run_dir / name).is_file()]
    if missing:
        return None, f"missing {', '.join(missing)}"

    try:
        config = yaml.safe_load((run_dir / "config.yaml").read_text(encoding="utf-8"))
        meta = json.loads((run_dir / "meta.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, yaml.YAMLError) as error:
        return None, f"unreadable saved data ({error})"

    if not isinstance(config, dict):
        return None, "config.yaml is not a mapping"
    if not isinstance(meta, dict):
        return None, "meta.json is not an object"
    if meta.get("status") != "completed":
        return None, f"status is {meta.get('status', 'missing')!r}"

    workflow = config.get("workflow")
    if not isinstance(workflow, dict):
        return None, "workflow is not a mapping"
    workflow_type = workflow.get("type")
    if not isinstance(workflow_type, str) or not workflow_type:
        return None, "workflow.type is missing or is not a non-empty string"

    parameters = {}
    for name, value in workflow.items():
        if name == "type":
            continue
        scalar = _json_scalar(value)
        if scalar is not None or value is None:
            parameters[str(name)] = scalar

    git_commit = meta.get("git_commit")
    started_at = meta.get("started_at")
    runtime_seconds = meta.get("runtime_seconds")
    if (
        isinstance(runtime_seconds, bool)
        or not isinstance(runtime_seconds, (int, float))
        or not math.isfinite(runtime_seconds)
    ):
        runtime_seconds = None
    return (
        {
            "run_id": run_dir.name,
            "git_commit": str(git_commit) if git_commit is not None else None,
            "workflow_type": workflow_type,
            "started_at": str(started_at) if started_at is not None else None,
            "runtime_seconds": float(runtime_seconds) if runtime_seconds is not None else None,
            "parameters_json": json.dumps(
                parameters,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ),
        },
        None,
    )


def _initialize_schema(connection: sqlite3.Connection) -> None:
    table_exists = connection.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'runs'").fetchone()
    version = connection.execute("PRAGMA user_version").fetchone()[0]
    if table_exists and version != SCHEMA_VERSION:
        connection.execute("DROP TABLE runs")
        table_exists = None
    if not table_exists:
        connection.execute(
            """
            CREATE TABLE runs (
                run_id TEXT PRIMARY KEY,
                git_commit TEXT,
                workflow_type TEXT NOT NULL,
                started_at TEXT,
                runtime_seconds REAL,
                parameters_json TEXT NOT NULL
            )
            """
        )
        connection.execute("CREATE INDEX runs_by_type_and_id ON runs (workflow_type, run_id DESC)")
    connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")


def _database_records(connection: sqlite3.Connection) -> list[dict]:
    rows = connection.execute(
        """
        SELECT run_id, git_commit, workflow_type, started_at, runtime_seconds, parameters_json
        FROM runs
        ORDER BY run_id DESC
        """
    ).fetchall()
    return [
        {
            "run_id": row[0],
            "git_commit": row[1],
            "workflow_type": row[2],
            "started_at": row[3],
            "runtime_seconds": row[4],
            "parameters": json.loads(row[5]),
            "summary_href": f"{quote(row[0], safe='')}/summary.html",
        }
        for row in rows
    ]


def _embedded_json(value) -> str:
    return (
        json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        .replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def _render_index(project_name: str, records: list[dict]) -> str:
    document = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>__PROJECT_NAME__ runs · Labframe</title>
<style>
:root{color-scheme:light dark;--background:#f4f6f8;--surface:#fff;--text:#17202a;--muted:#667085;--border:#d8dee6;--accent:#2457a7;--accent-text:#fff;--danger:#a33a3a}
@media(prefers-color-scheme:dark){:root{--background:#11151a;--surface:#191f26;--text:#e7edf3;--muted:#a5b0bd;--border:#35404c;--accent:#8bb8ff;--accent-text:#101820;--danger:#ff9999}}
*{box-sizing:border-box}body{margin:0;background:var(--background);color:var(--text);font:16px/1.5 system-ui}main{width:min(86rem,calc(100% - 2rem));margin:0 auto;padding:3rem 0 5rem}h1{margin:0 0 .35rem}.muted,.lede{color:var(--muted)}
.panel{margin-top:1.5rem;padding:1.25rem;border:1px solid var(--border);border-radius:.75rem;background:var(--surface)}label,.filter-label{font-size:.82rem;font-weight:700;letter-spacing:.03em;text-transform:uppercase;color:var(--muted)}input,select,button{min-height:2.5rem;border:1px solid var(--border);border-radius:.45rem;background:var(--surface);color:var(--text);font:inherit;padding:.45rem .65rem}button{cursor:pointer}button:hover{border-color:var(--accent)}button.primary{border-color:var(--accent);background:var(--accent);color:var(--accent-text);font-weight:650}
.type-row,.filter-heading,.results-heading,.pagination{display:flex;align-items:center;justify-content:space-between;gap:1rem}.type-field{display:grid;grid-template-columns:auto minmax(14rem,24rem);align-items:center;gap:.8rem}.filter-section{margin-top:1.2rem;padding-top:1rem;border-top:1px solid var(--border)}.filter-list{display:grid;gap:.65rem;margin-top:.75rem}.filter-row{display:grid;grid-template-columns:minmax(14rem,2fr) minmax(8rem,.8fr) minmax(10rem,1.2fr) auto;gap:.55rem}.remove-filter{color:var(--danger)}.filter-actions{display:flex;gap:.6rem;margin-top:.8rem}
.table-wrap{overflow:auto;margin-top:.75rem;border:1px solid var(--border);border-radius:.6rem}table{width:100%;border-collapse:collapse}th,td{padding:.8rem .9rem;border-bottom:1px solid var(--border);text-align:left;vertical-align:top;white-space:nowrap}th{font-size:.78rem;text-transform:uppercase;letter-spacing:.04em;color:var(--muted);background:var(--background)}tbody tr:last-child td{border-bottom:0}.run-link{font-weight:650}.commit{font-family:ui-monospace,SFMono-Regular,Consolas,monospace}.details-row td{padding:0;white-space:normal;background:var(--background)}.details-panel{padding:1rem}.parameter-table{font-size:.9rem}.parameter-table td:first-child{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;color:var(--muted)}.parameter-table td:last-child{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;white-space:pre-wrap;overflow-wrap:anywhere}.parameter-table tr:last-child td{border-bottom:0}.pagination{margin-top:1rem;justify-content:flex-end}.pagination span{min-width:10rem;text-align:center}.empty{padding:2rem;text-align:center;color:var(--muted)}[hidden]{display:none!important}
@media(max-width:52rem){main{padding-top:1.5rem}.type-row,.results-heading,.pagination{align-items:flex-start;flex-wrap:wrap}.type-field,.filter-row{grid-template-columns:1fr}.remove-filter{justify-self:start}th,td{padding:.65rem}}
</style></head><body><main><h1>__PROJECT_NAME__ runs</h1><p class="lede">Completed runs indexed by workflow type and saved parameters.</p>
<section class="panel" aria-label="Run filters"><div class="type-row"><div class="type-field"><label for="workflow-type">Workflow type</label><select id="workflow-type"></select></div><span id="type-count" class="muted"></span></div>
<div class="filter-section"><div class="filter-heading"><span class="filter-label">Parameter filters</span><span class="muted">All filters must match</span></div><div id="filter-list" class="filter-list"></div><div class="filter-actions"><button id="add-filter" class="primary" type="button">Add parameter filter</button><button id="reset-filters" type="button">Reset</button></div></div></section>
<section class="panel" aria-live="polite"><div class="results-heading"><strong id="result-count">0 runs</strong><span class="muted">Newest runs first</span></div><div id="table-wrap" class="table-wrap"><table><thead><tr><th>Run</th><th>Started</th><th>Git commit</th><th>Runtime</th><th>Parameters</th></tr></thead><tbody id="results-body"></tbody></table></div><div id="empty-results" class="empty" hidden>No matching runs.</div><div id="pagination" class="pagination"><button id="previous-page" type="button">Previous</button><span id="page-status"></span><button id="next-page" type="button">Next</button></div></section>
<noscript><div class="panel">JavaScript is required to filter this local catalog.</div></noscript>
<script type="application/json" id="run-data">__RUN_DATA__</script>
<script>
(() => {
  "use strict";
  const runs = JSON.parse(document.getElementById("run-data").textContent);
  const pageSize = 100;
  let selectedRuns = [];
  let filteredRuns = [];
  let parameterPaths = [];
  let page = 1;
  const typeSelect = document.getElementById("workflow-type");
  const typeCount = document.getElementById("type-count");
  const filterList = document.getElementById("filter-list");
  const resultsBody = document.getElementById("results-body");
  const resultCount = document.getElementById("result-count");
  const tableWrap = document.getElementById("table-wrap");
  const emptyResults = document.getElementById("empty-results");
  const pagination = document.getElementById("pagination");
  const pageStatus = document.getElementById("page-status");
  const previousPage = document.getElementById("previous-page");
  const nextPage = document.getElementById("next-page");

  function addOption(select, value, label = value) {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = label;
    select.append(option);
  }

  const typeCounts = new Map();
  for (const run of runs) typeCounts.set(run.workflow_type, (typeCounts.get(run.workflow_type) || 0) + 1);
  for (const [type, count] of typeCounts) addOption(typeSelect, type, `${type} (${count})`);
  if (!runs.length) {
    addOption(typeSelect, "", "No completed runs");
    typeSelect.disabled = true;
  }

  function displayValue(value) {
    if (value === null) return "null";
    if (typeof value === "string") return value;
    return JSON.stringify(value);
  }

  function parameterKind(path) {
    const kinds = new Set();
    for (const run of selectedRuns) {
      if (!Object.hasOwn(run.parameters, path)) continue;
      const value = run.parameters[path];
      kinds.add(value === null ? "null" : typeof value);
    }
    if (kinds.size > 1) kinds.delete("null");
    return kinds.size === 1 ? [...kinds][0] : "string";
  }

  function parameterLabel(path) {
    const count = selectedRuns.filter(run => Object.hasOwn(run.parameters, path)).length;
    return `${path} (${count}/${selectedRuns.length})`;
  }

  function configureFilterRow(row) {
    const path = row._key.value;
    const kind = path ? parameterKind(path) : "string";
    row._operator.replaceChildren();
    const operators = kind === "number"
      ? [["eq", "="], ["neq", "≠"], ["gt", ">"], ["gte", "≥"], ["lt", "<"], ["lte", "≤"], ["present", "is present"], ["missing", "is missing"]]
      : kind === "string"
        ? [["eq", "="], ["neq", "≠"], ["contains", "contains"], ["present", "is present"], ["missing", "is missing"]]
        : [["eq", "="], ["neq", "≠"], ["present", "is present"], ["missing", "is missing"]];
    for (const [value, label] of operators) addOption(row._operator, value, label);
    row._operator.disabled = !path;
    configureValue(row, kind);
  }

  function configureValue(row, kind) {
    const oldValue = row._value ? row._value.value : "";
    const operator = row._operator.value;
    let control;
    if (kind === "boolean") {
      control = document.createElement("select");
      addOption(control, "true", "true");
      addOption(control, "false", "false");
    } else {
      control = document.createElement("input");
      control.type = kind === "number" ? "number" : "text";
      if (kind === "number") control.step = "any";
      if (kind === "null") control.value = "null";
      else control.value = oldValue;
    }
    control.dataset.kind = kind;
    control.setAttribute("aria-label", "Filter value");
    control.disabled = !row._key.value || kind === "null" || operator === "present" || operator === "missing";
    if (!control.disabled) control.placeholder = "Value";
    control.addEventListener("input", () => renderResults(true));
    control.addEventListener("change", () => renderResults(true));
    row._valueCell.replaceChildren(control);
    row._value = control;
  }

  function addFilterRow() {
    const row = document.createElement("div");
    row.className = "filter-row";
    const key = document.createElement("select");
    key.setAttribute("aria-label", "Parameter");
    addOption(key, "", "Choose parameter…");
    for (const path of parameterPaths) addOption(key, path, parameterLabel(path));
    const operator = document.createElement("select");
    operator.setAttribute("aria-label", "Operator");
    const valueCell = document.createElement("span");
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "remove-filter";
    remove.textContent = "Remove";
    row._key = key;
    row._operator = operator;
    row._valueCell = valueCell;
    key.addEventListener("change", () => { configureFilterRow(row); renderResults(true); });
    operator.addEventListener("change", () => { configureValue(row, row._value.dataset.kind); renderResults(true); });
    remove.addEventListener("click", () => { row.remove(); renderResults(true); });
    row.append(key, operator, valueCell, remove);
    filterList.append(row);
    configureFilterRow(row);
    key.focus();
  }

  function activeFilters() {
    const filters = [];
    for (const row of filterList.children) {
      const path = row._key.value;
      const operator = row._operator.value;
      const kind = row._value.dataset.kind;
      const rawValue = row._value.value;
      if (!path) continue;
      if (!['present', 'missing'].includes(operator) && kind !== "null" && rawValue === "") continue;
      let value = rawValue;
      if (kind === "number") value = Number(rawValue);
      if (kind === "boolean") value = rawValue === "true";
      if (kind === "null") value = null;
      filters.push({path, operator, kind, value});
    }
    return filters;
  }

  function matchesParameter(run, filter) {
    const present = Object.hasOwn(run.parameters, filter.path);
    if (filter.operator === "present") return present;
    if (filter.operator === "missing") return !present;
    if (!present) return false;
    const actual = run.parameters[filter.path];
    if (filter.operator === "eq") return filter.kind === "string" ? String(actual) === filter.value : actual === filter.value;
    if (filter.operator === "neq") return filter.kind === "string" ? String(actual) !== filter.value : actual !== filter.value;
    if (filter.operator === "contains") return String(actual).toLocaleLowerCase().includes(String(filter.value).toLocaleLowerCase());
    if (typeof actual !== "number") return false;
    if (filter.operator === "gt") return actual > filter.value;
    if (filter.operator === "gte") return actual >= filter.value;
    if (filter.operator === "lt") return actual < filter.value;
    if (filter.operator === "lte") return actual <= filter.value;
    return false;
  }

  function appendCell(row, text) {
    const cell = document.createElement("td");
    cell.textContent = text;
    row.append(cell);
    return cell;
  }

  function parameterTable(run) {
    const table = document.createElement("table");
    table.className = "parameter-table";
    const body = document.createElement("tbody");
    for (const [name, value] of Object.entries(run.parameters)) {
      const row = document.createElement("tr");
      appendCell(row, name);
      appendCell(row, displayValue(value));
      body.append(row);
    }
    table.append(body);
    return table;
  }

  function renderResults(resetPage = true) {
    if (resetPage) page = 1;
    const filters = activeFilters();
    filteredRuns = selectedRuns.filter(run => filters.every(filter => matchesParameter(run, filter)));
    const pageCount = Math.max(1, Math.ceil(filteredRuns.length / pageSize));
    page = Math.min(page, pageCount);
    const start = (page - 1) * pageSize;
    resultsBody.replaceChildren();
    for (const run of filteredRuns.slice(start, start + pageSize)) {
      const row = document.createElement("tr");
      const runCell = document.createElement("td");
      const link = document.createElement("a");
      link.className = "run-link";
      link.href = run.summary_href;
      link.textContent = run.run_id;
      runCell.append(link);
      row.append(runCell);
      appendCell(row, run.started_at || "—");
      const commitCell = appendCell(row, run.git_commit || "—");
      commitCell.className = "commit";
      appendCell(row, run.runtime_seconds === null ? "—" : `${run.runtime_seconds} s`);
      const actionCell = document.createElement("td");
      const show = document.createElement("button");
      show.type = "button";
      show.textContent = "Show";
      show.setAttribute("aria-expanded", "false");
      actionCell.append(show);
      row.append(actionCell);
      const details = document.createElement("tr");
      details.className = "details-row";
      details.hidden = true;
      const detailsCell = document.createElement("td");
      detailsCell.colSpan = 5;
      const panel = document.createElement("div");
      panel.className = "details-panel";
      panel.append(parameterTable(run));
      detailsCell.append(panel);
      details.append(detailsCell);
      show.addEventListener("click", () => {
        details.hidden = !details.hidden;
        show.textContent = details.hidden ? "Show" : "Hide";
        show.setAttribute("aria-expanded", String(!details.hidden));
      });
      resultsBody.append(row, details);
    }
    resultCount.textContent = `${filteredRuns.length} run${filteredRuns.length === 1 ? "" : "s"}`;
    tableWrap.hidden = filteredRuns.length === 0;
    emptyResults.hidden = filteredRuns.length !== 0;
    pagination.hidden = filteredRuns.length <= pageSize;
    pageStatus.textContent = filteredRuns.length ? `${start + 1}–${Math.min(start + pageSize, filteredRuns.length)} of ${filteredRuns.length}` : "";
    previousPage.disabled = page === 1;
    nextPage.disabled = page === pageCount;
  }

  function selectType() {
    selectedRuns = runs.filter(run => run.workflow_type === typeSelect.value);
    parameterPaths = [...new Set(selectedRuns.flatMap(run => Object.keys(run.parameters)))].sort((a, b) => a.localeCompare(b));
    filterList.replaceChildren();
    typeCount.textContent = `${selectedRuns.length} run${selectedRuns.length === 1 ? "" : "s"}`;
    document.getElementById("add-filter").disabled = parameterPaths.length === 0;
    renderResults(true);
  }

  typeSelect.addEventListener("change", selectType);
  document.getElementById("add-filter").addEventListener("click", addFilterRow);
  document.getElementById("reset-filters").addEventListener("click", () => { filterList.replaceChildren(); renderResults(true); });
  previousPage.addEventListener("click", () => { page -= 1; renderResults(false); });
  nextPage.addEventListener("click", () => { page += 1; renderResults(false); });
  selectType();
})();
</script></main></body></html>
"""
    return document.replace("__PROJECT_NAME__", html.escape(project_name)).replace(
        "__RUN_DATA__", _embedded_json(records)
    )


def synchronize_catalog(
    project_root: Path,
    runs_dir: Path,
    *,
    warn: bool = False,
) -> CatalogSyncResult:
    """Synchronize new run folders into SQLite and rebuild the static index."""
    project_root = project_root.resolve()
    runs_dir = runs_dir.resolve()
    runs_dir.mkdir(parents=True, exist_ok=True)
    database_path = runs_dir / CATALOG_FILENAME
    connection = sqlite3.connect(database_path, timeout=30.0)
    connection.execute("PRAGMA busy_timeout = 30000")
    added = 0
    removed = 0
    skipped = 0
    try:
        connection.execute("BEGIN IMMEDIATE")
        _initialize_schema(connection)
        run_directories = {path.name: path for path in runs_dir.iterdir() if path.is_dir()}
        known_ids = {row[0] for row in connection.execute("SELECT run_id FROM runs")}
        folder_ids = set(run_directories)

        stale_ids = known_ids - folder_ids
        if stale_ids:
            connection.executemany("DELETE FROM runs WHERE run_id = ?", ((run_id,) for run_id in stale_ids))
            removed = len(stale_ids)

        for run_id in sorted(folder_ids - known_ids):
            record, problem = _read_run_record(run_directories[run_id])
            if problem is not None:
                skipped += 1
                if warn:
                    print(f"warning: catalog skipping {run_id}: {problem}", file=sys.stderr)
                continue
            connection.execute(
                """
                INSERT INTO runs (
                    run_id, git_commit, workflow_type, started_at, runtime_seconds, parameters_json
                ) VALUES (
                    :run_id, :git_commit, :workflow_type, :started_at, :runtime_seconds, :parameters_json
                )
                """,
                record,
            )
            added += 1

        records = _database_records(connection)
        index_path = runs_dir / INDEX_FILENAME
        _write_text(index_path, _render_index(project_root.name, records))
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()

    return CatalogSyncResult(index_path=index_path, added=added, removed=removed, skipped=skipped)
