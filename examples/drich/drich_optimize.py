#!/usr/bin/env python3
"""
Example: run dRICH optimization with AID2E optimizer and scheduler.
Each Ax trial is submitted as one scheduler job running drich_trial.py,
which then calls drich_eval.py worker stages to execute the dRICH workflow
and return metrics. After each batch of trials is completed, the objectives
are returned to Ax and next batch is suggested.
"""

import argparse
import json
import shlex
import sys
from pathlib import Path

from ax.service.utils.report_utils import exp_to_df

from aid2e.utilities import build_optimizer_from_config, build_scheduler_from_config
from aid2e.utilities.configurations import ObjectiveDirection
from drich_utils import (
    failed_trials_from_stage_result,
    load_drich_config,
    metrics_for_ax,
)


# AID2E optimizer setup

def configure_optimizer(run_config, max_trials=None):
    """Build the AID2E optimizer"""

    cfg = run_config["cfg"]
    objectives = [obj.name for obj in cfg.problem.objectives]
    directions = {obj.name: obj.direction for obj in cfg.problem.objectives}

    if max_trials is not None:
        cfg.optimizer.parameters = {**cfg.optimizer.parameters, "n_iterations": max_trials}

    optimizer = build_optimizer_from_config(cfg.problem, cfg.optimizer)
    ax_config = optimizer.config
    sobol_trials = min(ax_config.n_initial_samples, ax_config.n_iterations)

    optimizer_state = {
        "objectives": objectives,
        "directions": directions,
        "ax_config": ax_config,
        "optimizer": optimizer,
        "sobol_trials": sobol_trials,
    }
    return optimizer_state


# AID2E scheduler setup

def configure_scheduler(run_config, optimizer_state):
    """Build the AID2E scheduler and trial-level parallelism policy."""

    scheduler = build_scheduler_from_config(run_config["cfg"].scheduler)
    parallelism_policy = {"max_concurrent": optimizer_state["ax_config"].batch_size}
    return scheduler, parallelism_policy


def run_trial_batch(assignments, phase_name, batch_id, run_config, optimizer_state, trial_state):
    """Write trial inputs, submit trial workflow jobs, and collect completed metrics."""

    output_dir = run_config["output_dir"]
    trial_script = Path(__file__).resolve().parent / "drich_trial.py"
    active_trials = {trial_index: design_point for trial_index, design_point in assignments}

    # Prepare one scheduler job per Ax trial
    job_definitions = []
    for trial_index, design_point in assignments:
        trial_tag = f"{trial_index:03d}"
        (run_config["trial_scripts_dir"] / f"jobconfig_job{trial_index}.json").write_text(
            json.dumps(design_point, indent=2)
        )

        q = shlex.quote
        command = (
            f"{q(sys.executable)} {q(str(trial_script))} --trial-index {trial_index} "
            f"--output-dir {q(str(output_dir))} --config-path {q(str(run_config['config_path']))}"
        )
        job_definitions.append(
            {
                "name": f"trial_{trial_tag}",
                "command": command,
            }
        )

    stage_name = f"{phase_name.lower()}_batch_{batch_id}_trials"

    scheduler, parallelism_policy = configure_scheduler(run_config, optimizer_state)
    try:
        result = scheduler.run_stage(
            stage_name,
            job_definitions,
            parallelism_policy=parallelism_policy,
            working_dir=str(output_dir),
        )
    finally:
        scheduler.shutdown()

    # Failed trial jobs are marked failed in Ax; successful trials continue.
    if not result.success:
        failed_trials = failed_trials_from_stage_result(result)
        if not failed_trials:
            raise RuntimeError(result.error_message or f"stage failed: {stage_name}")
        for trial_index in sorted(failed_trials & set(active_trials)):
            optimizer_state["optimizer"].set_trial_status(
                trial_index=trial_index,
                status="failed",
                parameters=active_trials[trial_index],
                metadata={"reason": result.error_message},
            )
            trial_state["failed_by_trial"].add(trial_index)
            del active_trials[trial_index]

    # Each successful trial writes one objective result file
    batch_results = {}
    for trial_index, design_point in active_trials.items():
        result_path = output_dir / "log" / "results" / f"drich-out_{trial_index:03d}.json"
        batch_results[trial_index] = (design_point, json.loads(result_path.read_text()))
    return batch_results


# Run Optimization Loop

