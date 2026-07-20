# AID2E Framework

[![Tests](https://github.com/aid2e/AID2E-framework/actions/workflows/tests.yml/badge.svg?branch=main)](https://github.com/aid2e/AID2E-framework/actions/workflows/tests.yml)
[![Documentation](https://github.com/aid2e/AID2E-framework/actions/workflows/docs-deploy.yml/badge.svg?branch=main)](https://aid2e.github.io/AID2E-framework)

AI assisted Detector Design for EIC (AID2E) is a Python toolkit for authoring and validating detector design optimization workflows. It provides typed configuration models, a Click-based CLI, scheduler/optimizer hooks, and ePIC-specific utilities. Docs: https://aid2e.github.io/AID2E-framework

------------------------------------------------------------------------

## Requirements

-   Python **3.11+**
-   pip

------------------------------------------------------------------------

## Installation

### Clone the repo

``` bash
git clone https://github.com/aid2e/AID2E-framework.git
cd AID2E-framework
```

### Create environment (recommended)

``` bash
python -m venv .venv
source .venv/bin/activate
```

### Install

**Core install:**

``` bash
pip install -e .
```

**Full install (recommended):**

``` bash
pip install -e ".[all]"
```

------------------------------------------------------------------------

## Quick Checks

### Import check

``` bash
python -c "import aid2e; print('OK')"
```

### CLI check

``` bash
aid2e --help
```

------------------------------------------------------------------------

## Optional Features Check

``` bash
python - <<'PY'
modules = ["ax", "pymoo", "joblib", "pandaclient", "idds.common"]
for m in modules:
    try:
        __import__(m)
        print(f"{m}: OK")
    except:
        print(f"{m}: MISSING")
PY
```

------------------------------------------------------------------------

## Run Tests

``` bash
pytest
```

------------------------------------------------------------------------

## MCP Server

To use AID2E from Copilot or another MCP-aware assistant, install the package
with the MCP extra and launch the server command:

```bash
python -m pip install -e ".[mcp]"
aid2e mcp
```

The standalone `mcp` console script is also installed. Once connected, the
assistant can query AID2E's package overview, module list, and API references.

------------------------------------------------------------------------

## Dev Setup

``` bash
pip install -e ".[dev]"
```

Formatting / linting:

``` bash
black src tests
isort src tests
flake8 src tests
mypy src
```

------------------------------------------------------------------------

## Docs

``` bash
pip install -e ".[docs]"
mkdocs serve
```

------------------------------------------------------------------------

## Project Structure

    src/aid2e/
      cli/
      optimizers/
        ax/
        pymoo/
      schedulers/
      utilities/

------------------------------------------------------------------------

## Links

-   Repo: https://github.com/aid2e/AID2E-framework
-   Docs: https://aid2e.github.io/AID2E-framework

------------------------------------------------------------------------

## License

MIT
