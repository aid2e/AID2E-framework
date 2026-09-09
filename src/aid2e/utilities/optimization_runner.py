"""Generic optimization orchestration for config-driven AID2E runs."""

from __future__ import annotations

import json
import warnings
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol, Union

from aid2e.utilities.configurations import FullConfig, load_config
from aid2e.utilities.runtime_builders import (
    build_optimizer_from_config,
    build_workflow_executor_from_config,
    infer_optimizer_backend,
)


class CandidateEvaluator(Protocol):
    """Evaluate one optimizer candidate and return objective metrics."""

    def evaluate(self, parameters: Dict[str, Any]) -> Dict[str, float]:
        """Evaluate candidate parameters."""
        ...


@dataclass
class OptimizationRunOptions:
    """Runtime options for a generic optimization run."""

    workflow_name: Optional[str] = None
    output_dir: Optional[Union[str, Path]] = None
    run_id: Optional[str] = None
    log_level: str = "INFO"


@dataclass
class TrialRecord:
    """Persisted record for one candidate evaluation."""

    trial_index: int
    parameters: Dict[str, Any]
    metrics: Optional[Dict[str, float]] = None
    status: str = "pending"
    workflow: Optional[str] = None
    error: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


@dataclass
class OptimizationRunResult:
    """Summary returned by the generic optimization runner."""

    run_id: str
    run_dir: str
    optimizer_backend: str
    workflow_name: str
    n_trials: int
    completed_trials: int
    failed_trials: int
    pareto_front: List[Dict[str, Any]] = field(default_factory=list)
    trials: List[TrialRecord] = field(default_factory=list)


class WorkflowCandidateEvaluator:
    """Candidate evaluator backed by a workflow DAG."""

    def __init__(
        self,
        executor: Any,
        *,
        objective_names: List[str],
    ) -> None:
        self.executor = executor
        self.objective_names = list(objective_names)

    def evaluate(self, parameters: Dict[str, Any]) -> Dict[str, float]:
        metrics = self.executor.execute(parameters)
        missing = [name for name in self.objective_names if name not in metrics]
        if missing:
            raise ValueError(
                "Workflow did not return all configured objectives. "
                f"Missing {missing}; got {list(metrics.keys())}."
            )
        return {name: float(metrics[name]) for name in self.objective_names}


def run_optimization_from_config(
    config_or_path: Union[str, Path, FullConfig],
    *,
    options: Optional[OptimizationRunOptions] = None,
) -> OptimizationRunResult:
    """Run a generic workflow-backed optimization from a canonical config."""
    options = options or OptimizationRunOptions()
    config = (
        load_config(str(config_or_path))
        if isinstance(config_or_path, (str, Path))
        else config_or_path
    )

    if config.workflows is None:
        raise ValueError(
            "Generic optimization requires a top-level 'workflows' section. "
            "Problem-specific built-in evaluators are not part of the CLI runner."
        )

    run_id = options.run_id or _utc_timestamp()
    run_dir = _resolve_run_dir(config, options, run_id)
    run_dir.mkdir(parents=True, exist_ok=True)

    backend = infer_optimizer_backend(config.optimizer)
    optimizer = build_optimizer_from_config(
        config.problem,
        config.optimizer,
        backend=backend,
    )
    executor = build_workflow_executor_from_config(
        config.workflows,
        problem_cfg=config.problem,
        scheduler_cfg=config.scheduler,
        workflow_name=options.workflow_name,
        base_output_dir=str(run_dir / "workflows"),
        log_level=options.log_level,
    )
    objective_names = [objective.name for objective in config.problem.objectives]
    evaluator = WorkflowCandidateEvaluator(
        executor,
        objective_names=objective_names,
    )

    _write_json(run_dir / "run.json", _run_metadata(config, backend, run_id, run_dir))
    _write_config_snapshot(run_dir / "resolved_config.json", config)

    records: List[TrialRecord] = []
    for n_candidates in _candidate_batch_sizes(
        config.optimizer.parameters or {},
        backend,
    ):
        before_trials = optimizer.get_trials()
        candidates = _suggest_candidates(optimizer, n_candidates, backend)
        new_trials = optimizer.get_trials()[len(before_trials):]

        if len(new_trials) < len(candidates):
            raise RuntimeError(
                "Optimizer did not expose trial records for all suggested candidates."
            )

        for trial, parameters in zip(new_trials, candidates):
            record = TrialRecord(
                trial_index=trial.index,
                parameters=dict(parameters),
                status="running",
                workflow=executor.workflow.name,
                started_at=_utc_timestamp(),
            )
            records.append(record)
            _append_trial_record(run_dir / "trials.jsonl", record)

            try:
                optimizer.set_trial_status(
                    trial.index,
                    "running",
                    parameters=dict(parameters),
                )
                metrics = evaluator.evaluate(parameters)
                optimizer.update_with_results(trial.index, parameters, metrics)
                record.metrics = metrics
                record.status = "completed"
            except Exception as exc:
                record.status = "failed"
                record.error = str(exc)
                optimizer.set_trial_status(
                    trial.index,
                    "failed",
                    parameters=dict(parameters),
                    metadata={"error": str(exc)},
                )
                record.completed_at = _utc_timestamp()
                _append_trial_record(run_dir / "trials.jsonl", record)
                _write_summary(
                    run_dir, optimizer, backend, executor.workflow.name, records, run_id
                )
                raise

            record.completed_at = _utc_timestamp()
            _append_trial_record(run_dir / "trials.jsonl", record)
            _write_summary(
                run_dir, optimizer, backend, executor.workflow.name, records, run_id
            )

    return _write_summary(
        run_dir, optimizer, backend, executor.workflow.name, records, run_id
    )


