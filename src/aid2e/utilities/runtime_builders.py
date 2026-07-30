"""Runtime builders for config-driven AID2E execution.

This module is the boundary between canonical configuration models and runtime
objects. CLI commands should use these helpers instead of constructing
optimizers, schedulers, or workflow executors directly.
"""

from __future__ import annotations

import importlib
import shlex
from pathlib import Path
from typing import Any, Dict, Optional, Union

from aid2e.utilities.configurations.full_config import FullConfig
from aid2e.utilities.configurations.optimizer_config import OptimizerConfiguration
from aid2e.utilities.configurations.problem_config import ProblemConfiguration
from aid2e.utilities.configurations.scheduler_config import SchedulerConfiguration
from aid2e.utilities.configurations.scheduler_cascade import resolve_scheduler_cascade
from aid2e.utilities.configurations.workflow_config import (
    JobDefinition,
    WorkflowDefinition,
    WorkflowsConfiguration,
)


# Optimizer builders


def infer_optimizer_backend(optimizer_cfg: OptimizerConfiguration) -> str:
    """Infer optimizer backend name from optimizer configuration."""
    name = (optimizer_cfg.name or "").strip().lower()
    opt_type = (optimizer_cfg.type or "").strip().lower()
    params = optimizer_cfg.parameters or {}
    algorithm = str(params.get("algorithm", "")).strip().lower()

    tokens = {name, opt_type, algorithm}
    if tokens & {"ax", "bo", "mobo", "bayesian"}:
        return "ax"
    if tokens & {"pymoo", "ga", "nsga2", "nsga3", "moead", "evolutionary"}:
        return "pymoo"

    raise ValueError(
        "Could not infer optimizer backend from optimizer config. "
        "Use optimizer.name/type like 'ax' or 'pymoo'."
    )


def build_optimizer_from_config(
    problem_cfg: ProblemConfiguration,
    optimizer_cfg: OptimizerConfiguration,
    *,
    backend: Optional[str] = None,
):
    """Build a concrete optimizer from parsed configs."""
    backend_name = (backend or infer_optimizer_backend(optimizer_cfg)).lower()
    objective_names = [obj.name for obj in problem_cfg.objectives]
    objective_directions = {obj.name: obj.direction for obj in problem_cfg.objectives}
    params = dict(optimizer_cfg.parameters or {})

    if backend_name == "ax":
        from aid2e.optimizers.ax import AxOptimizer, AxOptimizerConfig

        ax_cfg = AxOptimizerConfig(**params)
        return AxOptimizer(
            search_space=problem_cfg.design_config,
            config=ax_cfg,
            objective_names=objective_names,
            objective_directions=objective_directions,
            seed=ax_cfg.seed,
        )

    if backend_name == "pymoo":
        from aid2e.optimizers.pymoo import PyMOOOptimizer, PyMOOOptimizerConfig

        if "seed" not in params:
            params["seed"] = None
        pymoo_cfg = PyMOOOptimizerConfig(**params)
        return PyMOOOptimizer(
            search_space=problem_cfg.design_config,
            config=pymoo_cfg,
            objective_names=objective_names,
            seed=pymoo_cfg.seed,
        )

    raise ValueError(f"Unsupported optimizer backend: {backend_name}")


# Scheduler builders


def build_scheduler_runtime_config(
    scheduler_cfg: Optional[SchedulerConfiguration],
) -> Optional[Dict[str, Any]]:
    """Convert SchedulerConfiguration to DAGExecutor scheduler payload."""
    if scheduler_cfg is None:
        return None

    runner_type = scheduler_cfg.runner_type
    params = dict(scheduler_cfg.parameters or {})

    if not params:
        payload = scheduler_cfg.model_dump()
        if runner_type == "JobLibRunner":
            params = dict(payload.get("joblib") or {})
        elif runner_type == "PanDAiDDSRunner":
            params = dict(payload.get("pandaidds") or payload.get("panda") or {})

    if runner_type == "JobLibRunner":
        from aid2e.schedulers.JobLib import JobLibRunnerConfig

        cfg = JobLibRunnerConfig(**params)
    elif runner_type == "SlurmRunner":
        from aid2e.schedulers.Slurm import SlurmRunnerConfig

        cfg = SlurmRunnerConfig(**params)
    elif runner_type == "PanDAiDDSRunner":
        from aid2e.schedulers.PanDAiDDS import PanDAiDDSRunnerConfig

        cfg = PanDAiDDSRunnerConfig(**params)
    else:
        raise ValueError(f"Unsupported scheduler runner_type: {runner_type}")

    return {"runner_type": runner_type, "config": cfg}


