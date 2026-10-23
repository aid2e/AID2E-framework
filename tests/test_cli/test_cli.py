"""Tests for aid2e.cli CLI functionality."""

import pytest
from click.testing import CliRunner
from aid2e.cli.aid2e_cli import cli


@pytest.fixture
def runner():
    """Create a CLI test runner."""
    return CliRunner()


def test_cli_help(runner):
    """Test CLI help command."""
    result = runner.invoke(cli, ['--help'])
    assert result.exit_code == 0
    assert 'AID2E' in result.output
    assert 'Usage:' in result.output


def test_cli_version(runner):
    """Test CLI version command."""
    result = runner.invoke(cli, ['--version'])
    assert result.exit_code == 0
    assert 'version' in result.output.lower()


def test_cli_version_subcommand(runner):
    """Test CLI version subcommand."""
    result = runner.invoke(cli, ['version'])
    assert result.exit_code == 0



def test_optimize_delegates_to_generic_runner(runner, tmp_path, monkeypatch):
    """Optimize should validate config and delegate execution generically."""
    output_dir = tmp_path / "output"
    work_dir = tmp_path / "work"
    output_dir.mkdir()
    work_dir.mkdir()
    config_path = tmp_path / "input.yml"
    config_path.write_text(
        f"""
problem:
  name: Generic CLI Problem
  problem_type: generic
  output_location: {output_dir}
  work_location: {work_dir}
  inline_design:
    design_space:
      design_parameters:
        design:
          parameters:
            x:
              value: 0.0
              bounds: [0.0, 1.0]
      parameter_constraints: []
  objectives:
    - name: score
      direction: minimize
optimizer:
  name: ax
  type: bayesian
  parameters:
    n_initial_samples: 1
    n_iterations: 1
    batch_size: 1
workflows:
  workflows:
    - name: generic_eval
      branches: []
""",
        encoding="utf-8",
    )

    calls = []

    def fake_run(config, config_file, **kwargs):
        calls.append((config, config_file, kwargs))
        return {
            "run_dir": output_dir / "run-1",
            "optimization_results": output_dir / "run-1" / "optimization_results.json",
        }

    monkeypatch.setattr(
        "aid2e.cli.workflow_commands.run_optimization",
        fake_run,
    )

    result = runner.invoke(
        cli,
        [
            "optimize",
            str(config_path),
            "--workflow",
            "generic_eval",
            "--run-id",
            "run-1",
        ],
    )

    assert result.exit_code == 0
    assert "Optimization completed" in result.output
    assert len(calls) == 1
    assert calls[0][1] == str(config_path)
    assert calls[0][2]["workflow_name"] == "generic_eval"
    assert calls[0][2]["run_id"] == "run-1"


def test_optimize_saves_run_outputs(tmp_path):
    """Save run settings and collected results."""
    import json
    from pathlib import Path
    from aid2e.utilities.configurations import load_config
    from aid2e.utilities.runtime_builders import run_optimization

    example = Path(__file__).parents[2] / "examples/dtlz2/configurations/dtlz2_ax_joblib.yml"
    config = load_config(str(example))
    config.problem.work_location = str(tmp_path / "work")
    config.optimizer.parameters.update(n_iterations=2, n_initial_samples=3, batch_size=2)
    outputs = run_optimization(config, str(example), output_dir=str(tmp_path / "output"), run_id="records")
    snapshot = json.loads(outputs["resolved_config"].read_text())
    assert snapshot["problem"]["output_location"] == str(tmp_path / "output")
    assert snapshot["problem"]["design_config"]["design_parameters"]["DTLZ2_variables"]["parameters"]["x1"]["type"] == "range"
    summary = json.loads(outputs["summary"].read_text())
    assert summary["status"] == "completed" and summary["completed_trials"] == 2
    checkpoints = json.loads(outputs["optimizer_checkpoints"].read_text())["checkpoints"]
    collected = [cp["context"] for cp in checkpoints if cp["stage"] == "trial_collected"]
    assert len(collected) == 2 and all(cp["outputs"] for cp in collected)
