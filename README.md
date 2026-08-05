# Labframe

Labframe initializes and runs small, independent simulation or experiment repositories. A local layout can be:

```text
projects/
├── labframe/
├── caoh-simulation/
└── microwave-experiment/
```

## Install locally

From `projects/`:

```bash
uv tool install --editable ./labframe
labframe --version
```

For development without installing the command globally:

```bash
uv run --project labframe labframe --version
```

## Initialize a project

```bash
labframe init caoh-simulation
```

This creates and syncs a uv project, initializes Git, and makes the initial commit. The generated project is deliberately small:

```text
caoh-simulation/
├── simulation.py
├── fit_models.py
├── plot_results.py
├── build_summary.py
├── configs/
│   ├── default.yaml
│   └── smoke.yaml
├── runs/
├── pyproject.toml
├── uv.lock
└── README.md
```

The local uv source in the generated `pyproject.toml` points to the sibling Labframe checkout.

## Run the smoke configuration

```bash
cd caoh-simulation
uv run labframe run --no-commit configs/smoke.yaml
```

Labframe runs these stages:

```text
configuration -> simulation/acquisition with its fit -> saved results -> combined figure -> summary.md + summary.html
```

The generated `simulation.py` dispatches on `simulation.type`; the included `rabi_flop` function is a QuTiP two-level simulation and directly calls `fit_rabi_flop` after saving its result. The fitting function reads the saved NPZ, constructs every lmfit parameter with `value`, `min`, `max`, and `vary` rather than calling `guess()`, evaluates the model on a separate dense time grid, and saves its own NPZ. `fit_models.py` defines a reusable sine-plus-offset model from lmfit's `SineModel` and `ConstantModel`, alongside linear, Gaussian, exponential, and power-law models. `plot_results.py` verifies compatible x/y names and valid per-file shapes before plotting differently sampled results in one figure.

Each run is saved under `runs/<timestamp>_<config-hash>/`. `--no-commit` requires a clean working tree and records the current `HEAD` in `meta.json`. Plain `labframe run` selects `configs/default.yaml`, so automated validation must always pass `configs/smoke.yaml` explicitly.

## Development checks

```bash
uv run python -m unittest discover -s tests
uv run ruff check labframe tests
```
