"""Minimal PyMOO optimizer-only DTLZ2 example."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import List

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from aid2e.utilities import build_optimizer_from_config
from aid2e.utilities.configurations import load_config
from examples.dtlz2.dtlz2_evaluator import design_vector, dtlz2_both_objectives


DEFAULT_CONFIG_PATH = REPO_ROOT / "examples" / "dtlz2" / "configurations" / "dtlz2_pymoo_joblib.yml"


def main(argv: List[str]) -> int:
    config_file = Path(argv[1]).resolve() if len(argv) >= 2 else DEFAULT_CONFIG_PATH
    config = load_config(str(config_file))
    optimizer_config = config.optimizer.parse_algorithm_params()
    if optimizer_config is None:
        raise RuntimeError("No registered optimizer config model found for PyMOO example.")

    optimizer = build_optimizer_from_config(config.problem, config.optimizer)

    print("Backend: pymoo")
    print(f"Config: {config_file}")
    print(f"Objectives: {[objective.name for objective in config.problem.objectives]}")
    print(f"Design variables: {len(config.problem.design_config.get_flat_parameters())}")
    print(f"Resolved algorithm: {optimizer.resolved_algorithm}")
    print(f"Generations: {optimizer_config.n_iterations}")
    print(f"Population size: {optimizer_config.pop_size}")
    print(
        f"\n{'Trial':<6} {'Gen':<6} {'x1':<10} {'x2':<10} {'x3':<10} "
        f"{'f1':<12} {'f2':<12}"
    )
    print("-" * 76)

    for generation in range(optimizer_config.n_iterations):
        candidates = optimizer.suggest_candidates()
        start_index = len(optimizer.get_trials()) - len(candidates)
        for offset, parameters in enumerate(candidates):
            trial_index = start_index + offset
            metrics = dtlz2_both_objectives(design_vector(parameters))
            optimizer.update_with_results(
                trial_index=trial_index,
                parameters=parameters,
                metrics=metrics,
            )
            vector = design_vector(parameters)
            print(
                f"{trial_index + 1:<6} {generation + 1:<6} "
                f"{vector[0]:<10.4f} {vector[1]:<10.4f} {vector[2]:<10.4f} "
                f"{metrics['f1']:<12.6f} {metrics['f2']:<12.6f}"
            )

    results = optimizer.get_optimization_results()
    pareto_front = optimizer.get_pareto_front()

    print("\nSummary")
    print(f"Trials recorded: {results['n_trials']}")
    print(f"Pareto points: {len(pareto_front)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
