"""PyMOO-based evolutionary optimizer for AID2E framework.

AID2E philosophy — separation of concerns
------------------------------------------
An AID2E optimizer is a *candidate generator* and a *result ledger*. It has
no knowledge of how evaluations are performed — that is the job of schedulers,
workflow engines, and simulation back-ends.  The optimizer only:

1. Produces design-point candidates (``suggest_candidates``).
2. Records objective values once evaluations are complete (``update_with_results``).

This module wires the PyMOO evolutionary library into that interface via the
**ask/tell protocol**:

- ``suggest_candidates()`` → ``algorithm.ask()`` — returns the current
  generation as parameter dicts.
- ``update_with_results()`` → buffers one result; flushes
  ``algorithm.tell()`` automatically when the full generation has results.

The ``_flush_generation`` mechanism is entirely internal. Callers never need
to think in terms of "generations" — they simply call the same two methods
repeatedly regardless of the backend.

PyMOOProblem
------------
The public ``PyMOOProblem`` class represents the search space as a proper
PyMOO ``Problem``.  It is structural only (variables, bounds, objectives)
and intentionally does not evaluate candidates.  Evaluations are always
handled externally by workflow/scheduler components and reported back via
``update_with_results``.

Backend switching
-----------------
Use ``seed_from_trials(prior_optimizer.get_trials())`` to inject completed
results from a different backend (e.g. a random-initialisation phase) before
starting the evolutionary search.

Project: AID2E v0.0.0 — AI assisted Detector Design for EIC
Homepage: https://aid2e.github.io/AID2E-framework
Repository: https://github.com/aid2e/AID2E-framework.git
"""

from __future__ import annotations

import logging
import warnings
from typing import Any, Dict, List, Optional, Tuple, Union, TYPE_CHECKING

import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional PyMOO import guard
# ---------------------------------------------------------------------------
try:
    from pymoo.core.problem import Problem
    from pymoo.core.termination import NoTermination
    from pymoo.operators.crossover.sbx import SBX
    from pymoo.operators.mutation.pm import PM
    from pymoo.operators.sampling.rnd import FloatRandomSampling

    PYMOO_AVAILABLE = True
except ImportError as _pymoo_err:  # pragma: no cover
    PYMOO_AVAILABLE = False
    if TYPE_CHECKING:
        from pymoo.core.problem import Problem
    else:
        Problem = object  # type: ignore[assignment,misc]
    logger.warning(
        "PyMOO not available: %s. Install with: pip install pymoo",
        _pymoo_err,
    )

from aid2e.optimizers.base import BaseOptimizer, SearchSpace, Trial
from aid2e.utilities.configurations.base_models import (
    ChoiceParameter as DesignChoiceParameter,
    RangeParameter as DesignRangeParameter,
)
from aid2e.utilities.configurations.design_config import DesignConfig
from .config import PyMOOOptimizerConfig


# ---------------------------------------------------------------------------
# Public PyMOO problem class
# ---------------------------------------------------------------------------

class PyMOOProblem(Problem):
    """PyMOO Problem that wraps an AID2E ``SearchSpace``.

        This problem is structural-only for ask/tell workflows. ``decode_x``
        translates PyMOO float vectors into
    human-readable AID2E parameter dicts — the same representation returned
    by ``suggest_candidates``.

    Args:
        n_var: Number of continuous decision variables.
        n_obj: Number of objectives.
        xl: Lower-bound array of shape ``(n_var,)``.
        xu: Upper-bound array of shape ``(n_var,)``.
        param_items: Ordered list of ``(name, BaseParameter)`` pairs used for
            encoding/decoding.
        objective_names: Ordered objective names.
    """

    def __init__(
        self,
        n_var: int,
        n_obj: int,
        xl: np.ndarray,
        xu: np.ndarray,
        param_items: List[Tuple[str, Any]],
        objective_names: List[str],
    ) -> None:
        """Initialise the PyMOO problem with search-space metadata."""
        super().__init__(n_var=n_var, n_obj=n_obj, xl=xl, xu=xu)
        self._param_items = param_items
        self._objective_names = objective_names

    def decode_x(self, x_row: np.ndarray) -> Dict[str, Any]:
        """Translate a PyMOO float vector into an AID2E parameter dictionary.

        Args:
            x_row: 1-D float array of length ``n_var``.

        Returns:
            Mapping of parameter names to decoded values (``float`` for
            ``RangeParameter``, choice value for ``ChoiceParameter``).
        """
        params: Dict[str, Any] = {}
        for i, (name, param) in enumerate(self._param_items):
            val = float(x_row[i])
            if isinstance(param, DesignRangeParameter):
                params[name] = val
            elif isinstance(param, DesignChoiceParameter):
                idx = int(round(val))
                idx = max(0, min(idx, len(param.choices) - 1))
                params[name] = param.choices[idx]
        return params

    def _evaluate(
        self, x: np.ndarray, out: dict, *args: Any, **kwargs: Any
    ) -> None:
        """Raise because AID2E always uses external evaluation.

        Args:
            x: Population matrix (unused).
            out: Output dictionary (unused).

        Raises:
            NotImplementedError: Always, because evaluation belongs to the
                workflow/scheduler layer in AID2E.
        """
        raise NotImplementedError(
            "PyMOOProblem is structural-only in ask/tell mode. "
            "Use PyMOOOptimizer.suggest_candidates() and "
            "PyMOOOptimizer.update_with_results() with external evaluation."
        )


