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

    class Result:
        run_dir = str(output_dir / "run-1")
        completed_trials = 1
        failed_trials = 0
        pareto_front = []

    calls = []

    def fake_run(config, options):
        calls.append((config, options))
        return Result()

    monkeypatch.setattr(
        "aid2e.cli.workflow_commands.run_optimization_from_config",
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
    assert calls[0][1].workflow_name == "generic_eval"
    assert calls[0][1].run_id == "run-1"
