"""CLI smoke tests for aid2e command."""

import sys
from pathlib import Path

from click.testing import CliRunner

# Ensure the core src directory is importable when running tests from repo root
SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_ROOT))

from core.aid2e_cli import cli


def _example_config_path() -> Path:
    # Navigate from tests/ up to repo root, then into examples/configurations
    return Path(__file__).resolve().parents[3] / "examples" / "configurations" / "dtlz2_optimization.yml"


def _ensure_required_dirs():
    out_dir = Path.cwd() / "output" / "dtlz2"
    work_dir = Path.cwd() / "work" / "dtlz2"
    out_dir.mkdir(parents=True, exist_ok=True)
    work_dir.mkdir(parents=True, exist_ok=True)


def test_load_validate_only():
    cfg = _example_config_path()
    _ensure_required_dirs()
    runner = CliRunner()
    result = runner.invoke(cli, ["load", str(cfg), "--validate-only"])
    assert result.exit_code == 0
    assert "Configuration loaded successfully" in result.output
    assert "Validation complete" in result.output


def test_info_command():
    cfg = _example_config_path()
    _ensure_required_dirs()
    runner = CliRunner()
    result = runner.invoke(cli, ["info", str(cfg)])
    assert result.exit_code == 0
    assert "PROBLEM CONFIGURATION" in result.output
    assert "OPTIMIZATION CONFIGURATION" in result.output
