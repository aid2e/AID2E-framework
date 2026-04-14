"""Runtime builder helpers for config-driven AID2E execution."""

from __future__ import annotations

import importlib
from typing import Any, Dict, Optional, Sequence, Tuple, Union

from .optimization_config import OptimizationConfiguration
from .problem_config import ProblemConfiguration
from .scheduler_config import SchedulerConfiguration
from .workflow_config import JobDefinition, WorkflowDefinition, WorkflowsConfiguration


def infer_optimizer_backend(optimization_cfg: OptimizationConfiguration) -> str:
    """Infer optimizer backend name from optimization configuration."""
    name = (optimization_cfg.optimizer.name or "").strip().lower()
    opt_type = (optimization_cfg.optimizer.type or "").strip().lower()
    params = optimization_cfg.optimizer.parameters or {}
    algorithm = str(params.get("algorithm", "")).strip().lower()

    tokens = {name, opt_type, algorithm}
    if tokens & {"ax", "bo", "mobo", "bayesian"}:
        return "ax"
    if tokens & {"pymoo", "nsga2", "nsga3", "moead", "evolutionary"}:
        return "pymoo"

    raise ValueError(
        "Could not infer optimizer backend from optimization config. "
        "Use optimizer.name/type like 'ax' or 'pymoo'."
    )


def build_optimizer_from_config(
    problem_cfg: ProblemConfiguration,
    optimization_cfg: OptimizationConfiguration,
    *,
    backend: Optional[str] = None,
):
    """Build a concrete optimizer from parsed configs."""
    backend_name = (backend or infer_optimizer_backend(optimization_cfg)).lower()
    objective_names = [obj.name for obj in optimization_cfg.objectives] or [
        obj.name for obj in problem_cfg.objectives
    ]

    params = dict(optimization_cfg.optimizer.parameters or {})

    if backend_name == "ax":
        from aid2e.optimizers.ax import AxOptimizer, AxOptimizerConfig

        ax_payload = {
            "n_initial_samples": optimization_cfg.n_initial_samples,
            "n_iterations": optimization_cfg.n_iterations,
            "batch_size": optimization_cfg.parallel_evaluations,
            **params,
        }
        ax_cfg = AxOptimizerConfig(**ax_payload)
        return AxOptimizer(
            search_space=problem_cfg.design_config,
            config=ax_cfg,
            objective_names=objective_names,
            seed=ax_cfg.seed,
        )

    if backend_name == "pymoo":
        from aid2e.optimizers.pymoo import PyMOOOptimizer, PyMOOOptimizerConfig

        pymoo_payload = {**params}
        if "seed" not in pymoo_payload:
            pymoo_payload["seed"] = None
        pymoo_cfg = PyMOOOptimizerConfig(**pymoo_payload)
        return PyMOOOptimizer(
            search_space=problem_cfg.design_config,
            config=pymoo_cfg,
            objective_names=objective_names,
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


def _resolve_workflow_python_callables(workflow: WorkflowDefinition) -> WorkflowDefinition:
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
    scheduler_cfg: Optional[SchedulerConfiguration] = None,
    workflow_name: Optional[str] = None,
    base_output_dir: str = "/tmp/aid2e_runs",
    log_level: str = "INFO",
) -> DAGExecutor:
    """Build a DAGExecutor from workflow + scheduler configuration."""
    from aid2e.utilities.workflows import DAGExecutor

    workflow = select_workflow(workflows_cfg, workflow_name=workflow_name)
    resolved = _resolve_workflow_python_callables(workflow)

    runtime_scheduler_cfg = build_scheduler_runtime_config(scheduler_cfg)
    if runtime_scheduler_cfg is None and isinstance(workflows_cfg, WorkflowsConfiguration):
        runtime_scheduler_cfg = build_scheduler_runtime_config(workflows_cfg.global_scheduler)

    return DAGExecutor(
        workflow=resolved,
        base_output_dir=base_output_dir,
        log_level=log_level,
        scheduler_config=runtime_scheduler_cfg,
    )
