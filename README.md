# Cat-state simulation

`cat-state-simulation` is a configuration-driven project for cat-state simulations. Its smoke test uses QuTiP to simulate an ideal, coherently driven two-level system, while the default configuration selects the in-progress cat-generation model.

## Setup

Install the Python environment and activate it:

```bash
uv sync
source .venv/bin/activate
```

Jinja2 is installed with the project. No separate site generator or web server is required.

## Running simulations

With the environment activated:

```bash
run configs/smoke.yaml
run

run --no-commit configs/smoke.yaml
run --message "Add motional heating model" configs/another-scan.yaml
```

Without activating the environment:

```bash
uv run run configs/smoke.yaml
uv run run
uv run run --no-commit configs/smoke.yaml
```

The `run` command performs the complete workflow: it loads a YAML configuration, runs the simulation, saves numerical results, generates figures from those saved results, builds `summary.md`, renders `summary.html` with Jinja2, and rebuilds the root `index.html`.

Do not run `run` without arguments during automated validation because it selects `configs/default.yaml`. Use `configs/smoke.yaml` for quick validation.

### Smoke simulation

The smoke configuration starts the qubit in $|0\rangle$ and evolves it under

$$
H = \frac{\hbar}{2}\left(\Omega \sigma_x + \Delta \sigma_z\right).
$$

It saves the excited-state probability as a function of time. At zero detuning, the expected result is $P_1(t) = \sin^2(\Omega t / 2)$. This is intentionally small and fast, but it exercises a real QuTiP solver and the same saved-results, plotting, and summary pipeline as the main simulation.

## Source provenance

Commit mode is enabled by default. `run` snapshots tracked changes and untracked project files without touching the real Git index, runs from that snapshot, and advances the branch only after the complete workflow succeeds. If the launch snapshot contains project changes, pass `--yes` to skip the interactive confirmation. Use `--no-commit` for a clean working tree when the run must not create a commit; it refuses a dirty tree because that state would not have exact Git provenance.

The run metadata records the exact source commit used for the simulation. Trackable generated artifacts are saved in a following run commit, so a clean launch creates one commit while a launch with source changes creates a source commit followed by the run commit. Numerical `.npz` files remain ignored. Edits made in the project after launch remain uncommitted and are not added to either commit. The command never pushes or rewrites history.

## Outputs

Each invocation creates an immutable folder under `runs/` containing the selected configuration, metadata, numerical results, figures, captured console `output`, and per-run Markdown and HTML summaries. Standard output and standard error from simulation and plotting are shown live and saved to `output`, so fit reports and diagnostics appear in the summary's Output section. The root `index.html` links to every run folder that contains `summary.html`; open it directly in a browser to browse completed runs. Numerical `.npz` files are ignored by Git.

Each `.npz` result file must contain exactly two one-dimensional arrays: the horizontal coordinate followed by the dependent value. A run with one result file produces a figure named after that file. A run with several result files overlays all datasets in `combined_results.png`; each legend label is the complete `.npz` filename.

The root `reports/` directory is reserved for later reports that compare or combine several completed runs. Individual run summaries do not belong there.

## Fitting models

`fit_models.py` exports ready-to-use lmfit models for sine, linear, Gaussian, exponential, and power-law fits:

```python
from fit_models import gaussian_model, sine_model

sine_parameters = sine_model.guess(y_values, x=x_values)
sine_fit = sine_model.fit(y_values, sine_parameters, x=x_values)

gaussian_parameters = gaussian_model.guess(histogram, x=bin_centers)
gaussian_fit = gaussian_model.fit(histogram, gaussian_parameters, x=bin_centers)
```

The sine model is $y = c + A\sin(2\pi f x + \phi)$, where `frequency` is measured in cycles per unit of $x$. The other models use lmfit's standard parameterizations: `slope` and `intercept` for linear, area `amplitude`, `center`, and `sigma` for Gaussian, `amplitude` and decay `decay` for exponential, and `amplitude` and `exponent` for power law.

## Extending the simulation

The smoke simulation is selected by `simulation.type: rabi_oscillation`. The default configuration uses `simulation.type: cat_generation`; extend that simulation and its saved output schema as the scientific scope develops. The root run index groups completed runs by this type. Existing run folders that used the former `simulation.model` key remain readable.
