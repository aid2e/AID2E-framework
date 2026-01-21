"""Integration test for BaseOptimizer and AxOptimizer with AxOptimizerConfig."""

import pytest
from aid2e.optimizers import BaseOptimizer, SearchSpace, Trial, AxOptimizer, AxOptimizerConfig


def test_base_optimizer_is_abstract():
    """Test that BaseOptimizer cannot be instantiated directly."""
    search_space = SearchSpace(
        parameters={"x": {"type": "range", "bounds": [0.0, 1.0]}}
    )
    
    with pytest.raises(TypeError, match="Can't instantiate abstract class"):
        BaseOptimizer(search_space=search_space, n_objectives=1)


def test_ax_optimizer_inherits_from_base():
    """Test that AxOptimizer inherits from BaseOptimizer."""
    assert issubclass(AxOptimizer, BaseOptimizer)


def test_ax_optimizer_with_config():
    """Test AxOptimizer integrates properly with AxOptimizerConfig."""
    # Create config
    config = AxOptimizerConfig(
        initialization_strategy="sobol",
        surrogate_model="saasbo",
        acquisition_function="qnehvi",
        n_initial_samples=10,
        n_iterations=50,
        batch_size=5,
        seed=42
    )
    
    # Create search space
    search_space = SearchSpace(
        parameters={
            "x": {"type": "range", "bounds": [0.0, 1.0]},
            "y": {"type": "range", "bounds": [-1.0, 1.0]}
        }
    )
    
    # Create optimizer
    optimizer = AxOptimizer(
        search_space=search_space,
        config=config,
        objective_names=["loss", "time"]
    )
    
    # Verify attributes
    assert optimizer.n_objectives == 2
    assert optimizer.seed == 42
    assert optimizer.config.initialization_strategy == "sobol"
    assert optimizer.config.surrogate_model == "saasbo"
    assert optimizer.config.acquisition_function == "qnehvi"
    assert optimizer.objective_names == ["loss", "time"]


def test_ax_optimizer_suggest_and_update():
    """Test basic suggest and update workflow."""
    config = AxOptimizerConfig(
        initialization_strategy="sobol",
        surrogate_model="saasbo",
        n_initial_samples=5,
        seed=42
    )
    
    search_space = SearchSpace(
        parameters={
            "x": {"type": "range", "bounds": [0.0, 1.0]},
            "y": {"type": "range", "bounds": [0.0, 1.0]}
        }
    )
    
    optimizer = AxOptimizer(
        search_space=search_space,
        config=config,
        objective_names=["loss"]
    )
    
    # Suggest candidates
    candidates = optimizer.suggest_candidates(n_candidates=3)
    assert len(candidates) == 3
    assert all("x" in c and "y" in c for c in candidates)
    
    # Update with results
    for i, candidate in enumerate(candidates):
        optimizer.update_with_results(
            trial_index=i,
            parameters=candidate,
            metrics={"loss": 0.5 * i}
        )
    
    # Get trials
    trials = optimizer.get_trials()
    assert len(trials) == 3
    assert all(t.status == "completed" for t in trials)
    
    # Get best trial
    best = optimizer.get_best_trial()
    assert best is not None
    assert best.metrics["loss"] == 0.0  # First trial has lowest loss


def test_ax_optimizer_pareto_front_single_objective():
    """Test Pareto front for single objective returns best trial."""
    config = AxOptimizerConfig(seed=42)
    search_space = SearchSpace(
        parameters={"x": {"type": "range", "bounds": [0.0, 1.0]}}
    )
    
    optimizer = AxOptimizer(
        search_space=search_space,
        config=config,
        objective_names=["loss"]
    )
    
    # Add some trials
    candidates = optimizer.suggest_candidates(n_candidates=5)
    for i, candidate in enumerate(candidates):
        optimizer.update_with_results(
            trial_index=i,
            parameters=candidate,
            metrics={"loss": float(i)}
        )
    
    pareto_front = optimizer.get_pareto_front()
    assert len(pareto_front) == 1
    assert pareto_front[0].metrics["loss"] == 0.0


def test_ax_optimizer_serialize_deserialize():
    """Test state serialization and deserialization."""
    config = AxOptimizerConfig(seed=42)
    search_space = SearchSpace(
        parameters={"x": {"type": "range", "bounds": [0.0, 1.0]}}
    )
    
    optimizer = AxOptimizer(
        search_space=search_space,
        config=config,
        objective_names=["loss"]
    )
    
    # Run some trials
    candidates = optimizer.suggest_candidates(n_candidates=3)
    for i, candidate in enumerate(candidates):
        optimizer.update_with_results(
            trial_index=i,
            parameters=candidate,
            metrics={"loss": 0.1 * i}
        )
    
    # Serialize state
    state = optimizer.serialize_state()
    
    # Verify state structure
    assert "search_space" in state
    assert "objective_names" in state
    assert "config" in state
    assert "trials" in state
    assert len(state["trials"]) == 3
    
    # Create new optimizer and load state
    optimizer2 = AxOptimizer(
        search_space=search_space,
        config=config,
        objective_names=["loss"]
    )
    optimizer2.load_state(state)
    
    # Verify restored state
    trials = optimizer2.get_trials()
    assert len(trials) == 3
    best = optimizer2.get_best_trial()
    assert best.metrics["loss"] == 0.0


def test_search_space_and_trial_classes():
    """Test SearchSpace and Trial data classes."""
    # SearchSpace
    search_space = SearchSpace(
        parameters={
            "x": {"type": "range", "bounds": [0.0, 1.0]},
            "y": {"type": "choice", "values": ["a", "b", "c"]}
        }
    )
    assert len(search_space.parameters) == 2
    assert "x" in search_space.parameters
    
    # Trial
    trial = Trial(
        index=0,
        parameters={"x": 0.5, "y": "a"},
        metrics={"loss": 0.1},
        status="completed"
    )
    assert trial.index == 0
    assert trial.status == "completed"
    assert trial.metadata == {}  # Default value
    
    # Trial with metadata
    trial2 = Trial(
        index=1,
        parameters={"x": 0.3},
        metadata={"note": "test"}
    )
    assert trial2.metadata["note"] == "test"
    assert trial2.metrics is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
