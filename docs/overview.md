# AID2E Framework

AI assisted Detector Design for EIC (AID2E) is a Python framework for
configuring and running detector design optimization workflows. It provides
typed configuration models, optimizer and scheduler integrations, workflow
execution, a command-line interface, and ePIC-specific utilities.

## Start Here

- [Installation](getting-started/installation.md): Install AID2E and optional dependencies.
- [Quick Start](getting-started/quick-start.md): Validate and run the DTLZ2 example.

## User Guide

- [Configuration](user-guide/configuration.md): Define problems, design spaces, optimizers, schedulers, and workflows.
- [Workflows](user-guide/workflows.md): Execute stages, jobs, stack layers, and objective plans.
- [Optimizers](user-guide/optimizers.md): Configure Ax and PyMOO.
- [Schedulers](user-guide/schedulers.md): Configure JobLib, Slurm, and PanDA/iDDS.
- [CLI](user-guide/cli.md): Inspect configurations and run optimization workflows.

## How Optimization Runs

When a user runs `aid2e optimize`, the framework:

1. Loads and validates the full configuration.
2. Builds the configured optimizer and schedulers.
3. Requests a batch of candidate design points from the optimizer.
4. Executes one configured workflow for each candidate.
5. Collects the objective values and updates the optimizer.
6. Saves the run results and requests another batch until the configured
   evaluation budget is complete.

## Contributing

### Development Setup

Follow the [installation guide](getting-started/installation.md), then install
the development and documentation tools:

```bash
python -m pip install -e ".[dev,docs]"
```

### Contribution Workflow

1. **Create a branch** for your changes:
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make changes** in `src/aid2e/`. Keep imports under the `aid2e` namespace.

3. **Add tests** in the corresponding `tests/` directory. Update documentation
   and fixtures when changing configuration schemas.

4. **Run tests**:
   ```bash
   # Run all tests
   pytest tests/

   # Run with coverage
   pytest tests/ --cov=src/aid2e --cov-report=html

   # Run a specific test file
   pytest tests/test_cli/test_cli.py
   ```

   Example fixtures live in `tests/test_utilities/fixtures/dtlz2/`
   (`design.params`, `problem.config`).

5. **Format and lint** the code:
   ```bash
   black src/ tests/
   isort src/ tests/
   flake8 src/ tests/
   mypy src/
   ```

6. **Commit and push**:
   ```bash
   git add .
   git commit -m "Description of changes"
   git push origin feature/your-feature-name
   ```

7. **Open a pull request** on GitHub.

**CLI design principles**

The CLI follows these design principles:

1. **Auto-detection**: Commands should detect config type automatically.
2. **Consistency**: Similar output formats across commands.
3. **Composability**: JSON and YAML output formats for scripting.
4. **Clear errors**: Specific, actionable error messages.
5. **Progressive disclosure**: Compact by default, detailed on demand.
6. **Exit codes**: `0` for success, `1` for command failures, and `2` for
   invalid CLI usage.

### Maintaining Documentation

**Build and preview**

The repository provides scripts to build or preview the documentation:

```bash
# Build the static site into site/
./scripts/docs-build.sh

# Preview locally with live reload
./scripts/docs-serve.sh
```

When previewing, the documentation is available at `http://localhost:8000/`.

**Writing and API documentation**

MkDocs site sources are under `docs/` using the Material theme. Navigation is
defined in `mkdocs.yml`.

- Add new pages under `docs/` as `.md` files.
- Update navigation in `mkdocs.yml` under the `nav:` section.
- Use Markdown and admonitions supported by the Material theme.

MkDocs uses `mkdocstrings` to generate Python API documentation. Ensure modules
under `src/aid2e/` are importable when building the site.

**Deployment**

Pushes to `main` and manual workflow runs deploy the documentation through
`.github/workflows/docs-deploy.yml`.

To deploy manually to GitHub Pages:

```bash
./scripts/docs-deploy-ghpages.sh
```

GitHub Pages must be enabled in the repository settings before using the manual
deployment script.

**Troubleshooting**

- If `mkdocs` is not found, install the documentation extras with
  `python -m pip install -e ".[docs]"`.
- If API pages fail to render, verify the import paths in `mkdocs.yml` and that
  the package is installed in editable mode with `python -m pip install -e .`.

## Repository Structure

```text
AID2E-framework/
|-- src/aid2e/
|   |-- cli/
|   |-- optimizers/
|   |-- schedulers/
|   `-- utilities/
|       |-- configurations/
|       |-- epic_utils/
|       `-- workflows/
|-- examples/
|-- tests/
|-- docs/
|-- scripts/
|-- .github/workflows/
|-- pyproject.toml
|-- mkdocs.yml
`-- pytest.ini
```

## Support

For issues or questions, use the
[AID2E issue tracker](https://github.com/aid2e/AID2E-framework/issues).
