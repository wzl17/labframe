# Labframe

Labframe is a small, installable command-line tool for reproducible simulation and experiment projects. It initializes an independent Git/uv repository containing editable files for simulation or acquisition, fitting, plotting, summarizing, and configuration. It then orchestrates those files into immutable run folders.

With sibling repositories, the intended local layout is:

```text
projects/
├── labframe/
├── caoh-simulation/
└── microwave-experiment/
```

## Install or run locally with uv

From the directory containing `labframe/`:

```bash
uv tool install --editable ./labframe
labframe --version
```

For development without a tool installation:

```bash
uv run --project labframe labframe --version
```

## Initialize a project

From the common parent directory:

```bash
labframe init caoh-simulation
```

Or, without installing the command globally:

```bash
uv run --project labframe labframe init caoh-simulation
```

Initialization copies the bundled project template, adds an editable uv source pointing back to the local sibling `labframe` checkout, runs `uv sync`, initializes Git, and creates the initial commit. The generated repository contains:

```text
caoh-simulation/
├── simulation.py
├── fit_results.py
├── plot_results.py
├── plot_style.py
├── build_summary.py
├── labframe.yaml
├── configs/
│   ├── default.yaml
│   └── smoke.yaml
├── tests/
├── runs/
├── reports/
├── pyproject.toml
└── uv.lock
```

Use `--no-sync` to create files without resolving the uv environment, or `--no-git` when another tool owns repository initialization.

## Run a project

Inside a generated project:

```bash
uv run labframe run --no-commit configs/smoke.yaml
```

Labframe executes:

```text
configuration
    -> simulation or experiment acquisition
    -> saved numerical data
    -> saved fit products
    -> figures
    -> summary.md and summary.html
```

Each invocation creates `runs/<timestamp>_<config-hash>/` with the copied configuration, `meta.json`, captured output, `results/`, `figures/`, and summaries. Plotting and summary hooks operate only on saved artifacts and never rerun acquisition.

Commit mode is enabled by default. For a run that must not create commits, use `--no-commit` with a clean project working tree. Automated validation must use `configs/smoke.yaml`; plain `labframe run` selects `configs/default.yaml`.

## Bundled Rabi example

The generated template contains a deterministic noisy Rabi simulation and a SciPy fit that recovers the oscillation frequency, contrast, offset, uncertainty, and RMSE. It is a working example for validation, not project-specific experimental physics. Replace the hook implementations while keeping their function contracts.

Run the Labframe package tests with:

```bash
uv run python -m unittest discover -s tests
```
