# Labframe

Labframe is a command-line tool for creating and running independent simulation or experiment projects. Each project keeps its configuration, source provenance, numerical results, figures, logs, and summaries together.

## 1. Install uv and Labframe

[Install uv](https://docs.astral.sh/uv/getting-started/installation/) on your workstation first. On macOS or Linux, the official standalone installer is:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Then confirm that it is available:

```bash
uv --version
```

Then install Labframe from this source checkout. The editable installation makes the `labframe` command available while keeping it connected to the local source code:

```bash
uv tool install --editable /path/to/labframe
labframe --version
```

Replace `/path/to/labframe` with the path to this repository.

## 2. Create a project

Create a new, independent project anywhere on your filesystem:

```bash
labframe init /path/to/my-experiment
cd /path/to/my-experiment
```

### What `labframe init` does

By default, `labframe init /path/to/my-experiment`:

- creates `/path/to/my-experiment`; it stops if that directory already contains files;
- derives the project name from the directory name, normalizes it, and writes it into the generated files;
- copies the complete starter project, including configurations and working simulation, fitting, plotting, and summary hooks;
- writes a standalone `pyproject.toml` and connects it to the editable Labframe source checkout when Labframe is run from that checkout;
- runs `uv sync`, which creates the project environment, resolves its dependencies, and writes `uv.lock`;
- runs `git init`, stages the generated files, and creates the initial commit named `Initialize Labframe project`.

The initializer accepts these options:

| Option | Meaning |
|---|---|
| `directory` | Required path of the new project. The directory must be absent or empty. |
| `--name NAME` | Use `NAME` in generated files instead of deriving the name from the directory. |
| `--no-venv` | Use a containing project's environment. This omits the standalone `pyproject.toml`, does not invoke uv, and creates neither `.venv` nor `uv.lock`. |
| `--no-sync` | Write the standalone `pyproject.toml` but do not invoke uv. Dependency resolution and environment creation can be performed later with `uv sync`. |
| `--no-git` | Do not create an independent Git repository or initial commit. Use this only when the generated project is inside an existing Git repository with at least one commit. |
| `-h`, `--help` | Show the `init` command help. |

`--no-venv` and `--no-sync` are mutually exclusive. Use `--no-venv` for a simulation nested inside an existing uv project; the containing project's `pyproject.toml`, `uv.lock`, and `.venv` own its dependencies. Use `--no-sync` for a standalone project whose first uv synchronization should be deferred, such as during offline scaffolding.

### Git repository requirement

Every generated project must resolve to a Git repository with an existing `HEAD` commit before `labframe run` can start. Choose one of these arrangements:

- Let the default `labframe init` create an independent repository and initial commit inside the generated project.
- Use `labframe init --no-git` only when the generated project is nested inside an existing containing repository that already has a commit.

`--no-git` skips creation of the independent repository; it does not enable Git-free runs. When Labframe finds a containing repository, default commit mode records changed launch source in that repository and advances its current branch after a successful run. Even `labframe run --no-commit` requires the resolved repository to have an existing `HEAD` commit.

For a simulation inside an existing project and Git repository:

```bash
cd /path/to/my-project
labframe init --no-venv --no-git my-simulation
uv run labframe run --project my-simulation configs/smoke.yaml
```

The containing project must declare `labframe` and the dependencies imported by the simulation. Running `uv run` from the containing project uses its environment; no environment is created inside `my-simulation`.

### Generated project files

```text
my-experiment/
├── .git/
├── .venv/
├── configs/
│   ├── default.yaml
│   └── smoke.yaml
├── runs/
│   └── .gitkeep
├── build_summary.py
├── fit_models.py
├── plot_results.py
├── simulation.py
├── .gitignore
├── pyproject.toml
├── uv.lock
└── README.md
```

| File or directory | Purpose |
|---|---|
| `.git/` | Independent Git repository created by `labframe init`. With `--no-git`, it is absent and a containing repository must provide source history instead. |
| `.venv/` | Project-specific Python environment created by `uv sync`. It is absent with `--no-venv`, which uses the containing project's environment, and initially absent with `--no-sync`. |
| `configs/default.yaml` | Normal project configuration. `labframe run` selects this file when no configuration is given. |
| `configs/smoke.yaml` | Small, fast configuration for validating the complete workflow. |
| `runs/` | Contains one immutable artifact directory per run. Generated contents are ignored by Git. |
| `runs/.gitkeep` | Keeps the initially empty `runs/` directory in Git. |
| `simulation.py` | Reads the selected configuration, runs the simulation or acquisition, writes numerical data to `results/`, and performs fitting examples. |
| `fit_models.py` | Defines reusable lmfit model objects imported by `simulation.py`. Parameter values, bounds, and `vary` settings stay in `simulation.py`. |
| `plot_results.py` | Reads saved data from `results/` and writes Matplotlib figures to `figures/`. It is the single place for Matplotlib presentation settings. |
| `build_summary.py` | Builds `summary.md` and `summary.html` from the saved configuration, metadata, log, results, and figures. |
| `.gitignore` | Excludes the project environment, Python build files, and generated run contents from Git. |
| `pyproject.toml` | Declares dependencies and the Labframe source for a standalone project. It is omitted by `--no-venv`. |
| `uv.lock` | Records the exact dependency resolution produced by `uv sync`. It is omitted by `--no-venv` and initially absent with `--no-sync`. |
| `README.md` | Gives project-local instructions for running and customizing the generated starter. |

The bundled starter is a complete Rabi-flop example: QuTiP generates numerical data, lmfit fits the saved data, Matplotlib creates a figure, and the summary hook writes Markdown and HTML reports.

## 3. Run the project

Before running, confirm that the generated project has either its own repository created by `labframe init` or a containing repository, and that the selected repository has at least one commit. Labframe uses that repository for source provenance in both commit and `--no-commit` modes.

From the generated project directory, the normal command is:

```bash
uv run labframe run
```

This uses `configs/default.yaml` and commit mode. Labframe finds the project root, captures the source state at launch, and runs the following pipeline:

```text
configuration -> simulation or acquisition and fitting -> saved results -> figures -> summaries
```

Fitting, plotting, and summary generation use saved artifacts; they do not rerun the simulation or experiment.

### `labframe run` arguments and options

| Argument or option | Meaning |
|---|---|
| `config` | Optional configuration path relative to the project root. The default is `configs/default.yaml`. The file must be inside the project. |
| `--project PATH` | Use `PATH` as the project root. Without it, Labframe searches upward for the conventional simulation, plotting, and summary hook files. |
| `--commit` | Use commit mode. This is the default. The run uses the source state captured at launch and commits changed launch source only after a successful run. |
| `--no-commit` | Run directly from the working tree without creating a source commit. This requires a clean working tree. |
| `--message TEXT` | Use `TEXT` as the commit message if commit mode needs to commit changed launch source. The default is `labframe run: <config-name>`. |
| `--yes` | In commit mode, approve capturing dirty source without an interactive confirmation. This is useful in a non-interactive shell. |
| `-h`, `--help` | Show the `run` command help. |

`--message` and `--yes` apply only to commit mode and cannot be combined with `--no-commit`.

Common invocations are:

```bash
# Run the default configuration in the current project.
uv run labframe run

# Run a specific configuration.
uv run labframe run configs/my-run.yaml

# Validate the complete pipeline with the small smoke configuration.
uv run labframe run configs/smoke.yaml

# Run the smoke configuration without committing; the working tree must be clean.
uv run labframe run --no-commit configs/smoke.yaml

# Run a project while currently outside its directory.
uv run labframe run --project /path/to/my-experiment configs/my-run.yaml

# Choose the source commit message and approve dirty launch source non-interactively.
uv run labframe run --message "Run calibrated scan" --yes configs/my-run.yaml
```

Do not edit a completed run directory. In commit mode, Labframe runs from the captured launch source, advances the branch only after success, and records that source commit in the run metadata. If the run fails, it does not commit or advance the branch.

### Run output

Every invocation creates `runs/<timestamp>_<config-hash>/`:

```text
runs/<timestamp>_<config-hash>/
├── results/
├── figures/
├── config.yaml
├── meta.json
├── output.log
├── summary.md
└── summary.html
```

| File or directory | Purpose |
|---|---|
| `results/` | Numerical simulation, acquisition, and fitting results written by `simulation.py`. |
| `figures/` | Plots created from the saved results by `plot_results.py`. |
| `config.yaml` | Exact configuration used for this run. |
| `meta.json` | Run status, start time, runtime, and source commit. |
| `output.log` | Standard output and error captured from the simulation and plotting stages. |
| `summary.md` | Markdown report built from the saved artifacts. |
| `summary.html` | Standalone HTML version of the run report. |

## 4. Customize a generated project

Labframe uses three conventional hook locations:

| Stage | Hook |
|---|---|
| Simulation, acquisition, and fitting | `simulation.py:run_simulation` |
| Plotting | `plot_results.py:plot_results` |
| Summary generation | `build_summary.py:build_summary` |

The hook contracts are:

- The simulation or acquisition hook receives the parsed configuration and the run's `results/` path. It writes all numerical output there. Fitting belongs in this stage and consumes saved results.
- The plotting hook receives the run path, reads `results/`, and writes figures into `figures/`.
- The summary hook receives the run path and builds reports only from saved configuration, metadata, logs, results, and figures.

## Development checks

When working on Labframe itself:

```bash
uv sync
uv run python -m unittest discover -s tests
uv run ruff check labframe tests
uv build
```
