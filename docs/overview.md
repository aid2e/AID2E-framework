# AID2E Framework

AI assisted Detector Design for EIC (AID2E) is a Python framework for
configuring and running detector design optimization workflows. It provides
typed configuration models, optimizer and scheduler integrations, workflow
execution, a command-line interface, and ePIC-specific utilities.

## Getting Started

- [Installation](getting-started/installation.md): Install AID2E and optional dependencies.
- [Quick Start](getting-started/quick-start.md): Validate and run the DTLZ2 example.

## User Guide

- [Configuration](user-guide/configuration.md): Define problems, design spaces, optimizers, schedulers, and workflows.
- [Workflows](user-guide/workflows.md): Execute stages, jobs, stack layers, and objective plans.
- [Optimizers](user-guide/optimizers.md): Configure Ax and PyMOO.
- [Schedulers](user-guide/schedulers.md): Configure JobLib, Slurm, and PanDA/iDDS.
- [CLI](user-guide/cli.md): Inspect configurations and run optimization workflows.

## Developer Guide

### Development Workflow

#### Setting Up for Development

```bash
# Clone the repository
git clone https://github.com/aid2e/AID2E-framework.git
cd AID2E-framework

# Create a virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install with all development tools
pip install -e ".[dev,docs]"
```

#### Running Tests

- Tests: pytest -v

```bash
# Run all tests
pytest tests/

# Run with verbose output
pytest tests/ -v

# Run with coverage report
pytest tests/ --cov=src/aid2e --cov-report=html

# Run specific test file
pytest tests/test_cli/test_cli.py
```

#### Code Quality

- Lint/format/type: black ., flake8, mypy (install extras with pip install -e ".[dev]")

```bash
# Format code with black
black src/ tests/

# Check code style with flake8
flake8 src/ tests/

# Sort imports with isort
isort src/ tests/

# Type checking with mypy
mypy src/
```

#### Making Changes

- Prefer adding tests alongside changes.
- Keep imports under the aid2e namespace (aid2e.cli, aid2e.utilities.configurations, etc.).
- Update docs and fixtures when changing configuration schemas.

1. **Create a branch** for your changes:
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make changes** to files in `src/aid2e/`

3. **Write tests** in the corresponding `tests/` directory

4. **Run tests** to ensure everything works:
   ```bash
   pytest tests/ -v
   ```

5. **Format and lint** your code:
   ```bash
   black src/ tests/
   isort src/ tests/
   flake8 src/ tests/
   ```

6. **Commit and push**:
   ```bash
   git add .
   git commit -m "Description of changes"
   git push origin feature/your-feature-name
   ```

7. **Open a Pull Request** on GitHub

### CLI Design Principles

The CLI follows these design principles:

1. **Auto-detection**: Commands should detect config type automatically
2. **Consistency**: Similar output formats across commands
3. **Composability**: Output formats (JSON/YAML) for scripting
4. **Clear errors**: Specific, actionable error messages
5. **Progressive disclosure**: Compact by default, detailed on demand
6. **Exit codes**: 0 for success, 1 for failure (script-friendly)

### Documentation

#### Building and Previewing

- Python 3.11+
- MkDocs tooling (install via project extras):

```bash
pip install -e ".[docs]"
```

- Built site output: `site/` (created on build)

Build or serve the documentation directly with MkDocs:

```bash
# Build static site
mkdocs build

# Serve documentation locally (with live reload)
mkdocs serve
```

The repository also provides documentation scripts:

```bash
# Build static site into site/
./scripts/docs-build.sh

# Preview locally (live-reload on changes)
./scripts/docs-serve.sh
```

The documentation will be available at `http://localhost:8000/`

#### Writing Documentation

MkDocs site sources are under docs/ (Material theme). The navigation is defined in mkdocs.yml.

- MkDocs config: `mkdocs.yml` (repo root)
- Markdown sources: `docs/` (this directory)
- Add new pages under `docs/` as `.md` files.
- Update navigation in `mkdocs.yml` under the `nav:` section.
- Use Markdown and admonitions (notes, tips) supported by Material theme.

#### API Reference

MkDocs is configured to use `mkdocstrings` for Python API docs. Ensure modules are importable from `src`.

- Package source: `src/aid2e/`

#### Deployment

Pushes to `main` and manual workflow runs deploy the documentation through
`.github/workflows/docs-deploy.yml`.

For manual deployment with MkDocs:

```bash
./scripts/docs-deploy-ghpages.sh
```

GitHub Pages must be enabled in the repository settings to deploy with
`gh-deploy`.

#### Troubleshooting

- If `mkdocs` is not found, install docs extras: `pip install -e ".[docs]"`.
- If API pages fail to render, verify import paths in `mkdocs.yml` and that the package is installed in editable mode: `pip install -e .`.

### Project Layout

```text
AID2E-framework/
|-- src/aid2e/
|   |-- utilities/
|   |   |-- configurations/
|   |   |   |-- base_models.py             BaseParameter, RangeParameter, ChoiceParameter
|   |   |   |-- design_config.py           DesignConfig, DesignParameters, ParameterConstraint
|   |   |   |-- problem_config.py          ProblemConfiguration
|   |   |   |-- optimizer_config.py        OptimizerConfiguration
|   |   |   |-- objectives.py              ObjectiveDirection, ObjectivePlanSpec, ObjectiveDefinition
|   |   |   |-- scheduler_config.py         SchedulerConfiguration
|   |   |   |-- scheduler_cascade.py        Scheduler resolution by workflow scope
|   |   |   |-- workflow_config.py          WorkflowDefinition, BranchDefinition, StageDefinition, JobDefinition
|   |   |   |-- stack_registry.py           StackRegistry
|   |   |   `-- full_config.py              FullConfig
|   |   |-- workflows/
|   |   |   |-- dag_types.py                DagDefinition, DagNode, DagEdge, DagValidator
|   |   |   |                                  topological_sort(), detect_cycles()
|   |   |   |-- dag_executor.py             DAGExecutor
|   |   |   `-- execution_engine.py         Bash, Python, container, and stack execution engines
|   |   |-- epic_utils/
|   |   `-- runtime_builders.py             Runtime construction and optimization orchestration
|   |-- schedulers/
|   |   |-- base.py                         BaseScheduler
|   |   |-- JobLib/                         JobLibScheduler
|   |   |-- Slurm/                          SlurmScheduler
|   |   `-- PanDAiDDS/                      PanDAiDDSScheduler
|   |-- optimizers/
|   |   |-- base.py                         BaseOptimizer
|   |   |-- ax/                             AxOptimizer
|   |   `-- pymoo/                          PyMOOOptimizer
|   `-- cli/
|       |-- aid2e_cli.py
|       |-- config_commands.py
|       |-- workflow_commands.py
|       `-- utility_commands.py
|-- examples/
|-- tests/
|-- docs/
|-- scripts/
|-- .github/workflows/
|-- pyproject.toml
|-- mkdocs.yml
`-- pytest.ini
```