def run_optimization(run_config, optimizer_state):
    trial_state = {"errors_by_trial": {}, "failed_by_trial": set()}
    trial_index = 0

    # Split the run into the configured Sobol initialization and Bayesian phases.
    phases = [
        ("Sobol", optimizer_state["sobol_trials"]),
        ("Bayes", optimizer_state["ax_config"].n_iterations - optimizer_state["sobol_trials"]),
    ]

    for phase_name, n_trials in phases:
        if n_trials <= 0:
            continue
        batch_id, completed = 0, 0

        while completed < n_trials:
            batch_id += 1
            n_new = min(optimizer_state["ax_config"].batch_size, n_trials - completed)

            # Ask Ax/AID2E for the next batch of design points.
            design_points = optimizer_state["optimizer"].suggest_candidates(n_candidates=n_new)
            assignments = list(zip(range(trial_index, trial_index + n_new), design_points))
            trial_index += len(assignments)

            # Run each design point as one trial workflow job.
            batch_results = run_trial_batch(assignments, phase_name, batch_id, run_config, optimizer_state, trial_state)
            completed += len(assignments) - len(batch_results)

            # Scheduler-level failures are skipped unless the configured tolerance is exceeded.
            failed = len(trial_state["failed_by_trial"])
            if failed > run_config["max_failed_trials"]:
                raise RuntimeError(f"Too many failed trials: {failed} failed, max_failed_trials={run_config['max_failed_trials']}")

            # Convert completed result into optimizer metrics and update Ax.
            for idx, (design_point, raw_metrics) in batch_results.items():
                metrics = {name: float(raw_metrics[name]) for name in optimizer_state["objectives"]}
                trial_state["errors_by_trial"][idx] = {
                    name: float(raw_metrics[f"{name}_sem"]) for name in optimizer_state["objectives"]
                }
                optimizer_state["optimizer"].update_with_results(
                    idx, design_point, metrics_for_ax(metrics, optimizer_state["objectives"], optimizer_state["directions"])
                )
                completed += 1

            # Save results after each batch.
            if batch_results or trial_state["failed_by_trial"]:
                df = exp_to_df(optimizer_state["optimizer"].experiment)
                for name in optimizer_state["objectives"]:
                    if name in df and optimizer_state["directions"][name] == ObjectiveDirection.MAXIMIZE:
                        df[name] = -df[name]
                    df[f"{name}_sem"] = df["trial_index"].map(
                        lambda idx: trial_state["errors_by_trial"].get(int(idx), {}).get(name)
                    )
                df.sort_values("trial_index").to_csv(run_config["results_csv"], index=False)

                pareto_trials = []
                for trial in optimizer_state["optimizer"].get_pareto_front():
                    pareto_trials.append(
                        {
                            "trial_index": trial.index,
                            "parameters": trial.parameters,
                            "metrics": {
                                name: -value if optimizer_state["directions"][name] == ObjectiveDirection.MAXIMIZE else value
                                for name, value in trial.metrics.items()
                            },
                        }
                    )
                run_config["pareto_front_json"].write_text(json.dumps(pareto_trials, indent=2))
                optimizer_state["optimizer"].save_optimization_results(run_config["optimization_results_json"])


# Main

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Run example dRICH optimization from workflow.yml")
    parser.add_argument("--config", default="examples/drich/workflow.yml", help="Path to workflow YAML")
    parser.add_argument("--max-trials", type=int, default=None, help="Optional cap on total trials")
    args = parser.parse_args(argv)

    config_path, cfg, eval_config = load_drich_config(args.config)
    output_dir = Path(cfg.problem.output_location)
    output_dir.mkdir(parents=True, exist_ok=True)
    trial_scripts_dir = output_dir / "trial_scripts"
    trial_scripts_dir.mkdir(parents=True, exist_ok=True)
    run_config = {
        "config_path": config_path,
        "cfg": cfg,
        "output_dir": output_dir,
        "trial_scripts_dir": trial_scripts_dir,
        "max_failed_trials": int(eval_config.get("max_failed_trials", 0)),
        "optimization_results_json": output_dir / "drich_optimization_results.json",
        "pareto_front_json": output_dir / f"{eval_config['output_name']}_pareto_front.json",
        "results_csv": output_dir / f"{eval_config['output_name']}.csv",
    }
    run_optimization(run_config, configure_optimizer(run_config, max_trials=args.max_trials))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
