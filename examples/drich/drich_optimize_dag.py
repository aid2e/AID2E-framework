"""
Run dRICH optimization runner from workflow.yml

  1. Load YAML configuration
  3. Build SearchSpace and AxOptimizer
  4. Execute stage plan with DAGExecutor
  4. Run optimization loop
  5. Save trials, Pareto summary, CSV, and state
"""

import argparse
import json
from math import ceil
from pathlib import Path

import yaml

from aid2e.optimizers import SearchSpace, AxOptimizer, AxOptimizerConfig
from aid2e.utilities.configurations import ObjectiveDirection, load_config
from aid2e.utilities.workflows import (
    DAGExecutor,
    WorkflowDefinition,
    BranchDefinition,
    StageDefinition,
    JobDefinition,
    JobContext,
)
from drich_eval import evaluate_design_point

def main():
    parser = argparse.ArgumentParser(description="Run dRICH optimization from workflow.yml")
    parser.add_argument("--config", default="examples/drich/workflow.yml", help="Path to workflow YAML")
    parser.add_argument("--max-trials", type=int, default=None, help="Optional cap on total trials")
    args = parser.parse_args()

    print("\n" + "=" * 80)
    print("AID2E dRICH Example w DAGExecutor")
    print("=" * 80)

    #---------Load---------
    config_path = Path(args.config).resolve()
    with open(config_path, "r") as f:
        config_data = yaml.safe_load(f) or {}
    cfg = load_config(str(config_path))
    wf_cfg = config_data["workflow"]

    workflow = WorkflowDefinition(
        name=wf_cfg["name"],
        description=wf_cfg["description"],
        branches=wf_cfg["branches"],
        objectives=cfg.problem.objectives,
    )

    branch = workflow.branches[0]

    #Confirm/create output paths 
    work_dir = Path(cfg.problem.work_location).expanduser().resolve()
    output_dir = Path(cfg.problem.output_location).expanduser().resolve()

    for d in (
        work_dir,
        output_dir,
        output_dir / "log" / "results",
        output_dir / "log" / "sim_files",
        output_dir / "log" / "reco",
        output_dir / "log" / "overlaps",
        output_dir / "log" / "job_output",
        output_dir / "trial_scripts",
    ):
        d.mkdir(parents=True, exist_ok=True)

    # Search space from design config

    # -----------Optimizer---------------

    objectives = [obj.name for obj in cfg.problem.objectives]
    objective_directions = {obj.name: obj.direction for obj in cfg.problem.objectives}
    flat_parameters = cfg.problem.design_config.get_flat_parameters()

    search_space = SearchSpace(
        parameters={
            name: {"type": "range", "bounds": [float(p.bounds[0]), float(p.bounds[1])]}
            for name, p in flat_parameters.items()
            if hasattr(p, "bounds")
        }
    )

    n_iterations = int(args.max_trials) if args.max_trials is not None else int(cfg.optimization.n_iterations)

    ax_config = AxOptimizerConfig(
        **cfg.optimization.optimizer.parameters,
        n_iterations=n_iterations,
    )
    optimizer = AxOptimizer(
        search_space=search_space,
        config=ax_config,
        objective_names=objectives,
        seed=ax_config.seed,
    )

    # -----------DAGExecutor---------------

    stage_plan = []
    for stage in branch.stages:
        if stage.job_factory and stage.job_factory.type == "range" and stage.jobs:
            n_jobs = int(stage.job_factory.params.get("n", 1))
        elif stage.jobs:
            n_jobs = len(stage.jobs)
        else:
            n_jobs = 1
        stage_plan.append((stage.name, n_jobs))

    def evaluate_with_stages(context: JobContext) -> dict:
        trial_index = int(context.design_point.get("__trial_index", 0))
        design_point = {k: v for k, v in context.design_point.items() if not str(k).startswith("__")}
        metrics = {name: 0.0 for name in objectives}

        for stage_name, n_jobs in stage_plan:
            last = None
            for job_index in range(n_jobs):
                last = evaluate_design_point(
                    design_point=design_point,
                    trial_index=trial_index,
                    output_dir=str(output_dir),
                    config_path=str(config_path),
                    stage=stage_name,
                    job_index=job_index,
                )
            if stage_name == "collect_objectives" and isinstance(last, dict):
                metrics = {name: float(last.get(name, 0.0)) for name in objectives}

        context.xcom_push("objectives", metrics)
        return metrics

    eval_job = JobDefinition(
        name="evaluate_design",
        command="python",
        payload={
            "evaluator_type": "python",
            "python_callable": evaluate_with_stages,
            "op_args": (),
            "op_kwargs": {},
        },
    )
    eval_stage = StageDefinition(name="evaluate", jobs=[eval_job])
    eval_branch = BranchDefinition(name="main", stages=[eval_stage])
    exec_workflow = WorkflowDefinition(
        name=workflow.name,
        description=workflow.description,
        branches=[eval_branch],
        objectives=workflow.objectives,
    )
    executor = DAGExecutor(
        workflow=exec_workflow,
        base_output_dir=str(output_dir / "dag_runs"),
        log_level="WARNING",
    )

    def run_trial(design_point, trial_index):
        params_file = output_dir / "trial_scripts" / f"jobconfig_job{trial_index}.json"
        params_file.write_text(json.dumps(design_point, indent=2))
        design_with_trial = dict(design_point)
        design_with_trial["__trial_index"] = trial_index
        payload = executor.execute(design_with_trial)
        return {name: float(payload.get(name, 0.0)) for name in objectives}

    trial_index = 0

    # Sobol phase
    sobol_trials = min(ax_config.n_initial_samples, ax_config.n_iterations)
    n_sobol_batches = int(ceil(sobol_trials / ax_config.batch_size))
    for batch in range(n_sobol_batches):
        batch_size = min(ax_config.batch_size, sobol_trials - batch * ax_config.batch_size)
        for design_point in optimizer.suggest_candidates(n_candidates=batch_size):
            raw_metrics = run_trial(design_point, trial_index)
            metrics_for_ax = {
                name: (
                    -float(raw_metrics[name])
                    if objective_directions[name] == ObjectiveDirection.MAXIMIZE
                    else float(raw_metrics[name])
                )
                for name in objectives
            }
            optimizer.update_with_results(trial_index, design_point, metrics_for_ax)
            trial_index += 1

    # Bayesian phase
    while trial_index < ax_config.n_iterations:
        batch_size = min(ax_config.batch_size, ax_config.n_iterations - trial_index)
        for design_point in optimizer.suggest_candidates(n_candidates=batch_size):
            raw_metrics = run_trial(design_point, trial_index)
            metrics_for_ax = {
                name: (
                    -float(raw_metrics[name])
                    if objective_directions[name] == ObjectiveDirection.MAXIMIZE
                    else float(raw_metrics[name])
                )
                for name in objectives
            }
            optimizer.update_with_results(trial_index, design_point, metrics_for_ax)
            trial_index += 1

    best = optimizer.get_best_trial()
    print("\nBest trial:")
    print(f"  trial={best.index}")
    print(f"  params={best.parameters}")
    print(f"  metrics={best.metrics}")

if __name__ == "__main__":
    main()