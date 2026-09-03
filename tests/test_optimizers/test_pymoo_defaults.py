"""Regression tests for PyMOO default algorithm inference."""

from __future__ import annotations

import pytest

from aid2e.optimizers.base import SearchSpace
from aid2e.optimizers.pymoo import PyMOOOptimizer, PyMOOOptimizerConfig
from aid2e.utilities import build_optimizer_from_config
from aid2e.utilities.configurations import OptimizerConfiguration
from aid2e.utilities.configurations.problem_config import ProblemConfigLoader


def _make_search_space() -> SearchSpace:
    return SearchSpace(
        parameters={
            "x": {"type": "range", "value": 0.5, "bounds": [0.0, 1.0]},
            "y": {"type": "range", "value": 0.5, "bounds": [0.0, 1.0]},
        }
    )


def _complete_generation(optimizer: PyMOOOptimizer) -> None:
    candidates = optimizer.suggest_candidates()
    start_index = len(optimizer.get_trials()) - len(candidates)
    for offset, parameters in enumerate(candidates):
        trial_index = start_index + offset
        if optimizer.n_objectives == 1:
            metrics = {"loss": float(parameters["x"] + parameters["y"])}
        else:
            metrics = {
                "f1": float(parameters["x"]),
                "f2": float(parameters["y"]),
            }
        optimizer.update_with_results(
            trial_index=trial_index,
            parameters=parameters,
            metrics=metrics,
        )


def test_config_resolve_algorithm_defaults() -> None:
    config = PyMOOOptimizerConfig(n_iterations=4)
    assert config.n_iterations == 4
    assert config.resolve_algorithm(1) == "ga"
    assert config.resolve_algorithm(2) == "nsga2"


@pytest.mark.parametrize(
    ("algorithm", "n_objectives", "message"),
    [
        ("ga", 2, "single-objective"),
        ("nsga2", 1, "single-objective optimization"),
        ("nsga3", 1, "single-objective optimization"),
        ("moead", 1, "single-objective optimization"),
    ],
)
def test_config_rejects_incompatible_explicit_algorithms(
    algorithm: str,
    n_objectives: int,
    message: str,
) -> None:
    config = PyMOOOptimizerConfig(algorithm=algorithm)
    with pytest.raises(ValueError, match=message):
        config.resolve_algorithm(n_objectives)


def test_single_objective_optimizer_defaults_to_ga_and_round_trips_state() -> None:
    optimizer = PyMOOOptimizer(
        search_space=_make_search_space(),
        config=PyMOOOptimizerConfig(pop_size=4, n_offsprings=4, seed=11),
        objective_names=["loss"],
        seed=11,
    )

    assert optimizer.resolved_algorithm == "ga"
    assert optimizer._algorithm.__class__.__name__ == "GA"

    _complete_generation(optimizer)
    _complete_generation(optimizer)

    results = optimizer.get_optimization_results()
    assert results["n_trials"] == len(optimizer.get_trials()) == 8

    state = optimizer.serialize_state()
    assert state["resolved_algorithm"] == "ga"

    restored = PyMOOOptimizer(
        search_space=_make_search_space(),
        config=PyMOOOptimizerConfig(pop_size=4, n_offsprings=4, seed=99),
        objective_names=["loss"],
        seed=99,
    )
    restored.load_state(state)

    assert restored.resolved_algorithm == "ga"
    assert restored.get_optimization_results()["n_trials"] == 8
    assert len(restored.get_trials()) == 8


def test_multi_objective_optimizer_defaults_to_nsga2() -> None:
    optimizer = PyMOOOptimizer(
        search_space=_make_search_space(),
        config=PyMOOOptimizerConfig(pop_size=4, n_offsprings=4, seed=7),
        objective_names=["f1", "f2"],
        objective_directions={"f1": "minimize", "f2": "maximize"},
        seed=7,
    )

    assert optimizer.resolved_algorithm == "nsga2"
    assert optimizer._algorithm.__class__.__name__ == "NSGA2"

    candidates = optimizer.suggest_candidates()
    optimizer.mark_trial_failed(0, parameters=candidates[0], reason="evaluation failed")
    for trial_index, parameters in enumerate(candidates[1:], start=1):
        optimizer.update_with_results(
            trial_index,
            parameters,
            {"f1": parameters["x"], "f2": parameters["y"]},
        )
    objective_values = optimizer._algorithm.pop.get("F").tolist()
    assert [float("inf"), float("inf")] in objective_values
    assert any(
        values[1] < 0
        for values in objective_values
        if values[1] != float("inf")
    )
    _complete_generation(optimizer)

    results = optimizer.get_optimization_results()
    assert results["n_trials"] == len(optimizer.get_trials()) == 8
    assert len(optimizer.get_pareto_front()) >= 1


def test_explicit_incompatible_algorithm_fails_on_optimizer_init() -> None:
    with pytest.raises(ValueError, match="single-objective optimization"):
        PyMOOOptimizer(
            search_space=_make_search_space(),
            config=PyMOOOptimizerConfig(algorithm="nsga2", pop_size=4, seed=3),
            objective_names=["loss"],
            seed=3,
        )


def test_runtime_builder_accepts_omitted_pymoo_algorithm(tmp_path) -> None:
    output_dir = tmp_path / "output"
    work_dir = tmp_path / "work"
    output_dir.mkdir()
    work_dir.mkdir()

    problem_cfg = ProblemConfigLoader.from_dict(
        {
            "name": "DTLZ2",
            "problem_type": "toy",
            "output_location": str(output_dir),
            "work_location": str(work_dir),
            "inline_design": {
                "design_space": {
                    "design_parameters": {
                        "group1": {
                            "parameters": {
                                "x": {"value": 0.5, "bounds": [0.0, 1.0]},
                                "y": {"value": 0.5, "bounds": [0.0, 1.0]},
                            }
                        }
                    }
                }
            },
            "objectives": [
                {"name": "f1", "direction": "minimize"},
                {"name": "f2", "direction": "maximize"},
            ],
        },
    )
    optimizer_cfg = OptimizerConfiguration(
        name="pymoo",
        type="evolutionary",
        parameters={
            "pop_size": 4,
            "n_offsprings": 4,
            "n_iterations": 2,
            "seed": 5,
        },
    )

    optimizer = build_optimizer_from_config(problem_cfg, optimizer_cfg)

    assert isinstance(optimizer, PyMOOOptimizer)
    assert optimizer.objective_directions["f2"].value == "maximize"
    assert optimizer.resolved_algorithm == "nsga2"
    assert optimizer.config.algorithm is None