def build_scheduler_from_config(scheduler_cfg: Optional[SchedulerConfiguration]):
    """Build a scheduler instance from scheduler configuration."""
    runtime_cfg = build_scheduler_runtime_config(scheduler_cfg)
    if runtime_cfg is None:
        return None

    runner_type = runtime_cfg["runner_type"]
    cfg_obj = runtime_cfg["config"]
    if runner_type == "JobLibRunner":
        from aid2e.schedulers.JobLib import JobLibScheduler

        return JobLibScheduler(config=cfg_obj)
    if runner_type == "SlurmRunner":
        from aid2e.schedulers.Slurm import SlurmScheduler

        return SlurmScheduler(config=cfg_obj)
    if runner_type == "PanDAiDDSRunner":
        from aid2e.schedulers.PanDAiDDS import PanDAiDDSScheduler

        return PanDAiDDSScheduler(config=cfg_obj)

    raise ValueError(f"Unsupported scheduler runner_type: {runner_type}")


# Workflow builders


def _resolve_callable(spec: str):
    """Resolve a callable from '<module>:<symbol>' or '<module>.<symbol>'."""
    if ":" in spec:
        module_name, symbol_name = spec.split(":", 1)
    else:
        module_name, symbol_name = spec.rsplit(".", 1)
    module = importlib.import_module(module_name)
    return getattr(module, symbol_name)


def _resolve_workflow_python_callables(
    workflow: WorkflowDefinition,
) -> WorkflowDefinition:
    """Resolve string payload callable references for workflow jobs."""
    wf = workflow.model_copy(deep=True)
    for branch in wf.branches:
        for stage in branch.stages:
            resolved_jobs = []
            for job in stage.jobs:
                payload = dict(job.payload or {})
                callable_spec = payload.get("python_callable")
                if isinstance(callable_spec, str):
                    payload["python_callable"] = _resolve_callable(callable_spec)
                resolved_jobs.append(
                    JobDefinition(
                        name=job.name,
                        command=job.command,
                        payload=payload,
                        rule=job.rule,
                        resources=job.resources,
                        outputs=job.outputs,
                    )
                )
            stage.jobs = resolved_jobs
    return wf


def select_workflow(
    workflows_cfg: Union[WorkflowDefinition, WorkflowsConfiguration],
    workflow_name: Optional[str] = None,
) -> WorkflowDefinition:
    """Select one workflow definition from a workflow config container."""
    if isinstance(workflows_cfg, WorkflowDefinition):
        return workflows_cfg

    workflows = workflows_cfg.workflows
    if not workflows:
        raise ValueError("No workflows found in workflow configuration")

    if workflow_name:
        for wf in workflows:
            if wf.name == workflow_name:
                return wf
        raise ValueError(f"Workflow '{workflow_name}' not found in config")

    return workflows[0]


