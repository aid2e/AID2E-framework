# AID2E Framework - Installation Guide

## Overview

The AID2E Framework is a modular project containing the CLI, optimizers, schedulers, and utilities for AI-assisted detector design for the EIC. All modules are organized within the `src/aid2e/` directory structure.

## Installation

### Install with Core Dependencies

```bash
pip install -e .
```

This installs the framework with core dependencies:
- `pyyaml>=5.4` - YAML configuration parsing
- `pydantic>=2.0` - Data validation
- `click>=8.0` - CLI framework

### Install with Development Tools

```bash
pip install -e ".[dev]"
```

Installs development tools for testing and code quality:
- `pytest>=6.0` - Testing framework
- `pytest-cov>=2.12` - Code coverage
- `black>=21.0` - Code formatter
- `flake8>=3.9` - Linter
- `isort>=5.9` - Import sorting
- `mypy>=0.910` - Type checking

### Install with Documentation Tools

```bash
pip install -e ".[docs]"
```

Installs documentation generation tools:
- `mkdocs>=1.2` - Documentation generator
- `mkdocs-material>=7.1` - Material theme
- `mkdocstrings>=0.18` - API documentation
- `mkdocstrings-python>=1.0.0` - Python docstring support

### Install Everything

```bash
pip install -e ".[dev,docs]"
```

## Project Structure

```
AID2E-framework/
├── src/aid2e/                     # Main source package
│   ├── __init__.py
│   ├── cli/                       # Command-line interface
│   │   ├── __init__.py
│   │   └── aid2e_cli.py
│   ├── optimizers/                # Optimization algorithms
│   │   └── __init__.py
│   ├── schedulers/                # Job schedulers
│   │   └── __init__.py
│   └── utilities/                 # Utility modules
│       ├── __init__.py
│       ├── configurations/        # Configuration loading
│       │   ├── __init__.py
│       │   ├── base_models.py
│       │   ├── design_config.py
│       │   ├── problem_config.py
│       │   ├── optimization_config.py
│       │   ├── optimization_registry.py
│       │   └── full_config.py
│       └── epic_utils/            # EIC physics utilities
│           ├── __init__.py
│           ├── epic_design_config.py
│           ├── epic_env_config.py
│           └── epic_problem_config.py
│
├── tests/                         # Test suite
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_integration.py
│   ├── test_cli/
│   │   ├── test_cli_module.py
│   │   └── test_cli.py
│   ├── test_optimizers/
│   │   └── test_optimizers_module.py
│   ├── test_schedulers/
│   │   └── test_schedulers_module.py
│   ├── test_utilities/
│   │   ├── test_utilities_module.py
│   │   ├── test_configurations/
│   │   │   ├── test_config_file_loading.py
│   │   │   └── test_configurations_module.py
│   │   └── test_epic_utils/
│   │       ├── test_epic_design_config.py
│   │       └── test_epic_utils_module.py
│   └── integration/
│       └── test_integration_example.py
│
├── docs/                          # Documentation (MkDocs)
│   ├── README.md
│   ├── docs-guide.md
│   ├── user-guide/
│   │   └── overview.md
│   └── api-reference/
│       ├── cli.md
│       ├── optimizers.md
│       ├── schedulers.md
│       └── utilities.md
│
├── examples/                      # Configuration examples
│   ├── basic/
│   │   ├── design.params
│   │   ├── full_example.yml
│   │   ├── optimizer.config
│   │   ├── problem.config
│   │   └── slurm.template
│   └── configurations/
│       ├── dtlz2_optimization.yml
│       ├── epic_tracking_optimization.yml
│       └── README.md
│
├── scripts/                       # Helper scripts
│   ├── docs-build.sh
│   ├── docs-deploy-ghpages.sh
│   └── docs-serve.sh
│
├── .github/
│   └── instructions/              # Project instructions
│       └── project-def.instructions.md
│
├── pyproject.toml                 # Project configuration
├── pytest.ini                     # Pytest configuration
├── mkdocs.yml                     # Documentation configuration
├── README.md                      # Project overview
└── INSTALLATION.md                # This file
```

## Using the AID2E CLI

After installation, the `aid2e` command-line tool is available:

```bash
# Display version
aid2e --version

# Show available commands
aid2e --help

# Launch the MCP server command
aid2e mcp

# Load and display configuration
aid2e load examples/basic/full_example.yml

# Show configuration details
aid2e info examples/basic/full_example.yml
```

For the MCP extra, install it with:

```bash
python -m pip install -e ".[mcp]"
```

The standalone `mcp` console script is also installed.

## Import Examples

### Using Modules in Python

```python
# CLI module
from aid2e.cli import cli

# Optimizers module
from aid2e.optimizers import SomeOptimizer

# Schedulers module
from aid2e.schedulers import SomeScheduler

# Configuration utilities
from aid2e.utilities.configurations import load_config, FullConfig
from aid2e.utilities.epic_utils import some_function
```

### Loading Configurations

```python
from aid2e.utilities.configurations import load_config

# Load a full configuration
config = load_config('examples/basic/full_example.yml')

# Access configuration components
print(config.design)
print(config.problem)
print(config.optimization)
```

## Development Workflow

### Setting Up for Development

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

### Running Tests

```bash
# Run all tests
pytest tests/

# Run with verbose output
pytest tests/ -v

# Run with coverage report
pytest tests/ --cov=src/aid2e --cov-report=html

# Run specific test file
pytest tests/test_cli/test_aid2e_cli.py
```

### Building Documentation Locally

```bash
# Build static site
mkdocs build

# Serve documentation locally (with live reload)
mkdocs serve
```

The documentation will be available at `http://localhost:8000/`

### Code Quality

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

### Making Changes

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
