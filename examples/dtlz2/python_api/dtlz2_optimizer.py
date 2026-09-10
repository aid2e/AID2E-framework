#!/usr/bin/env python3
"""Example demonstrating config-driven AxOptimizer integration with DTLZ2.

This script shows how to:
1. Load a full optimizer configuration from a JSON or YAML file
2. Load only the problem section from a full configuration
3. Build the search space and AxOptimizer through AID2E
4. Run multi-objective optimization on the DTLZ2 benchmark
5. Retrieve the optimization results, Pareto front, and best trial
6. Serialize and deserialize optimizer state
7. Enable debug logging and write detailed optimization diagnostics

DTLZ2 is a multi-objective test problem with a known Pareto front. For the
two-objective problem used here, the optimal solutions lie on the first-quadrant
unit circle.

Project: AID2E - AI assisted Detector Design for EIC
Homepage: https://aid2e.github.io/AID2E-framework
Repository: https://github.com/aid2e/AID2E-framework.git
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from pprint import pformat
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from aid2e.utilities import build_optimizer_from_config
from aid2e.utilities.configurations import load_config, load_problem_config

DEFAULT_CONFIG_PATH = (
    REPO_ROOT / "examples" / "dtlz2" / "configurations" / "dtlz2_ax_joblib.json"
)
LOGGER = logging.getLogger("examples.dtlz2.optimizer")


def parse_args(argv: List[str]) -> argparse.Namespace:
    """Parse the config, iteration, logging, and diagnostic options."""
    parser = argparse.ArgumentParser(
        description="Run the config-driven AxOptimizer DTLZ2 example."
    )
    parser.add_argument(
        "config",
        nargs="?",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help="Path to the DTLZ2 optimizer configuration.",
    )
    parser.add_argument(
        "iterations",
        nargs="?",
        type=int,
        help="Optional optimization-iteration override.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Optional directory for JSON diagnostic artifacts.",
    )
    parser.add_argument(
        "--debug",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Enable verbose debug logging.",
    )
    return parser.parse_args(argv)


def configure_logging(debug: bool) -> None:
    """Configure example and optimizer-library logging."""
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-8s [%(name)s] %(message)s",
        force=True,
    )
    for logger_name in ("aid2e", "ax", "botorch", "gpytorch"):
        logging.getLogger(logger_name).setLevel(level)


def trial_to_dict(trial: Any) -> Dict[str, Any]:
    """Convert an optimizer trial into JSON-serializable diagnostics."""
    return {
        "index": trial.index,
        "status": trial.status,
        "parameters": dict(trial.parameters),
        "metrics": dict(trial.metrics or {}),
        "metadata": dict(trial.metadata or {}),
    }


def ordered_dtlz_vector(parameters: Dict[str, Any]) -> List[float]:
    """Return ordered DTLZ decision variables from a flat parameter dictionary.

    Args:
        parameters: Flat AID2E parameter dictionary using qualified names such
            as ``DTLZ2_variables.x1`` through ``DTLZ2_variables.x10``.

    Returns:
        Parameter values ordered numerically by variable name.
    """
    indexed: List[tuple[int, float]] = []
    for key, value in parameters.items():
        short_key = key.split(".")[-1].split("__")[-1]
        if short_key.startswith("x") and short_key[1:].isdigit():
            indexed.append((int(short_key[1:]), float(value)))
    indexed.sort(key=lambda item: item[0])
    return [value for _, value in indexed]


def dtlz2_objectives(
    x: List[float],
    n_objectives: int = 2,
) -> Dict[str, float]:
    """Compute the DTLZ2 multi-objective test function.

    Args:
        x: Ordered decision variables ``x1``, ``x2``, and so on.
        n_objectives: Number of objectives. Defaults to two.

    Returns:
        Dictionary containing objective values ``f1`` through
        ``f<n_objectives>``.

    Notes:
        The auxiliary function ``g`` is the sum of squared deviations from
        ``0.5`` for the decision variables after the first
        ``n_objectives - 1`` variables. When those variables equal ``0.5``,
        ``g = 0`` and the objectives lie on the first-quadrant unit
        hypersphere. For two objectives, ``f1**2 + f2**2 = 1`` describes a
        unit circle.
    """
    g = sum((value - 0.5) ** 2 for value in x[n_objectives - 1 :])
    objectives: Dict[str, float] = {}
    for index in range(n_objectives):
        value = 1.0 + g
        for variable_index in range(n_objectives - index - 1):
            value *= math.cos(x[variable_index] * math.pi / 2.0)
        if index > 0:
            value *= math.sin(x[n_objectives - index - 1] * math.pi / 2.0)
        objectives[f"f{index + 1}"] = float(value)
    return objectives


def example_problem_only_loader(config_file: Path) -> None:
    """Load only the problem section from a complete configuration file."""
    problem = load_problem_config(str(config_file))
    print("Problem-only configuration:")
    print(f"  Name: {problem.name}")
    print(f"  Objectives: {[objective.name for objective in problem.objectives]}")
    print(
        "  Design variables: "
        f"{len(problem.design_config.get_flat_parameters())}"
    )


def main(argv: List[str]) -> int:
    args = parse_args(argv[1:])
    configure_logging(args.debug)

    # 1. Load the full configuration from JSON or YAML.
    config_file = args.config.resolve()
    example_problem_only_loader(config_file)
    config = load_config(str(config_file))

    output_dir = args.output_dir.resolve() if args.output_dir else None
    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)

    LOGGER.info("Repository root: %s", REPO_ROOT)
    LOGGER.info("Config path: %s", config_file)
    LOGGER.info("Output directory: %s", output_dir)
    LOGGER.info("Debug logging enabled: %s", args.debug)

    # 2. Parse the registered Ax configuration and optional iteration override.
    optimizer_config = config.optimizer.parse_algorithm_params()
    if optimizer_config is None:
        raise RuntimeError("No registered optimizer config model found for Ax example.")
    n_iterations = (
        args.iterations
        if args.iterations is not None
        else optimizer_config.n_iterations
    )

    # 3. Build the search space and AxOptimizer from the validated configuration.
    optimizer = build_optimizer_from_config(config.problem, config.optimizer)
    n_objectives = len(config.problem.objectives)

    nodes = getattr(optimizer.generation_strategy, "nodes", None)
    generation_summary = {
        "name": optimizer.generation_strategy.name,
        "nodes": [node.name for node in nodes] if nodes else [],
    }

    # 4. Display the effective optimizer and problem settings.
    print("Backend: ax")
    print(f"Config: {config_file}")
    print(f"Objectives: {[objective.name for objective in config.problem.objectives]}")
    print(
        f"Design variables: {len(config.problem.design_config.get_flat_parameters())}"
    )
    print(f"Generator: {optimizer_config.generator}")
    print(f"Initial samples: {optimizer_config.n_initial_samples}")
    print(f"Optimization iterations: {n_iterations}")
    print(f"Batch size: {optimizer_config.batch_size}")
    print("Generation strategy summary:")
    print(pformat(generation_summary))
    print(
        f"\n{'Trial':<6} {'Phase':<10} {'x1':<10} {'x2':<10} {'x3':<10} "
        f"{'f1':<12} {'f2':<12}"
    )
    print("-" * 80)

    # This Python API example evaluates candidates locally and feeds results
    # directly into the optimizer; it does not execute the configured workflow.

    # 5. Generate and evaluate the configured Sobol initialization points.
    records: List[Dict[str, Any]] = []
    first_candidate: Dict[str, Any] | None = None
    remaining_init = optimizer_config.n_initial_samples
    init_batch = 0
    while remaining_init > 0:
        init_batch += 1
        current_batch = min(optimizer_config.batch_size, remaining_init)
        candidates = optimizer.suggest_candidates(n_candidates=current_batch)
        if first_candidate is None and candidates:
            first_candidate = dict(candidates[0])
            print("First Ax candidate from the configured optimizer:")
            print(pformat(first_candidate))
        start_index = len(optimizer.get_trials()) - len(candidates)
        for offset, parameters in enumerate(candidates):
            trial_index = start_index + offset
            metrics = dtlz2_objectives(
                ordered_dtlz_vector(parameters),
                n_objectives=n_objectives,
            )
            optimizer.update_with_results(
                trial_index=trial_index,
                parameters=parameters,
                metrics=metrics,
            )
            record = {
                "trial_index": trial_index,
                "phase": f"init-{init_batch}",
                "parameters": dict(parameters),
                "metrics": metrics,
            }
            LOGGER.debug("Recorded %s", pformat(record))
            records.append(record)
            vector = ordered_dtlz_vector(parameters)
            print(
                f"{trial_index + 1:<6} {'init':<10} "
                f"{vector[0]:<10.4f} {vector[1]:<10.4f} {vector[2]:<10.4f} "
                f"{metrics['f1']:<12.6f} {metrics['f2']:<12.6f}"
            )
        remaining_init -= current_batch

    # 6. Generate and evaluate each Bayesian optimization batch.
    for iteration in range(n_iterations):
        candidates = optimizer.suggest_candidates(
            n_candidates=optimizer_config.batch_size
        )
        start_index = len(optimizer.get_trials()) - len(candidates)
        for offset, parameters in enumerate(candidates):
            trial_index = start_index + offset
            metrics = dtlz2_objectives(
                ordered_dtlz_vector(parameters),
                n_objectives=n_objectives,
            )
            optimizer.update_with_results(
                trial_index=trial_index,
                parameters=parameters,
                metrics=metrics,
            )
            record = {
                "trial_index": trial_index,
                "phase": f"iter-{iteration + 1}",
                "parameters": dict(parameters),
                "metrics": metrics,
            }
            LOGGER.debug("Recorded %s", pformat(record))
            records.append(record)
            vector = ordered_dtlz_vector(parameters)
            print(
                f"{trial_index + 1:<6} {f'iter-{iteration + 1}':<10} "
                f"{vector[0]:<10.4f} {vector[1]:<10.4f} {vector[2]:<10.4f} "
                f"{metrics['f1']:<12.6f} {metrics['f2']:<12.6f}"
            )

    # 7. Retrieve the complete result summary and Pareto-optimal trials.
    results = optimizer.get_optimization_results()
    pareto_front = optimizer.get_pareto_front()

    print("\nSummary")
    print(f"Trials recorded: {results['n_trials']}")
    print(f"Pareto points: {len(pareto_front)}")

    # 8. Get a representative best trial from the Pareto front.
    print("\nBest trial (from Pareto front):")
    best_trial = optimizer.get_best_trial()
    if best_trial:
        print(f"Objectives: {best_trial.metrics}")
        print("(For two-objective DTLZ2, the optimal Pareto front is a unit circle)")

    # 9. Serialize the optimizer state for storage or later reconstruction.
    print("\nTesting state serialization...")
    state = optimizer.serialize_state()
    print(f"Serialized state has {len(state['trials'])} trials")

    # 10. Create a second optimizer and restore the serialized state.
    optimizer2 = build_optimizer_from_config(config.problem, config.optimizer)
    optimizer2.load_state(state)
    print(f"Loaded state: {len(optimizer2.get_trials())} trials restored")

    pareto_front2 = optimizer2.get_pareto_front()
    print(f"Pareto front after reload: {len(pareto_front2)} solutions")

    if len(optimizer2.get_trials()) != len(optimizer.get_trials()):
        raise RuntimeError("Optimizer trial count was not restored")
    if len(pareto_front2) != len(pareto_front):
        raise RuntimeError("Optimizer Pareto front was not restored")

    # 11. Optionally write detailed trial and execution diagnostics.
    if output_dir is not None:
        summary = {
            "n_trials": results["n_trials"],
            "pareto_points": len(pareto_front),
            "objective_names": [
                objective.name for objective in config.problem.objectives
            ],
        }
        artifact = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "slurm_job_id": os.environ.get("SLURM_JOB_ID"),
            "cwd": str(Path.cwd()),
            "config_path": str(config_file),
            "output_dir": str(output_dir),
            "debug": args.debug,
            "optimizer_parameters": config.optimizer.parameters,
            "generation_strategy": generation_summary,
            "first_candidate": first_candidate,
            "records": records,
            "summary": summary,
            "trials": [trial_to_dict(trial) for trial in optimizer.get_trials()],
        }

        job_suffix = os.environ.get("SLURM_JOB_ID", "local")
        artifact_path = output_dir / f"dtlz2_optimizer_diagnostics_{job_suffix}.json"
        artifact_path.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
        print(f"Diagnostic artifact written to: {artifact_path}")
        LOGGER.info("Diagnostic artifact written to %s", artifact_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
