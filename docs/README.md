# AID2E Framework

AI assisted Detector Design for EIC (AID2E) is a Python toolkit for authoring and validating detector design optimization workflows. It provides typed configuration models, a Click-based CLI, scheduler/optimizer hooks, and ePIC-specific utilities. Docs: https://aid2e.github.io/AID2E-framework

## Repository Layout

- src/aid2e/ main package (CLI at aid2e.cli, optimizers, schedulers, utilities)
- tests/ mirrored test suite, including fixtures for DTLZ2 and ePIC configs
- docs/ MkDocs site sources (published to GitHub Pages)
- scripts/ helper scripts for docs build/deploy
- packages/ legacy package splits (kept for reference; primary code now lives under src/)

## Quickstart

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .

# Run tests
pytest -v

# Try the CLI
aid2e --help
aid2e version
```

## Using Configuration Loaders

- Load a problem + design config:

```python
from aid2e.utilities.configurations import load_config

cfg = load_config("path/to/problem.config")
print(cfg.problem.design_config.get_parameter_names())
```

- Example fixtures live in tests/test_utilities/fixtures/dtlz2/ (design.params, problem.config).

## Developing

- Lint/format/type: black ., flake8, mypy (install extras with pip install -e ".[dev]")
- Docs: pip install -e ".[docs]" && ./scripts/docs-serve.sh
- Tests: pytest -v

## Documentation

MkDocs site sources are under docs/ (Material theme). The navigation is defined in mkdocs.yml; API reference is generated via mkdocstrings.

## Contributing

- Prefer adding tests alongside changes.
- Keep imports under the aid2e namespace (aid2e.cli, aid2e.utilities.configurations, etc.).
- Update docs and fixtures when changing configuration schemas.
