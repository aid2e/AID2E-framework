"""Single-objective PyMOO example with inferred GA default."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from aid2e.optimizers.pymoo import PyMOOOptimizer, PyMOOOptimizerConfig
from aid2e.utilities.configurations.loaders import load_raw_config
from aid2e.utilities.configurations.problem_config import ProblemConfigLoader

from examples.evaluators.dtlz2 import dtlz2_both_objectives


DEFAULT_CONFIG_PATH = REPO_ROOT / "examples" / "optimizers" / "dtlz2_framework_shared.yml"


def _ordered_dtlz_vector(parameters: Dict[str, Any]) -> List[float]:
    indexed: List[tuple[int, float]] = []
    for key, value in parameters.items():
        short_key = key.split(".")[-1].split("__")[-1]
        if short_key.startswith("x") and short_key[1:].isdigit():
            indexed.append((int(short_key[1:]), float(value)))
    indexed.sort(key=lambda item: item[0])
    return [value for _, value in indexed]


def _evaluate(parameters: Dict[str, Any]) -> Dict[str, float]:
    return {"f1": dtlz2_both_objectives(_ordered_dtlz_vector(parameters))["f1"]}


def _save_payload(path: Path, payload: Dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    return path


def main(argv: List[str]) -> int:
    config_file = Path(argv[1]).resolve() if len(argv) >= 2 else DEFAULT_CONFIG_PATH
    raw_config = load_raw_config(str(config_file))
    problem_cfg = ProblemConfigLoader.from_dict(
        raw_config["problem"],
        base_dir=str(config_file.parent),
    )

    optimizer_config = PyMOOOptimizerConfig(
        pop_size=8,
        n_offsprings=8,
        crossover_prob=0.9,
        crossover_eta=15.0,
        mutation_eta=20.0,
        n_iterations=4,
        seed=42,
        verbose=False,
    )

    optimizer = PyMOOOptimizer(
        search_space=problem_cfg.design_config,
        config=optimizer_config,
        objective_names=["f1"],
        seed=optimizer_config.seed,
    )

    print("Backend: aid2e-pymoo")
    print(f"Config: {config_file}")
    print("Objectives: ['f1']")
    print(f"Algorithm: {optimizer.resolved_algorithm}")
    print(f"Design variables: {len(problem_cfg.design_config.get_flat_parameters())}")
    print(f"Generations: {optimizer_config.n_iterations}")
    print(f"Population size: {optimizer_config.pop_size}")
    print(f"\n{'Iter':<6} {'Gen':<6} {'x1':<10} {'x2':<10} {'x3':<10} {'f1':<12}")
    print("-" * 64)

    records: List[Dict[str, Any]] = []

    for generation in range(optimizer_config.n_iterations):
        candidates = optimizer.suggest_candidates()
        start_index = len(optimizer.get_trials()) - len(candidates)
        for offset, parameters in enumerate(candidates):
            trial_index = start_index + offset
            metrics = _evaluate(parameters)
            optimizer.update_with_results(
                trial_index=trial_index,
                parameters=parameters,
                metrics=metrics,
            )
            vector = _ordered_dtlz_vector(parameters)
            print(
                f"{trial_index + 1:<6} {generation + 1:<6} "
                f"{vector[0]:<10.4f} {vector[1]:<10.4f} {vector[2]:<10.4f} "
                f"{metrics['f1']:<12.6f}"
            )
            records.append(
                {
                    "trial_index": trial_index,
                    "parameters": parameters,
                    "metrics": metrics,
                    "generation": generation + 1,
                }
            )

    results_path = (Path.cwd() / "dtlz2_framework_pymoo_single_objective_results.json").resolve()
    session_path = (Path.cwd() / "dtlz2_framework_pymoo_single_objective_session.json").resolve()

    results_payload = optimizer.get_optimization_results()
    results_payload["config_file"] = str(config_file)
    results_payload["optimizer_config"] = optimizer_config.model_dump()
    results_payload["records"] = records
    results_payload["summary"] = {
        "backend": "pymoo",
        "algorithm": optimizer.resolved_algorithm,
        "n_trials": results_payload["n_trials"],
        "best_loss": optimizer.get_best_trial().metrics["f1"] if optimizer.get_best_trial() else None,
    }

    _save_payload(results_path, results_payload)
    _save_payload(session_path, optimizer.serialize_state())

    print(f"\nSaved results to: {results_path}")
    print(f"Saved session to: {session_path}")
    print(f"Trials recorded: {results_payload['n_trials']}")
    print(f"Best f1: {results_payload['summary']['best_loss']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
