"""Ax-based Bayesian optimizer for AID2E framework.

This module provides the AxOptimizer class that integrates with AxOptimizerConfig
and implements the BaseOptimizer interface for multi-objective Bayesian optimization.
"""

from typing import List, Dict, Any, Optional, TYPE_CHECKING, Union
import logging
import numpy as np

logger = logging.getLogger(__name__)

# Import Ax components (lazy to avoid import errors if Ax not installed)
try:
    import ax
    from ax.core.experiment import Experiment
    from ax.core.search_space import SearchSpace as AxSearchSpace
    from ax.core.parameter import ChoiceParameter as AxChoiceParameter
    from ax.core.parameter import ParameterType, RangeParameter as AxRangeParameter
    from ax.core.parameter_constraint import (
        ParameterConstraint as AxParameterConstraint,
        SumConstraint as AxSumConstraint,
    )
    from ax.core.objective import MultiObjective, Objective
    from ax.core.optimization_config import MultiObjectiveOptimizationConfig, OptimizationConfig
    from ax.core.metric import Metric
    from ax.core.arm import Arm
    from ax.generation_strategy.generation_strategy import GenerationStrategy, GenerationStep
    from ax.modelbridge.registry import Generators
    AX_AVAILABLE = True
except ImportError as e:
    AX_AVAILABLE = False
    # Create type stubs when Ax is not available
    if TYPE_CHECKING:
        from ax.core.experiment import Experiment
        from ax.core.search_space import SearchSpace as AxSearchSpace
        from ax.core.optimization_config import OptimizationConfig
        from ax.generation_strategy.generation_strategy import GenerationStrategy
    else:
        AxSearchSpace = None
        OptimizationConfig = None
        GenerationStrategy = None
    logger.warning(f"Ax not available: {e}. Install with: pip install ax-platform==1.0.0")

from aid2e.optimizers.base import BaseOptimizer, SearchSpace, Trial
from aid2e.utilities.configurations.base_models import (
    ChoiceParameter as DesignChoiceParameter,
    RangeParameter as DesignRangeParameter,
)
from aid2e.utilities.configurations.design_config import DesignConfig
from .config import AxOptimizerConfig


