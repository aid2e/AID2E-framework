#!/usr/bin/env python3
"""Example implementing a custom ``BaseOptimizer`` for DTLZ2.

This example demonstrates how to:
1. Define a custom optimizer using the AID2E ``BaseOptimizer`` interface
2. Suggest random candidates from an AID2E ``SearchSpace``
3. Validate candidates against design constraints
4. Record completed trials through ``update_with_results``
5. Use the inherited trial, best-result, and Pareto-front utilities
6. Serialize and restore custom optimizer state
7. Evaluate candidates through an AID2E DTLZ2 workflow
8. Add optional ``suggest()``, ``tell()``, and Pareto helper methods

The random search is intentionally simple. It demonstrates the optimizer
extension interface; production optimization should generally use a maintained
backend such as Ax or PyMOO.

Project: AID2E - AI assisted Detector Design for EIC
Homepage: https://aid2e.github.io/AID2E-framework
Repository: https://github.com/aid2e/AID2E-framework.git
"""

from __future__ import annotations

from typing import Any, Dict, List

import numpy as np

from aid2e.optimizers.base import BaseOptimizer, SearchSpace
from aid2e.utilities.configurations.base_models import (
    ChoiceParameter,
    RangeParameter,
)
from aid2e.utilities.workflows import DAGExecutor

from dtlz2_optimization import create_single_branch_workflow


# =============================================================================
# Custom Random Optimizer
# =============================================================================

class RandomSearchOptimizer(BaseOptimizer):
    """Simple random-search implementation of the AID2E optimizer interface.

    ``BaseOptimizer`` supplies shared trial history, failure handling,
    optimization-result export, and Pareto-front calculation. A custom backend
    implements candidate generation, result ingestion, and state persistence.
    """

    def __init__(
        self,
        search_space: SearchSpace,
        objective_names: List[str],
        n_iterations: int = 15,
        seed: int = 42,
    ) -> None:
        """Initialize the optimizer and its reproducible random generator."""
        super().__init__(
            search_space=search_space,
            objective_names=objective_names,
            seed=seed,
        )
        self.n_iterations = n_iterations
        self.rng = np.random.RandomState(seed)

    def suggest_candidates(self, n_candidates: int = 1) -> List[Dict[str, Any]]:
        """Suggest random candidates that satisfy the search-space constraints."""
        candidates: List[Dict[str, Any]] = []

        while len(candidates) < n_candidates:
            candidate: Dict[str, Any] = {}
            for name, parameter in self.search_space.parameters.items():
                if isinstance(parameter, RangeParameter):
                    lower, upper = parameter.bounds
                    candidate[name] = float(self.rng.uniform(lower, upper))
                elif isinstance(parameter, ChoiceParameter):
                    candidate[name] = self.rng.choice(parameter.choices).item()
                else:
                    raise TypeError(
                        f"Unsupported parameter type for random search: {type(parameter)}"
                    )

            is_valid, _ = self.search_space.validate(candidate)
            if not is_valid:
                continue

            trial_index = self._trial_counter
            self.set_trial_status(
                trial_index=trial_index,
                status="suggested",
                parameters=candidate,
            )
            candidates.append(candidate)

        return candidates

    def update_with_results(
        self,
        trial_index: int,
        parameters: Dict[str, Any],
        metrics: Dict[str, float],
    ) -> None:
        """Record objective values returned by the workflow evaluation."""
        missing = [name for name in self.objective_names if name not in metrics]
        if missing:
            raise ValueError(
                f"Missing objectives {missing}; received {list(metrics.keys())}"
            )

        self.set_trial_status(
            trial_index=trial_index,
            status="completed",
            parameters=parameters,
            metrics={name: float(metrics[name]) for name in self.objective_names},
        )

    # The following methods are optional convenience utilities. AID2E requires
    # suggest_candidates() and update_with_results(); custom implementations may
    # expose additional methods when another calling convention is useful.

    def suggest(self) -> Dict[str, Any]:
        """Suggest one design point through a compact ask-style interface."""
        return self.suggest_candidates(n_candidates=1)[0]

    def tell(
        self,
        design_point: Dict[str, Any],
        objectives: Dict[str, float],
    ) -> None:
        """Record one result through a compact tell-style interface."""
        pending = [
            trial
            for trial in self.get_trials()
            if trial.status == "suggested" and trial.parameters == design_point
        ]
        if not pending:
            raise ValueError("No suggested trial matches this design point")
        self.update_with_results(pending[-1].index, design_point, objectives)

    def get_best_pareto_front(
        self,
        n_points: int = 5,
    ) -> List[Dict[str, Any]]:
        """Get approximate Pareto-front points with a custom result format.

        Args:
            n_points: Number of points to return.

        Returns:
            List of dictionaries containing design points and objectives.

        Notes:
            ``BaseOptimizer.get_pareto_front()`` already provides the standard
            AID2E implementation. This method demonstrates how a custom
            optimizer can provide its own Pareto utility or output format.
        """
        completed = [
            trial
            for trial in self.get_trials()
            if trial.status == "completed" and trial.metrics
        ]

        # Simple Pareto dominance check.
        pareto_indices: List[int] = []
        for i, trial_i in enumerate(completed):
            is_dominated = False
            for j, trial_j in enumerate(completed):
                if i == j:
                    continue
                # Check if j dominates i: all objectives are no worse and at
                # least one objective is better.
                if all(
                    trial_j.metrics[name] <= trial_i.metrics[name]
                    for name in self.objective_names
                ) and any(
                    trial_j.metrics[name] < trial_i.metrics[name]
                    for name in self.objective_names
                ):
                    is_dominated = True
                    break
            if not is_dominated:
                pareto_indices.append(i)

        return [
            {
                "design_point": completed[index].parameters,
                "objectives": completed[index].metrics,
            }
            for index in pareto_indices[:n_points]
        ]

    def serialize_state(self) -> Dict[str, Any]:
        """Return JSON-compatible random-generator and trial state."""
        rng_name, rng_keys, rng_position, has_gauss, cached_gaussian = (
            self.rng.get_state()
        )
        return {
            "seed": self.seed,
            "n_iterations": self.n_iterations,
            "objective_names": list(self.objective_names),
            "trial_counter": self._trial_counter,
            "trials": [
                {
                    "index": trial.index,
                    "parameters": trial.parameters,
                    "metrics": trial.metrics,
                    "metadata": trial.metadata,
                    "status": trial.status,
                }
                for trial in self.get_trials()
            ],
            "rng_state": {
                "name": rng_name,
                "keys": rng_keys.tolist(),
                "position": rng_position,
                "has_gauss": has_gauss,
                "cached_gaussian": cached_gaussian,
            },
        }

    def load_state(self, state: Dict[str, Any]) -> None:
        """Restore random-generator state and recorded trials."""
        self.seed = state["seed"]
        self.n_iterations = state["n_iterations"]
        self.objective_names = list(state["objective_names"])
        self._trials = []
        self._trial_counter = 0

        for trial in state["trials"]:
            self.set_trial_status(
                trial_index=trial["index"],
                status=trial["status"],
                parameters=trial["parameters"],
                metrics=trial["metrics"],
                metadata=trial["metadata"],
            )

        rng_state = state["rng_state"]
        self.rng.set_state(
            (
                rng_state["name"],
                np.asarray(rng_state["keys"], dtype=np.uint32),
                rng_state["position"],
                rng_state["has_gauss"],
                rng_state["cached_gaussian"],
            )
        )
        self._trial_counter = state["trial_counter"]


