"""Extensible test suite for optimizer implementations.

This module provides an AbstractOptimizerTestSuite base class that any optimizer
implementation should extend and pass. This ensures consistent interface compliance
and behavior across all optimizer implementations.

Usage:
    >>> class TestMyOptimizer(AbstractOptimizerTestSuite):
    ...     @staticmethod
    ...     def create_optimizer(**kwargs):
    ...         return MyOptimizer(**kwargs)
    ...     
    ...     @staticmethod
    ...     def get_config_class():
    ...         return MyOptimizerConfig
    
Project: AID2E v0.0.0 - AI assisted Detector Design for EIC
Homepage: https://aid2e.github.io/aid2e-framework
Repository: https://github.com/aid2e/AID2E-framework.git
"""

import json
from abc import ABC, abstractmethod
from typing import Any, Dict
import numpy as np
import pytest

from aid2e.optimizers.base import BaseOptimizer, SearchSpace, Trial


class AbstractOptimizerTestSuite(ABC):
    """Abstract base class for testing optimizer implementations.
    
    Any optimizer implementation should subclass this and provide implementations
    for the abstract methods. This ensures that all optimizers comply with the
    BaseOptimizer interface and basic functionality requirements.
    
    Attributes:
        search_space: Common search space for testing.
        objective_names: Common objective names for testing.
    
    Examples:
        >>> class TestAxOptimizer(AbstractOptimizerTestSuite):
        ...     @staticmethod
        ...     def create_optimizer(**kwargs):
        ...         return AxOptimizer(**kwargs)
        ...     
        ...     @staticmethod
        ...     def get_config_class():
        ...         return AxOptimizerConfig
    
    Notes:
        Subclasses should not override test methods. Instead, they should
        implement the abstract methods to configure the test suite for
        their specific optimizer.
    """
    
    @staticmethod
    @abstractmethod
    def create_optimizer(
        search_space: SearchSpace,
        config: Any,
        objective_names: list,
        seed: int = 42
    ) -> BaseOptimizer:
        """Create an optimizer instance for testing.
        
        Args:
            search_space: Parameter search space definition.
            config: Optimizer configuration (e.g., AxOptimizerConfig).
            objective_names: List of objective names to optimize.
            seed: Random seed for reproducibility.
        
        Returns:
            Instance of the optimizer being tested.
        """
        pass
    
    @staticmethod
    @abstractmethod
    def get_config_class() -> type:
        """Get the configuration class for this optimizer.
        
        Returns:
            The Pydantic config class (e.g., AxOptimizerConfig).
        
        Examples:
            >>> return AxOptimizerConfig
        """
        pass
    
    @staticmethod
    def get_search_space() -> SearchSpace:
        """Get the search space to use for testing.
        
        Returns:
            A SearchSpace with simple 2D bounds suitable for testing.
        
        Notes:
            Override this method if your optimizer has special requirements
            for the search space.
        """
        return SearchSpace(
            parameters={
                "x": {"type": "range", "bounds": [0.0, 1.0]},
                "y": {"type": "range", "bounds": [0.0, 1.0]},
            }
        )
    
    @staticmethod
    def get_objective_names() -> list:
        """Get the objective names for testing.
        
        Returns:
            List of objective names (default: single objective for simplicity).
        
        Notes:
            Override this to test multi-objective optimization.
        """
        return ["loss"]
    
    def create_default_config(self) -> Any:
        """Create a default configuration for the optimizer.
        
        Returns:
            A valid configuration instance for the optimizer.
        """
        config_class = self.get_config_class()
        if config_class is None:
            raise NotImplementedError("get_config_class() must be implemented by subclass")
        return config_class()
    
    # ========== Test Methods ==========
    # These should NOT be overridden by subclasses
    
    def test_optimizer_initialization(self) -> None:
        """Test that optimizer initializes correctly."""
        search_space = self.get_search_space()
        config = self.create_default_config()
        objective_names = self.get_objective_names()
        
        optimizer = self.create_optimizer(
            search_space=search_space,
            config=config,
            objective_names=objective_names,
            seed=42
        )
        
        # Verify initialization
        assert isinstance(optimizer, BaseOptimizer)
        assert optimizer.n_objectives == len(objective_names)
        assert optimizer.seed == 42
        assert len(optimizer.search_space.parameters) == len(search_space.parameters)
    
    def test_optimizer_inherits_from_base(self) -> None:
        """Test that optimizer properly inherits from BaseOptimizer."""
        search_space = self.get_search_space()
        config = self.create_default_config()
        objective_names = self.get_objective_names()
        
        optimizer = self.create_optimizer(
            search_space=search_space,
            config=config,
            objective_names=objective_names
        )
        
        assert isinstance(optimizer, BaseOptimizer)
        assert hasattr(optimizer, 'suggest_candidates')
        assert hasattr(optimizer, 'update_with_results')
        assert hasattr(optimizer, 'get_pareto_front')
        assert hasattr(optimizer, 'get_best_trial')
        assert hasattr(optimizer, 'get_trials')
        assert hasattr(optimizer, 'serialize_state')
        assert hasattr(optimizer, 'load_state')
    
    def test_suggest_candidates(self) -> None:
        """Test that the optimizer can suggest candidate parameters."""
        search_space = self.get_search_space()
        config = self.create_default_config()
        objective_names = self.get_objective_names()
        
        optimizer = self.create_optimizer(
            search_space=search_space,
            config=config,
            objective_names=objective_names
        )
        
        # Suggest some candidates
        candidates = optimizer.suggest_candidates(n_candidates=3)
        
        # Verify structure
        assert isinstance(candidates, list)
        assert len(candidates) == 3
        
        for candidate in candidates:
            assert isinstance(candidate, dict)
            assert set(candidate.keys()) == set(search_space.parameters.keys())
            
            # Verify bounds
            for param_name, param_value in candidate.items():
                bounds = search_space.parameters[param_name].bounds
                assert bounds[0] <= param_value <= bounds[1]
    
    def test_update_with_results(self) -> None:
        """Test that the optimizer can update with trial results."""
        search_space = self.get_search_space()
        config = self.create_default_config()
        objective_names = self.get_objective_names()
        
        optimizer = self.create_optimizer(
            search_space=search_space,
            config=config,
            objective_names=objective_names
        )
        
        # Suggest candidates
        candidates = optimizer.suggest_candidates(n_candidates=2)
        
        # Update with results
        for i, candidate in enumerate(candidates):
            metrics = {obj: np.random.random() for obj in objective_names}
            optimizer.update_with_results(
                trial_index=i,
                parameters=candidate,
                metrics=metrics
            )
        
        # Verify trials were recorded
        trials = optimizer.get_trials()
        assert len(trials) == 2
        assert all(isinstance(t, Trial) for t in trials)
        assert all(t.status == "completed" for t in trials)
    
    def test_get_best_trial(self) -> None:
        """Test retrieving the best trial."""
        search_space = self.get_search_space()
        config = self.create_default_config()
        objective_names = self.get_objective_names()
        
        optimizer = self.create_optimizer(
            search_space=search_space,
            config=config,
            objective_names=objective_names
        )
        
        # Initially no trials
        best = optimizer.get_best_trial()
        assert best is None
        
        # Add some trials
        candidates = optimizer.suggest_candidates(n_candidates=3)
        metrics_list = [
            {"loss": 0.5},
            {"loss": 0.2},  # Best
            {"loss": 0.8},
        ]
        
        for i, candidate in enumerate(candidates):
            optimizer.update_with_results(
                trial_index=i,
                parameters=candidate,
                metrics=metrics_list[i]
            )
        
        # Verify best trial
        best = optimizer.get_best_trial()
        assert best is not None
        assert best.metrics["loss"] == 0.2
    
    def test_get_pareto_front_single_objective(self) -> None:
        """Test Pareto front computation for single-objective problems."""
        search_space = self.get_search_space()
        config = self.create_default_config()
        objective_names = self.get_objective_names()  # Single objective
        
        optimizer = self.create_optimizer(
            search_space=search_space,
            config=config,
            objective_names=objective_names
        )
        
        # Initially empty
        pareto = optimizer.get_pareto_front()
        assert len(pareto) == 0
        
        # Add trials
        candidates = optimizer.suggest_candidates(n_candidates=3)
        for i, candidate in enumerate(candidates):
            metrics = {objective_names[0]: float(i + 1)}
            optimizer.update_with_results(
                trial_index=i,
                parameters=candidate,
                metrics=metrics
            )
        
        # For single objective, Pareto front = best trial
        pareto = optimizer.get_pareto_front()
        assert len(pareto) == 1
        assert pareto[0].metrics[objective_names[0]] == 1.0
    
    def test_get_pareto_front_multi_objective(self) -> None:
        """Test Pareto front computation for multi-objective problems."""
        search_space = self.get_search_space()
        config = self.create_default_config()
        objective_names = ["f1", "f2"]
        
        optimizer = self.create_optimizer(
            search_space=search_space,
            config=config,
            objective_names=objective_names
        )
        
        # Add trials with known Pareto structure
        # Dominated: (1.0, 1.0)
        # Pareto: (0.5, 1.0), (1.0, 0.5), (0.3, 1.2)
        candidates = optimizer.suggest_candidates(n_candidates=4)
        metrics_list = [
            {"f1": 1.0, "f2": 1.0},  # Dominated
            {"f1": 0.5, "f2": 1.0},  # Pareto
            {"f1": 1.0, "f2": 0.5},  # Pareto
            {"f1": 0.3, "f2": 1.2},  # Pareto
        ]
        
        for i, candidate in enumerate(candidates):
            optimizer.update_with_results(
                trial_index=i,
                parameters=candidate,
                metrics=metrics_list[i]
            )
        
        pareto = optimizer.get_pareto_front()
        assert len(pareto) == 3  # One dominated solution excluded
    
    def test_serialize_and_load_state(self) -> None:
        """Test state serialization and loading."""
        search_space = self.get_search_space()
        config = self.create_default_config()
        objective_names = self.get_objective_names()
        
        optimizer = self.create_optimizer(
            search_space=search_space,
            config=config,
            objective_names=objective_names,
            seed=42
        )
        
        # Add some trials
        candidates = optimizer.suggest_candidates(n_candidates=3)
        for i, candidate in enumerate(candidates):
            metrics = {obj: np.random.random() for obj in objective_names}
            optimizer.update_with_results(
                trial_index=i,
                parameters=candidate,
                metrics=metrics
            )
        
        # Serialize state
        state = optimizer.serialize_state()
        
        # Verify state is JSON-serializable
        json_str = json.dumps(state)
        assert isinstance(json_str, str)
        assert len(json_str) > 0
        
        # Load state into new optimizer
        optimizer2 = self.create_optimizer(
            search_space=search_space,
            config=config,
            objective_names=objective_names,
            seed=42
        )
        optimizer2.load_state(state)
        
        # Verify trials were restored
        trials1 = optimizer.get_trials()
        trials2 = optimizer2.get_trials()
        assert len(trials1) == len(trials2)
        
        # Verify trial data matches
        for t1, t2 in zip(trials1, trials2):
            assert t1.index == t2.index
            assert t1.status == t2.status
            assert t1.parameters == t2.parameters
    
    def test_config_validation(self) -> None:
        """Test that configuration class validates inputs properly."""
        config_class = self.get_config_class()
        
        # Valid config should work
        config = config_class()
        assert config is not None
        
        # Test with custom parameters if config_class is Pydantic
        if hasattr(config_class, 'model_validate'):
            config_dict = {}
            config2 = config_class.model_validate(config_dict)
            assert config2 is not None


class TestAxOptimizer(AbstractOptimizerTestSuite):
    """Test suite for AxOptimizer implementation.
    
    This test class extends AbstractOptimizerTestSuite to test the Ax-based
    optimizer implementation. It provides the necessary configuration methods
    and can add Ax-specific tests if needed.
    """
    
    config_class = None
    
    @classmethod
    def setup_class(cls):
        """Setup test class by importing AxOptimizer."""
        from aid2e.optimizers.ax import AxOptimizer, AxOptimizerConfig
        cls.ax_optimizer_class = AxOptimizer
        cls.config_class = AxOptimizerConfig
    
    @staticmethod
    def create_optimizer(
        search_space: SearchSpace,
        config: Any,
        objective_names: list,
        seed: int = 42
    ) -> BaseOptimizer:
        """Create an AxOptimizer instance for testing."""
        from aid2e.optimizers.ax import AxOptimizer
        return AxOptimizer(
            search_space=search_space,
            config=config,
            objective_names=objective_names,
            seed=seed
        )
    
    @staticmethod
    def get_config_class() -> type:
        """Get the AxOptimizerConfig class."""
        from aid2e.optimizers.ax import AxOptimizerConfig
        return AxOptimizerConfig