class AxOptimizer(BaseOptimizer):
    """Ax-based Bayesian optimization for multi-objective optimization.
    
    This optimizer uses the Ax platform for Bayesian optimization with
    support for multiple objectives and advanced acquisition functions.
    Implements the BaseOptimizer interface for consistency with other optimizers.
    
    Attributes:
        config: AxOptimizerConfig instance with strategy settings.
        objective_names: List of objective metric names.
        experiment: Ax Experiment object managing trials.
        generation_strategy: Ax GenerationStrategy for candidate generation.
    
    Examples:
        >>> from aid2e.optimizers.ax import AxOptimizer, AxOptimizerConfig
        >>> search_space = SearchSpace(
        ...     parameters={
        ...         "x": {"type": "range", "bounds": [0.0, 1.0]},
        ...         "y": {"type": "range", "bounds": [0.0, 1.0]}
        ...     }
        ... )
        >>> config = AxOptimizerConfig(
        ...     initialization_strategy="sobol",
        ...     surrogate_model="saasbo",
        ...     acquisition_function="qnehvi"
        ... )
        >>> optimizer = AxOptimizer(
        ...     search_space=search_space,
        ...     config=config,
        ...     objective_names=["loss", "time"]
        ... )
    
    Notes:
        This implementation uses Ax 1.0.0 with Sobol initialization,
        SAASBO surrogate modeling, and qNEHVI acquisition for multi-objective
        Bayesian optimization. It properly integrates with AxOptimizerConfig
        for configuration management.
        
        Project: AID2E v0.0.1 - AI assisted Detector Design for EIC
        Homepage: https://aid2e.github.io/AID2E-framework
        Repository: https://github.com/aid2e/AID2E-framework.git
    """
    
    def __init__(
        self,
        search_space: Union[SearchSpace, DesignConfig],
        config: AxOptimizerConfig,
        objective_names: List[str],
        seed: Optional[int] = None
    ):
        """Initialize the Ax optimizer.
        
        Args:
            search_space: Parameter search space definition.
            config: AxOptimizerConfig instance with strategy settings.
            objective_names: List of objective metric names to optimize.
            seed: Random seed for reproducibility (overrides config.seed if provided).
        
        Raises:
            ImportError: If Ax is not installed.
            ValueError: If search_space is empty or config is invalid.
        
        Notes:
            The optimizer is initialized but not yet ready to suggest candidates.
            Ax Experiment and GenerationStrategy are created lazily on first use.
        """
        if not AX_AVAILABLE:
            raise ImportError(
                "Ax is required but not installed. "
                "Install with: pip install ax-platform==1.0.0"
            )
        
        # Initialize base class (handles DesignConfig → SearchSpace conversion)
        super().__init__(
            search_space=search_space,
            n_objectives=len(objective_names),
            seed=seed if seed is not None else config.seed,
        )

        self.config = config
        self.objective_names = objective_names
        
        # Validate Ax version
        ax_version = getattr(ax, '__version__', '1.0.0')
        if ax_version != '1.0.0' and hasattr(ax, '__version__'):
            logger.warning(
                f"Expected Ax 1.0.0, found {ax_version}. "
                "This may cause compatibility issues."
            )
        
        # Create Ax search space
        self.ax_search_space = self._create_ax_search_space()
        
        # Create optimization config
        self.optimization_config = self._create_optimization_config()
        
        # Create Ax experiment
        self.experiment = Experiment(
            name=f"aid2e_optimization",
            search_space=self.ax_search_space,
            optimization_config=self.optimization_config
        )
        
        # Create generation strategy
        self.generation_strategy = self._create_generation_strategy()
        
        # Track trials
        self._trials: List[Trial] = []
        self._trial_counter = 0
        
        logger.info(
            f"AxOptimizer initialized: {len(self.search_space.parameters)} params, "
            f"{len(objective_names)} objectives, strategy={config.initialization_strategy}, "
            f"model={config.surrogate_model}, acq={config.acquisition_function}"
        )
    
    def _parse_constraint_to_ax(
        self, constraint
    ) -> Optional[Union[AxParameterConstraint, AxSumConstraint]]:
        """Parse a ParameterConstraint rule to an Ax constraint object.
        
        Args:
            constraint: The ParameterConstraint from design_config.
            
        Returns:
            Ax constraint object (ParameterConstraint or SumConstraint), or None if parsing fails.
            
        Notes:
            Ax ParameterConstraint supports linear constraints of the form:
                sum(w_i * param_i) <= bound
            
            This method attempts to parse simple sum constraints like "x + y <= 1.5"
            into Ax's format. More complex expressions may not be supported.
        """
        import re
        
        rule = constraint.rule
        
        # Try to parse sum constraints: "param1 + param2 + ... <= bound" or "param1 + param2 + ... < bound"
        # Also handle >= and > by negating
        
        # Pattern: captures parameters, operator, and bound
        # Example: "DTLZ2.x1 + DTLZ2.x2 <= 1.5"
        pattern = r'^([^<>=]+)\s*([<>]=?)\s*([\d.]+)$'
        match = re.match(pattern, rule.strip())
        
        if not match:
            logger.warning(
                f"Constraint '{constraint.name}' has unsupported format: {rule}. "
                "Only simple sum constraints are supported (e.g., 'x + y <= 1.5')."
            )
            return None
        
        lhs, operator, bound_str = match.groups()
        bound = float(bound_str)
        
        # Parse left-hand side to extract parameters and coefficients
        # For now, only handle simple addition with coefficient 1
        # Pattern: param_name optionally preceded by + or -
        param_pattern = r'([+-]?)\s*([a-zA-Z_][a-zA-Z0-9_.]*)'
        terms = re.findall(param_pattern, lhs)
        
        if not terms:
            logger.warning(
                f"Constraint '{constraint.name}': Could not parse parameters from: {lhs}"
            )
            return None
        
        # Build constraint_dict: {param_name: coefficient}
        constraint_dict = {}
        for sign, param_name in terms:
            coeff = 1.0 if sign != '-' else -1.0
            constraint_dict[param_name.strip()] = coeff
        
        # Determine if upper or lower bound based on operator
        # sum <= bound or sum < bound: upper bound
        # sum >= bound or sum > bound: flip to -sum <= -bound (upper bound with negated coeffs)
        if operator in ['<=', '<']:
            is_upper_bound = True
        elif operator in ['>=', '>']:
            # Convert sum >= bound to -sum <= -bound
            is_upper_bound = True
            constraint_dict = {k: -v for k, v in constraint_dict.items()}
            bound = -bound
        else:
            logger.warning(f"Unsupported operator in constraint: {operator}")
            return None
        
        # Check if all coefficients are the same (typically 1.0 for sum constraints)
        coeffs = list(constraint_dict.values())
        if all(c == coeffs[0] for c in coeffs) and coeffs[0] == 1.0:
            # Use SumConstraint for simple sum constraints
            # Note: SumConstraint requires Parameter objects, not just names
            # We'll use ParameterConstraint instead which takes names
            pass
        
        try:
            # Create Ax ParameterConstraint
            # ParameterConstraint(constraint_dict={param: coeff}, bound=value)
            ax_constraint = AxParameterConstraint(
                constraint_dict=constraint_dict,
                bound=bound
            )
            logger.debug(
                f"Converted constraint '{constraint.name}' to Ax format: "
                f"{constraint_dict} <= {bound}"
            )
            return ax_constraint
        except Exception as e:
            logger.warning(
                f"Failed to create Ax constraint for '{constraint.name}': {e}"
            )
            return None
    
    def _create_ax_search_space(self) -> AxSearchSpace:
        """Create an Ax SearchSpace from the typed SearchSpace parameters.

        Returns:
            Ax SearchSpace describing the optimization domain with constraints.

        Raises:
            ValueError: If a parameter type is not supported by the Ax backend.

        Notes:
            Constraints from search_space.constraints are automatically converted
            to Ax ParameterConstraint objects and included in the search space.
        """

        ax_params = []
        for param_name, param in self.search_space.parameters.items():
            if isinstance(param, DesignRangeParameter):
                lower, upper = param.bounds
                ax_params.append(
                    AxRangeParameter(
                        name=param_name,
                        parameter_type=ParameterType.FLOAT,
                        lower=float(lower),
                        upper=float(upper),
                    )
                )
            elif isinstance(param, DesignChoiceParameter):
                ax_params.append(
                    AxChoiceParameter(
                        name=param_name,
                        parameter_type=ParameterType.STRING,
                        values=list(param.choices),
                        is_ordered=False,
                    )
                )
            else:
                raise ValueError(
                    f"Unsupported parameter type for Ax: {param.__class__.__name__}"
                )

        # Convert design constraints to Ax parameter constraints
        ax_constraints = []
        for constraint in self.search_space.constraints:
            ax_constraint = self._parse_constraint_to_ax(constraint)
            if ax_constraint is not None:
                ax_constraints.append(ax_constraint)
                logger.debug(f"Added constraint '{constraint.name}': {constraint.rule}")

        return AxSearchSpace(
            parameters=ax_params,
            parameter_constraints=ax_constraints if ax_constraints else None
        )
    
    def _create_optimization_config(self):
        """Create Ax optimization configuration for multi-objective optimization.
        
        Returns:
            Ax OptimizationConfig or None for single objective.
        """
        if len(self.objective_names) == 1:
            # Single objective case
            return OptimizationConfig(
                objective=Objective(
                    metric=Metric(name=self.objective_names[0]),
                    minimize=True
                )
            )
        else:
            # Multi-objective case
            objectives = [
                Objective(metric=Metric(name=name), minimize=True)
                for name in self.objective_names
            ]
            return MultiObjectiveOptimizationConfig(
                objective=MultiObjective(objectives=objectives)
            )
    
    def _create_generation_strategy(self):
        """Create Ax GenerationStrategy based on config.
        
        Returns:
            Ax GenerationStrategy configured with Sobol + SAASBO/GPEI.
        
        Notes:
            Strategy has two steps:
            1. Sobol initialization for n_initial_samples
            2. Model-based optimization (SAASBO or GPEI) for remaining iterations
        """
        steps = []
        
        # Step 1: Sobol initialization
        if self.config.initialization_strategy.lower() == "sobol":
            steps.append(
                GenerationStep(
                    model=Generators.SOBOL,
                    num_trials=self.config.n_initial_samples,
                    max_parallelism=self.config.batch_size
                )
            )
        
        # Step 2: Model-based optimization
        if self.config.surrogate_model.lower() == "saasbo":
            model = Generators.SAASBO
        else:
            # Default to GPEI for other cases
            model = Generators.GPEI
        
        steps.append(
            GenerationStep(
                model=model,
                num_trials=-1,  # Run indefinitely after Sobol
                max_parallelism=self.config.batch_size
            )
        )
        
        return GenerationStrategy(steps=steps)
    
    def suggest_candidates(self, n_candidates: int = 1) -> List[Dict[str, Any]]:
        """Suggest the next batch of parameter configurations to evaluate.

        Args:
            n_candidates: Number of candidates to generate.

        Returns:
            List of parameter dictionaries ready for evaluation.

        Notes:
            Constraints are handled natively by Ax when present in search_space.
            Ax enforces constraints during candidate generation automatically.
            
            IMPLEMENTATION NOTE: This method generates n_candidates in a single
            call to generation_strategy.gen(), but creates n separate trials
            (one per candidate). While Ax supports batch trials natively, we use
            individual trials for API simplicity - each evaluation gets its own
            trial_index. This approach trades batch optimization benefits for
            clearer sequential evaluation semantics that match the typical
            optimization loop pattern.
            
            The GenerationStrategy still properly tracks progress: after
            n_initial_samples individual trials complete (regardless of how
            they were generated), it automatically switches from Sobol to BO.
        """

        # Generate n candidates using the generation strategy
        # After n_initial_samples trials are completed (tracked in experiment),
        # this will automatically switch from Sobol to SAASBO/GPEI
        generator_run = self.generation_strategy.gen(
            experiment=self.experiment,
            n=n_candidates,
        )

        # Create individual trials for each arm
        # This allows simple sequential evaluation: suggest() → evaluate() → update()
        candidates = []
        for arm in generator_run.arms:
            # For each arm, create a single-arm trial
            # We create a minimal generator_run for this specific arm
            from ax.core.generator_run import GeneratorRun
            
            single_arm_gr = GeneratorRun(
                arms=[arm],
                weights=[1.0],
            )
            # Copy over critical metadata from the original generator_run
            single_arm_gr._model_key = generator_run._model_key
            
            trial = self.experiment.new_trial(generator_run=single_arm_gr)
            trial.mark_running(no_runner_required=True)
            candidates.append(dict(arm.parameters))

        logger.debug(
            "Generated %d candidates using %s (trials %d-%d, step=%d)",
            n_candidates,
            getattr(generator_run, '_model_key', 'unknown'),
            len(self.experiment.trials) - n_candidates,
            len(self.experiment.trials) - 1,
            self.generation_strategy.current_step_index
        )
        return candidates
    
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
        
        Examples:
            >>> optimizer.update_with_results(
            ...     trial_index=0,
            ...     parameters={'x': 0.5, 'y': 0.3},
            ...     metrics={'loss': 0.1, 'accuracy': 0.9}
            ... )
        
        Notes:
            Completes the trial in Ax experiment and attaches data.
            This allows the surrogate model to learn from the evaluation.
        """
        # Validate metrics
        for obj_name in self.objective_names:
            if obj_name not in metrics:
                raise ValueError(
                    f"Missing objective '{obj_name}' in metrics. "
                    f"Expected: {self.objective_names}, got: {list(metrics.keys())}"
                )
        
        # Get the trial from experiment
        if trial_index < len(self.experiment.trials):
            trial = self.experiment.trials[trial_index]
            
            # Complete the trial with data
            trial.mark_completed()
            
            # Attach data to experiment
            from ax.core.data import Data
            import pandas as pd
            
            data_rows = []
            for metric_name, metric_value in metrics.items():
                if metric_name in self.objective_names:
                    data_rows.append({
                        'trial_index': trial_index,
                        'metric_name': metric_name,
                        'arm_name': trial.arm.name if trial.arm else f"arm_{trial_index}",
                        'mean': float(metric_value),
                        'sem': 0.0  # Standard error of mean (0 for deterministic)
                    })
            
            if data_rows:
                df = pd.DataFrame(data_rows)
                data = Data(df=df)
                self.experiment.attach_data(data)
        
        # Update internal trial tracking
        trial_obj = Trial(
            index=trial_index,
            parameters=parameters,
            metrics=metrics,
            status="completed"
        )
        
        # Update or append trial
        while len(self._trials) <= trial_index:
            self._trials.append(None)
        self._trials[trial_index] = trial_obj
        self._trial_counter = max(self._trial_counter, trial_index + 1)
        
        logger.debug(
            f"Updated trial {trial_index} with {len(metrics)} metrics"
        )
    
    def get_pareto_front(self) -> List[Trial]:
        """Retrieve the current Pareto front of non-dominated solutions.
        
        Returns:
            List of Trial objects representing Pareto-optimal solutions.
        
        Notes:
            For single-objective, returns the best trial.
            For multi-objective, computes Pareto front from all completed trials.
        """
        completed_trials = [t for t in self._trials if t and t.status == "completed"]
        
        if not completed_trials:
            return []
        
        if self.n_objectives == 1:
            # Single objective: return best trial
            best_trial = min(
                completed_trials,
                key=lambda t: t.metrics[self.objective_names[0]]
            )
            return [best_trial]
        
        # Multi-objective: compute Pareto front
        pareto_front = []
        for trial in completed_trials:
            is_dominated = False
            for other_trial in completed_trials:
                if trial == other_trial:
                    continue
                
                # Check if trial is dominated by other_trial
                better_in_all = True
                better_in_at_least_one = False
                
                for obj_name in self.objective_names:
                    trial_val = trial.metrics[obj_name]
                    other_val = other_trial.metrics[obj_name]
                    
                    if trial_val < other_val:
                        better_in_all = False
                    elif trial_val > other_val:
                        better_in_at_least_one = True
                
                if better_in_all and better_in_at_least_one:
                    is_dominated = True
                    break
            
            if not is_dominated:
                pareto_front.append(trial)
        
        return pareto_front
    
    def get_trials(self) -> List[Trial]:
        """Get all trials that have been evaluated.
        
        Returns:
            List of all Trial objects.
        """
        return [t for t in self._trials if t is not None]
    
    def get_best_trial(self) -> Optional[Trial]:
        """Get the best trial found so far.
        
        Returns:
            Trial with the best objective value, or None if no trials completed.
        """
        pareto_front = self.get_pareto_front()
        if not pareto_front:
            return None
        
        # For single objective, return the best
        # For multi-objective, return first from Pareto front
        return pareto_front[0]
    
    def serialize_state(self) -> Dict[str, Any]:
        """Serialize optimizer state for distributed execution.
        
        Returns:
            Dictionary containing all necessary state to reconstruct the optimizer.
        
        Examples:
            >>> state = optimizer.serialize_state()
            >>> json.dumps(state)  # Should be JSON-serializable
        """
        space_payload = {
            name: param.model_dump()
            for name, param in self.search_space.parameters.items()
        }
        constraints_payload = [
            constraint.model_dump()
            for constraint in self.search_space.constraints
        ]

        return {
            "search_space": {
                "parameters": space_payload,
                "constraints": constraints_payload,
                "name": self.search_space.name,
            },
            "n_objectives": self.n_objectives,
            "seed": self.seed,
            "objective_names": self.objective_names,
            "config": {
                "initialization_strategy": self.config.initialization_strategy,
                "surrogate_model": self.config.surrogate_model,
                "acquisition_function": self.config.acquisition_function,
                "n_initial_samples": self.config.n_initial_samples,
                "n_iterations": self.config.n_iterations,
                "batch_size": self.config.batch_size,
                "seed": self.config.seed
            },
            "trials": [
                {
                    "index": t.index,
                    "parameters": t.parameters,
                    "metrics": t.metrics,
                    "status": t.status,
                    "metadata": t.metadata
                }
                for t in self._trials if t is not None
            ],
            "trial_counter": self._trial_counter
        }
    
    def load_state(self, state: Dict[str, Any]) -> None:
        """Load optimizer state from serialized form.
        
        Args:
            state: Dictionary containing serialized optimizer state.
        
        Raises:
            ValueError: If state is invalid or incompatible.
        
        Notes:
            This recreates the Ax experiment and generation strategy,
            then replays all trials to restore the optimizer state.
        """
        # Validate state
        required_keys = ["search_space", "objective_names", "config", "trials"]
        for key in required_keys:
            if key not in state:
                raise ValueError(f"Missing required key in state: {key}")

        # Restore config and objective metadata
        self.config = AxOptimizerConfig(**state["config"])
        self.objective_names = list(state["objective_names"])

        # Rebuild search space and Ax components from serialized payload
        saved_space = state["search_space"] or {}
        parameters_payload = saved_space.get("parameters", saved_space)
        constraints_payload = saved_space.get("constraints", [])

        self.search_space = SearchSpace(
            parameters=parameters_payload,
            constraints=constraints_payload,
            name=saved_space.get("name"),
        )

        self.ax_search_space = self._create_ax_search_space()
        self.optimization_config = self._create_optimization_config()
        self.experiment = Experiment(
            name="aid2e_optimization",
            search_space=self.ax_search_space,
            optimization_config=self.optimization_config,
        )
        self.generation_strategy = self._create_generation_strategy()
        
        # Restore trials
        self._trials = []
        for trial_data in state["trials"]:
            trial = Trial(
                index=trial_data["index"],
                parameters=trial_data["parameters"],
                metrics=trial_data.get("metrics"),
                status=trial_data.get("status", "pending"),
                metadata=trial_data.get("metadata", {})
            )
            
            while len(self._trials) <= trial.index:
                self._trials.append(None)
            self._trials[trial.index] = trial
            
            # Replay trial in Ax experiment if completed
            if trial.status == "completed" and trial.metrics:
                # Create trial in Ax
                ax_trial = self.experiment.new_trial()
                ax_trial.mark_running(no_runner_required=True)
                
                # Update with results
                self.update_with_results(
                    trial_index=trial.index,
                    parameters=trial.parameters,
                    metrics=trial.metrics
                )
        
        self._trial_counter = state.get("trial_counter", len(self._trials))
        
        logger.info(f"Loaded optimizer state with {len(self._trials)} trials")
    
    def __repr__(self) -> str:
        """Return string representation of the optimizer.
        
        Returns:
            String describing the optimizer configuration.
        """
        return (
            f"AxOptimizer("
            f"n_params={len(self.search_space.parameters)}, "
            f"n_objectives={self.n_objectives}, "
            f"strategy={self.config.initialization_strategy}, "
            f"model={self.config.surrogate_model}, "
            f"acq={self.config.acquisition_function}, "
            f"seed={self.seed}"
            f")"
        )
