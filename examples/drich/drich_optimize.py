#!/usr/bin/env python3
"""
Example: run dRICH optimization with AID2E optimizer and scheduler.
Each Ax trial is submitted as one scheduler job calling run_trial(),
which then uses DAGExecutor to run drich_eval.py stages and return
metrics. After each batch of trials is completed, the objectives are returned
to Ax and next batch is suggested.
"""

import argparse
import json
import shlex

from ax.service.utils.report_utils import exp_to_df

from aid2e.utilities import build_optimizer_from_config, build_scheduler_from_config, build_scheduler_runtime_config
from aid2e.utilities.configurations import (
    BranchDefinition,
    JobDefinition,
    StageDefinition,
    WorkflowDefinition,
    resolve_scheduler_cascade,
)
from aid2e.utilities.workflows import DAGExecutor
from drich_utils import load_drich_config, make_paths


# AID2E trial workflow setup

def load_trial_config(config_path, output_dir):
    """Load config and prepare DAGExecutor paths."""

    config_path, cfg, _ = load_drich_config(config_path)
    paths = make_paths(output_dir)
    return config_path, cfg, paths


def build_trial_workflow(cfg, config_path, paths, trial_index):
    """Create the one-trial DAG in the stage order from workflow.yml."""

    source_workflow = cfg.workflows.workflows[0]
    source_branch = source_workflow.branches[0]
    trial_id = str(trial_index)
    result_json = paths.results_dir / f"out-{trial_index}.json"
    base_payload = {
        "trial_index": trial_index,
        "output_dir": shlex.quote(str(paths.output_root)),
        "config_path": shlex.quote(str(config_path)),
        "result_json": str(result_json),
    }

    def make_stage(source):
        source_job = source.jobs[0]
        stage_resources = dict(source.scheduler.parameters) if source.scheduler else {}
        jobs = [
            JobDefinition(
                name=source_job.name,
                command=source_job.command,
                rule=source_job.rule,
                payload={**source_job.payload, **base_payload},
                resources={**stage_resources, **source_job.resources},
                outputs=source_job.outputs,
            )
        ]
        return StageDefinition(
            name=source.name,
            jobs=jobs,
            job_factory=source.job_factory,
            scheduler=source.scheduler,
            parallelism=source.parallelism,
            outputs=source.outputs,
        )

    return WorkflowDefinition(
        name=f"drich_trial_{trial_id}",
        stack_type=source_workflow.stack_type,
        branches=[
            BranchDefinition(
                name=source_branch.name,
                stages=[make_stage(stage) for stage in source_branch.stages],
                scheduler=source_branch.scheduler,
            )
        ],
        objectives=list(cfg.problem.objectives),
        scheduler=source_workflow.scheduler,
    )


def run_trial(config_path, output_dir, trial_index, design_point):
    """Execute one trial workflow and return its objective metrics."""

    config_path, cfg, paths = load_trial_config(config_path, output_dir)

    workflow = build_trial_workflow(cfg, config_path, paths, trial_index)
    dag_scheduler = resolve_scheduler_cascade(
        branch_scheduler=workflow.branches[0].scheduler,
        workflow_scheduler=workflow.scheduler,
        global_scheduler=cfg.scheduler,
    )
    executor = DAGExecutor(
        workflow=workflow,
        base_output_dir=str(paths.output_root),
        log_level="WARNING",
        problem_config=cfg.problem,
        scheduler_config=build_scheduler_runtime_config(dag_scheduler),
    )
    executor.execute(design_point)

    result_path = paths.results_dir / f"out-{trial_index}.json"
    if not result_path.exists():
        raise RuntimeError(f"DAGExecutor did not write objective result file: {result_path}")
    return json.loads(result_path.read_text())


# AID2E optimizer setup

def configure_optimizer(run_config, max_trials=None):
    """Build the AID2E optimizer."""

    cfg = run_config["cfg"]

    if max_trials is not None:
        cfg.optimizer.parameters = {**cfg.optimizer.parameters, "n_iterations": max_trials}

    optimizer = build_optimizer_from_config(cfg.problem, cfg.optimizer)
    ax_config = optimizer.config
    sobol_trials = min(ax_config.n_initial_samples, ax_config.n_iterations)

    optimizer_state = {
        "objectives": optimizer.objective_names,
        "ax_config": ax_config,
        "optimizer": optimizer,
        "sobol_trials": sobol_trials,
    }
    return optimizer_state


