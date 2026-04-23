"""Integration tests for BaseOptimizer and the strict Ax optimizer surface."""

import pytest
from ax.adapter.registry import Generators
from ax.generators.torch.botorch_modular.surrogate import SurrogateSpec

from aid2e.optimizers import (
    AxOptimizer,
    AxOptimizerConfig,
    BaseOptimizer,
    SearchSpace,
    Trial,
)
from aid2e.optimizers.ax import optimizer as ax_optimizer_module


AX_NODE_RUNTIME_AVAILABLE = ax_optimizer_module.AX_NODE_STRATEGY_AVAILABLE


def _search_space() -> SearchSpace:
    """Create a canonical search space used across optimizer tests."""
    return SearchSpace(
        parameters={
            "x": {"type": "range", "value": 0.5, "bounds": [0.0, 1.0]},
            "y": {"type": "range", "value": 0.0, "bounds": [-1.0, 1.0]},
        }
    )


def test_base_optimizer_is_abstract():
    """Test that BaseOptimizer cannot be instantiated directly."""
    search_space = SearchSpace(
        parameters={"x": {"type": "range", "value": 0.5, "bounds": [0.0, 1.0]}}
    )

    with pytest.raises(TypeError, match="Can't instantiate abstract class"):
        BaseOptimizer(search_space=search_space, n_objectives=1)


def test_ax_optimizer_inherits_from_base():
    """Test that AxOptimizer inherits from BaseOptimizer."""
    assert issubclass(AxOptimizer, BaseOptimizer)


def test_ax_optimizer_requires_node_generation_runtime():
    """Ax should fail fast when the installed runtime lacks node generation APIs."""
    config = AxOptimizerConfig(seed=42)

    if AX_NODE_RUNTIME_AVAILABLE:
        optimizer = AxOptimizer(
            search_space=_search_space(),
            config=config,
            objective_names=["loss"],
        )
        assert optimizer.generation_strategy is not None
        return

    with pytest.raises(RuntimeError, match="node-based generation API required"):
        AxOptimizer(
            search_space=_search_space(),
            config=config,
            objective_names=["loss"],
        )


@pytest.mark.skipif(
    not AX_NODE_RUNTIME_AVAILABLE,
    reason="Installed Ax runtime lacks required node-based generation APIs.",
)
def test_ax_optimizer_with_config():
    """Test AxOptimizer integrates properly with the strict Ax config surface."""
    config = AxOptimizerConfig(
        initialization_strategy="sobol",
        generator="BOTORCH_MODULAR",
        n_initial_samples=10,
        n_iterations=50,
        batch_size=5,
        seed=42,
    )

    optimizer = AxOptimizer(
        search_space=_search_space(),
        config=config,
        objective_names=["loss", "time"],
    )

    assert optimizer.n_objectives == 2
    assert optimizer.seed == 42
    assert optimizer.config.initialization_strategy == "sobol"
    assert optimizer.config.generator == "BOTORCH_MODULAR"
    assert optimizer.objective_names == ["loss", "time"]


@pytest.mark.skipif(
    not AX_NODE_RUNTIME_AVAILABLE,
    reason="Installed Ax runtime lacks required node-based generation APIs.",
)
def test_ax_optimizer_builds_default_sobol_to_mbm_strategy():
    """Test that the default strategy is Sobol followed by Modular BoTorch."""
    config = AxOptimizerConfig(
        initialization_strategy="sobol",
        n_initial_samples=6,
        seed=42,
    )

    optimizer = AxOptimizer(
        search_space=_search_space(),
        config=config,
        objective_names=["f1", "f2"],
    )

    nodes = optimizer.generation_strategy.nodes
    assert [node.name for node in nodes] == ["Sobol", "ModularBoTorch"]
    sobol_spec = nodes[0].generator_specs[0]
    model_spec = nodes[1].generator_specs[0]

    assert sobol_spec.generator_enum == Generators.SOBOL
    assert sobol_spec.generator_kwargs == {"seed": 42}
    assert nodes[0].transition_criteria[0].threshold == 6
    assert model_spec.generator_enum == Generators.BOTORCH_MODULAR
    assert model_spec.generator_kwargs == {}


