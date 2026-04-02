"""PyMOO-based evolutionary optimizer for AID2E framework.

This module integrates PyMOO's evolutionary algorithms (NSGA-II, NSGA-III,
MOEA/D) with the AID2E ``BaseOptimizer`` interface via PyMOO's ask/tell
protocol.

Design overview
---------------
PyMOO algorithms are inherently *batch-generational*: an entire population of
candidates is generated, evaluated externally, and then fed back before the
next generation can be produced.  This maps cleanly to the AID2E interface as
follows:

- ``suggest_candidates(n)`` → calls ``algorithm.ask()`` and returns the
  current generation as a list of parameter dicts.
- ``update_with_results(trial_index, params, metrics)`` → buffers one result;
  when all candidates of the current generation have been returned, the buffer
  is flushed by calling ``algorithm.tell()`` internally.

Because ``update_with_results`` is called once per individual while PyMOO
requires all result in a single ``tell()`` call, a *generation buffer* is
maintained internally.  The caller need not be aware of this detail.

Parameter encoding
------------------
``RangeParameter`` values are passed directly as float variables.
``ChoiceParameter`` values are encoded as integers in ``[0, n_choices − 1]``
and decoded back to string choices when building the candidate dict.

Constraints
-----------
Linear parameter constraints (``ParameterConstraint``) are not yet natively
passed to PyMOO algorithms.  When a search space has constraints, a warning is
logged and runtime validation via ``SearchSpace.validate()`` is left to the
caller.  Native constraint support (via PyMOO's ``G`` output) is planned for a
future release.

Project: AID2E v0.0.0 — AI assisted Detector Design for EIC
Homepage: https://aid2e.github.io/AID2E-framework
Repository: https://github.com/aid2e/AID2E-framework.git
"""

from __future__ import annotations

import logging
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
# Internal PyMOO problem proxy
# ---------------------------------------------------------------------------

class _ExternalEvalProblem(Problem):
    """Minimal PyMOO Problem that carries search‑space metadata.

    ``_evaluate`` is intentionally not implemented here.  In the ask/tell
    workflow the optimizer sets objective values on the population directly,
    so this class only exists to provide ``n_var``, ``n_obj``, ``xl``, and
    ``xu`` to the initialising algorithm.

    Args:
        n_var: Number of decision variables.
        n_obj: Number of objectives.
        xl: Lower bounds array of shape ``(n_var,)``.
        xu: Upper bounds array of shape ``(n_var,)``.
    """

    def __init__(self, n_var: int, n_obj: int, xl: np.ndarray, xu: np.ndarray) -> None:
        """Initialise the proxy problem with structural metadata only."""
        super().__init__(n_var=n_var, n_obj=n_obj, xl=xl, xu=xu)

    def _evaluate(self, x: np.ndarray, out: dict, *args: Any, **kwargs: Any) -> None:
        """Raise an error — evaluation is handled externally via ask/tell."""
        raise NotImplementedError(
            "_ExternalEvalProblem is only valid in ask/tell mode. "
            "Do not call _evaluate directly."
        )


# ---------------------------------------------------------------------------
# Main optimizer class
# ---------------------------------------------------------------------------

class PyMOOOptimizer(BaseOptimizer):
    """Evolutionary multi-objective optimizer backed by PyMOO algorithms.

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
        >>> config = PyMOOOptimizerConfig(algorithm="nsga2", pop_size=20, seed=0)
        >>> opt = PyMOOOptimizer(space, config, objective_names=["f1", "f2"])
        >>> candidates = opt.suggest_candidates()
        >>> for trial_idx, c in enumerate(candidates):
        ...     opt.update_with_results(trial_idx, c, {"f1": c["x"], "f2": c["y"]})
        >>> pareto = opt.get_pareto_front()

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

        # Create the structural problem proxy
        self._problem = _ExternalEvalProblem(
            n_var=n_var,
            n_obj=self.n_objectives,
            xl=self._xl,
            xu=self._xu,
        )

        # Create the PyMOO algorithm
        self._algorithm = self._create_algorithm()
        self._algorithm.setup(
            self._problem,
            seed=self.seed,
            verbose=self.config.verbose,
            termination=NoTermination(),
        )

        # Trial bookkeeping
        self._trials: List[Optional[Trial]] = []
        self._trial_counter: int = 0
        self.n_gen_completed: int = 0

        # Per-generation state (cleared after each tell())
        self._generation_infills: Any = None           # pymoo Population
        self._gen_pos_to_trial_idx: Dict[int, int] = {}  # position → trial_index
        self._result_buffer: Dict[int, Dict[str, float]] = {}  # trial_index → metrics

        logger.info(
            "PyMOOOptimizer initialised: algorithm=%s, pop_size=%d, "
            "n_params=%d, n_objectives=%d, seed=%s",
            config.algorithm,
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
        """Decode a PyMOO individual vector into a parameter dictionary.

        Args:
            x_row: 1-D float array of length ``n_var`` as returned by PyMOO.

        Returns:
            Mapping of parameter names to their decoded values (float for
            ``RangeParameter``, str for ``ChoiceParameter``).
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
            ValueError: If ``config.algorithm`` is not a supported identifier.

        Notes:
            Algorithm objects are created *before* ``setup()`` is called so
            that ``__init__`` can validate the config without triggering any
            sampling.
        """
        alg = self.config.algorithm.lower()
        n_offsprings = self.config.n_offsprings  # None → pop_size default

        crossover = SBX(
            prob=self.config.crossover_prob,
            eta=self.config.crossover_eta,
        )
        mutation = PM(eta=self.config.mutation_eta)
        sampling = FloatRandomSampling()

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
            f"Unknown PyMOO algorithm '{self.config.algorithm}'. "
            "Supported: 'nsga2', 'nsga3', 'moead'."
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
    # BaseOptimizer abstract interface
    # ------------------------------------------------------------------

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

    def get_trials(self) -> List[Trial]:
        """Return all recorded trials (pending, completed, and failed).

        Returns:
            List of non-``None`` Trial objects in the order they were created.

        Examples:
            >>> done = [t for t in optimizer.get_trials() if t.status == "completed"]
        """
        return [t for t in self._trials if t is not None]

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

        saved_space = state["search_space"]
        self.search_space = SearchSpace(
            parameters=saved_space.get("parameters", {}),
            constraints=saved_space.get("constraints", []),
            name=saved_space.get("name"),
        )

        self._param_items = list(self.search_space.parameters.items())
        self._xl, self._xu = self._build_bounds()
        self._problem = _ExternalEvalProblem(
            n_var=len(self._param_items),
            n_obj=self.n_objectives,
            xl=self._xl,
            xu=self._xu,
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
                    self._problem,
                    seed=self.seed,
                    verbose=self.config.verbose,
                    termination=NoTermination(),
                )
        else:
            self._algorithm = self._create_algorithm()
            self._algorithm.setup(
                self._problem,
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
            "PyMOO optimizer state loaded: %d trials, %d generations completed.",
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
            f"algorithm={self.config.algorithm}, "
            f"pop_size={self.config.pop_size}, "
            f"n_params={len(self.search_space.parameters)}, "
            f"n_objectives={self.n_objectives}, "
            f"n_gen_completed={self.n_gen_completed}, "
            f"seed={self.seed})"
        )
