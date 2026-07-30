"""Tests for config-driven optimization execution."""

import json
from pathlib import Path
from types import SimpleNamespace

from aid2e.optimizers.base import Trial
from aid2e.utilities.configurations import load_config
from aid2e.utilities.runtime_builders import (
    execute_trial_workflow_from_config,
    run_optimization_from_config,
)


class RecordingOptimizer:
    def __init__(self):
        self.config = SimpleNamespace(n_iterations=2, batch_size=1)
        self.objective_names = ["f1"]
        self._next = 0
        self._trials = []

    def suggest_candidates(self, n_candidates=1):
        candidates = []
        for _ in range(n_candidates):
            candidates.append({"x": float(self._next)})
            self._next += 1
        return candidates

    def update_with_results(self, trial_index, parameters, metrics):
        self._trials.append(
            Trial(
                index=trial_index,
                parameters=parameters,
                metrics=metrics,
                status="completed",
            )
        )

    def get_trials(self):
        return self._trials

    def save_optimization_results(
        self,
        output_path,
        save_pareto_front=None,
        errors_by_trial=None,
    ):
        output_path.write_text(
            json.dumps(
                {
                    "n_trials": len(self._trials),
                    "errors_by_trial": errors_by_trial or {},
                }
            )
        )
        if save_pareto_front is not None:
            save_pareto_front.write_text(json.dumps([]))


class SchedulerWithShutdown:
    def shutdown(self):
        pass


def test_dtlz2_example_follows_benchmark_config(tmp_path):
    """The shipped DTLZ2 config should execute the benchmark objective path."""
    config_path = Path("examples/configurations/dtlz2_optimization.yml")
    config = load_config(str(config_path))

    assert config.problem.design_config.get_parameter_names() == [
        "DTLZ2_variables.x1",
        "DTLZ2_variables.x2",
        "DTLZ2_variables.x3",
        "DTLZ2_variables.x4",
        "DTLZ2_variables.x5",
    ]
    assert [objective.to_directive() for objective in config.problem.objectives] == [
        "minimize:f1",
        "minimize:f2",
    ]
    assert config.optimizer.parameters["n_initial_samples"] == 4
    assert config.optimizer.parameters["n_iterations"] == 8
    assert config.optimizer.parameters["batch_size"] == 2

    result = execute_trial_workflow_from_config(
        str(config_path),
        str(tmp_path / "output"),
        trial_index=0,
        design_point={
            "DTLZ2_variables.x1": 0.5,
            "DTLZ2_variables.x2": 0.5,
            "DTLZ2_variables.x3": 0.5,
            "DTLZ2_variables.x4": 0.5,
            "DTLZ2_variables.x5": 0.5,
        },
    )

    assert result == {"f1": 0.5000000000000001, "f2": 0.5}


def test_run_optimization_from_config_updates_optimizer_and_writes_results(tmp_path, monkeypatch):
    """The runner should update the optimizer and write result artifacts."""
    config_path = tmp_path / "workflow.yml"
    config_path.write_text("{}")
    config = SimpleNamespace(
        problem=SimpleNamespace(
            output_location=str(tmp_path / "output"),
            evaluation_config={
                "max_failed_trials": 0,
            },
        ),
        optimizer=SimpleNamespace(parameters={}),
        scheduler=SimpleNamespace(),
    )
    optimizer = RecordingOptimizer()

    def complete_trial_batch(
        scheduler,
        batch_id,
        assignments,
        optimizer,
        config_path,
        output_dir,
        failed_trials,
        max_failed_trials,
    ):
        return {
            trial_index: (design_point, {"f1": design_point["x"] + 1.0, "f1_sem": 0.1})
            for trial_index, design_point in assignments
        }

    monkeypatch.setattr(
        "aid2e.utilities.runtime_builders.build_optimizer_from_config",
        lambda problem, optimizer_config: optimizer,
    )
    monkeypatch.setattr(
        "aid2e.utilities.runtime_builders.build_scheduler_from_config",
        lambda scheduler_config: SchedulerWithShutdown(),
    )
    monkeypatch.setattr(
        "aid2e.utilities.runtime_builders._run_optimizer_trial_batch",
        complete_trial_batch,
    )

    results = run_optimization_from_config(config, str(config_path))

    assert len(optimizer.get_trials()) == 2
    assert results["optimization_results"].exists()
    assert results["pareto_front"].name == "pareto_front.json"
    assert "results_csv" not in results
