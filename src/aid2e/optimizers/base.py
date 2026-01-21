"""Base optimizer abstractions for the AID2E framework.

This module defines reusable dataclasses and abstract interfaces that optimizers
use to consume design parameter definitions coming from the design configuration
layer. Search spaces are built from typed design parameters, and trials track
optimizer evaluations in a consistent structure.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Union

from aid2e.utilities.configurations.base_models import BaseParameter, parse_parameter
from aid2e.utilities.configurations.design_config import (
    DesignConfig,
    ParameterConstraint,
)


@dataclass
class SearchSpace:
    """Represent an optimization search space built from design parameters.

    Attributes:
        parameters: Mapping of parameter names to typed design parameters.
        constraints: Optional list of parameter constraints to enforce.
        name: Optional identifier for the search space.
        source_config: Optional originating DesignConfig for traceability.

    Examples:
        >>> from aid2e.utilities.configurations.base_models import RangeParameter
        >>> params = {
        ...     "x": RangeParameter(name="x", value=0.5, bounds=(0.0, 1.0)),
        ... }
        >>> space = SearchSpace(parameters=params)
        >>> space.validate({"x": 0.4})
        (True, [])
    """

    parameters: Dict[str, BaseParameter]
    constraints: List[ParameterConstraint] = field(default_factory=list)
    name: Optional[str] = None
    source_config: Optional[DesignConfig] = None

    def __post_init__(self) -> None:
        """Normalize parameter and constraint inputs after initialization."""
        parsed_parameters: Dict[str, BaseParameter] = {}
        for param_name, param in self.parameters.items():
            if isinstance(param, BaseParameter):
                parsed = param
            elif isinstance(param, dict):
                param_data = dict(param)
                if "values" in param_data and "choices" not in param_data:
                    param_data["choices"] = param_data.pop("values")
                if "bounds" in param_data and "value" not in param_data:
                    lower, _ = param_data["bounds"]
                    param_data["value"] = float(lower)
                if "choices" in param_data and "value" not in param_data:
                    first_choice = param_data["choices"][0]
                    param_data["value"] = first_choice
                parsed = parse_parameter(param_name, param_data)
            else:
                raise TypeError(
                    "Parameters must be BaseParameter instances or dictionaries"
                )

            if parsed.name != param_name:
                parsed = parsed.model_copy(update={"name": param_name})
            parsed_parameters[param_name] = parsed

        self.parameters = parsed_parameters

        constraints_input = self.constraints or []
        self.constraints = [
            c if isinstance(c, ParameterConstraint) else ParameterConstraint(**c)
            for c in constraints_input
        ]

    @classmethod
    def from_design_config(cls, design_config: DesignConfig) -> "SearchSpace":
        """Build a search space from a DesignConfig instance.

        Args:
            design_config: Fully validated design configuration containing
                parameters and optional parameter constraints.

        Returns:
            SearchSpace populated with flattened parameters and constraints.
        """

        return cls(
            parameters=design_config.get_flat_parameters(),
            constraints=design_config.parameter_constraints or [],
            name=getattr(design_config, "name", None),
            source_config=design_config,
        )

    def validate(self, param_values: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Check if parameter values satisfy all constraints (for non-Ax optimizers).

        This method is for optimizers that DON'T have native constraint support
        (e.g., random search, simple evolutionary algorithms). For optimizers
        with native constraint support (e.g., Ax), pass self.constraints directly
        to the optimizer instead of calling this method.

        Args:
            param_values: Mapping of qualified parameter names to concrete values.

        Returns:
            Tuple of ``(all_valid, failed_constraints)`` where ``all_valid`` is
            ``True`` when every constraint passes and ``failed_constraints``
            lists the names (or error strings) of failing constraints.

        Example:
            >>> # For optimizers WITHOUT constraint support
            >>> is_valid, failures = search_space.validate(candidate)
            >>> if not is_valid:
            ...     print(f"Constraint violations: {failures}")
            
            >>> # For Ax (HAS constraint support) - DON'T use this method
            >>> # Instead, pass search_space.constraints to Ax optimizer

        Notes:
            - Only use this for runtime checking with constraint-agnostic optimizers
            - Ax and similar optimizers handle constraints internally via self.constraints
            - Syntax validation already done at DesignConfig load time
        """

        if not self.constraints:
            return True, []

        failed: List[str] = []
        for constraint in self.constraints:
            try:
                if not constraint.evaluate(param_values):
                    failed.append(constraint.name)
            except Exception as exc:  # pragma: no cover - defensive logging
                failed.append(f"{constraint.name} (error: {exc})")

        return len(failed) == 0, failed


