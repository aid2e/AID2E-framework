"""Runtime builder helpers for config-driven AID2E execution."""

from __future__ import annotations

import importlib
import shlex
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Union

from aid2e.utilities.configurations.full_config import FullConfig
from aid2e.utilities.configurations.optimizer_config import OptimizerConfiguration
from aid2e.utilities.configurations.problem_config import ProblemConfiguration
from aid2e.utilities.configurations.scheduler_config import SchedulerConfiguration
from aid2e.utilities.configurations.scheduler_cascade import resolve_scheduler_cascade
from aid2e.utilities.configurations.workflow_config import (
    WorkflowDefinition,
    WorkflowsConfiguration,
)


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
            objective_directions=objective_directions,
            seed=pymoo_cfg.seed,
        )

    raise ValueError(f"Unsupported optimizer backend: {backend_name}")


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
                resolved_jobs.append(job.model_copy(update={"payload": payload}))
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
    output_dir: Optional[str] = None,
    work_dir: Optional[str] = None,
):
    """Build a DAGExecutor from loaded workflow, problem, and scheduler configs."""
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
        output_dir=output_dir,
        work_dir=work_dir,
    )


def run_trial_workflow(
    config_path: str,
    run_dir: str,
    run_work_dir: str,
    trial_index: int,
    design_point: Dict[str, Any],
    workflow_name: Optional[str] = None,
    log_level: str = "WARNING",
) -> Dict[str, Any]:
    """Execute one optimizer candidate through the configured workflow."""
    from aid2e.utilities.configurations import load_config

    config_path_obj = Path(config_path).resolve()
    config = load_config(str(config_path_obj))
    trial_name = f"trial_{trial_index}"
    output_dir = Path(run_dir).resolve() / "trials" / trial_name
    work_dir = Path(run_work_dir).resolve() / "trials" / trial_name

    trial_metadata = {
        "trial_index": trial_index,
        "config_path": str(config_path_obj),
    }
    trial_payload = {
        "trial_index": trial_index,
        "output_dir": shlex.quote(str(output_dir)),
        "config_path": shlex.quote(str(config_path_obj)),
    }
    workflow = select_workflow(
        config.workflows,
        workflow_name=workflow_name,
    ).model_copy(deep=True)
    workflow.name = f"{workflow.name}_trial_{trial_index}"
    for branch in workflow.branches:
        for stage in branch.stages:
            for job in stage.jobs:
                job.payload = {**job.payload, **trial_payload}

    return build_workflow_executor_from_config(
        workflow,
        problem_cfg=config.problem,
        scheduler_cfg=config.scheduler,
        log_level=log_level,
        config_dir=str(config_path_obj.parent),
        trial_metadata=trial_metadata,
        output_dir=str(output_dir),
        work_dir=str(work_dir),
    ).execute(design_point)


def run_optimization(
    config: FullConfig,
    config_path: str,
    *,
    workflow_name: Optional[str] = None,
    output_dir: Optional[str] = None,
    run_id: Optional[str] = None,
    log_level: str = "WARNING",
) -> Dict[str, Path]:
    """Run an optimization from a full configuration."""
    config_path_obj = Path(config_path).resolve()
    output_root = Path(output_dir or config.problem.output_location).resolve()
    run_name = run_id or datetime.now().strftime("%Y%m%d_%H%M")
    run_dir = output_root / run_name
    run_work_dir = Path(config.problem.work_location).resolve() / run_name
    if run_dir.exists() or run_work_dir.exists():
        raise FileExistsError(f"Run ID '{run_name}' already exists")
    run_dir.mkdir(parents=True)
    outputs = {
        "run_dir": run_dir,
        "optimization_results": run_dir / "optimization_results.json",
        "pareto_front": run_dir / "pareto_front.json",
    }
    evaluation_config = config.problem.evaluation_config or {}
    trial_failure_policy = evaluation_config.get("trial_failure_policy", "fail")
    if trial_failure_policy not in {"fail", "penalty"}:
        raise ValueError("trial_failure_policy must be 'fail' or 'penalty'")
    penalty_objectives = evaluation_config.get("penalty_objectives", {})
    if trial_failure_policy == "penalty":
        try:
            penalty_objectives = {
                objective.name: float(penalty_objectives[objective.name])
                for objective in config.problem.objectives
            }
        except KeyError as error:
            raise ValueError(
                f"penalty_objectives missing declared objective: {error.args[0]}"
            ) from error
    max_failed_trials = int(evaluation_config.get("max_failed_trials", 0))
    failed_trials: set[int] = set()
    errors_by_trial: Dict[int, Dict[str, float]] = {}

    optimizer = build_optimizer_from_config(config.problem, config.optimizer)
    optimizer_config = optimizer.config
    n_iterations = optimizer_config.n_iterations
    batch_size = getattr(optimizer_config, "batch_size", None)
    scheduler = build_scheduler_from_config(config.scheduler)
    if scheduler is None:
        raise ValueError("Optimization execution requires a scheduler configuration")

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
            existing_trial_indices = {trial.index for trial in optimizer.get_trials()}
            design_points = optimizer.suggest_candidates(n_candidates=n_new)
            if not design_points:
                raise RuntimeError("Optimizer did not suggest any candidates")
            new_trials = [
                trial
                for trial in optimizer.get_trials()
                if trial.index not in existing_trial_indices
            ]
            if len(new_trials) != len(design_points):
                raise RuntimeError(
                    "Optimizer must record one trial for each suggested candidate"
                )
            assignments = [
                (trial.index, design_point)
                for trial, design_point in zip(new_trials, design_points)
            ]
            completed += len(assignments) if batch_size is not None else 1

            batch_results = _run_trial_batch(
                scheduler,
                batch_id,
                assignments,
                optimizer,
                config_path_obj,
                run_dir,
                run_work_dir,
                workflow_name,
                failed_trials,
                max_failed_trials,
                trial_failure_policy,
                penalty_objectives,
                log_level,
            )
            for trial_index, (design_point, raw_metrics, metadata) in batch_results.items():
                metrics = {
                    name: float(raw_metrics[name])
                    for name in optimizer.objective_names
                }
                errors_by_trial[trial_index] = {
                    f"{name}_err": float(raw_metrics[f"{name}_err"])
                    for name in optimizer.objective_names
                    if f"{name}_err" in raw_metrics
                }
                optimizer.update_with_results(trial_index, design_point, metrics)
                if metadata:
                    optimizer.set_trial_status(
                        trial_index,
                        "completed",
                        metadata=metadata,
                    )
            optimizer.save_optimization_results(
                run_dir,
                errors_by_trial=errors_by_trial,
            )
    finally:
        scheduler.shutdown()

    return outputs