class AID2EProblem(PyMOOProblem):
    """Deprecated compatibility alias for ``PyMOOProblem``."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Warn and delegate to ``PyMOOProblem``."""
        warnings.warn(
            "AID2EProblem is deprecated and will be removed in the next "
            "iteration. Use PyMOOProblem instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        # TODO: Remove this compatibility alias in the next iteration.
        super().__init__(*args, **kwargs)


# ---------------------------------------------------------------------------
# Main optimizer class
# ---------------------------------------------------------------------------

class PyMOOOptimizer(BaseOptimizer):
    """Evolutionary optimizer backed by PyMOO algorithms.

    Implements the ``BaseOptimizer`` interface using PyMOO's ask/tell protocol
    so that evaluations can be performed externally (e.g. via schedulers or
    simulation jobs) without blocking PyMOO's internal loop.

    The generation lifecycle is::

        candidates = optimizer.suggest_candidates()   # calls algorithm.ask()
        for i, c in enumerate(candidates):
            metrics = my_evaluate(c)
            optimizer.update_with_results(i, c, metrics)
        # After the last call above, algorithm.tell() is invoked automatically.
        # The next suggest_candidates() call produces the next generation.

    Supported algorithms:
        - ``"ga"`` — Genetic Algorithm for single-objective optimisation.
        - ``"nsga2"`` — NSGA-II, recommended for 2–3 objectives.
        - ``"nsga3"`` — NSGA-III, recommended for 3+ objectives.
        - ``"moead"`` — MOEA/D, weight-decomposition approach.

    Attributes:
        config: ``PyMOOOptimizerConfig`` instance controlling algorithm behaviour.
        n_gen_completed: Number of generations that have been fully evaluated.

    Examples:
        >>> from aid2e.optimizers.pymoo import PyMOOOptimizer, PyMOOOptimizerConfig
        >>> from aid2e.optimizers.base import SearchSpace
        >>> space = SearchSpace(
        ...     parameters={
        ...         "x": {"type": "range", "bounds": [0.0, 1.0]},
        ...         "y": {"type": "range", "bounds": [0.0, 1.0]},
        ...     }
        ... )
        >>> config = PyMOOOptimizerConfig(pop_size=20, seed=0)
        >>> opt = PyMOOOptimizer(space, config, objective_names=["loss"])
        >>> candidates = opt.suggest_candidates()
        >>> for trial_idx, c in enumerate(candidates):
        ...     opt.update_with_results(trial_idx, c, {"loss": c["x"] + c["y"]})
        >>> best = opt.get_best_trial()

    Notes:
        - All objectives are treated as *minimisation* targets.  To maximise,
          negate values before passing them to ``update_with_results``.
        - Linear parameter constraints are not yet forwarded to PyMOO.  A
          warning is emitted when the search space contains constraints.
        - ``n_candidates`` passed to ``suggest_candidates`` is informational
          only; the actual batch size is determined by the algorithm
          (``pop_size`` for the first generation, ``n_offsprings`` thereafter).

        Project: AID2E v0.0.0 — AI assisted Detector Design for EIC
        Homepage: https://aid2e.github.io/AID2E-framework
        Repository: https://github.com/aid2e/AID2E-framework.git
    """

    def __init__(
        self,
        search_space: Union[SearchSpace, DesignConfig],
        config: PyMOOOptimizerConfig,
        objective_names: List[str],
        seed: Optional[int] = None,
    ) -> None:
        """Initialise the PyMOO optimizer.

        Args:
            search_space: Parameter search space or a ``DesignConfig`` instance.
                ``DesignConfig`` is automatically converted to ``SearchSpace``.
            config: ``PyMOOOptimizerConfig`` controlling algorithm selection and
                operator hyper-parameters.
            objective_names: Ordered list of objective metric names.  These must
                match keys in the ``metrics`` dict passed to
                ``update_with_results``.
            seed: Integer seed overriding ``config.seed`` when provided.

        Raises:
            ImportError: If PyMOO is not installed.
            ValueError: If the search space is empty or ``objective_names`` is
                empty.

        Notes:
            The algorithm is initialised lazily; the actual PyMOO ``Problem``
            and ``Algorithm`` objects are created here but no evaluations occur
            until ``suggest_candidates`` is called.
        """
        if not PYMOO_AVAILABLE:
            raise ImportError(
                "PyMOO is required but not installed. "
                "Install with: pip install pymoo"
            )

        effective_seed = seed if seed is not None else config.seed

        super().__init__(
            search_space=search_space,
            objective_names=objective_names,
            seed=effective_seed,
        )

        self.config = config
        self.resolved_algorithm = self.config.resolve_algorithm(self.n_objectives)

        if self.search_space.constraints:
            logger.warning(
                "PyMOOOptimizer: %d parameter constraint(s) detected in the search "
                "space but are not yet forwarded to PyMOO. Constraint satisfaction "
                "is not guaranteed during candidate generation.",
                len(self.search_space.constraints),
            )

        # Build ordered parameter list (deterministic iteration order)
        self._param_items: List[Tuple[str, Any]] = list(
            self.search_space.parameters.items()
        )

        # Build numpy bounds
        self._xl, self._xu = self._build_bounds()
        n_var = len(self._param_items)

        # Public PyMOO problem (structural-only ask/tell mode).
        self.problem: PyMOOProblem = PyMOOProblem(
            n_var=n_var,
            n_obj=self.n_objectives,
            xl=self._xl,
            xu=self._xu,
            param_items=self._param_items,
            objective_names=self.objective_names,
        )

        # Create the PyMOO algorithm
        self._algorithm = self._create_algorithm()
        self._algorithm.setup(
            self.problem,
            seed=self.seed,
            verbose=self.config.verbose,
            termination=NoTermination(),
        )

        # _trials and _trial_counter are owned by BaseOptimizer.__init__
        self.n_gen_completed: int = 0

        # Per-generation state (cleared after each tell())
        self._generation_infills: Any = None           # pymoo Population
        self._gen_pos_to_trial_idx: Dict[int, int] = {}  # position → trial_index
        self._result_buffer: Dict[int, Dict[str, float]] = {}  # trial_index → metrics

        logger.info(
            "PyMOOOptimizer initialised: algorithm=%s, pop_size=%d, "
            "n_params=%d, n_objectives=%d, seed=%s",
            self.resolved_algorithm,
            config.pop_size,
            n_var,
            self.n_objectives,
            self.seed,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_bounds(self) -> Tuple[np.ndarray, np.ndarray]:
        """Build lower/upper bound arrays from the search space parameters.

        ``RangeParameter`` contributes its ``bounds``; ``ChoiceParameter``
        contributes ``[0, n_choices − 1]`` as a continuous range to be
        rounded during decoding.

        Returns:
            Tuple of ``(xl, xu)`` each as a ``float64`` array of shape
            ``(n_var,)``.
        """
        xl, xu = [], []
        for _, param in self._param_items:
            if isinstance(param, DesignRangeParameter):
                xl.append(float(param.bounds[0]))
                xu.append(float(param.bounds[1]))
            elif isinstance(param, DesignChoiceParameter):
                xl.append(0.0)
                xu.append(float(len(param.choices) - 1))
            else:
                raise ValueError(
                    f"Unsupported parameter type for PyMOO: "
                    f"{param.__class__.__name__}"
                )
        return np.array(xl, dtype=float), np.array(xu, dtype=float)

    def _decode_x(self, x_row: np.ndarray) -> Dict[str, Any]:
        """Delegate to ``self.problem.decode_x`` for internal use.

        Args:
            x_row: 1-D float array of length ``n_var``.

        Returns:
            Parameter dictionary for the given individual.
        """
        return self.problem.decode_x(x_row)

    def _encode_params(self, params: Dict[str, Any]) -> np.ndarray:
        """Encode a parameter dictionary back to a PyMOO-compatible float vector.

        Used by ``load_state`` when re-seeding completed trials into PyMOO's
        memory structures.

        Args:
            params: Mapping of parameter names to values.

        Returns:
            1-D float array of length ``n_var``.
        """
        x_row = np.zeros(len(self._param_items), dtype=float)
        for i, (name, param) in enumerate(self._param_items):
            val = params.get(name)
            if isinstance(param, DesignRangeParameter):
                x_row[i] = float(val)
            elif isinstance(param, DesignChoiceParameter):
                if val in param.choices:
                    x_row[i] = float(param.choices.index(val))
                else:
                    x_row[i] = 0.0
        return x_row

    def _create_algorithm(self) -> Any:
        """Instantiate the PyMOO algorithm from the current config.

        Returns:
            An uninitialised PyMOO ``Algorithm`` instance.

        Raises:
            ValueError: If the resolved algorithm is not a supported identifier.

        Notes:
            Algorithm objects are created *before* ``setup()`` is called so
            that ``__init__`` can validate the config without triggering any
            sampling.
        """
        alg = self.resolved_algorithm.lower()
        n_offsprings = self.config.n_offsprings  # None → pop_size default

        crossover = SBX(
            prob=self.config.crossover_prob,
            eta=self.config.crossover_eta,
        )
        mutation = PM(eta=self.config.mutation_eta)
        sampling = FloatRandomSampling()

        if alg == "ga":
            from pymoo.algorithms.soo.nonconvex.ga import GA  # type: ignore[import]

            return GA(
                pop_size=self.config.pop_size,
                n_offsprings=n_offsprings,
                crossover=crossover,
                mutation=mutation,
                sampling=sampling,
            )

        if alg == "nsga2":
            from pymoo.algorithms.moo.nsga2 import NSGA2  # type: ignore[import]

            return NSGA2(
                pop_size=self.config.pop_size,
                n_offsprings=n_offsprings,
                crossover=crossover,
                mutation=mutation,
                sampling=sampling,
            )

        if alg == "nsga3":
            from pymoo.algorithms.moo.nsga3 import NSGA3  # type: ignore[import]
            from pymoo.util.ref_dirs import get_reference_directions  # type: ignore[import]

            ref_dirs = get_reference_directions(
                "das-dennis",
                n_dim=self.n_objectives,
                n_partitions=self.config.n_partitions,
            )
            return NSGA3(
                ref_dirs=ref_dirs,
                pop_size=self.config.pop_size,
                n_offsprings=n_offsprings,
                crossover=crossover,
                mutation=mutation,
                sampling=sampling,
            )

        if alg == "moead":
            from pymoo.algorithms.moo.moead import MOEAD  # type: ignore[import]
            from pymoo.util.ref_dirs import get_reference_directions  # type: ignore[import]

            ref_dirs = get_reference_directions(
                "uniform",
                n_dim=self.n_objectives,
                n_points=self.config.pop_size,
            )
            return MOEAD(
                ref_dirs=ref_dirs,
                n_neighbors=15,
                crossover=crossover,
                mutation=mutation,
                sampling=sampling,
            )

        raise ValueError(
            f"Unknown PyMOO algorithm '{self.resolved_algorithm}'. "
            "Supported: 'ga', 'nsga2', 'nsga3', 'moead'."
        )

    def _flush_generation(self) -> None:
        """Advance the algorithm by one generation using buffered results.

        Called automatically by ``update_with_results`` when every candidate
        produced by the most recent ``suggest_candidates`` call has a result.
        Builds the objective matrix ``F`` from the buffer and calls
        ``algorithm.tell()``.

        Notes:
            This method clears ``_generation_infills``, ``_gen_pos_to_trial_idx``,
            and ``_result_buffer`` after flushing.
        """
        n_gen = len(self._gen_pos_to_trial_idx)
        F = np.zeros((n_gen, self.n_objectives), dtype=float)

        for pos, trial_idx in self._gen_pos_to_trial_idx.items():
            metrics = self._result_buffer[trial_idx]
            for j, obj in enumerate(self.objective_names):
                F[pos, j] = metrics[obj]

        self._generation_infills.set("F", F)
        self._algorithm.tell(infills=self._generation_infills)
        self.n_gen_completed += 1

        logger.debug(
            "Generation %d completed: %d individuals evaluated.",
            self.n_gen_completed,
            n_gen,
        )

        # Reset generation state
        self._generation_infills = None
        self._gen_pos_to_trial_idx = {}
        self._result_buffer = {}

    # ------------------------------------------------------------------
    # BaseOptimizer interface overrides + extensions
    # ------------------------------------------------------------------

    def seed_from_trials(
        self,
        trials: List[Trial],
        *,
        only_completed: bool = True,
    ) -> int:
        """Inject completed trials from an external source into the history.

        Extends the base implementation with a guard that prevents seeding
        while a generation is in-flight (i.e., ``suggest_candidates`` has
        been called but not all ``update_with_results`` calls have come back).

        The injected trials are recorded in the optimizer's history and
        visible via ``get_trials()`` and ``get_pareto_front()``.  They do
        *not* advance PyMOO's internal population — the next
        ``suggest_candidates`` call still produces the next generation.

        Args:
            trials: Trials to inject, typically from a previous backend
                (e.g. random-initialisation results).
            only_completed: When ``True`` (default), non-completed trials are
                silently skipped.

        Returns:
            Number of trials actually injected.

        Raises:
            RuntimeError: If a generation is currently in-flight.

        Examples:
            >>> n = pymoo_opt.seed_from_trials(random_opt.get_trials())
            >>> print(f"Seeded {n} prior evaluations")
            >>> candidates = pymoo_opt.suggest_candidates()  # gen 1 starts
        """
        if self._generation_infills is not None:
            raise RuntimeError(
                "Cannot seed trials while a generation is in-flight. "
                "Call update_with_results() for all pending candidates first."
            )
        return super().seed_from_trials(trials, only_completed=only_completed)

    def suggest_candidates(self, n_candidates: int = 1) -> List[Dict[str, Any]]:
        """Suggest the next batch of candidates to evaluate.

        Calls ``algorithm.ask()`` to retrieve the current generation population
        from PyMOO and returns them as a list of parameter dicts.  The actual
        number of candidates is determined by the algorithm (``pop_size`` for
        the initial generation, ``n_offsprings`` thereafter), not by
        ``n_candidates``.

        Args:
            n_candidates: Advisory hint only.  A ``DEBUG``-level message is
                emitted when the hint differs from the actual batch size.

        Returns:
            List of parameter dicts, one per individual in the current
            generation.  Trial indices for these candidates begin at the
            current ``_trial_counter``.

        Raises:
            RuntimeError: If a previous generation has not yet been fully
                evaluated (i.e. some ``update_with_results`` calls are
                outstanding).

        Examples:
            >>> candidates = optimizer.suggest_candidates()
            >>> len(candidates)
            100  # pop_size
        """
        # Guard: cannot ask for a new generation while one is in flight
        if self._generation_infills is not None:
            n_pending = len(self._gen_pos_to_trial_idx) - len(self._result_buffer)
            raise RuntimeError(
                f"Cannot suggest new candidates: {n_pending} evaluation(s) from "
                "the current generation are still outstanding. Call "
                "update_with_results() for all pending candidates first."
            )

        infills = self._algorithm.ask()
        X = infills.get("X")   # shape (batch_size, n_var)
        batch_size = len(X)

        if n_candidates != 1 and n_candidates != batch_size:
            logger.debug(
                "n_candidates=%d ignored — PyMOO algorithm produces %d candidates "
                "(pop_size=%d). Use optimizer.suggest_candidates() without a hint "
                "to suppress this message.",
                n_candidates,
                batch_size,
                self.config.pop_size,
            )

        self._generation_infills = infills
        self._gen_pos_to_trial_idx = {}
        self._result_buffer = {}

        candidates: List[Dict[str, Any]] = []
        for pos, x_row in enumerate(X):
            trial_idx = self._trial_counter
            self._trial_counter += 1
            self._gen_pos_to_trial_idx[pos] = trial_idx

            params = self._decode_x(x_row)

            # Register as pending
            trial = Trial(index=trial_idx, parameters=params, status="pending")
            while len(self._trials) <= trial_idx:
                self._trials.append(None)
            self._trials[trial_idx] = trial

            candidates.append(params)

        logger.debug(
            "Generation %d: suggested %d candidates (trial indices %d–%d).",
            self.n_gen_completed + 1,
            batch_size,
            self._trial_counter - batch_size,
            self._trial_counter - 1,
        )
        return candidates

    def update_with_results(
        self,
        trial_index: int,
        parameters: Dict[str, Any],
        metrics: Dict[str, float],
    ) -> None:
        """Record evaluation results for one candidate and advance the algorithm.

        When the last outstanding candidate of the current generation is
        updated, the generation buffer is flushed automatically via
        ``algorithm.tell()``.

        Args:
            trial_index: Index as returned in ``_trial_counter`` during
                ``suggest_candidates``.  Must correspond to a pending trial.
            parameters: Parameter values that were evaluated (used for
                bookkeeping; the underlying search point is already tracked).
            metrics: Objective values keyed by objective name.  All names
                listed in ``objective_names`` must be present.

        Raises:
            ValueError: If any required objective is missing from ``metrics``.

        Examples:
            >>> optimizer.update_with_results(
            ...     trial_index=0,
            ...     parameters={"x": 0.5, "y": 0.3},
            ...     metrics={"f1": 0.1, "f2": 0.9},
            ... )
        """
        missing = [o for o in self.objective_names if o not in metrics]
        if missing:
            raise ValueError(
                f"update_with_results: missing objectives {missing}. "
                f"Expected {self.objective_names}, got {list(metrics.keys())}."
            )

        # Buffer the result
        self._result_buffer[trial_index] = {k: float(v) for k, v in metrics.items()}

        # Update trial record
        trial = Trial(
            index=trial_index,
            parameters=parameters,
            metrics={k: float(v) for k, v in metrics.items()},
            status="completed",
        )
        while len(self._trials) <= trial_index:
            self._trials.append(None)
        self._trials[trial_index] = trial

        # Flush once all candidates of the current generation have results
        if len(self._result_buffer) == len(self._gen_pos_to_trial_idx):
            self._flush_generation()

    def serialize_state(self) -> Dict[str, Any]:
        """Serialise optimizer state to a JSON-compatible dictionary.

        The serialised state includes the config, search space description,
        objective names, and all recorded trials.  The PyMOO algorithm's
        internal population state is serialised via ``pickle`` and encoded as
        a base-64 string to allow full resumption without re-running
        evaluations.

        Returns:
            JSON-serialisable dictionary containing all state needed to
            rebuild this optimizer via ``load_state``.

        Examples:
            >>> import json
            >>> state = optimizer.serialize_state()
            >>> with open("checkpoint.json", "w") as f:
            ...     json.dump(state, f)

        Notes:
            If the algorithm cannot be pickled (rare), the ``"algorithm_pickle"``
            key is omitted and a WARNING is logged.  ``load_state`` will then
            recreate the algorithm from the config + seed instead.
        """
        import base64
        import pickle

        space_payload = {
            name: param.model_dump()
            for name, param in self.search_space.parameters.items()
        }
        constraints_payload = [
            c.model_dump() for c in self.search_space.constraints
        ]

        algorithm_pickle: Optional[str] = None
        try:
            algorithm_pickle = base64.b64encode(
                pickle.dumps(self._algorithm)
            ).decode("ascii")
        except Exception as exc:
            logger.warning(
                "Could not pickle PyMOO algorithm state: %s. "
                "load_state will restart the algorithm from scratch.",
                exc,
            )

        return {
            "backend": "pymoo",
            "search_space": {
                "parameters": space_payload,
                "constraints": constraints_payload,
                "name": self.search_space.name,
            },
            "objective_names": self.objective_names,
            "seed": self.seed,
            "config": self.config.model_dump(),
            "resolved_algorithm": self.resolved_algorithm,
            "trials": [
                {
                    "index": t.index,
                    "parameters": t.parameters,
                    "metrics": t.metrics,
                    "status": t.status,
                    "metadata": t.metadata,
                }
                for t in self._trials
                if t is not None
            ],
            "trial_counter": self._trial_counter,
            "n_gen_completed": self.n_gen_completed,
            "algorithm_pickle": algorithm_pickle,
        }

    def load_state(self, state: Dict[str, Any]) -> None:
        """Restore optimizer state from a serialised dictionary.

        The search space, config, objective names, completed trials, and
        (when available) the pickled algorithm state are all restored.  If
        ``algorithm_pickle`` is absent or cannot be deserialised, the algorithm
        is rebuilt from the config and seed, which means the internal
        population will be reset.

        Args:
            state: Dictionary as returned by ``serialize_state``.

        Raises:
            ValueError: If required keys are missing from ``state``.
            ImportError: If PyMOO is not installed.

        Notes:
            After a successful load, ``suggest_candidates`` resumes from where
            optimisation left off (provided the algorithm pickle was valid).
            Any in-flight generation (partial results) is discarded on load.
        """
        if not PYMOO_AVAILABLE:
            raise ImportError(
                "PyMOO is required but not installed. "
                "Install with: pip install pymoo"
            )

        required = {"search_space", "objective_names", "config", "trials"}
        missing = required - state.keys()
        if missing:
            raise ValueError(f"load_state: missing keys in state: {missing}")

        # Restore config, objectives, seed
        self.config = PyMOOOptimizerConfig(**state["config"])
        self.objective_names = list(state["objective_names"])
        self.seed = state.get("seed", self.config.seed)
        resolved_algorithm = self.config.resolve_algorithm(self.n_objectives)
        stored_algorithm = state.get("resolved_algorithm")
        if stored_algorithm and stored_algorithm != resolved_algorithm:
            logger.warning(
                "Stored resolved_algorithm '%s' does not match current resolved "
                "algorithm '%s'; using current value.",
                stored_algorithm,
                resolved_algorithm,
            )
        self.resolved_algorithm = resolved_algorithm

        saved_space = state["search_space"]
        self.search_space = SearchSpace(
            parameters=saved_space.get("parameters", {}),
            constraints=saved_space.get("constraints", []),
            name=saved_space.get("name"),
        )

        self._param_items = list(self.search_space.parameters.items())
        self._xl, self._xu = self._build_bounds()
        self.problem = PyMOOProblem(
            n_var=len(self._param_items),
            n_obj=self.n_objectives,
            xl=self._xl,
            xu=self._xu,
            param_items=self._param_items,
            objective_names=self.objective_names,
        )

        # Try to restore the algorithm state from pickle
        import base64
        import pickle

        algorithm_pickle = state.get("algorithm_pickle")
        if algorithm_pickle:
            try:
                self._algorithm = pickle.loads(
                    base64.b64decode(algorithm_pickle.encode("ascii"))
                )
                logger.info("PyMOO algorithm state restored from pickle.")
            except Exception as exc:
                logger.warning(
                    "Could not unpickle algorithm state (%s); "
                    "recreating from config + seed.",
                    exc,
                )
                self._algorithm = self._create_algorithm()
                self._algorithm.setup(
                    self.problem,
                    seed=self.seed,
                    verbose=self.config.verbose,
                    termination=NoTermination(),
                )
        else:
            self._algorithm = self._create_algorithm()
            self._algorithm.setup(
                self.problem,
                seed=self.seed,
                verbose=self.config.verbose,
                termination=NoTermination(),
            )

        # Restore trials
        self._trials = []
        for td in state["trials"]:
            trial = Trial(
                index=td["index"],
                parameters=td["parameters"],
                metrics=td.get("metrics"),
                status=td.get("status", "pending"),
                metadata=td.get("metadata", {}),
            )
            while len(self._trials) <= trial.index:
                self._trials.append(None)
            self._trials[trial.index] = trial

        self._trial_counter = state.get("trial_counter", len(self._trials))
        self.n_gen_completed = state.get("n_gen_completed", 0)

        # Clear any in-flight generation state
        self._generation_infills = None
        self._gen_pos_to_trial_idx = {}
        self._result_buffer = {}

        logger.info(
            "PyMOO optimizer state loaded: algorithm=%s, %d trials, %d generations completed.",
            self.resolved_algorithm,
            len(self._trials),
            self.n_gen_completed,
        )

    # ------------------------------------------------------------------
    # Dunder helpers
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        """Return a concise string representation of the optimizer.

        Returns:
            Human-readable description including algorithm, parameter count,
            objective count, and seed.
        """
        return (
            f"PyMOOOptimizer("
            f"algorithm={self.resolved_algorithm}, "
            f"pop_size={self.config.pop_size}, "
            f"n_params={len(self.search_space.parameters)}, "
            f"n_objectives={self.n_objectives}, "
            f"n_gen_completed={self.n_gen_completed}, "
            f"seed={self.seed})"
        )