def build_workflow_executor_from_config(
    workflows_cfg: Union[WorkflowDefinition, WorkflowsConfiguration],
    *,
    problem_cfg: Optional[ProblemConfiguration] = None,
    scheduler_cfg: Optional[SchedulerConfiguration] = None,
    workflow_name: Optional[str] = None,
    base_output_dir: str = "/tmp/aid2e_runs",
    log_level: str = "INFO",
    config_dir: Optional[str] = None,
    trial_metadata: Optional[Dict[str, Any]] = None,
):
    """Build a DAGExecutor from workflow + scheduler configuration."""
    from aid2e.utilities.workflows import DAGExecutor

    workflow = select_workflow(workflows_cfg, workflow_name=workflow_name)
    if problem_cfg is not None and workflow.objectives:
        raise ValueError(
            "Canonical full-config workflows must not repeat 'workflows[].objectives'. "
            "Use 'problem.objectives' as the single source of truth."
        )
    resolved = _resolve_workflow_python_callables(workflow)
    if problem_cfg is not None:
        resolved.objectives = list(problem_cfg.objectives)

    workflow_global_scheduler = (
        workflows_cfg.global_scheduler
        if isinstance(workflows_cfg, WorkflowsConfiguration)
        else None
    )
    global_scheduler = (
        scheduler_cfg if scheduler_cfg is not None else workflow_global_scheduler
    )

    def resolve_stage_scheduler(branch, stage):
        return build_scheduler_runtime_config(
            resolve_scheduler_cascade(
                stage_scheduler=stage.scheduler,
                branch_scheduler=branch.scheduler,
                workflow_scheduler=resolved.scheduler,
                global_scheduler=global_scheduler,
            )
        )

    runtime_scheduler_cfg = build_scheduler_runtime_config(global_scheduler)

    return DAGExecutor(
        workflow=resolved,
        base_output_dir=base_output_dir,
        log_level=log_level,
        problem_config=problem_cfg,
        scheduler_config=runtime_scheduler_cfg,
        scheduler_config_resolver=resolve_stage_scheduler,
        config_dir=config_dir,
        trial_metadata=trial_metadata,
    )


# Optimization execution


def execute_trial_workflow_from_config(
    config_path: str,
    output_dir: str,
    trial_index: int,
    design_point: Dict[str, Any],
) -> Dict[str, Any]:
    """Execute one optimizer candidate through the configured workflow.

    The optimizer loop schedules this function as one trial job. It reloads the
    full config, copies the selected workflow, injects the trial
    payload fields used by command-based workflow jobs, and returns the
    objective payload collected by the DAG executor.
    """
    from aid2e.utilities.configurations import load_config
    from aid2e.utilities.workflows import create_executor_from_config

    config_path_obj = Path(config_path).resolve()
    config = load_config(str(config_path_obj))
    output_root = Path(output_dir).resolve()

    workflow = select_workflow(config.workflows).model_copy(deep=True)
    trial_metadata = {
        "trial_index": trial_index,
        "output_dir": str(output_root),
        "config_path": str(config_path_obj),
        "result_json": str(
            output_root / "log" / "results" / f"out-{trial_index}.json"
        ),
    }
    trial_payload = {
        "trial_index": trial_index,
        "output_dir": shlex.quote(str(output_root)),
        "config_path": shlex.quote(str(config_path_obj)),
        "result_json": trial_metadata["result_json"],
    }
    workflow.name = f"{workflow.name}_trial_{trial_index}"
    for branch in workflow.branches:
        for stage in branch.stages:
            for job in stage.jobs:
                job.payload = {**job.payload, **trial_payload}

    executor = create_executor_from_config(
        str(config_path_obj),
        output_dir=str(output_root),
        workflow=workflow,
        log_level="WARNING",
        trial_metadata=trial_metadata,
    )
    return executor.execute(design_point)