def _run_trial_batch(
    scheduler,
    batch_id: int,
    assignments: list[tuple[int, Dict[str, Any]]],
    optimizer,
    config_path: Path,
    run_dir: Path,
    run_work_dir: Path,
    workflow_name: Optional[str],
    failed_trials: set[int],
    max_failed_trials: int,
    trial_failure_policy: str,
    penalty_objectives: Dict[str, float],
    log_level: str,
) -> Dict[int, tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]]:
    """Submit one optimizer batch through the configured scheduler."""
    active_trials = {
        trial_index: design_point for trial_index, design_point in assignments
    }
    job_definitions = [
        {
            "job_id": str(trial_index),
            "name": f"trial_{trial_index}",
            "function": run_trial_workflow,
            "params": {
                "config_path": str(config_path),
                "run_dir": str(run_dir),
                "run_work_dir": str(run_work_dir),
                "trial_index": trial_index,
                "design_point": design_point,
                "workflow_name": workflow_name,
                "log_level": log_level,
            },
        }
        for trial_index, design_point in assignments
    ]

    result = scheduler.run_stage(
        f"optimizer_batch_{batch_id}_trials",
        job_definitions,
        parallelism_policy={"max_concurrent": len(assignments)},
        working_dir=str(run_work_dir),
    )
    trial_results = {}
    if not result.success:
        failed_statuses = {
            int(status.job_id): status
            for status in result.job_statuses
            if status.status != "completed" and str(status.job_id).isdigit()
        }
        if not failed_statuses:
            raise RuntimeError(result.error_message or "Optimizer trial batch failed")

        for trial_index in sorted(failed_statuses.keys() & active_trials.keys()):
            design_point = active_trials.pop(trial_index)
            reason = failed_statuses[trial_index].stderr or result.error_message
            failed_trials.add(trial_index)
            if trial_failure_policy == "penalty":
                trial_results[trial_index] = (
                    design_point,
                    penalty_objectives,
                    {"penalized": True, "reason": reason},
                )
            else:
                optimizer.mark_trial_failed(
                    trial_index,
                    parameters=design_point,
                    reason=reason,
                )

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
    missing_results = sorted(set(active_trials) - set(completed_statuses))
    if missing_results:
        raise RuntimeError(
            "Completed optimizer batch missing trial results: "
            + ", ".join(str(index) for index in missing_results)
        )
    trial_results.update({
        trial_index: (
            design_point,
            _completed_status_payload(
                completed_statuses[trial_index].outputs or {},
                optimizer.objective_names,
            ),
            {},
        )
        for trial_index, design_point in active_trials.items()
    })
    return trial_results


def _completed_status_payload(
    outputs: Dict[str, Any],
    objective_names: list[str],
) -> Dict[str, Any]:
    """Return the objective payload from scheduler job outputs."""
    if "result" in outputs:
        return outputs["result"]
    if "objectives" in outputs:
        return outputs["objectives"]
    if all(name in outputs for name in objective_names):
        return outputs
    raise RuntimeError("Completed optimizer trial did not return objective outputs")