@dataclass
class Trial:
    """Capture the parameters and results of a single optimization trial.

    Attributes:
        index: Unique trial identifier within the optimizer.
        parameters: Parameter values evaluated during the trial.
        metrics: Objective values produced by evaluation (if available).
        metadata: Optional auxiliary metadata about the trial.
        status: Lifecycle status such as ``pending``, ``completed``, or ``failed``.

    Examples:
        >>> trial = Trial(
        ...     index=0,
        ...     parameters={"x": 0.5},
        ...     metrics={"loss": 0.1},
        ...     status="completed",
        ... )
        >>> trial.metadata
        {}
    """

    index: int
    parameters: Dict[str, Any]
    metrics: Optional[Dict[str, float]] = None
    metadata: Dict[str, Any] = None
    status: str = "pending"

    def __post_init__(self) -> None:
        """Ensure metadata is always a dictionary after initialization."""
        if self.metadata is None:
            self.metadata = {}


class BaseOptimizer(ABC):
    """Abstract base class for all AID2E optimizers.

    Subclasses must implement the abstract methods to suggest candidates, ingest
    evaluation results, and surface optimizer state. The interface is intentionally
    minimal to support a range of backends (Ax, genetic algorithms, grid search)
    while keeping a consistent contract for the rest of the framework.
    """

    def __init__(
        self,
        search_space: Union[SearchSpace, DesignConfig],
        n_objectives: int = 1,
        seed: Optional[int] = None,
    ) -> None:
        """Initialize the optimizer with a search space.

        Args:
            search_space: Typed search space or DesignConfig to optimize over.
            n_objectives: Number of objectives to optimize.
            seed: Optional seed for reproducibility.

        Raises:
            ValueError: If the search space is empty or the objective count is < 1.
        """

        resolved_space = (
            SearchSpace.from_design_config(search_space)
            if isinstance(search_space, DesignConfig)
            else search_space
        )

        if not resolved_space.parameters:
            raise ValueError("Search space cannot be empty")
        if n_objectives < 1:
            raise ValueError(f"n_objectives must be >= 1, got {n_objectives}")

        self.search_space = resolved_space
        self.n_objectives = n_objectives
        self.seed = seed
    
    @abstractmethod
    def suggest_candidates(self, n_candidates: int = 1) -> List[Dict[str, Any]]:
        """Suggest next parameter configurations to evaluate.
        
        Args:
            n_candidates: Number of candidates to suggest.
        
        Returns:
            List of parameter dictionaries, where each dictionary maps
            parameter names to their suggested values.
        
        Raises:
            RuntimeError: If optimizer is not properly initialized.
        
        Examples:
            >>> candidates = optimizer.suggest_candidates(n_candidates=5)
            >>> candidates[0]
            {'x': 0.5, 'y': 0.3, 'z': 2.1}
        
        Notes:
            The implementation should use the configured strategy
            (e.g., Sobol sampling, Bayesian optimization, genetic algorithms).
        """
        pass
    
    @abstractmethod
    def update_with_results(
        self,
        trial_index: int,
        parameters: Dict[str, Any],
        metrics: Dict[str, float]
    ) -> None:
        """Update optimizer with evaluation results from a trial.
        
        Args:
            trial_index: Unique identifier for the trial.
            parameters: Parameter values that were evaluated.
            metrics: Objective values obtained from evaluation.
                Keys are metric names, values are metric values.
        
        Raises:
            ValueError: If metrics don't match expected objectives.
        
        Examples:
            >>> optimizer.update_with_results(
            ...     trial_index=0,
            ...     parameters={'x': 0.5, 'y': 0.3},
            ...     metrics={'loss': 0.1, 'accuracy': 0.9}
            ... )
        
        Notes:
            After updating, the optimizer can use this information to
            suggest better candidates in subsequent calls to suggest_candidates().
        """
        pass
    
    @abstractmethod
    def get_pareto_front(self) -> List[Trial]:
        """Retrieve the current Pareto front of non-dominated solutions.
        
        Returns:
            List of Trial objects representing Pareto-optimal solutions.
            For single-objective optimization, returns the best trial.
        
        Examples:
            >>> pareto_front = optimizer.get_pareto_front()
            >>> for trial in pareto_front:
            ...     print(f"Params: {trial.parameters}, Metrics: {trial.metrics}")
        
        Notes:
            A solution is Pareto-optimal if no other solution is better
            in all objectives. This method is particularly useful for
            multi-objective optimization.
        """
        pass
    
    @abstractmethod
    def get_trials(self) -> List[Trial]:
        """Get all trials that have been evaluated.
        
        Returns:
            List of all Trial objects, including pending, completed, and failed.
        
        Examples:
            >>> trials = optimizer.get_trials()
            >>> completed_trials = [t for t in trials if t.status == "completed"]
            >>> print(f"Total trials: {len(trials)}")
        
        Notes:
            Trials are returned in the order they were created.
            This method is useful for analyzing optimization progress.
        """
        pass
    
    @abstractmethod
    def get_best_trial(self) -> Optional[Trial]:
        """Get the best trial found so far.
        
        Returns:
            Trial with the best objective value(s), or None if no trials
            have been completed. For multi-objective, returns a representative
            best trial from the Pareto front.
        
        Examples:
            >>> best = optimizer.get_best_trial()
            >>> if best:
            ...     print(f"Best parameters: {best.parameters}")
            ...     print(f"Best metrics: {best.metrics}")
        """
        pass
    
    @abstractmethod
    def serialize_state(self) -> Dict[str, Any]:
        """Serialize optimizer state for distributed execution or checkpointing.
        
        Returns:
            Dictionary containing all necessary state to reconstruct
            the optimizer. Should be JSON-serializable.
        
        Examples:
            >>> state = optimizer.serialize_state()
            >>> # Save to file or transmit to another worker
            >>> import json
            >>> with open('optimizer_state.json', 'w') as f:
            ...     json.dump(state, f)
        
        Notes:
            This is crucial for distributed optimization where optimizer
            state needs to be shared across workers or checkpointed.
        """
        pass
    
    @abstractmethod
    def load_state(self, state: Dict[str, Any]) -> None:
        """Load optimizer state from serialized form.
        
        Args:
            state: Dictionary containing serialized optimizer state,
                as returned by serialize_state().
        
        Raises:
            ValueError: If state is invalid or incompatible.
        
        Examples:
            >>> import json
            >>> with open('optimizer_state.json', 'r') as f:
            ...     state = json.load(f)
            >>> optimizer.load_state(state)
        
        Notes:
            After loading state, the optimizer should be able to continue
            optimization as if it never stopped.
        """
        pass
    
    def __repr__(self) -> str:
        """Return string representation of the optimizer.
        
        Returns:
            String describing the optimizer configuration.
        """
        return (
            f"{self.__class__.__name__}("
            f"n_params={len(self.search_space.parameters)}, "
            f"n_objectives={self.n_objectives}, "
            f"seed={self.seed}"
            f")"
        )