@pytest.mark.skipif(
    not AX_NODE_RUNTIME_AVAILABLE,
    reason="Installed Ax runtime lacks required node-based generation APIs.",
)
def test_ax_optimizer_resolves_symbolic_generator_kwargs():
    """Test that YAML-friendly generator kwargs are resolved at runtime."""
    config = AxOptimizerConfig(
        initialization_strategy="sobol",
        generator="BOTORCH_MODULAR",
        objective_thresholds={"f1": 1.0, "f2": 1.0},
        generator_kwargs={
            "botorch_acqf_class": "qLogNoisyExpectedHypervolumeImprovement",
            "surrogate_spec": {
                "model_configs": [{"botorch_model_class": "SingleTaskGP"}]
            },
        },
        generator_gen_kwargs={
            "model_gen_options": {
                "optimizer_kwargs": {"sequential": False, "num_restarts": 5}
            }
        },
        seed=42,
    )

    optimizer = AxOptimizer(
        search_space=_search_space(),
        config=config,
        objective_names=["f1", "f2"],
    )

    model_spec = optimizer.generation_strategy.nodes[1].generator_specs[0]
    assert model_spec.generator_kwargs["botorch_acqf_class"].__name__ == (
        "qLogNoisyExpectedHypervolumeImprovement"
    )
    assert isinstance(model_spec.generator_kwargs["surrogate_spec"], SurrogateSpec)
    assert optimizer.optimization_config.objective_thresholds[0].bound == 1.0
    assert model_spec.generator_gen_kwargs["model_gen_options"]["optimizer_kwargs"][
        "sequential"
    ] is False


@pytest.mark.skipif(
    not AX_NODE_RUNTIME_AVAILABLE,
    reason="Installed Ax runtime lacks required node-based generation APIs.",
)
def test_ax_optimizer_supports_center_initialization():
    """Test center initialization inserts a center node before Sobol."""
    config = AxOptimizerConfig(
        initialization_strategy="center",
        n_initial_samples=4,
        seed=42,
    )

    optimizer = AxOptimizer(
        search_space=_search_space(),
        config=config,
        objective_names=["loss"],
    )

    nodes = optimizer.generation_strategy.nodes
    assert nodes[0].__class__.__name__ == "CenterGenerationNode"
    assert nodes[1].name == "Sobol"
    assert nodes[1].transition_criteria[0].threshold == 3


@pytest.mark.skipif(
    not AX_NODE_RUNTIME_AVAILABLE,
    reason="Installed Ax runtime lacks required node-based generation APIs.",
)
def test_ax_optimizer_supports_uniform_initialization():
    """Test uniform initialization uses Ax's UNIFORM generator when available."""
    config = AxOptimizerConfig(
        initialization_strategy="uniform",
        n_initial_samples=5,
        seed=42,
    )

    optimizer = AxOptimizer(
        search_space=_search_space(),
        config=config,
        objective_names=["loss"],
    )

    first_node_enum = optimizer.generation_strategy.nodes[0].generator_specs[0].generator_enum
    assert first_node_enum in {Generators.UNIFORM, Generators.SOBOL}


@pytest.mark.skipif(
    not AX_NODE_RUNTIME_AVAILABLE,
    reason="Installed Ax runtime lacks required node-based generation APIs.",
)
def test_ax_optimizer_suggest_and_update():
    """Test basic suggest and update workflow."""
    config = AxOptimizerConfig(
        initialization_strategy="sobol",
        n_initial_samples=5,
        seed=42,
    )

    optimizer = AxOptimizer(
        search_space=_search_space(),
        config=config,
        objective_names=["loss"],
    )

    candidates = optimizer.suggest_candidates(n_candidates=3)
    assert len(candidates) == 3
    assert all("x" in c and "y" in c for c in candidates)

    for i, candidate in enumerate(candidates):
        optimizer.update_with_results(
            trial_index=i,
            parameters=candidate,
            metrics={"loss": 0.5 * i},
        )

    trials = optimizer.get_trials()
    assert len(trials) == 3
    assert all(t.status == "completed" for t in trials)

    best = optimizer.get_best_trial()
    assert best is not None
    assert best.metrics["loss"] == 0.0


