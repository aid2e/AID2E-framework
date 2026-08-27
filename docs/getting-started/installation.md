# Installation

AID2E requires Python 3.11 or later and is currently installed from source.

## Install from Source

Clone the repository and create a Python environment (recommended):

```bash
git clone https://github.com/aid2e/AID2E-framework.git
cd AID2E-framework

python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

The editable installation includes AID2E's core optimizer and local scheduler dependencies.

## PanDA/iDDS Support

Install the optional PanDA dependencies when using the PanDA/iDDS scheduler:

```bash
python -m pip install -e ".[panda]"
```

Slurm, PanDA/iDDS, and ePIC software require their corresponding external environments. See the [scheduler guide](../user-guide/schedulers.md) and [workflow guide](../user-guide/workflows.md) for configuration details.

## Verify the Installation

```bash
aid2e version
aid2e --help
```

Continue with the [Quick Start](quick-start.md) to validate and run the DTLZ2 example.
