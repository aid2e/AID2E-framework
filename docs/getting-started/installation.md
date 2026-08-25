# Installation

## Requirements

- Python 3.11 or later

## Installation

### Clone the repo

```bash
git clone https://github.com/aid2e/AID2E-framework.git
cd AID2E-framework
```

### Create environment (recommended)

```bash
python -m venv .venv
source .venv/bin/activate
```

### Install AID2E

```bash
pip install -e .
```

Core and optional dependency groups are defined in `pyproject.toml`.

### Optional PanDA Dependencies

```bash
pip install -e ".[panda]"
```

This extra is required only when using the PanDA/iDDS scheduler.

## Verify the Installation

```bash
aid2e --help
```
