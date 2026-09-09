"""PanDA/iDDS-local builder for stage-native dependency graph payloads.

This module intentionally accepts plain dictionaries instead of importing
workflow executor models. It gives the PanDA scheduler a place to translate
stage-shaped metadata into the ``panda_multistage`` coordinator payload without
putting scheduler-specific graph semantics in core AID2E execution code.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional
import copy
import importlib


_STAGE_KEYS = {
    "depends_on",
    "dep_type",
    "dep_map",
    "runner",
    "execution",
    "job_type",
    "with_output_dataset",
    "output_file",
    "output_file_name",
    "output_dataset",
    "output_dataset_name",
    "num_events",
    "num_events_per_job",
    "with_input_datasets",
    "input_datasets",
    "parent_results_key",
    "parent_result_parameter_name",
    "produces_objective",
    "final",
    "produces",
}

_JOB_INSTANCE_KEYS = {
    "with_output_dataset",
    "output_file",
    "output_file_name",
    "output_dataset",
    "output_dataset_name",
    "num_events",
    "num_events_per_job",
    "with_input_datasets",
    "input_datasets",
}


@dataclass
class PanDAMultiStageGraphBuilder:
    """Build a ``panda_multistage`` payload from scheduler-local stage records."""

    default_dep_type: str = "datasets"

    def build_payload(
        self,
        stage_records: Iterable[Dict[str, Any]],
        *,
        final_stage: Optional[str] = None,
        trial_index: Any = None,
        design_point: Optional[Dict[str, Any]] = None,
        extra_payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Return a nested payload consumable by ``PanDAMultiStageJob``.

        Stage records are intentionally loose dictionaries. The expected shape is
        close to AID2E workflow YAML:

        ``{"name": "simreco", "jobs": [{"name": "...", "payload": {...}}]}``

        A caller may also pass already-normalized stage records with stage-level
        ``python_callable`` and optional ``jobs`` entries.
        """
        stages = [self._build_stage(record) for record in stage_records]
        if not stages:
            raise ValueError("panda_multistage_graph requires at least one stage record")

        payload: Dict[str, Any] = {
            "evaluator_type": "panda_multistage",
            "stages": stages,
        }
        if final_stage:
            payload["final_stage"] = final_stage
        if trial_index is not None:
            payload["trial_index"] = trial_index
        if design_point is not None:
            payload["design_point"] = copy.deepcopy(design_point)
        if extra_payload:
            for key, value in extra_payload.items():
                if key not in {"evaluator_type", "stages", "stage_records"}:
                    payload[key] = copy.deepcopy(value)
        return payload

    def build_scheduler_job(
        self,
        job_definition: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Convert a ``panda_multistage_graph`` job into ``panda_multistage``."""
        payload = dict(job_definition.get("payload") or {})
        stage_records = payload.get("stage_records") or payload.get("stages")
        if stage_records is None:
            raise ValueError("panda_multistage_graph payload must define 'stage_records'")

        graph_payload = self.build_payload(
            stage_records,
            final_stage=payload.get("final_stage") or payload.get("final"),
            trial_index=payload.get("trial_index"),
            design_point=payload.get("design_point"),
            extra_payload=payload,
        )
        graph_job = dict(job_definition)
        graph_job["payload"] = graph_payload
        return graph_job

    def _build_stage(self, record: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(record, dict):
            raise ValueError("panda_multistage_graph stage records must be mappings")
        stage_name = record.get("name") or record.get("stage")
        if not stage_name:
            raise ValueError("panda_multistage_graph stage record is missing 'name'")

        jobs = list(record.get("jobs") or record.get("children") or record.get("instances") or [])
        payloads = [self._job_payload(job) for job in jobs]
        representative = self._representative_payload(record, payloads)
        python_callable = representative.get("python_callable") or record.get("python_callable")
        if python_callable is None:
            raise ValueError(f"panda_multistage_graph stage '{stage_name}' is missing python_callable")
        python_callable = self._resolve_python_callable(python_callable)

        stage: Dict[str, Any] = {
            "name": stage_name,
            "python_callable": python_callable,
        }
        for key in _STAGE_KEYS:
            if key in record:
                stage[key] = copy.deepcopy(record[key])
            elif key in representative:
                stage[key] = copy.deepcopy(representative[key])

        if "dep_type" not in stage and self._has_dependency(stage):
            stage["dep_type"] = self.default_dep_type

        if jobs:
            stage["jobs"] = [
                self._build_instance(stage_name, job, python_callable)
                for job in jobs
            ]
        return stage

    def _representative_payload(
        self,
        record: Dict[str, Any],
        payloads: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        if record.get("payload"):
            return dict(record["payload"])
        if payloads:
            return dict(payloads[0])
        return {}

    def _build_instance(
        self,
        stage_name: str,
        job: Dict[str, Any],
        stage_callable: Any,
    ) -> Dict[str, Any]:
        if not isinstance(job, dict):
            raise ValueError(f"panda_multistage_graph stage '{stage_name}' jobs must be mappings")
        payload = self._job_payload(job)
        python_callable = payload.get("python_callable")
        if python_callable is not None and self._resolve_python_callable(python_callable) != stage_callable:
            raise ValueError(
                f"panda_multistage_graph stage '{stage_name}' has mixed python_callable values"
            )

        key = job.get("key") or job.get("name") or job.get("job_id")
        if key is None:
            raise ValueError(f"panda_multistage_graph stage '{stage_name}' job is missing name/key")

        instance: Dict[str, Any] = {"key": str(key)}
        if "params" in job:
            instance["params"] = copy.deepcopy(job["params"])
        op_kwargs = copy.deepcopy(job.get("op_kwargs") or payload.get("op_kwargs") or {})
        if op_kwargs:
            instance["op_kwargs"] = op_kwargs
        for key_name in _JOB_INSTANCE_KEYS:
            if key_name in job:
                instance[key_name] = copy.deepcopy(job[key_name])
            elif key_name in payload:
                instance[key_name] = copy.deepcopy(payload[key_name])
        return instance

    def _resolve_python_callable(self, value: Any) -> Any:
        if not isinstance(value, str):
            return value
        if ":" not in value:
            return value
        module_name, qualname = value.split(":", 1)
        target = importlib.import_module(module_name)
        for attr in qualname.split("."):
            target = getattr(target, attr)
        return target

    def _job_payload(self, job: Dict[str, Any]) -> Dict[str, Any]:
        payload = job.get("payload") if isinstance(job, dict) else None
        return dict(payload or {})

    def _has_dependency(self, stage: Dict[str, Any]) -> bool:
        depends = stage.get("depends_on")
        if isinstance(depends, dict):
            return bool(depends.get("stage") or depends.get("parent"))
        return bool(depends)