# =============================================================================
# DTLZ2 Optimization Example
# =============================================================================

def main() -> None:
    """Run the custom optimizer with the maintained DTLZ2 workflow."""
    # Define the parameter domain consumed by the custom optimizer.
    search_space = SearchSpace(
        parameters={
            "x1": {"value": 0.5, "bounds": [0.0, 1.0]},
            "x2": {"value": 0.5, "bounds": [0.0, 1.0]},
            "x3": {"value": 0.5, "bounds": [0.0, 1.0]},
        }
    )

    # Create the custom optimizer through the same BaseOptimizer interface used
    # by the built-in Ax and PyMOO backends.
    optimizer = RandomSearchOptimizer(
        search_space=search_space,
        objective_names=["f1", "f2"],
        n_iterations=15,
        seed=42,
    )

    # Reuse the single-branch workflow from the Ax/JobLib optimization example.
    # The workflow does not depend on which optimizer generated the candidate.
    executor = DAGExecutor(
        workflow=create_single_branch_workflow(),
        base_output_dir="/tmp/dtlz2_custom_optimizer",
        log_level="WARNING",
    )

    print("DTLZ2 Custom BaseOptimizer Example")
    print("=" * 80)

    for _ in range(optimizer.n_iterations):
        # 1. Ask the optimizer for the next design point. suggest() is an
        # optional convenience wrapper around suggest_candidates().
        candidate = optimizer.suggest()

        # 2. Evaluate that point through the configured workflow.
        objectives = executor.execute(candidate)

        # 3. Return the objective values to the optimizer. tell() is an
        # optional convenience wrapper around update_with_results().
        optimizer.tell(candidate, objectives)
        trial_index = optimizer.get_trials()[-1].index
        print(
            f"Trial {trial_index:2d}: "
            f"x1={candidate['x1']:.4f}, "
            f"x2={candidate['x2']:.4f}, "
            f"x3={candidate['x3']:.4f}, "
            f"f1={objectives['f1']:.6f}, "
            f"f2={objectives['f2']:.6f}"
        )

    # BaseOptimizer provides common result queries for custom implementations.
    pareto_front = optimizer.get_pareto_front()
    custom_pareto_front = optimizer.get_best_pareto_front(n_points=5)
    best_trial = optimizer.get_best_trial()
    print(f"\nCompleted trials: {len(optimizer.get_trials())}")
    print(f"Pareto-front points: {len(pareto_front)}")
    print(f"Custom Pareto-front points shown: {len(custom_pareto_front)}")
    print(f"Representative best trial: {best_trial.index if best_trial else None}")
    print(f"XCom entries collected: {len(executor.global_xcom)}")

    # Demonstrate the required checkpoint interface by restoring a second
    # optimizer instance from the serialized custom state.
    state = optimizer.serialize_state()
    restored = RandomSearchOptimizer(
        search_space=search_space,
        objective_names=["f1", "f2"],
        n_iterations=optimizer.n_iterations,
        seed=42,
    )
    restored.load_state(state)
    print(f"Restored trials: {len(restored.get_trials())}")


if __name__ == "__main__":
    main()
