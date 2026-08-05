# Labframe

Labframe is a small command-line tool for creating and running independent simulation or experiment projects. It keeps configuration, source provenance, numerical results, figures, logs, and summaries together without turning the Labframe repository itself into a data repository.

## Install

From this checkout:

```bash
uv tool install --editable .
labframe --version
```

For development, use the repository environment instead:

```bash
uv sync
uv run labframe --version
```

## Create a project

```bash
labframe init ../my-experiment
cd ../my-experiment
```

By default, `labframe init` copies the bundled starter, runs `uv sync`, initializes Git, and creates an initial commit. Use `--no-sync` or `--no-git` when those steps should be handled separately.

The generated project is self-contained:

```text
my-experiment/
├── configs/
│   ├── default.yaml
│   └── smoke.yaml
├── runs/
├── build_summary.py
├── fit_models.py
├── plot_results.py
├── simulation.py
├── .gitignore
├── pyproject.toml
├── uv.lock
└── README.md
```

When Labframe is run from a source checkout, the generated `pyproject.toml` includes an editable uv source pointing back to that checkout.

## Run a project

Always select a configuration explicitly:

```bash
labframe run configs/smoke.yaml
```

Calling `labframe run` without a path selects `configs/default.yaml`. Automated validation should instead use the small smoke configuration and avoid creating a source commit:

```bash
labframe run --no-commit configs/smoke.yaml
```

`--no-commit` requires a clean generated-project working tree. Normal commit mode captures the source tree at launch, runs from that snapshot, and creates a source commit after a successful run when the launch tree differs from `HEAD`. Use `--yes` to approve dirty launch source in a non-interactive shell.

The pipeline is:

```text
config -> simulation or acquisition (including fitting) -> saved results -> figures -> summaries
```

Each invocation creates `runs/<timestamp>_<config-hash>/` containing:

```text
config.yaml
meta.json
output.log
results/
figures/
summary.md
summary.html
```

Generated run folders are ignored by the generated project's Git repository. `meta.json` records status, runtime, start time, and the exact source commit associated with a completed run.

## Customize the generated project

The hook paths are configured under `[tool.labframe]` in the generated `pyproject.toml`:

- The simulation hook receives the parsed configuration and a `results/` path. It must write all numerical results there; fitting belongs in this stage and must consume saved results.
- The plotting hook receives the run path, reads `results/`, and writes figures to `figures/`.
- The summary hook receives the run path and builds reports only from saved configuration, metadata, logs, results, and figures.

The bundled starter demonstrates these contracts with a QuTiP Rabi-flop simulation and an explicit lmfit fit.

## Development checks

```bash
uv run python -m unittest discover -s tests
uv run ruff check labframe tests
uv build
```
