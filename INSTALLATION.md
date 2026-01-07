# AID2E Framework - Installation Guide

## Overview

The AID2E Framework is now set up as a modular monorepo with a root meta-package that manages all subpackages. This allows for flexible installation options.

## Installation Options

### 1. Install Everything (Default)

```bash
pip install -e .
```

This installs all packages:
- `aid2e-core` → import as `core`
- `aid2e-optimizers` → import as `optimizers`
- `aid2e-schedulers` → import as `schedulers`
- `aid2e-utilities` → import as `configurations` and `epic_utils`

### 2. Install Specific Packages

#### Core Only
```bash
pip install -e ".[core]"
```
Installs: `core`

#### Optimizers Only
```bash
pip install -e ".[optimizers]"
```
Installs: `optimizers`

#### Schedulers Only
```bash
pip install -e ".[schedulers]"
```
Installs: `schedulers`

#### Utilities Only
```bash
pip install -e ".[utilities]"
```
Installs: `configurations` and `epic_utils`

#### All Packages Explicitly
```bash
pip install -e ".[all]"
```

## Package Structure

```
AID2E-framework/
├── pyproject.toml                 # Root meta-package
│
├── packages/
│   ├── aid2e-core/
│   │   ├── pyproject.toml
│   │   ├── README.md
│   │   └── src/
│   │       └── core/
│   │           └── __init__.py
│   │
│   ├── aid2e-optimizers/
│   │   ├── pyproject.toml
│   │   ├── README.md
│   │   └── src/
│   │       └── optimizers/
│   │           └── __init__.py
│   │
│   ├── aid2e-schedulers/
│   │   ├── pyproject.toml
│   │   ├── README.md
│   │   └── src/
│   │       └── schedulers/
│   │           └── __init__.py
│   │
│   └── aid2e-utilities/
│       ├── pyproject.toml
│       ├── README.md
│       └── src/
│           ├── configurations/
│           │   └── __init__.py
│           └── epic_utils/
│               └── __init__.py
│
└── docs/                          # Root documentation
    ├── index.md
    ├── getting-started.md
    ├── installation.md
    ├── architecture.md
    ├── development.md
    ├── contributing.md
    ├── changelog.md
    ├── user-guide/
    ├── api-reference/
    ├── tutorials/
    └── assets/
```

## Import Examples

[Note] This is purely form GenAI and needs to updated

### When All Packages are Installed

```python
# Core
from core import Workflow

# Optimizers
from optimizers import BayesianOptimizer

# Schedulers
from schedulers import SlurmScheduler

# Utilities
from configurations import load_config
from epic_utils import some_function
```

### When Only Core is Installed

```python
# This works
from core import Workflow

# These will raise ImportError
from optimizers import BayesianOptimizer  # ImportError
from configurations import load_config    # ImportError
```

## Development

For development with all tools:

```bash
pip install -e ".[dev,docs]"
```

This installs:
- pytest, pytest-cov (testing)
- black, flake8, isort, mypy (code quality)
- mkdocs, mkdocs-material (documentation)

## Adding New Code

Each package can now be developed independently while being managed through the root package.

### Adding to a Subpackage

1. Edit files in `packages/aid2e-<package>/src/`
2. The changes are immediately available due to editable installation
3. No need to reinstall unless you modify `pyproject.toml`

### Creating a New Package

1. Create `packages/aid2e-<newpackage>/`
2. Add `pyproject.toml` with package metadata
3. Create `src/` directory structure
4. Update root `pyproject.toml` to reference the new package

## Testing the Installation

```python
# Test 1: All packages
python -c "
import core
import optimizers
import schedulers
import configurations
print('All packages available!')
"

# Test 2: Specific package
python -c "import core; print('Core available!')"
```

## Next Steps

Now that the skeleton is set up and working:

1. **Add Core Code**: Start implementing actual functionality in each package
2. **Write Tests**: Create test suites in each package
3. **Documentation**: Fill in the documentation templates
4. **Examples**: Add working examples demonstrating package usage
5. **Dependencies**: Update `pyproject.toml` files with actual dependencies

All packages are ready for development!
