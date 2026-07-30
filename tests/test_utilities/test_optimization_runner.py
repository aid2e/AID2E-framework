"""Tests for config-driven optimization execution."""

from pathlib import Path

from aid2e.utilities.configurations import load_config
from aid2e.utilities.runtime_builders import execute_trial_workflow_from_config


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
