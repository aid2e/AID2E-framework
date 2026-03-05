"""
Run dRICH optimization runner from workflow.yml

  1. Load YAML configuration
  3. Build SearchSpace, AxOptimizer, Scheduler
  4. Run optimization
  5. Save trials, Pareto summary, CSV, and state
"""

import argparse
import json
import shlex
from math import ceil
from pathlib import Path

import yaml

from aid2e.optimizers import SearchSpace, AxOptimizer, AxOptimizerConfig
from aid2e.schedulers import get_scheduler, JobLibRunnerConfig
from aid2e.utilities.configurations import ObjectiveDirection, load_config, resolve_scheduler_cascade
from aid2e.utilities.workflows import WorkflowDefinition


def _replace_placeholders(text: str, values: dict) -> str:
    out = text
    for key, value in values.items():
        out = out.replace(f"{{{key}}}", str(value))
    return out


def _python_command(command: str) -> str:
    parts = shlex.split(command)
    if len(parts) >= 2 and parts[0] in ("python", "python3"):
        parts[1] = str(Path(parts[1]).resolve())
    return " ".join(shlex.quote(x) for x in parts)

def main():
    parser = argparse.ArgumentParser(description="Run dRICH optimization from workflow.yml")
    parser.add_argument("--config", default="examples/drich/workflow.yml", help="Path to workflow YAML")
    parser.add_argument("--max-trials", type=int, default=None, help="Optional cap on total trials")
    args = parser.parse_args()

    print("\n" + "=" * 80)
    print("AID2E dRICH Example")
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

    # -----------Scheduler---------------
    stage_exec = []
    schedulers = []

    for stage in branch.stages:
        scheduler_cfg = resolve_scheduler_cascade(
            stage_scheduler=stage.scheduler,
            branch_scheduler=branch.scheduler,
            workflow_scheduler=workflow.scheduler,
            objective_scheduler=None,
            global_scheduler=cfg.scheduler,
        )
        if scheduler_cfg is None:
            raise ValueError(f"No scheduler configured for stage '{stage.name}'")

        runner_key = str(scheduler_cfg.runner_type).lower()
        if runner_key.endswith("runner"):
            runner_key = runner_key[:-6]

        SchedulerClass = get_scheduler(runner_key)
        runner_params = scheduler_cfg.parse_runner_params() or JobLibRunnerConfig()
        scheduler = SchedulerClass(config=runner_params)
        schedulers.append(scheduler)
        stage_exec.append((stage, scheduler, stage.parallelism.model_dump()))

    # -----------Run trials---------------

    def run_trial(design_point, trial_index):
        trial_tag = f"{trial_index:03d}"
        
        params_file = output_dir / "trial_scripts" / f"jobconfig_job{trial_index}.json"
        metrics_file = output_dir / "log" / "results" / f"drich-mobo-out_{trial_tag}.json"
        params_file.write_text(json.dumps(design_point, indent=2))

        for stage, scheduler, parallelism_policy in stage_exec:
            if stage.job_factory and stage.job_factory.type == "range" and stage.jobs: 
                n_jobs = int(stage.job_factory.params.get("n", 1))
                stage_jobs = [(stage.jobs[0], j) for j in range(n_jobs)]
            else:
                stage_jobs = [(j, i) for i, j in enumerate(stage.jobs)]

            job_definitions = []
            for job, job_index in stage_jobs:
                base_command = _python_command(job.command)
                context = {
                    "trial_index": str(trial_index),
                    "output_dir": str(output_dir),
                    "config_path": str(config_path),
                    "job_index": str(job_index),
                    "stage_name": stage.name,
                }

                template = job.rule.replace("{command}", base_command) if job.rule else base_command
                command = _replace_placeholders(template, context)

                job_definitions.append(
                    {
                        "name": job.name,
                        "command": command,
                    }
                )

            result = scheduler.run_stage(
                stage_name=stage.name,
                job_definitions=job_definitions,
                parallelism_policy=parallelism_policy,
                working_dir=str(output_dir),
            )
            if not result.success:
                raise RuntimeError(result.error_message or f"stage failed: {stage.name}")

        payload = json.loads(metrics_file.read_text())
        return {name: float(payload[name]) for name in objectives}

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

    for scheduler in schedulers:
        scheduler.shutdown()

if __name__ == "__main__":
    main()
