"""Ax-based Bayesian optimizer for AID2E framework."""

from copy import deepcopy
from typing import List, Dict, Any, Optional, TYPE_CHECKING, Union
import logging, sys
import numpy as np

logger = logging.getLogger(__name__)

# Import Ax components (lazy to avoid import errors if Ax not installed)
try:
    import ax
    from ax.core.experiment import Experiment
    from ax.core.search_space import SearchSpace as AxSearchSpace
    from ax.core.parameter import ChoiceParameter as AxChoiceParameter
    from ax.core.parameter import ParameterType, RangeParameter as AxRangeParameter
    from ax.core.parameter_constraint import ParameterConstraint as AxParameterConstraint
    try:
        from ax.core.parameter_constraint import SumConstraint as AxSumConstraint
    except ImportError:
        AxSumConstraint = None
    from ax.core.objective import MultiObjective, Objective
    from ax.core.optimization_config import MultiObjectiveOptimizationConfig, OptimizationConfig
    from ax.core.metric import Metric
    from ax.core.outcome_constraint import ComparisonOp, ObjectiveThreshold
    from ax.generation_strategy.generation_strategy import GenerationStrategy
    try:
        from ax.generation_strategy.center_generation_node import CenterGenerationNode
        from ax.generation_strategy.transition_criterion import MinTrials
        from ax.generation_strategy.generation_node import GenerationNode
        from ax.generation_strategy.generator_spec import GeneratorSpec
        # Treat successful imports as the compatibility gate. In the Ax build
        # shipped in env_AID2E, the node-based APIs exist and work even though
        # `GenerationStrategy` does not expose `nodes` as a class attribute.
        AX_NODE_STRATEGY_AVAILABLE = True
    except ImportError:
        CenterGenerationNode = None
        MinTrials = None
        GenerationNode = None
        GeneratorSpec = None
        AX_NODE_STRATEGY_AVAILABLE = False
    from ax.adapter.registry import Generators
    AX_AVAILABLE = True
except ImportError as e:
    AX_AVAILABLE = False
    # Create type stubs when Ax is not available
    if TYPE_CHECKING:
        from ax.core.experiment import Experiment
        from ax.core.search_space import SearchSpace as AxSearchSpace
        from ax.core.optimization_config import OptimizationConfig
        from ax.generation_strategy.generation_strategy import GenerationStrategy
        from ax.core.parameter_constraint import (
            ParameterConstraint as AxParameterConstraint,
            SumConstraint as AxSumConstraint,
        )
    else:
        AxSearchSpace = None
        OptimizationConfig = None
        GenerationStrategy = None
        AxParameterConstraint = None
        AxSumConstraint = None
        CenterGenerationNode = None
        MinTrials = None
        GenerationNode = None
        GeneratorSpec = None
        AX_NODE_STRATEGY_AVAILABLE = False
    logger.warning(f"Ax not available: {e}. Install with: pip install ax-platform==1.0.0")

from aid2e.optimizers.base import (
    BaseOptimizer,
    SearchSpace,
    Trial,
    TRIAL_STATUS_SUGGESTED,
)
from aid2e.utilities.configurations.base_models import (
    ChoiceParameter as DesignChoiceParameter,
    RangeParameter as DesignRangeParameter,
)
from aid2e.utilities.configurations.design_config import DesignConfig
from ._resolver import resolve_generator_kwargs
from .config import AxOptimizerConfig