def _resolve_run_dir(
    config: FullConfig,
    options: OptimizationRunOptions,
    run_id: str,
) -> Path:
    base = (
        Path(options.output_dir)
        if options.output_dir
        else Path(config.problem.output_location)
    )
    return base / run_id


def _suggest_candidates(
    optimizer: Any,
    n_candidates: int,
    backend: str,
) -> List[Dict[str, Any]]:
    if backend == "pymoo":
        return optimizer.suggest_candidates()

    return optimizer.suggest_candidates(n_candidates=n_candidates)


def _candidate_batch_sizes(
    optimizer_params: Dict[str, Any],
    backend: str,
) -> List[int]:
    n_iterations = int(optimizer_params.get("n_iterations", 1))
    if backend == "ax":
        n_initial = int(optimizer_params.get("n_initial_samples", 1))
        batch_size = int(optimizer_params.get("batch_size", 1))
        return [1] * n_initial + [batch_size] * n_iterations
    return [1] * n_iterations


def _write_summary(
    run_dir: Path,
    optimizer: Any,
    optimizer_backend: str,
    workflow_name: str,
    records: List[TrialRecord],
    run_id: str,
) -> OptimizationRunResult:
    trials = optimizer.get_trials()
    completed = [record for record in records if record.status == "completed"]
    failed = [record for record in records if record.status == "failed"]
    pareto_front = [_trial_to_dict(trial) for trial in optimizer.get_pareto_front()]
    result = OptimizationRunResult(
        run_id=run_id,
        run_dir=str(run_dir),
        optimizer_backend=optimizer_backend,
        workflow_name=workflow_name,
        n_trials=len(trials),
        completed_trials=len(completed),
        failed_trials=len(failed),
        pareto_front=pareto_front,
        trials=list(records),
    )
    _write_json(run_dir / "summary.json", asdict(result))
    _write_json(run_dir / "pareto_front.json", pareto_front)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            optimizer_state = optimizer.serialize_state()
        _write_json(run_dir / "optimizer_state.json", optimizer_state)
    except Exception:
        pass
    return result


def _run_metadata(
    config: FullConfig,
    optimizer_backend: str,
    run_id: str,
    run_dir: Path,
) -> Dict[str, Any]:
    return {
        "run_id": run_id,
        "run_dir": str(run_dir),
        "created_at": _utc_timestamp(),
        "problem": config.problem.problem_type,
        "optimizer": config.optimizer.name,
        "optimizer_backend": optimizer_backend,
    }


def _write_config_snapshot(path: Path, config: FullConfig) -> None:
    try:
        payload = config.model_dump(mode="python", warnings=False)
    except TypeError:
        payload = config.model_dump(mode="python")
    _write_json(path, payload)


def _append_trial_record(path: Path, record: TrialRecord) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(asdict(record), default=str, sort_keys=True) + "\n")


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, default=str, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _trial_to_dict(trial: Any) -> Dict[str, Any]:
    return {
        "index": trial.index,
        "parameters": trial.parameters,
        "metrics": trial.metrics,
        "status": trial.status,
        "metadata": trial.metadata,
    }


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
