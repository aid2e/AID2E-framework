"""Run the advanced inline Ax configuration from starter_kit.ipynb in debug mode."""

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
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from aid2e.utilities import build_optimizer_from_config
from aid2e.utilities.configurations import load_config
from aid2e.utilities.configurations.optimizer_config import OptimizerConfiguration


DEFAULT_CONFIG_PATH = Path(__file__).resolve().with_name("dtlz2_ax_optimizer_only.yml")
LOGGER = logging.getLogger("examples.optimizers.ax_advanced_inline_debug")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Exercise the inline advanced Ax setup from starter_kit.ipynb "
            "with debug logging and JSON output."
        )
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help="Path to the DTLZ2 optimizer config YAML.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path.cwd(),
        help="Directory for JSON artifacts. Defaults to the current working directory.",
    )
    parser.add_argument(
        "--debug",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Enable verbose debug logging.",
    )
    return parser.parse_args(argv)


def configure_logging(debug: bool) -> None:
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-8s [%(name)s] %(message)s",
        force=True,
    )
    for logger_name in ("aid2e", "ax", "botorch", "gpytorch"):
        logging.getLogger(logger_name).setLevel(level)


def dtlz2_objectives(parameters: dict[str, Any]) -> dict[str, float]:
    """Compute the two-objective DTLZ2 values for the example design space."""
    x1 = float(parameters["DTLZ2_variables.x1"])
    tail = [
        float(parameters["DTLZ2_variables.x2"]),
        float(parameters["DTLZ2_variables.x3"]),
        float(parameters["DTLZ2_variables.x4"]),
        float(parameters["DTLZ2_variables.x5"]),
    ]
    g = sum((value - 0.5) ** 2 for value in tail)
    factor = 1.0 + g
    f1 = factor * math.cos(x1 * math.pi / 2.0)
    f2 = factor * math.sin(x1 * math.pi / 2.0)
    return {"f1": float(f1), "f2": float(f2)}


def trial_to_dict(trial: Any) -> dict[str, Any]:
    return {
        "index": trial.index,
        "status": trial.status,
        "parameters": dict(trial.parameters),
        "metrics": dict(trial.metrics or {}),
        "metadata": dict(trial.metadata or {}),
    }


def evaluate_candidates(
    optimizer: Any,
    candidates: list[dict[str, Any]],
    *,
    phase: str,
) -> list[dict[str, Any]]:
    """Evaluate locally and feed results back into the optimizer."""
    start_index = len(optimizer.get_trials()) - len(candidates)
    records: list[dict[str, Any]] = []

    for offset, parameters in enumerate(candidates):
        trial_index = start_index + offset
        metrics = dtlz2_objectives(parameters)
        optimizer.update_with_results(
            trial_index=trial_index,
            parameters=parameters,
            metrics=metrics,
        )
        record = {
            "trial_index": trial_index,
            "phase": phase,
            "parameters": dict(parameters),
            "metrics": metrics,
        }
        LOGGER.debug("Recorded %s", pformat(record))
        records.append(record)

    return records


def build_inline_payload() -> dict[str, Any]:
    return {
        "name": "ax",
        "type": "bayesian",
        "parameters": {
            "initialization_strategy": "sobol",
            "generator": "BOTORCH_MODULAR",
            "generator_kwargs": {
                "surrogate_spec": {
                    "model_configs": [
                        {
                            "botorch_model_class": "SaasFullyBayesianSingleTaskGP"
                        }
                    ]
                },
                "botorch_acqf_class": "qLogNoisyExpectedHypervolumeImprovement",
            },
            "objective_thresholds": {"f1": 1.0, "f2": 1.0},
            "n_initial_samples": 10,
            "n_iterations": 20,
            "batch_size": 4,
            "seed": 7,
        },
    }


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    configure_logging(args.debug)

    config_path = args.config.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    LOGGER.info("Repository root: %s", REPO_ROOT)
    LOGGER.info("Config path: %s", config_path)
    LOGGER.info("Output directory: %s", output_dir)
    LOGGER.info("Debug logging enabled: %s", args.debug)

    ax_full_config = load_config(str(config_path))
    ax_inline_optimizer_payload = build_inline_payload()
    ax_inline_optimizer_cfg = OptimizerConfiguration(**ax_inline_optimizer_payload)
    ax_inline_optimizer = build_optimizer_from_config(
        ax_full_config.problem,
        ax_inline_optimizer_cfg,
    )

    optimizer_config = ax_inline_optimizer_cfg.parse_algorithm_params()
    if optimizer_config is None:
        raise RuntimeError("Failed to parse the inline Ax optimizer configuration.")

    nodes = getattr(ax_inline_optimizer.generation_strategy, "nodes", None)
    generation_summary = {
        "name": ax_inline_optimizer.generation_strategy.name,
        "nodes": [node.name for node in nodes] if nodes else [],
    }

    print("Inline Ax optimizer payload (SAAS surrogate + qLogNEHVI):")
    print(pformat(ax_inline_optimizer_payload))
    print("Generation strategy summary:")
    print(pformat(generation_summary))

    records: list[dict[str, Any]] = []
    first_candidate: dict[str, Any] | None = None

    remaining_init = optimizer_config.n_initial_samples
    init_round = 0
    while remaining_init > 0:
        init_round += 1
        current_batch = min(optimizer_config.batch_size, remaining_init)
        candidates = ax_inline_optimizer.suggest_candidates(n_candidates=current_batch)
        if first_candidate is None and candidates:
            first_candidate = dict(candidates[0])
            print("First Ax candidate from the inline config:")
            print(pformat(first_candidate))
        records.extend(
            evaluate_candidates(
                ax_inline_optimizer,
                candidates,
                phase=f"init-{init_round}",
            )
        )
        remaining_init -= current_batch

    for iteration in range(optimizer_config.n_iterations):
        candidates = ax_inline_optimizer.suggest_candidates(
            n_candidates=optimizer_config.batch_size
        )
        records.extend(
            evaluate_candidates(
                ax_inline_optimizer,
                candidates,
                phase=f"iter-{iteration + 1}",
            )
        )

    summary = {
        "n_trials": ax_inline_optimizer.get_optimization_results()["n_trials"],
        "pareto_points": len(ax_inline_optimizer.get_pareto_front()),
        "objective_names": [obj.name for obj in ax_full_config.problem.objectives],
    }

    artifact = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "slurm_job_id": os.environ.get("SLURM_JOB_ID"),
        "cwd": str(Path.cwd()),
        "config_path": str(config_path),
        "output_dir": str(output_dir),
        "debug": args.debug,
        "inline_payload": ax_inline_optimizer_payload,
        "generation_strategy": generation_summary,
        "first_candidate": first_candidate,
        "records": records,
        "summary": summary,
        "trials": [trial_to_dict(trial) for trial in ax_inline_optimizer.get_trials()],
    }

    job_suffix = os.environ.get("SLURM_JOB_ID", "local")
    artifact_path = output_dir / f"ax_advanced_inline_debug_{job_suffix}.json"
    artifact_path.write_text(json.dumps(artifact, indent=2), encoding="utf-8")

    print("Optimization summary:")
    print(pformat(summary))
    print(f"Artifact written to: {artifact_path}")
    LOGGER.info("Artifact written to %s", artifact_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
