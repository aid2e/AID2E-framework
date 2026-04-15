"""Simple Ax optimizer example using direct DTLZ2 ask/tell evaluation."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from aid2e.optimizers import TrialObservation
from aid2e.optimizers.ax import AxOptimizer, AxOptimizerConfig
from aid2e.utilities.configurations import load_problem_config

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
    return dtlz2_both_objectives(_ordered_dtlz_vector(parameters))


def _save_payload(path: Path, payload: Dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


def main(argv: List[str]) -> int:
    config_file = Path(argv[1]).resolve() if len(argv) >= 2 else DEFAULT_CONFIG_PATH
    problem_cfg = load_problem_config(str(config_file))

    optimizer_config = AxOptimizerConfig(
        initialization_strategy="sobol",
        generator="BOTORCH_MODULAR",
        n_initial_samples=4,
        n_iterations=3,
        batch_size=2,
        seed=42,
        generator_kwargs={
            "botorch_acqf_class": "qLogNoisyExpectedImprovement",
            "acquisition_options": {
                "prune_baseline": True,
            }
        },
        generator_gen_kwargs={
            "model_gen_options": {
                "optimizer_kwargs": {
                    "num_restarts": 10,
                    "sequential": False,
                    "options": {
                        "batch_limit": 5,
                        "maxiter": 100,
                    },
                }
            }
        },
        objective_thresholds={
            "f1": 1.0,
            "f2": 1.0,
        },
    )

    optimizer = AxOptimizer(
        search_space=problem_cfg.design_config,
        config=optimizer_config,
        objective_names=[objective.name for objective in problem_cfg.objectives],
        seed=optimizer_config.seed,
    )

    print("Backend: aid2e-ax")
    print(f"Config: {config_file}")
    print(f"Objectives: {[objective.name for objective in problem_cfg.objectives]}")
    print(f"Design variables: {len(problem_cfg.design_config.get_flat_parameters())}")
    print(f"Initial samples: {optimizer_config.n_initial_samples}")
    print(f"Iterations: {optimizer_config.n_iterations}")
    print(f"Batch size: {optimizer_config.batch_size}")
    print(f"Generator: {optimizer_config.generator}")
    print(f"Generator kwargs: {optimizer_config.generator_kwargs}")
    print(f"Generator gen kwargs: {optimizer_config.generator_gen_kwargs}")
    print(
        f"\n{'Iter':<6} {'Batch':<6} {'x1':<10} {'x2':<10} {'x3':<10} "
        f"{'f1':<12} {'f2':<12} {'Phase':<10}"
    )
    print("-" * 90)

    records: List[Dict[str, Any]] = []

    remaining_init = optimizer_config.n_initial_samples
    batch_counter = 0
    while remaining_init > 0:
        batch_counter += 1
        current_batch = min(optimizer_config.batch_size, remaining_init)
        for suggestion in optimizer.ask(n_candidates=current_batch):
            metrics = _evaluate(suggestion.parameters)
            optimizer.tell(
                [
                    TrialObservation(
                        trial_index=suggestion.trial_index,
                        trial_id=suggestion.trial_id,
                        backend_trial_id=suggestion.backend_trial_id,
                        parameters=suggestion.parameters,
                        metrics=metrics,
                        metadata={"phase": "init", "batch": batch_counter},
                    )
                ]
            )
            vector = _ordered_dtlz_vector(suggestion.parameters)
            print(
                f"{suggestion.trial_index + 1:<6} {batch_counter:<6} "
                f"{vector[0]:<10.4f} {vector[1]:<10.4f} {vector[2]:<10.4f} "
                f"{metrics['f1']:<12.6f} {metrics['f2']:<12.6f} {'Init':<10}"
            )
            records.append(
                {
                    "trial_index": suggestion.trial_index,
                    "trial_id": suggestion.trial_id,
                    "parameters": suggestion.parameters,
                    "metrics": metrics,
                    "phase": "init",
                }
            )
        remaining_init -= current_batch

    for iteration in range(optimizer_config.n_iterations):
        for suggestion in optimizer.ask(n_candidates=optimizer_config.batch_size):
            metrics = _evaluate(suggestion.parameters)
            optimizer.tell(
                [
                    TrialObservation(
                        trial_index=suggestion.trial_index,
                        trial_id=suggestion.trial_id,
                        backend_trial_id=suggestion.backend_trial_id,
                        parameters=suggestion.parameters,
                        metrics=metrics,
                        metadata={"phase": "optimize", "iteration": iteration + 1},
                    )
                ]
            )
            vector = _ordered_dtlz_vector(suggestion.parameters)
            print(
                f"{suggestion.trial_index + 1:<6} {iteration + 1:<6} "
                f"{vector[0]:<10.4f} {vector[1]:<10.4f} {vector[2]:<10.4f} "
                f"{metrics['f1']:<12.6f} {metrics['f2']:<12.6f} {'Optimize':<10}"
            )
            records.append(
                {
                    "trial_index": suggestion.trial_index,
                    "trial_id": suggestion.trial_id,
                    "parameters": suggestion.parameters,
                    "metrics": metrics,
                    "phase": "optimize",
                }
            )

    results_path = (Path.cwd() / "dtlz2_framework_ax_results.json").resolve()
    session_path = (Path.cwd() / "dtlz2_framework_ax_session.json").resolve()

    results_payload = optimizer.get_optimization_results()
    results_payload["config_file"] = str(config_file)
    results_payload["optimizer_config"] = optimizer_config.model_dump()
    results_payload["records"] = records
    results_payload["summary"] = {
        "backend": "ax",
        "n_trials": results_payload["n_trials"],
        "pareto_points": len(optimizer.get_pareto_front()),
    }

    _save_payload(results_path, results_payload)
    optimizer.save_session(session_path)

    print(f"\nSaved results to: {results_path}")
    print(f"Saved session to: {session_path}")
    print(f"Trials recorded: {results_payload['n_trials']}")
    print(f"Pareto points: {results_payload['summary']['pareto_points']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
