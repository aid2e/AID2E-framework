#!/usr/bin/env python3
"""
Run dRICH optimization runner from workflow.yml (problem + scheduler + optimization + workflows)

  1. Load YAML configuration
  2. Parse problem / optimization / scheduler / workflow sections
  3. Build Ax optimizer and search space
  4. Evaluate objectives through the problem script
  5. Save trials, Pareto summary, CSV, and state

"""

import argparse
import csv
import json
import pickle
import shlex
from pathlib import Path
from typing import Dict, List

import yaml

from aid2e.optimizers import BaseOptimizer, SearchSpace, AxOptimizer, AxOptimizerConfig
from aid2e.schedulers import get_scheduler
from aid2e.schedulers.JobLib import JobLibRunnerConfig
from aid2e.utilities.configurations import (
    DesignConfigLoader,
    ObjectiveDirection,
    OptimizationConfiguration,
    WorkflowsConfiguration,
    create_scheduler_context,
    resolve_scheduler_cascade,
)

def main():
    parser = argparse.ArgumentParser(description="Run dRICH optimization from workflow.yml")
    parser.add_argument("--config", default="examples/drich/workflow.yml", help="Path to workflow YAML")
    parser.add_argument("--max-trials", type=int, default=None, help="Optional cap on number of trials")
    args = parser.parse_args()

    print("=" * 70)
    print("AID2E dRICH Example")
    print("=" * 70)

    # 1. Load configuration from YAML file
    print("\n1. Loading configuration from YAML file...")
    config_path = Path(args.config).resolve()
    with open(config_path, 'r') as f:
         config_data = yaml.safe_load(f)
    
    print(f"   Config file: {config_path.name}")
    print(f"   Problem: {config_data['problem']['name']}")

    problem = config_data["problem"]
    optimization = config_data["optimization"]
    scheduler = config_data["scheduler"]
    workflows = config_data["workflows"]

    #Confirm/create output paths 
    config_dir = config_path.parent
    output_dir = (config_dir / problem["output_location"]).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    log_dir = output_dir / "log"
    for d in (
        log_dir / "results",
        log_dir / "sim_files",
        log_dir / "reco",
        log_dir / "overlaps",
        log_dir / "job_output",
    ):
        d.mkdir(parents=True, exist_ok=True)
    (output_dir / "trial_scripts").mkdir(parents=True, exist_ok=True)
    job_output_dir = log_dir / "job_output"

    # 2. Parse configuration using OptimizationConfiguration (?, or just directly?)
    print("\n2. Parsing optimization configuration...")

    optimizer_params = optimization["optimizer"]["parameters"]
    output_name = str(optimizer_params["output_name"])

    # 3. Create AxOptimizerConfig from parsed parameters
    print("\n3. Creating AxOptimizerConfig...")

    n_iterations = int(optimization["n_iterations"])
    n_iterations = int(args.max_trials) if args.max_trials is not None else int(optimization["n_iterations"])

    n_sobol = int(optimizer_params["n_sobol"])
    n_mobo = int(optimizer_params["n_mobo"])
    n_batch_sobol = int(optimizer_params["n_batch_sobol"])
    n_batch_mobo = int(optimizer_params["n_batch_mobo"])

    ax_config = AxOptimizerConfig(
        initialization_strategy=optimizer_params["initialization_strategy"],
        surrogate_model=optimizer_params["mobo_surrogate"],
        acquisition_function=optimizer_params["mobo_acquisition"],
        n_initial_samples=optimizer_params["n_sobol"],
        n_iterations=optimization["n_iterations"],
        batch_size=optimizer_params["n_batch_sobol"],
        seed=optimizer_params["seed"],
    )

    print(f"   Optimizer: Ax Bayesian Optimizer; {optimization['optimizer']['type']}")
    print(f"   Initialization: {ax_config.initialization_strategy}")
    print(f"   Surrogate Model: {ax_config.surrogate_model}")
    print(f"   Acquisition: {ax_config.acquisition_function}")
    print(f"   Sobol initialization: {ax_config.n_initial_samples}")
    print(f"   Total iterations: {ax_config.n_iterations}")
    print(f"   Batch size: {ax_config.batch_size}")


    # 4. Define search space from design.params
    print("\n4. Defining search space from design.params...")

    design_path = (config_dir / problem["design_space"]["path"]).resolve()
    design_config = DesignConfigLoader.load(str(design_path))
    flat_parameters = design_config.get_flat_parameters()

    search_space_params = {}
    for param_name, param in flat_parameters.items():
        if hasattr(param, "bounds"):
            search_space_params[param_name] = {
                "type": "range",
                "bounds": [float(param.bounds[0]), float(param.bounds[1])],
            }

    search_space = SearchSpace(parameters=search_space_params)
    print(f"   Parameters: {list(search_space.parameters.keys())}")
    print(f"   Total dimensions: {len(search_space.parameters)}")

    metric_directions: Dict[str, ObjectiveDirection] = {}
    for objective in problem["objectives"]:
        metrics = objective.get("metrics", [])
        if not metrics:
            raise ValueError("Each problem.objective entry must define a non-empty 'metrics' list")
        for metric in metrics:
            metric_directions[str(metric["name"])] = ObjectiveDirection(str(metric["direction"]).lower())

    if optimization.get("target_metrics"):
        target_metrics = [str(name) for name in optimization["target_metrics"]]
    else:
        target_metrics = [str(metric["name"]) for metric in problem["objectives"][0]["metrics"]]

    # 5. Create AxOptimizer instance
    print("\n5. Creating AxOptimizer...")
    optimizer = AxOptimizer(
        search_space=search_space,
        config=ax_config,
        objective_names=target_metrics,   
        seed=ax_config.seed,
    )
    print(f"   Optimizer: {optimizer}")
    print(f"   Objectives: {target_metrics}")


    # 6. Scheduler
    print("\n6. Setting up scheduler...")
    workflows_cfg = WorkflowsConfiguration(workflows=workflows, global_scheduler=scheduler)
    workflow = workflows_cfg.workflows[0]
    branch = workflow.branches[0]
    stage = branch.stages[0]

    scheduler_cfg = resolve_scheduler_cascade(
        stage_scheduler=stage.scheduler,
        branch_scheduler=branch.scheduler,
        workflow_scheduler=workflow.scheduler,
        objective_scheduler=None,
        global_scheduler=workflows_cfg.global_scheduler,
    )
    scheduler_context = create_scheduler_context(
        objective_scheduler=None,
        workflow_scheduler=workflow.scheduler,
        branch_scheduler=branch.scheduler,
        stage_scheduler=stage.scheduler,
        global_scheduler=workflows_cfg.global_scheduler,
    )
    print(
        "Scheduler cascade: "
        f"source={scheduler_context['source']}, effective={scheduler_context['effective_scheduler']}"
    )

    scheduler_key = str(scheduler_cfg.runner_type).lower()
    if scheduler_key.endswith("runner"):
        scheduler_key = scheduler_key[:-6]
    SchedulerClass = get_scheduler(scheduler_key)
    scheduler_instance = SchedulerClass(config=scheduler_cfg.parse_runner_params() or JobLibRunnerConfig())
    parallelism_policy = stage.parallelism.model_dump()

    # 6. Run multi-objective optimization loop
    print("\n7. Running optimization...")

    objective_script_cfg = problem["objectives"][0]["objective_plan"]["script"]
    objective_script = (config_dir / objective_script_cfg["path"]).resolve()
    objective_output_file = objective_script_cfg["output_file"]

    failed_cfg = problem.get("epic_pipeline", {}).get("failed_objectives", {})
    failed_defaults = {name: float(failed_cfg.get(name, 0.0)) for name in target_metrics}
    objective_thresholds = optimizer_params.get("objective_thresholds", {})

    records: List[Dict[str, object]] = []

    while len(records) < n_iterations:
            remaining = n_iterations - len(records)
            if len(records) < n_sobol:
                phase = "sobol"
                batch_size = min(n_batch_sobol, remaining)
            else:
                phase = "mobo"
                batch_size = min(n_batch_mobo, remaining)

            # Suggest design points
            design_points = optimizer.suggest_candidates(n_candidates=batch_size)
            print(f"   - Suggested {len(design_points)} design points ({phase})")

            # Get current trial count before adding results
            trial_start_idx = len(optimizer.experiment.trials) - len(design_points)

            jobs = []
            batch_items = []

            # Evaluate each design point using ePIC dRICH pipeline
            for idx, design_point in enumerate(design_points):
                trial_idx = trial_start_idx + idx

                trial_dir = output_dir / f"trial_{trial_idx:04d}"
                trial_dir.mkdir(parents=True, exist_ok=True)

                params_file = trial_dir / "design_point.json"
                metrics_file = trial_dir / objective_output_file
                params_file.write_text(json.dumps(design_point, indent=2), encoding="utf-8")

                cmd_parts = [
                    "python",
                    str(objective_script),
                    "--design_params_file",
                    str(params_file),
                    "--output_file",
                    str(metrics_file),
                    "--trial-index",
                    str(trial_idx),
                    "--output-dir",
                    str(output_dir),
                    "--config-path",
                    str(config_path),
                ]

                job_name = f"trial_{trial_idx:04d}"
                jobs.append(
                    {
                        "name": job_name,
                        "command": " ".join(shlex.quote(p) for p in cmd_parts),
                        "payload": {"trial_index": trial_idx},
                        "outputs": [],
                    }
                )
                batch_items.append(
                    {
                        "job_name": job_name,
                        "trial_idx": trial_idx,
                        "design_point": dict(design_point),
                        "metrics_file": metrics_file,
                        "phase": phase,
                    }
                )

            stage_result = scheduler_instance.run_stage(
                stage_name=stage.name,
                job_definitions=jobs,
                parallelism_policy=parallelism_policy,
                working_dir=str(Path.cwd()),
            )

            for st in stage_result.job_statuses:
                log_id = str(st.job_id).replace("/", "_")
                (job_output_dir / f"{log_id}.out").write_text(st.stdout or "", encoding="utf-8")
                (job_output_dir / f"{log_id}.err").write_text(st.stderr or "", encoding="utf-8")

            status_by_job = {}
            stderr_by_job = {}
            for st in stage_result.job_statuses:
                for item in batch_items:
                    if f"_{item['job_name']}_" in st.job_id:
                        status_by_job[item["job_name"]] = st.status
                        stderr_by_job[item["job_name"]] = st.stderr or ""
                        break

            for item in batch_items:
                trial_idx = item["trial_idx"]
                design_point = item["design_point"]
                metrics_file = item["metrics_file"]
                job_name = item["job_name"]

                status = status_by_job.get(job_name, "failed")
                penalty_used = False
                error_message = None

                if status != "completed":
                    objectives_raw = dict(failed_defaults)
                    penalty_used = True
                    error_message = stderr_by_job.get(job_name, "unknown scheduler failure")
                elif not metrics_file.exists():
                    objectives_raw = dict(failed_defaults)
                    penalty_used = True
                    error_message = f"missing output file: {metrics_file}"
                else:
                    payload = json.loads(metrics_file.read_text(encoding="utf-8"))
                    objectives_raw = {k: float(v) for k, v in payload.items()}
                    for name in target_metrics:
                        if name not in objectives_raw:
                            objectives_raw[name] = failed_defaults[name]
                            penalty_used = True

                objectives_for_ax = {}
                for name in target_metrics:
                    value = float(objectives_raw[name])
                    if metric_directions[name] == ObjectiveDirection.MAXIMIZE:
                        objectives_for_ax[name] = -value
                    else:
                        objectives_for_ax[name] = value

                optimizer.update_with_results(
                    trial_index=trial_idx,
                    parameters=design_point,
                    metrics=objectives_for_ax,
                )

                threshold_pass = {}
                for name, threshold in objective_thresholds.items():
                    if name in objectives_raw:
                        threshold_pass[name] = bool(float(objectives_raw[name]) >= float(threshold))

                records.append(
                    {
                        "trial_index": trial_idx,
                        "phase": item["phase"],
                        "status": "failed" if penalty_used else "completed",
                        "penalty_used": penalty_used,
                        "error": error_message,
                        "parameters": design_point,
                        "raw_metrics": objectives_raw,
                        "threshold_pass": threshold_pass,
                    }
                )

                if penalty_used and error_message:
                    print(f"     Trial {trial_idx}: {objectives_raw} (penalty: {error_message})")
                else:
                    print(f"     Trial {trial_idx}: {objectives_raw}")

    # 7. Get Pareto front
    print("\n8. Retrieving Pareto front...")
    pareto_front = optimizer.get_pareto_front()
    print(f"   Pareto front size: {len(pareto_front)}")

    if pareto_front:
        print("\n   Pareto-optimal solutions:")
        for i, trial in enumerate(pareto_front[:5]):
            print(f"     Solution {i+1}: {trial.metrics}")
        if len(pareto_front) > 5:
            print(f"     ... and {len(pareto_front) - 5} more solutions")

    # Get best trial
    print("\n Best trial (from Pareto front):")
    best_trial = optimizer.get_best_trial()
    if best_trial:
        print(f"   Objectives: {best_trial.metrics}")

    # Get all trials
    print(f"\n Total trials evaluated: {len(optimizer.get_trials())}")

    # Serialize and deserialize state
    print("\n Testing state serialization...")
    state = optimizer.serialize_state()
    print(f"    Serialized state has {len(state['trials'])} trials")

    # Save to output directory
    print("\n 10. Saving results...")
    trials_csv = output_dir / f"{output_name}.csv"
    metric_cols = list(target_metrics)
    with trials_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["trial_index", "phase", "status", "penalty_used", "error", *metric_cols])
        for rec in records:
            raw = rec.get("raw_metrics", {})
            writer.writerow(
                [
                    rec.get("trial_index"),
                    rec.get("phase"),
                    rec.get("status"),
                    rec.get("penalty_used"),
                    rec.get("error"),
                    *[raw.get(name) for name in metric_cols],
                ]
            )

    state_pkl = output_dir / f"{output_name}.pkl"
    with state_pkl.open("wb") as f:
        pickle.dump(state, f)

    optimizer2 = AxOptimizer(
        search_space=search_space,
        config=ax_config,
        objective_names=target_metrics,
        seed=ax_config.seed,
    )
    optimizer2.load_state(state)

    pareto_front2 = optimizer2.get_pareto_front()
    print(f"    Pareto front after reload: {len(pareto_front2)} solutions")
    print(f"    Saved trials CSV: {trials_csv}")
    print(f"    Saved state PKL: {state_pkl}")

    print("\n" + "=" * 70)
    print("dRICH multi-objective optimization completed.")
    print("=" * 70)


if __name__ == "__main__":
    main()