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
    help_text = runner.invoke(cli, ['optimize', '--help']).output
    assert '--output' not in help_text and '--log' not in help_text


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
    assert "output_dir" not in calls[0][2]
    assert (output_dir / "run-1/run.log").is_file()
    assert calls[0][0].problem.work_location == str(work_dir)


@pytest.fixture
def optimization_config(tmp_path):
    from pathlib import Path
    from aid2e.utilities.configurations import load_config

    example = Path(__file__).parents[2] / "examples/dtlz2/configurations/dtlz2_ax_joblib.yml"
    config = load_config(str(example))
    config.problem.work_location = str(tmp_path / "work")
    config.optimizer.parameters.update(n_iterations=2, n_initial_samples=3, batch_size=2)
    return config, example


@pytest.mark.parametrize("update_fails", [False, True])
def test_optimize_saves_run_outputs(tmp_path, monkeypatch, optimization_config, update_fails):
    """Save run settings and collected results."""
    import json
    from aid2e.utilities.runtime_builders import run_optimization

    config, example = optimization_config
    if update_fails:
        from aid2e.optimizers.ax.optimizer import AxOptimizer
        update = AxOptimizer.update_with_results

        def fail_second_update(self, trial_index, *args, **kwargs):
            if trial_index == 1:
                raise RuntimeError("Optimizer update failed")
            return update(self, trial_index, *args, **kwargs)

        monkeypatch.setattr(AxOptimizer, "update_with_results", fail_second_update)
        with pytest.raises(RuntimeError, match="Optimizer update failed"):
            run_optimization(config, str(example), output_dir=str(tmp_path / "output"), run_id="records")
        saved = json.loads((tmp_path / "output/records/optimization_results.json").read_text())
        assert saved["trials"][0]["status"] == "completed" and saved["trials"][0]["objectives"]
        return
    outputs = run_optimization(config, str(example), output_dir=str(tmp_path / "output"), run_id="records")
    snapshot = json.loads(outputs["resolved_config"].read_text())
    assert snapshot["problem"]["output_location"] == str(tmp_path / "output")
    assert snapshot["problem"]["design_config"]["design_parameters"]["DTLZ2_variables"]["parameters"]["x1"]["type"] == "range"
    summary = json.loads(outputs["summary"].read_text())
    assert summary["status"] == "completed" and summary["completed_trials"] == 2
    assert outputs["summary"].name == "run.json"
    assert summary["config_path"] == str(example.resolve()) and summary["work_dir"] == str(tmp_path / "work/records")
    assert not (outputs["run_dir"] / "summary.json").exists()
    checkpoints = json.loads(outputs["optimizer_checkpoints"].read_text())["checkpoints"]
    collected = [cp["context"] for cp in checkpoints if cp["stage"] == "trial_collected"]
    assert len(collected) == 2 and all(cp["outputs"] for cp in collected)
    assert "." in checkpoints[0]["timestamp"]
    assert next(cp["context"]["duration"] for cp in checkpoints if cp["stage"] == "optimizer_update_complete") >= 0


@pytest.mark.parametrize("policy,invalid", [
    ("penalty", None),
    ("penalty", {"invalid_design": True, "reason": "confirmed bad design"}),
    ("fail", {"invalid_design": True, "reason": "confirmed bad design"}),
    ("penalty", {"f1": float("nan")}),
])
def test_failure_limit_preserves_batch_results(tmp_path, monkeypatch, optimization_config, policy, invalid):
    import json
    from aid2e.schedulers.JobLib import JobLibScheduler
    from aid2e.schedulers.base import JobStatus, StageExecutionResult
    from aid2e.utilities import runtime_builders as runtime

    config, example = optimization_config
    config.problem.evaluation_config = {"trial_failure_policy": policy, "penalty_objectives": {"f1": 100, "f2": 100}, "max_failed_trials": 0}
    batch = StageExecutionResult(
        stage_name="evaluate", success=invalid is not None, artifacts={}, job_statuses=[
            JobStatus(job_id="0", status="completed", outputs={"f1": 1.0, "f2": 2.0, **invalid}) if invalid is not None
            else JobStatus(job_id="0", status="failed", stderr="evaluation failed"),
            JobStatus(job_id="1", status="completed", outputs={"f1": 0.0, "f2": 2.0, "f1_err": 0.0}),
        ],
    )
    def run_stage(self, stage_name, jobs, **kwargs):
        assert jobs[0]["payload"]["output_dir"] == str(tmp_path / "records/trials/trial_0/log")
        assert kwargs["working_dir"] == str(tmp_path / "work/records")
        return batch

    monkeypatch.setattr(JobLibScheduler, "run_stage", run_stage)
    with pytest.raises(RuntimeError, match="Too many failed trials"):
        runtime.run_optimization(config, str(example), output_dir=str(tmp_path), run_id="records")
    results = json.loads((tmp_path / "records/optimization_results.json").read_text())["trials"]
    assert results[1]["objectives"] == {"f1": 0.0, "f2": 2.0}
    invalid_design = bool(invalid and invalid.get("invalid_design"))
    assert results[0]["metadata"]["reason"]
    assert results[0]["metadata"].get("penalized", False) == (policy == "penalty" and invalid_design)
    assert results[1]["metadata"]["uncertainties"] == {"f1": 0.0}
    pareto = json.loads((tmp_path / "records/pareto_front.json").read_text())
    assert results[1]["objective_errors"] == pareto[0]["objective_errors"] == {"f1_err": 0.0}
    summary = json.loads((tmp_path / "records/run.json").read_text())
    assert summary["status"] == "failed" and summary["failed_trials"] == summary["completed_trials"] == 1