def run_trial_batch(assignments, phase_name, batch_id, run_config, optimizer_state, trial_state):
    """Submit trial workflow jobs and collect completed metrics."""

    output_dir = run_config["output_dir"]
    active_trials = {trial_index: design_point for trial_index, design_point in assignments}

    job_definitions = []
    for trial_index, design_point in assignments:
        job_definitions.append(
            {
                "job_id": str(trial_index),
                "name": f"trial_{trial_index}",
                "function": run_trial,
                "params": {
                    "config_path": str(run_config["config_path"]),
                    "output_dir": str(output_dir),
                    "trial_index": trial_index,
                    "design_point": design_point,
                },
            }
        )

    stage_name = f"{phase_name.lower()}_batch_{batch_id}_trials"

    # The outer scheduler stage runs one trial workflow per Ax candidate.
    scheduler = build_scheduler_from_config(run_config["cfg"].scheduler)
    parallelism_policy = {"max_concurrent": optimizer_state["ax_config"].batch_size}
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
        failed_trials = {
            int(status.job_id)
            for status in result.job_statuses
            if status.status != "completed" and str(status.job_id).isdigit()
        }
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

    completed_statuses = {
        int(status.job_id): status
        for status in result.job_statuses
        if status.status == "completed" and str(status.job_id).isdigit()
    }

    # run_trial() returns metrics and also writes an objective JSON artifact.
    batch_results = {}
    for trial_index, design_point in active_trials.items():
        outputs = completed_statuses[trial_index].outputs or {}
        batch_results[trial_index] = (design_point, outputs["result"])
    return batch_results


# Run Optimization Loop

def run_optimization(run_config, optimizer_state):
    trial_state = {"errors_by_trial": {}, "failed_by_trial": set()}
    trial_index = 0

    # Sobol and Bayesian counts
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

            # Update Ax with the objective metrics declared in workflow.yml.
            for idx, (design_point, raw_metrics) in batch_results.items():
                metrics = {name: float(raw_metrics[name]) for name in optimizer_state["objectives"]}
                trial_state["errors_by_trial"][idx] = {
                    name: float(raw_metrics[f"{name}_sem"]) for name in optimizer_state["objectives"]
                }
                optimizer_state["optimizer"].update_with_results(
                    idx, design_point, metrics
                )
                completed += 1

            # Save after each batch for long Slurm runs.
            if batch_results:
                df = exp_to_df(optimizer_state["optimizer"].experiment)
                for name in optimizer_state["objectives"]:
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
                            "metrics": trial.metrics,
                        }
                    )
                run_config["pareto_front_json"].write_text(json.dumps(pareto_trials, indent=2))
                optimizer_state["optimizer"].save_optimization_results(run_config["optimization_results_json"])
            elif trial_state["failed_by_trial"]:
                optimizer_state["optimizer"].save_optimization_results(run_config["optimization_results_json"])


# Main

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Run example optimization from workflow.yml")
    parser.add_argument("--config", default="examples/drich/workflow.yml", help="Path to workflow YAML")
    parser.add_argument("--max-trials", type=int, default=None, help="Optional cap on total trials")
    args = parser.parse_args(argv)

    config_path, cfg, eval_config = load_drich_config(args.config)
    paths = make_paths(cfg.problem.output_location)
    paths.output_root.mkdir(parents=True, exist_ok=True)
    run_config = {
        "config_path": config_path,
        "cfg": cfg,
        "output_dir": paths.output_root,
        "max_failed_trials": int(eval_config.get("max_failed_trials", 0)),
        "optimization_results_json": paths.output_root / "drich_optimization_results.json",
        "pareto_front_json": paths.output_root / f"{eval_config['output_name']}_pareto_front.json",
        "results_csv": paths.output_root / f"{eval_config['output_name']}.csv",
    }
    run_optimization(run_config, configure_optimizer(run_config, max_trials=args.max_trials))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
