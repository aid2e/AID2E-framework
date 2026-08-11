"""Base optimizer abstractions for the AID2E framework.

This module defines reusable dataclasses and abstract interfaces that optimizers
use to consume design parameter definitions coming from the design configuration
layer. Search spaces are built from typed design parameters, and trials track
optimizer evaluations in a consistent structure.

Key concepts:
    - ``SearchSpace``: Typed parameter domain derived from a DesignConfig.
    - ``Trial``: One evaluated point in the search space, with metrics attached.
    - ``BaseOptimizer``: Abstract base that all optimizer backends must implement.
    - ``compute_pareto_front``: Backend-agnostic utility for Pareto front extraction.

Entrypoints:
    Most users interact with a concrete backend (e.g. ``AxOptimizer``,
    ``PyMOOOptimizer``) rather than these base classes directly.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Union
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

TRIAL_STATUS_PENDING = "pending"
TRIAL_STATUS_SUGGESTED = "suggested"
TRIAL_STATUS_RUNNING = "running"
TRIAL_STATUS_COMPLETED = "completed"
TRIAL_STATUS_FAILED = "failed"
TRIAL_STATUS_ABORTED = "aborted"
TRIAL_STATUS_CANCELLED = "cancelled"

VALID_TRIAL_STATUSES = {
    TRIAL_STATUS_PENDING,
    TRIAL_STATUS_SUGGESTED,
    TRIAL_STATUS_RUNNING,
    TRIAL_STATUS_COMPLETED,
    TRIAL_STATUS_FAILED,
    TRIAL_STATUS_ABORTED,
    TRIAL_STATUS_CANCELLED,
}

DISPLAY_STATUS_MAP = {
    TRIAL_STATUS_PENDING: "Pending",
    TRIAL_STATUS_SUGGESTED: "Suggested",
    TRIAL_STATUS_RUNNING: "Running",
    TRIAL_STATUS_COMPLETED: "Finished",
    TRIAL_STATUS_FAILED: "Failed",
    TRIAL_STATUS_ABORTED: "Aborted",
    TRIAL_STATUS_CANCELLED: "Cancelled",
}

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
                if "values" in param_data:
                    raise ValueError(
                        f"Parameter '{param_name}' uses retired key 'values'. "
                        "Use 'choices'."
                    )
                if "bounds" in param_data and "value" not in param_data:
                    raise ValueError(
                        f"Range parameter '{param_name}' must define an explicit "
                        "'value' alongside 'bounds'."
                    )
                if "choices" in param_data and "value" not in param_data:
                    raise ValueError(
                        f"Choice parameter '{param_name}' must define an explicit "
                        "'value' alongside 'choices'."
                    )
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
        """Normalize metadata and status values after initialization."""
        if self.metadata is None:
            self.metadata = {}
        normalized = str(self.status).strip().lower()
        self.status = normalized if normalized else TRIAL_STATUS_PENDING
        if self.status not in VALID_TRIAL_STATUSES:
            logger.warning(
                "Unknown trial status '%s'; keeping value as-is.",
                self.status,
            )

    def save_to_json(self, output_path: Union[str, Path]) -> Path:
        """Write the trial's design parameters to disk as pretty-printed JSON.

        This helper is intentionally design-point focused: it serializes only
        ``parameters`` so command-line evaluators can consume the resulting file
        as an input payload without needing optimizer metadata.

        Args:
            output_path: Target JSON path.

        Returns:
            Resolved path of the written file.
        """
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            json.dump(dict(self.parameters or {}), handle, indent=2, sort_keys=True)
        return path


def compute_pareto_front(
    trials: List["Trial"],
    objective_names: List[str],
    objective_directions: Optional[Dict[str, Any]] = None,
) -> List["Trial"]:
    """Extract non-dominated (Pareto-optimal) trials from a collection of completed trials.

    Objectives are compared using ``objective_directions``. Minimization is the
    default; maximization objectives treat larger values as better. For
    single-objective problems the function returns the best trial under that
    objective's direction.

    Args:
        trials: Iterable of Trial objects.  Only trials whose ``status`` is
            ``"completed"`` and whose ``metrics`` dict is non-empty are
            considered.
        objective_names: Ordered list of objective metric keys that must be
            present in each trial's ``metrics`` dict.
        objective_directions: Optional mapping from objective name to
            ``"minimize"`` or ``"maximize"``. Missing objectives default to
            minimization.

    Returns:
        List of non-dominated Trial objects ordered by their original
        position in ``trials``.  Returns an empty list when no completed
        trials are available.

    Examples:
        >>> from aid2e.optimizers.base import Trial, compute_pareto_front
        >>> t1 = Trial(index=0, parameters={}, metrics={"f1": 1.0, "f2": 3.0}, status="completed")
        >>> t2 = Trial(index=1, parameters={}, metrics={"f1": 2.0, "f2": 1.0}, status="completed")
        >>> t3 = Trial(index=2, parameters={}, metrics={"f1": 0.5, "f2": 2.0}, status="completed")
        >>> front = compute_pareto_front([t1, t2, t3], ["f1", "f2"])
        >>> {t.index for t in front}
        {0, 1, 2}

    Notes:
        Uses NumPy for vectorised comparisons when available; falls back to
        a pure-Python O(n²) loop otherwise.  For production workloads with
        thousands of trials, the NumPy path is strongly recommended.
    """
    completed = [
        t for t in trials
        if t is not None and t.status == "completed" and t.metrics
    ]
    if not completed:
        return []
    if len(completed) == 1:
        return completed

    directions = objective_directions or {}
    objective_signs = []
    for obj in objective_names:
        direction = getattr(directions.get(obj), "value", directions.get(obj, "minimize"))
        objective_signs.append(-1.0 if str(direction).lower() == "maximize" else 1.0)

    def score(trial: "Trial", obj: str, sign: float) -> float:
        value = trial.metrics.get(obj)
        return float("inf") if value is None else float(value) * sign

    try:
        import numpy as np

        n = len(completed)
        F = np.array(
            [
                [score(t, obj, sign) for obj, sign in zip(objective_names, objective_signs)]
                for t in completed
            ],
            dtype=float,
        )
        is_dominated = np.zeros(n, dtype=bool)
        for i in range(n):
            if is_dominated[i]:
                continue
            # Vectorised: does any other solution dominate i?
            # j dominates i iff F[j] <= F[i] (all) and F[j] < F[i] (any)
            dom_mask = np.all(F <= F[i], axis=1) & np.any(F < F[i], axis=1)
            dom_mask[i] = False  # Exclude self-comparison
            if np.any(dom_mask):
                is_dominated[i] = True

        return [t for t, dom in zip(completed, is_dominated) if not dom]

    except ImportError:  # pragma: no cover – NumPy should always be present
        logger.warning("NumPy not available; falling back to pure-Python Pareto computation.")
        n = len(completed)
        is_dominated = [False] * n
        for i in range(n):
            if is_dominated[i]:
                continue
            for j in range(n):
                if i == j or is_dominated[j]:
                    continue
                # Check whether j dominates i
                all_leq = all(
                    score(completed[j], obj, sign) <= score(completed[i], obj, sign)
                    for obj, sign in zip(objective_names, objective_signs)
                )
                any_lt = any(
                    score(completed[j], obj, sign) < score(completed[i], obj, sign)
                    for obj, sign in zip(objective_names, objective_signs)
                )
                if all_leq and any_lt:
                    is_dominated[i] = True
                    break

        return [t for t, dom in zip(completed, is_dominated) if not dom]


class BaseOptimizer(ABC):
    """Abstract base class for all AID2E optimizers.

    Subclasses must implement the abstract methods to suggest candidates, ingest
    evaluation results, and surface optimizer state. The interface is intentionally
    minimal to support a range of backends (Ax, genetic algorithms, grid search)
    while keeping a consistent contract for the rest of the framework.

    Concrete default implementations are provided for ``get_pareto_front`` and
    ``get_best_trial`` using :func:`compute_pareto_front`.  Individual backends
    may override these when native support (e.g. PyMOO's built-in Pareto tools)
    is preferable.
    """

    def __init__(
        self,
        search_space: Union[SearchSpace, DesignConfig],
        objective_names: List[str],
        seed: Optional[int] = None,
        objective_directions: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Initialize the optimizer with a search space and objective specification.

        Args:
            search_space: Typed search space or DesignConfig to optimize over.
            objective_names: Ordered list of objective metric names.  Each name
                must match the keys returned in the ``metrics`` dict when
                ``update_with_results`` is called.
            seed: Optional integer seed for reproducibility.
            objective_directions: Optional mapping from objective name to
                ``"minimize"`` or ``"maximize"``. Missing objectives default to
                minimization.

        Raises:
            ValueError: If the search space is empty or no objective names are
                provided.
        """

        resolved_space = (
            SearchSpace.from_design_config(search_space)
            if isinstance(search_space, DesignConfig)
            else search_space
        )

        if not resolved_space.parameters:
            raise ValueError("Search space cannot be empty")
        if not objective_names:
            raise ValueError("objective_names must contain at least one name")

        self.search_space = resolved_space
        self.objective_names: List[str] = list(objective_names)
        self.objective_directions: Dict[str, Any] = dict(objective_directions or {})
        self.seed = seed

        # Shared trial history managed by the base class.
        # All backends read and write through self._trials and self._trial_counter
        # so utilities like seed_from_trials, get_trials, get_pareto_front work
        # uniformly regardless of the backend.
        self._trials: List[Optional[Trial]] = []
        self._trial_counter: int = 0

    @property
    def n_objectives(self) -> int:
        """Return the number of optimisation objectives.

        Returns:
            Integer count derived from ``objective_names``.
        """
        return len(self.objective_names)

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

    def get_trials(self) -> List[Trial]:
        """Return all recorded trials (pending, completed, and failed).

        The base implementation reads directly from ``self._trials``, which is
        owned by ``BaseOptimizer`` and kept up to date by every backend.
        Backends that maintain additional internal state may override this to
        include synthetic or reconstructed trials, but doing so is uncommon.

        Returns:
            List of non-``None`` Trial objects in creation order.

        Examples:
            >>> done = [t for t in optimizer.get_trials() if t.status == "completed"]
        """
        return [t for t in self._trials if t is not None]

    def set_trial_status(
        self,
        trial_index: int,
        status: str,
        *,
        parameters: Optional[Dict[str, Any]] = None,
        metrics: Optional[Dict[str, float]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Trial:
        """Create or update a trial entry with a new lifecycle status.

        Args:
            trial_index: Unique trial identifier.
            status: Trial lifecycle status (for example ``running``,
                ``completed``, ``aborted``).
            parameters: Optional parameter dictionary to store on the trial.
            metrics: Optional objective dictionary to store on the trial.
            metadata: Optional metadata to merge into existing metadata.

        Returns:
            The updated Trial object.

        Raises:
            ValueError: If ``trial_index`` is negative.
        """
        if trial_index < 0:
            raise ValueError("trial_index must be >= 0")

        normalized_status = str(status).strip().lower()
        while len(self._trials) <= trial_index:
            self._trials.append(None)

        existing = self._trials[trial_index]
        existing_parameters = existing.parameters if existing else {}
        existing_metrics = existing.metrics if existing else None
        existing_metadata = dict(existing.metadata) if existing and existing.metadata else {}

        trial = Trial(
            index=trial_index,
            parameters=parameters if parameters is not None else existing_parameters,
            metrics=metrics if metrics is not None else existing_metrics,
            status=normalized_status,
            metadata={**existing_metadata, **(metadata or {})},
        )
        self._trials[trial_index] = trial
        self._trial_counter = max(self._trial_counter, trial_index + 1)
        return trial

    def get_optimization_results(
        self,
        errors_by_trial: Optional[Dict[int, Dict[str, float]]] = None,
    ) -> Dict[str, Any]:
        """Return a normalized optimization-results payload.

        Args:
            errors_by_trial: Optional uncertainty/error fields keyed by trial index.

        Returns:
            Dictionary containing objective names and trial records with
            parameters, metrics, and both raw and display status labels.
        """
        errors_by_trial = errors_by_trial or {}
        trials_payload: List[Dict[str, Any]] = []
        for trial in self.get_trials():
            trials_payload.append(
                {
                    "trial_index": trial.index,
                    "status": trial.status,
                    "display_status": DISPLAY_STATUS_MAP.get(
                        trial.status,
                        trial.status.title(),
                    ),
                    "design_parameters": dict(trial.parameters or {}),
                    "objectives": dict(trial.metrics or {}),
                    "objective_errors": dict(errors_by_trial.get(trial.index, {})),
                    "metadata": dict(trial.metadata or {}),
                }
            )

        return {
            "objective_names": list(self.objective_names),
            "n_objectives": self.n_objectives,
            "n_trials": len(trials_payload),
            "trials": trials_payload,
        }

    def save_optimization_results(
        self,
        output_path: Union[str, Path],
        *,
        errors_by_trial: Optional[Dict[int, Dict[str, float]]] = None,
    ) -> Dict[str, Path]:
        """Write optimization results to disk as pretty-printed JSON.

        Args:
            output_path: Directory where optimizer result files are written.
            errors_by_trial: Optional uncertainty/error fields keyed by trial index.

        Returns:
            Paths of the written result files.
        """
        output_dir = Path(output_path)
        output_dir.mkdir(parents=True, exist_ok=True)
        results_path = output_dir / "optimization_results.json"
        pareto_path = output_dir / "pareto_front.json"

        payload = self.get_optimization_results(errors_by_trial=errors_by_trial)
        with results_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)

        errors_by_trial = errors_by_trial or {}
        pareto_payload = [
            {
                "trial_index": trial.index,
                "design_parameters": dict(trial.parameters or {}),
                "objectives": dict(trial.metrics or {}),
                "objective_errors": dict(errors_by_trial.get(trial.index, {})),
                "metadata": dict(trial.metadata or {}),
            }
            for trial in self.get_pareto_front()
        ]
        with pareto_path.open("w", encoding="utf-8") as handle:
            json.dump(pareto_payload, handle, indent=2)
        return {
            "optimization_results": results_path,
            "pareto_front": pareto_path,
        }

    def seed_from_trials(
        self,
        trials: List[Trial],
        *,
        only_completed: bool = True,
    ) -> int:
        """Inject external trials into the optimizer history without advancing the algorithm.

        This is the *backend-switch primitive*.  It lets you:

        - Seed a new optimizer with results from a previous one (e.g. random
          init → MOEA → BO transition).
        - Inject prior knowledge before the first ``suggest_candidates`` call.
        - Resume an optimisation from a checkpoint produced by a *different*
          backend.

        Trials are appended to the internal ``_trials`` list with freshly
        assigned sequential indices (starting from the current
        ``_trial_counter``).  The original ``trial.index`` values from the
        source optimizer are preserved in each trial's ``metadata`` under the
        key ``"source_index"``.

        Args:
            trials: Iterable of Trial objects to inject.  The list may contain
                ``None`` placeholders (they are silently skipped).
            only_completed: When ``True`` (default), only trials whose
                ``status`` is ``"completed"`` are imported.  Set to ``False``
                to also import ``"pending"`` or ``"failed"`` trials.

        Returns:
            Number of trials actually injected.

        Examples:
            >>> # Transfer best results from a random-search warmup:
            >>> warmup_trials = random_opt.get_trials()
            >>> pymoo_opt.seed_from_trials(warmup_trials)
            100
            >>> # Now start MOEA generation — the history already has 100 points
            >>> candidates = pymoo_opt.suggest_candidates()

        Notes:
            - This method does NOT advance PyMOO's (or any other backend's)
              internal population.  The injected trials are purely visible in
              the history for Pareto-front and best-trial queries.
            - Backends that want to warm-start their internal state from these
              trials should override this method.
        """
        accepted = 0
        for trial in trials:
            if trial is None:
                continue
            if only_completed and trial.status != "completed":
                continue
            new_idx = self._trial_counter
            seeded_trial = Trial(
                index=new_idx,
                parameters=trial.parameters,
                metrics=trial.metrics,
                status=trial.status,
                metadata={**(trial.metadata or {}), "source_index": trial.index},
            )
            while len(self._trials) <= new_idx:
                self._trials.append(None)
            self._trials[new_idx] = seeded_trial
            self._trial_counter += 1
            accepted += 1

        if accepted:
            logger.debug(
                "seed_from_trials: injected %d trial(s) (total history: %d).",
                accepted,
                self._trial_counter,
            )
        return accepted

    def get_pareto_front(self) -> List[Trial]:
        """Retrieve the current Pareto front of non-dominated solutions.

        The default implementation delegates to :func:`compute_pareto_front`,
        which operates on the trials returned by :meth:`get_trials`.  Backends
        with native Pareto support (e.g. PyMOO) may override this method to
        expose more detailed Pareto metadata.

        Returns:
            List of Trial objects representing Pareto-optimal solutions.
            For single-objective optimisation, returns the single trial with
            the best metric value under its configured direction. Returns an
            empty list when no completed trials are available.

        Examples:
            >>> pareto_front = optimizer.get_pareto_front()
            >>> for trial in pareto_front:
            ...     print(f"Params: {trial.parameters}, Metrics: {trial.metrics}")

        Notes:
            Objective directions are read from ``self.objective_directions``.
        """
        return compute_pareto_front(
            self.get_trials(),
            self.objective_names,
            self.objective_directions,
        )

    def get_best_trial(self) -> Optional[Trial]:
        """Get the best trial found so far.

        For single-objective optimisation, returns the completed trial with the
        best metric value under its configured direction. For multi-objective,
        returns the first trial from the Pareto front (arbitrary representative;
        use :meth:`get_pareto_front` for the full front).

        Returns:
            Best Trial, or ``None`` if no completed trials exist.

        Examples:
            >>> best = optimizer.get_best_trial()
            >>> if best:
            ...     print(f"Best parameters: {best.parameters}")
            ...     print(f"Best metrics: {best.metrics}")
        """
        front = self.get_pareto_front()
        if not front:
            return None
        if self.n_objectives == 1:
            obj = self.objective_names[0]
            return min(front, key=lambda t: t.metrics[obj])
        # Multi-objective: return first element of the front
        return front[0]

    @abstractmethod
    def serialize_state(self) -> Dict[str, Any]:
        """Serialize optimizer state for distributed execution or checkpointing.

        Returns:
            Dictionary containing all necessary state to reconstruct
            the optimizer. Should be JSON-serializable.

        Examples:
            >>> state = optimizer.serialize_state()
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
