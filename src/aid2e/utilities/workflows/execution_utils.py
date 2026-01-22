"""Helpers for invoking objective scripts in workflows.

These utilities build language-agnostic command-line arguments and environment
variables for passing design parameters and collecting objective outputs.

Contract:
- Flags: --design_params_file, --output_file
- Env:   AID2E_PARAMS_FILE, AID2E_OUTPUT_FILE

Use both for maximum compatibility with Python, bash/csh, or other executables.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Tuple


def build_objective_call(
    command: List[str],
    params_file: Path,
    output_file: Path,
) -> Tuple[List[str], Dict[str, str]]:
    """Build command args and environment for objective execution.

    Args:
      command: Base command argv (e.g., ["python", "scripts/dtlz2_problem.py"]).
      params_file: Path to JSON design parameters file.
      output_file: Path to JSON output file.

    Returns:
      A tuple (argv, env) where:
        - argv: command with flags appended
        - env: environment variables to set

    Notes:
      - The flags are appended unconditionally; objective scripts may ignore
        them if they prefer env vars.
      - Caller is responsible for creating parent directories for output_file.
    """
    argv = list(command) + [
        "--design_params_file",
        str(params_file),
        "--output_file",
        str(output_file),
    ]
    env = {
        "AID2E_PARAMS_FILE": str(params_file),
        "AID2E_OUTPUT_FILE": str(output_file),
    }
    return argv, env