def run_optimization_from_config(
    config: FullConfig,
    config_path: str,
) -> Dict[str, Path]:
    """Run an optimization from a full configuration.

    The loop builds the configured optimizer and scheduler, asks the optimizer
    for candidates in configured batches, executes each candidate through the
    configured workflow, updates the optimizer with collected objectives, and
    writes result artifacts under ``config.problem.output_location``.
    """
    config_path_obj = Path(config_path).resolve()
    output_dir = Path(config.problem.output_location).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    max_failed_trials = int(
        (config.problem.evaluation_config or {}).get("max_failed_trials", 0)
    )
    failed_trials: set[int] = set()
    errors_by_trial: Dict[int, Dict[str, float]] = {}

    optimizer = build_optimizer_from_config(config.problem, config.optimizer)
    optimizer_config = optimizer.config
    n_iterations = optimizer_config.n_iterations
    batch_size = getattr(optimizer_config, "batch_size", None)
    scheduler = build_scheduler_from_config(config.scheduler)
    if scheduler is None:
        raise ValueError("Optimization execution requires a scheduler configuration")

    trial_index = 0
    completed = 0
    batch_id = 0
    try:
        while completed < n_iterations:
            batch_id += 1
            n_new = (
                min(batch_size, n_iterations - completed)
                if batch_size is not None
                else 1
            )
            design_points = optimizer.suggest_candidates(n_candidates=n_new)
            assignments = list(
                zip(
                    range(trial_index, trial_index + len(design_points)),
                    design_points,
                )
            )
            trial_index += len(assignments)
            completed += len(assignments) if batch_size is not None else 1

            batch_results = _run_optimizer_trial_batch(
                scheduler,
                batch_id,
                assignments,
                optimizer,
                config_path_obj,
                output_dir,
                failed_trials,
                max_failed_trials,
            )
            for trial_index, (design_point, raw_metrics) in batch_results.items():
                metrics = {
                    name: float(raw_metrics[name])
                    for name in optimizer.objective_names
                }
                errors_by_trial[trial_index] = {
                    f"{name}_sem": float(raw_metrics[f"{name}_sem"])
                    for name in optimizer.objective_names
                    if f"{name}_sem" in raw_metrics
                }
                optimizer.update_with_results(trial_index, design_point, metrics)
            optimizer.save_optimization_results(
                output_dir / "optimization_results.json",
                save_pareto_front=output_dir / "pareto_front.json",
                errors_by_trial=errors_by_trial,
            )
    finally:
        scheduler.shutdown()

    return {
        "optimization_results": output_dir / "optimization_results.json",
        "pareto_front": output_dir / "pareto_front.json",
    }


def _run_optimizer_trial_batch(
    scheduler,
    batch_id: int,
    assignments: list[tuple[int, Dict[str, Any]]],
    optimizer,
    config_path: Path,
    output_dir: Path,
    failed_trials: set[int],
    max_failed_trials: int,
) -> Dict[int, tuple[Dict[str, Any], Dict[str, Any]]]:
    """Submit one optimizer batch as scheduler jobs.

    Each scheduler job runs one full workflow for one optimizer candidate.
    Failed scheduler jobs are recorded as failed optimizer trials before the
    completed trial objective payloads are returned to the optimization loop.
    """
    active_trials = {
        trial_index: design_point for trial_index, design_point in assignments
    }
    job_definitions = [
        {
            "job_id": str(trial_index),
            "name": f"trial_{trial_index}",
            "function": execute_trial_workflow_from_config,
            "params": {
                "config_path": str(config_path),
                "output_dir": str(output_dir),
                "trial_index": trial_index,
                "design_point": design_point,
            },
        }
        for trial_index, design_point in assignments
    ]

    result = scheduler.run_stage(
        f"optimizer_batch_{batch_id}_trials",
        job_definitions,
        parallelism_policy={"max_concurrent": len(assignments)},
        working_dir=str(output_dir),
    )
    if not result.success:
        failed_job_ids = {
            int(status.job_id)
            for status in result.job_statuses
            if status.status != "completed" and str(status.job_id).isdigit()
        }
        if not failed_job_ids:
            raise RuntimeError(result.error_message or "Optimizer trial batch failed")

        for trial_index in sorted(failed_job_ids & set(active_trials)):
            optimizer.set_trial_status(
                trial_index=trial_index,
                status="failed",
                parameters=active_trials[trial_index],
                metadata={"reason": result.error_message},
            )
            failed_trials.add(trial_index)
            del active_trials[trial_index]

        if len(failed_trials) > max_failed_trials:
            raise RuntimeError(
                f"Too many failed trials: {len(failed_trials)} failed, "
                f"max_failed_trials={max_failed_trials}"
            )

    completed_statuses = {
        int(status.job_id): status
        for status in result.job_statuses
        if status.status == "completed" and str(status.job_id).isdigit()
    }
    return {
        trial_index: (
            design_point,
            (completed_statuses[trial_index].outputs or {})["result"],
        )
        for trial_index, design_point in active_trials.items()
    }
