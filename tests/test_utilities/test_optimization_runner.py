"""Tests for generic optimization orchestration."""

from pathlib import Path
import shlex
import sys

import pytest

from aid2e.optimizers.base import Trial
from aid2e.schedulers.JobLib import JobLibRunnerConfig
from aid2e.utilities.configurations import load_config
from aid2e.utilities.optimization_runner import (
    OptimizationRunOptions,
    run_optimization_from_config,
)
from aid2e.utilities.workflows import (
    BranchDefinition,
    DAGExecutor,
    JobDefinition,
    StageDefinition,
    WorkflowDefinition,
)


class DummyOptimizer:
    def __init__(self):
        self._trials = []
        self._next_index = 0

    def suggest_candidates(self, n_candidates=1):
        candidates = []
        for _ in range(n_candidates):
            params = {"design.x": float(self._next_index)}
            self._trials.append(
                Trial(index=self._next_index, parameters=params, status="suggested")
            )
            self._next_index += 1
            candidates.append(params)
        return candidates

    def get_trials(self):
        return list(self._trials)

    def set_trial_status(
        self, trial_index, status, parameters=None, metrics=None, metadata=None
    ):
        trial = self._trials[trial_index]
        updated = Trial(
            index=trial_index,
            parameters=parameters or trial.parameters,
            metrics=metrics or trial.metrics,
            status=status,
            metadata=metadata or trial.metadata,
        )
        self._trials[trial_index] = updated
        return updated

    def update_with_results(self, trial_index, parameters, metrics):
        self.set_trial_status(
            trial_index,
            "completed",
            parameters=parameters,
            metrics=metrics,
        )

    def get_pareto_front(self):
        return [trial for trial in self._trials if trial.status == "completed"][:1]

    def serialize_state(self):
        return {"n_trials": len(self._trials)}


class DummyExecutor:
    def __init__(self):
        self.workflow = WorkflowDefinition(name="generic_eval", branches=[])

    def execute(self, parameters):
        x = parameters["design.x"]
        return {"score": (x - 1.0) ** 2}


def _write_config(tmp_path: Path) -> Path:
    output_dir = tmp_path / "output"
    work_dir = tmp_path / "work"
    output_dir.mkdir()
    work_dir.mkdir()
    config_path = tmp_path / "input.yml"
    config_path.write_text(
        f"""
problem:
  name: Generic Quadratic
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
              bounds: [0.0, 2.0]
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
    batch_size: 2
workflows:
  workflows:
    - name: generic_eval
      branches: []
""",
        encoding="utf-8",
    )
    return config_path


def test_run_optimization_from_config_persists_generic_trials(tmp_path, monkeypatch):
    config = load_config(str(_write_config(tmp_path)))

    monkeypatch.setattr(
        "aid2e.utilities.optimization_runner.infer_optimizer_backend",
        lambda optimizer_cfg: "ax",
    )
    monkeypatch.setattr(
        "aid2e.utilities.optimization_runner.build_optimizer_from_config",
        lambda *args, **kwargs: DummyOptimizer(),
    )
    monkeypatch.setattr(
        "aid2e.utilities.optimization_runner.build_workflow_executor_from_config",
        lambda *args, **kwargs: DummyExecutor(),
    )

    result = run_optimization_from_config(
        config,
        options=OptimizationRunOptions(run_id="run-1"),
    )

    assert result.completed_trials == 3
    assert result.failed_trials == 0
    assert result.workflow_name == "generic_eval"
    run_dir = Path(result.run_dir)
    assert (run_dir / "summary.json").exists()
    assert (run_dir / "trials.jsonl").exists()
    assert len((run_dir / "trials.jsonl").read_text().splitlines()) == 6


def test_run_optimization_requires_workflows(tmp_path):
    config = load_config(str(_write_config(tmp_path)))
    config.workflows = None

    with pytest.raises(ValueError, match="top-level 'workflows'"):
        run_optimization_from_config(config)


def test_dag_executor_extracts_objectives_from_json_artifact(tmp_path):
    workflow = WorkflowDefinition(
        name="artifact_eval",
        objectives=[{"name": "score", "direction": "minimize"}],
    )
    executor = DAGExecutor(workflow=workflow, base_output_dir=str(tmp_path))
    executor.global_xcom["evaluate:artifact:/tmp/objectives.json"] = '{"score": 2.5}'

    assert executor._compute_objectives() == {"score": 2.5}


def test_dag_executor_joblib_command_returns_json_artifact_objectives(tmp_path):
    script = "import json, sys; json.dump({'score': 1.25}, open(sys.argv[1], 'w'))"
    command = (
        f"{sys.executable} -c {shlex.quote(script)} "
        "{{output_dir}}/objectives.json"
    )
    workflow = WorkflowDefinition(
        name="joblib_command_eval",
        objectives=[{"name": "score", "direction": "minimize"}],
        branches=[
            BranchDefinition(
                name="main",
                stages=[
                    StageDefinition(
                        name="evaluate",
                        jobs=[
                            JobDefinition(
                                name="write_metrics",
                                command=command,
                                payload={"evaluator_type": "bash"},
                                outputs=[
                                    {
                                        "path": "{{output_dir}}/objectives.json",
                                        "format": "json",
                                    }
                                ],
                            )
                        ],
                    )
                ],
            )
        ],
    )
    executor = DAGExecutor(
        workflow=workflow,
        base_output_dir=str(tmp_path),
        scheduler_config={
            "runner_type": "JobLibRunner",
            "config": JobLibRunnerConfig(n_jobs=1, backend="threading"),
        },
    )

    assert executor.execute({"design.x": 0.5}) == {"score": 1.25}