class AxOptimizer(BaseOptimizer):
    """Ax-based Bayesian optimization for multi-objective optimization.
    
    This optimizer uses the Ax platform for Bayesian optimization with
    support for multiple objectives and native Ax Modular BoTorch generation.
    
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
        ...     generator="BOTORCH_MODULAR"
        ... )
        >>> optimizer = AxOptimizer(
        ...     search_space=search_space,
        ...     config=config,
        ...     objective_names=["loss", "time"]
        ... )
    
    Notes:
        This implementation defaults to a native Ax node-based generation
        strategy that transitions from an initializer node into
        ``Generators.BOTORCH_MODULAR``.
        
        Project: AID2E v0.0.1 - AI assisted Detector Design for EIC
        Homepage: https://aid2e.github.io/AID2E-framework
        Repository: https://github.com/aid2e/AID2E-framework.git
    """
    
    def __init__(
        self,
        search_space: Union[SearchSpace, DesignConfig],
        config: AxOptimizerConfig,
        objective_names: List[str],
        seed: Optional[int] = None,
        objective_directions: Optional[Dict[str, Any]] = None,
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
        if not AX_NODE_STRATEGY_AVAILABLE:
            raise RuntimeError(
                "The installed Ax runtime does not support the node-based "
                "generation API required by AID2E. Upgrade Ax to a version "
                "that provides CenterGenerationNode, GenerationNode, "
                "GeneratorSpec, and MinTrials."
            )
        
        # Initialize base class (handles DesignConfig → SearchSpace conversion)
        super().__init__(
            search_space=search_space,
            objective_names=objective_names,
            objective_directions=objective_directions,
            seed=seed if seed is not None else config.seed,
        )

        self.config = config
        # self.objective_names and self.n_objectives are inherited from BaseOptimizer
        
        # TODO Version check removed for now, re-enable when ready
        
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
        # self._trials and self._trial_counter are owned by BaseOptimizer
        
        logger.info(
            f"AxOptimizer initialized: {len(self.search_space.parameters)} params, "
            f"{len(objective_names)} objectives, strategy={config.initialization_strategy}, "
            f"generator={config.generator}"
        )
    
    def _parse_constraint_to_ax(
        self, constraint
    ) -> Optional[Any]:
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
        
        strict_epsilon = sys.float_info.epsilon # this is the smallest representable positive number such that 1.0 + eps != 1.0, used to convert strict inequalities to non-strict

        # Determine if upper or lower bound based on operator
        # sum <= bound or sum < bound: upper bound
        # sum >= bound or sum > bound: flip to -sum <= -bound (upper bound with negated coeffs)
        if operator in ['<=', '<']:
            is_upper_bound = True
            if operator == '<':
                bound -= strict_epsilon
        elif operator in ['>=', '>']:
            # Convert sum >= bound to -sum <= -bound
            is_upper_bound = True
            constraint_dict = {k: -v for k, v in constraint_dict.items()}
            bound = -bound
            if operator == '>':
                bound -= strict_epsilon
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
            terms_rendered = []
            for param_name, coeff in constraint_dict.items():
                if coeff == 1.0:
                    terms_rendered.append(param_name)
                elif coeff == -1.0:
                    terms_rendered.append(f"-{param_name}")
                else:
                    terms_rendered.append(f"{coeff}*{param_name}")

            inequality = " + ".join(terms_rendered).replace("+ -", "- ")
            inequality = f"{inequality} <= {bound}"
            ax_constraint = AxParameterConstraint(inequality=inequality)
            logger.debug(
                f"Converted constraint '{constraint.name}' to Ax format: "
                f"{inequality}"
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
            name = self.objective_names[0]
            direction = getattr(
                self.objective_directions.get(name),
                "value",
                self.objective_directions.get(name, "minimize"),
            )
            minimize = str(direction).lower() != "maximize"
            return OptimizationConfig(
                objective=Objective(
                    metric=Metric(name=name, lower_is_better=minimize),
                    minimize=minimize,
                )
            )
        else:
            # Multi-objective case
            objectives = []
            for name in self.objective_names:
                direction = getattr(
                    self.objective_directions.get(name),
                    "value",
                    self.objective_directions.get(name, "minimize"),
                )
                minimize = str(direction).lower() != "maximize"
                objectives.append(
                    Objective(
                        metric=Metric(name=name, lower_is_better=minimize),
                        minimize=minimize,
                    )
                )
            objective_thresholds = []
            if self.config.objective_thresholds:
                for name, bound in self.config.objective_thresholds.items():
                    direction = getattr(
                        self.objective_directions.get(name),
                        "value",
                        self.objective_directions.get(name, "minimize"),
                    )
                    minimize = str(direction).lower() != "maximize"
                    objective_thresholds.append(
                        ObjectiveThreshold(
                            metric=Metric(name=name, lower_is_better=minimize),
                            bound=float(bound),
                            relative=False,
                            op=ComparisonOp.LEQ if minimize else ComparisonOp.GEQ,
                        )
                    )
            return MultiObjectiveOptimizationConfig(
                objective=MultiObjective(objectives=objectives),
                objective_thresholds=objective_thresholds,
            )
    
    def _create_generation_strategy(self):
        """Create Ax GenerationStrategy based on config.
        
        Returns:
            Ax GenerationStrategy configured with chosen initialization +
            model-based optimization backend.
        
        Notes:
            Strategy uses the required node-based Ax API and transitions from
            initialization into the configured model-based generator.
        """
        return self._create_node_generation_strategy()

    def _create_node_generation_strategy(self):
        """Create a node-based generation strategy using the latest Ax APIs.

        Notes:
            This mirrors the modern Modular BoTorch tutorial pattern of chaining
            CenterOfSearchSpace -> initializer node -> model-based node using
            transition criteria such as MinTrials.
        """
        model_node_name = self._get_model_node_name()
        model_node = GenerationNode(
            name=model_node_name,
            generator_specs=[
                GeneratorSpec(
                    generator_enum=self._get_model_based_generator_enum(),
                    generator_kwargs=self._get_model_generator_kwargs(),
                    generator_gen_kwargs=self._get_model_generator_gen_kwargs(),
                )
            ],
        )

        nodes = []
        init_strategy = self.config.initialization_strategy.lower()
        init_trials = int(self.config.n_initial_samples)

        if init_strategy == "center":
            remaining_init_trials = max(0, init_trials - 1)
            next_node_name = model_node.name
            if remaining_init_trials > 0:
                init_node = self._build_initialization_node(
                    node_name="Sobol",
                    generator_enum=Generators.SOBOL,
                    num_trials=remaining_init_trials,
                    transition_to=model_node.name,
                )
                next_node_name = init_node.name
                nodes.append(init_node)

            nodes.insert(0, CenterGenerationNode(next_node_name=next_node_name))
            nodes.append(model_node)
            return GenerationStrategy(
                name=f"Center+{next_node_name}+{model_node.name}",
                nodes=nodes,
            )

        init_node = self._build_initialization_node(
            node_name="Random" if init_strategy == "random" else "Sobol",
            generator_enum=self._get_initialization_model_enum(),
            num_trials=init_trials,
            transition_to=model_node.name,
        )

        return GenerationStrategy(
            name=f"{init_node.name}+{model_node.name}",
            nodes=[init_node, model_node],
        )

    def _build_initialization_node(
        self,
        *,
        node_name: str,
        generator_enum: Any,
        num_trials: int,
        transition_to: str,
    ):
        """Build one initialization node for the node-based Ax API."""
        return GenerationNode(
            name=node_name,
            generator_specs=[
                GeneratorSpec(
                    generator_enum=generator_enum,
                    generator_kwargs=self._get_initialization_generator_kwargs(),
                )
            ],
            transition_criteria=[
                MinTrials(
                    threshold=num_trials,
                    transition_to=transition_to,
                    use_all_trials_in_exp=True,
                )
            ],
        )

    def _get_initialization_model_enum(self):
        """Return Ax initializer generator enum for the configured strategy."""
        init_strategy = self.config.initialization_strategy.lower()
        if init_strategy == "uniform":
            uniform = getattr(Generators, "UNIFORM", None)
            if uniform is not None:
                return uniform
            logger.warning(
                "Generators.UNIFORM is unavailable in this Ax version; "
                "falling back to Sobol for initialization."
            )
        return Generators.SOBOL

    def _get_initialization_generator_kwargs(self) -> Dict[str, Any]:
        """Return generator kwargs for initialization nodes."""
        if self.seed is None:
            return {}
        return {"seed": int(self.seed)}

    def _get_model_based_generator_enum(self):
        """Return the configured Ax model-based generator enum."""
        generator_name = self.config.generator
        generator_enum = getattr(Generators, generator_name, None)
        if generator_enum is None:
            raise ValueError(
                f"Configured Ax generator '{generator_name}' is unavailable in "
                "the installed Ax version."
            )
        return generator_enum

    def _get_model_node_name(self) -> str:
        """Return the display name for the active model-based generation node."""
        if self.config.generator == "BOTORCH_MODULAR":
            return "ModularBoTorch"
        return self.config.generator

    def _get_model_generator_kwargs(self) -> Dict[str, Any]:
        """Return resolved generator kwargs for the configured backend."""
        return resolve_generator_kwargs(
            generator_name=self.config.generator,
            generator_kwargs=self.config.generator_kwargs,
        )

    def _get_model_generator_gen_kwargs(self) -> Dict[str, Any]:
        """Return generation-time kwargs for model-based candidate generation."""
        return deepcopy(self.config.generator_gen_kwargs)

    def _split_generator_run(self, generator_run: Any) -> List[Any]:
        """Split a possibly batched Ax generator run into per-arm runs.

        Args:
            generator_run: A generator run returned by Ax.

        Returns:
            List of single-arm generator runs.
        """
        if not hasattr(generator_run, "arms"):
            raise TypeError(
                "Expected an Ax generator run with an 'arms' attribute, got "
                f"{type(generator_run).__name__}"
            )

        arms = list(generator_run.arms)
        if len(arms) <= 1:
            return [generator_run]

        from ax.core.generator_run import GeneratorRun

        weights = list(getattr(generator_run, "weights", []) or [])
        single_runs: List[Any] = []
        for index, arm in enumerate(arms):
            weight = weights[index] if index < len(weights) else 1.0
            single_run = GeneratorRun(
                arms=[arm],
                weights=[weight],
                fit_time=getattr(generator_run, "fit_time", None),
                gen_time=getattr(generator_run, "gen_time", None),
                generation_node_name=getattr(generator_run, "_generation_node_name", None),
            )
            for attr_name in ("_model_key", "_generation_node_name"):
                if hasattr(generator_run, attr_name):
                    setattr(single_run, attr_name, getattr(generator_run, attr_name))
            single_runs.append(single_run)

        return single_runs

    def _normalize_generator_runs(self, gen_result: Any) -> List[Any]:
        """Normalize Ax generation output into per-arm generator runs.

        Args:
            gen_result: Value returned by ``generation_strategy.gen(...)``.

        Returns:
            List of single-arm generator runs.

        Raises:
            TypeError: If the return shape cannot be interpreted as generator
                run output.

        Notes:
            Newer Ax internals may return wrapper/list-like structures around
            generator runs. AID2E uses one Ax generation call per requested
            batch and then splits the result into individual trial records.
        """
        if hasattr(gen_result, "arms"):
            return self._split_generator_run(gen_result)

        if isinstance(gen_result, (list, tuple)):
            generator_runs: List[Any] = []
            for item in gen_result:
                generator_runs.extend(self._normalize_generator_runs(item))
            return generator_runs

        if hasattr(gen_result, "generator_run_structs"):
            structs = getattr(gen_result, "generator_run_structs")
            generator_runs: List[Any] = []
            for struct in structs:
                generator_runs.extend(self._normalize_generator_runs(struct))
            return generator_runs

        if hasattr(gen_result, "generator_run"):
            return self._normalize_generator_runs(getattr(gen_result, "generator_run"))

        raise TypeError(
            "Unsupported Ax generation result type: "
            f"{type(gen_result).__name__}"
        )

    def _get_generation_strategy_metadata(self) -> Dict[str, Any]:
        """Return strategy progress metadata compatible across Ax APIs.

        Returns:
            Dictionary containing ``ax_step_index`` when available and
            ``ax_node_name`` for node-based strategies.
        """
        metadata: Dict[str, Any] = {"ax_step_index": -1}

        step_index = getattr(self.generation_strategy, "current_step_index", None)
        if step_index is not None:
            try:
                metadata["ax_step_index"] = int(step_index)
            except (TypeError, ValueError):
                logger.debug("Unable to coerce Ax step index '%s' to int", step_index)

        node_name = getattr(self.generation_strategy, "current_node_name", None)
        if node_name is not None:
            metadata["ax_node_name"] = str(node_name)

        return metadata
    
    def suggest_candidates(self, n_candidates: int = 1) -> List[Dict[str, Any]]:
        """Suggest the next batch of parameter configurations to evaluate.

        Args:
            n_candidates: Number of candidates to generate.

        Returns:
            List of parameter dictionaries ready for evaluation.

        Notes:
            Constraints are handled natively by Ax when present in search_space.
            Ax enforces constraints during candidate generation automatically.
            
            IMPLEMENTATION NOTE: This method generates the requested batch in a
            single Ax call whenever possible, then splits the resulting batch
            into individual AID2E trial records so the rest of the framework can
            keep using single-trial ``update_with_results`` semantics.
            
            The GenerationStrategy still properly tracks progress: after
            n_initial_samples individual trials complete (regardless of how
            they were generated), it automatically switches from Sobol to BO.
        """

        candidates = []
        model_keys: List[str] = []

        generator_run_result = self.generation_strategy.gen(
            experiment=self.experiment,
            n=n_candidates,
        )
        strategy_metadata = self._get_generation_strategy_metadata()
        generator_runs = self._normalize_generator_runs(generator_run_result)
        if len(generator_runs) < n_candidates:
            raise RuntimeError(
                "Ax returned fewer generator runs than requested: "
                f"requested={n_candidates}, got={len(generator_runs)}"
            )

        for generator_run in generator_runs[:n_candidates]:
            trial = self.experiment.new_trial(generator_run=generator_run)
            trial.mark_running(no_runner_required=True)
            arm = generator_run.arms[0]
            candidate_params = dict(arm.parameters)
            model_key = getattr(generator_run, "_model_key", "unknown")
            self.set_trial_status(
                trial_index=trial.index,
                status=TRIAL_STATUS_SUGGESTED,
                parameters=candidate_params,
                metrics=None,
                metadata={
                    "ax_model_key": model_key,
                    **strategy_metadata,
                },
            )
            candidates.append(candidate_params)
            model_keys.append(model_key)

        self._trial_counter = max(self._trial_counter, len(self.experiment.trials))
        strategy_metadata = self._get_generation_strategy_metadata()
        strategy_ref = strategy_metadata.get(
            "ax_node_name",
            strategy_metadata.get("ax_step_index", -1),
        )

        logger.debug(
            "Generated %d candidates using %s (trials %d-%d, strategy=%s)",
            n_candidates,
            ",".join(model_keys) if model_keys else "unknown",
            len(self.experiment.trials) - n_candidates,
            len(self.experiment.trials) - 1,
            strategy_ref,
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
                        'metric_signature': metric_name,
                        'arm_name': trial.arm.name if trial.arm else f"arm_{trial_index}",
                        'mean': float(metric_value),
                        'sem': 0.0  # Standard error of mean (0 for deterministic)
                    })
            
            if data_rows:
                df = pd.DataFrame(data_rows)
                data = Data(df=df)
                self.experiment.attach_data(data)
        
        # Update internal trial tracking through the base API
        self.set_trial_status(
            trial_index=trial_index,
            status="completed",
            parameters=parameters,
            metrics={k: float(v) for k, v in metrics.items()},
        )
        
        logger.debug(
            f"Updated trial {trial_index} with {len(metrics)} metrics"
        )

    def mark_trial_failed(
        self,
        trial_index: int,
        *,
        parameters: Optional[Dict[str, Any]] = None,
        reason: Optional[str] = None,
    ) -> Trial:
        """Mark a failed evaluation in AID2E and the Ax experiment."""
        if trial_index in self.experiment.trials:
            self.experiment.trials[trial_index].mark_failed(reason=reason)
        return super().mark_trial_failed(
            trial_index,
            parameters=parameters,
            reason=reason,
        )
    
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
                "generator": self.config.generator,
                "generator_kwargs": deepcopy(self.config.generator_kwargs),
                "generator_gen_kwargs": deepcopy(self.config.generator_gen_kwargs),
                "objective_thresholds": (
                    deepcopy(self.config.objective_thresholds)
                    if self.config.objective_thresholds is not None
                    else None
                ),
                "n_initial_samples": self.config.n_initial_samples,
                "n_iterations": self.config.n_iterations,
                "batch_size": self.config.batch_size,
                "seed": self.config.seed,
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
        self._trial_counter = max(self._trial_counter, len(self.experiment.trials))
        
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
            f"generator={self.config.generator}, "
            f"seed={self.seed}"
            f")"
        )