@pytest.mark.skipif(
    not AX_NODE_RUNTIME_AVAILABLE,
    reason="Installed Ax runtime lacks required node-based generation APIs.",
)
def test_ax_optimizer_pareto_front_single_objective():
    """Test Pareto front for single objective returns best trial."""
    config = AxOptimizerConfig(seed=42)
    search_space = SearchSpace(
        parameters={"x": {"type": "range", "value": 0.5, "bounds": [0.0, 1.0]}}
    )

    optimizer = AxOptimizer(
        search_space=search_space,
        config=config,
        objective_names=["loss"],
    )

    candidates = optimizer.suggest_candidates(n_candidates=5)
    for i, candidate in enumerate(candidates):
        optimizer.update_with_results(
            trial_index=i,
            parameters=candidate,
            metrics={"loss": float(i)},
        )

    pareto_front = optimizer.get_pareto_front()
    assert len(pareto_front) == 1
    assert pareto_front[0].metrics["loss"] == 0.0


@pytest.mark.skipif(
    not AX_NODE_RUNTIME_AVAILABLE,
    reason="Installed Ax runtime lacks required node-based generation APIs.",
)
def test_ax_optimizer_serialize_deserialize():
    """Test state serialization and deserialization."""
    config = AxOptimizerConfig(
        seed=42,
        generator_kwargs={"botorch_acqf_class": "qLogNoisyExpectedImprovement"},
    )
    search_space = SearchSpace(
        parameters={"x": {"type": "range", "value": 0.5, "bounds": [0.0, 1.0]}}
    )

    optimizer = AxOptimizer(
        search_space=search_space,
        config=config,
        objective_names=["loss"],
    )

    candidates = optimizer.suggest_candidates(n_candidates=3)
    for i, candidate in enumerate(candidates):
        optimizer.update_with_results(
            trial_index=i,
            parameters=candidate,
            metrics={"loss": 0.1 * i},
        )

    state = optimizer.serialize_state()

    assert "search_space" in state
    assert "objective_names" in state
    assert "config" in state
    assert "trials" in state
    assert state["config"]["generator"] == "BOTORCH_MODULAR"
    assert state["config"]["generator_kwargs"]["botorch_acqf_class"] == (
        "qLogNoisyExpectedImprovement"
    )

    optimizer2 = AxOptimizer(
        search_space=search_space,
        config=config,
        objective_names=["loss"],
    )
    optimizer2.load_state(state)

    trials = optimizer2.get_trials()
    assert len(trials) == 3
    best = optimizer2.get_best_trial()
    assert best.metrics["loss"] == 0.0


def test_search_space_and_trial_classes():
    """Test SearchSpace and Trial data classes."""
    search_space = SearchSpace(
        parameters={
            "x": {"type": "range", "value": 0.5, "bounds": [0.0, 1.0]},
            "y": {"type": "choice", "value": "a", "choices": ["a", "b", "c"]},
        }
    )
    assert len(search_space.parameters) == 2
    assert "x" in search_space.parameters

    trial = Trial(
        index=0,
        parameters={"x": 0.5, "y": "a"},
        metrics={"loss": 0.1},
        status="completed",
    )
    assert trial.index == 0
    assert trial.status == "completed"
    assert trial.metadata == {}

    trial2 = Trial(
        index=1,
        parameters={"x": 0.3},
        metadata={"note": "test"},
    )
    assert trial2.metadata["note"] == "test"
    assert trial2.metrics is None


def test_search_space_rejects_legacy_parameter_shapes():
    """Legacy values/default coercions should no longer be accepted."""
    with pytest.raises(ValueError, match="retired key 'values'"):
        SearchSpace(
            parameters={"y": {"type": "choice", "value": "a", "values": ["a", "b"]}}
        )

    with pytest.raises(ValueError, match="explicit 'value'"):
        SearchSpace(parameters={"x": {"type": "range", "bounds": [0.0, 1.0]}})
