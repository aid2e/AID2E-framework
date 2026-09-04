"""AID2E-owned PanDA/iDDS multi-stage dependency coordinator.

This module models the issue-61 stage-native transition using the two dependency
families discussed in issue 60. Dataset-backed dependencies are submitted with
PanDA/iDDS metadata so PanDA can manage release. Result-backed/local edges are
kept as coordinator metadata for mixed local/remote stage maps.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import copy
import hashlib
import json
import re
import time as _time


def _work_internal_id(work: Any) -> Optional[str]:
    for attr in ("internal_id", "internalId", "_internal_id"):
        value = getattr(work, attr, None)
        if value is not None:
            return str(value)
    return None


@dataclass
class PanDAMultiStageWork:
    """One logical job instance inside a multi-stage PanDA/iDDS workflow."""

    stage_name: str
    instance_key: str
    job_id: str
    work: Any
    tf_id: Any
    job_key: str
    internal_id: Optional[str] = None
    status: str = "running"
    result: Any = None
    details: Any = None
    execution: str = "panda"


@dataclass
class PanDAMultiStageSpec:
    """Validated stage-native PanDA/iDDS dependency payload."""

    stages: List[Dict[str, Any]]
    final_stage: str
    by_name: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    @classmethod
    def from_payload(cls, payload: Dict[str, Any]) -> "PanDAMultiStageSpec":
        stages = payload.get("stages") or []
        if not isinstance(stages, list) or not stages:
            raise ValueError("panda_multistage payload must define a non-empty 'stages' list")

        by_name: Dict[str, Dict[str, Any]] = {}
        for index, raw_stage in enumerate(stages):
            if not isinstance(raw_stage, dict):
                raise ValueError(f"panda_multistage stage at index {index} must be a mapping")
            stage = dict(raw_stage)
            name = stage.get("name")
            if not name:
                raise ValueError(f"panda_multistage stage at index {index} is missing 'name'")
            if name in by_name:
                raise ValueError(f"Duplicate panda_multistage stage name: {name}")
            if stage.get("python_callable") is None:
                raise ValueError(f"panda_multistage stage '{name}' is missing 'python_callable'")

            dep_type = stage.get("dep_type", "datasets")
            if dep_type not in {"datasets", "results"}:
                raise ValueError(
                    f"panda_multistage stage '{name}' uses dep_type={dep_type!r}; "
                    "expected 'datasets' or 'results'"
                )
            dep_map = stage.get("dep_map", "one2one")
            if dep_map not in {"one2one", "one2many", "all2one", "many2one"}:
                raise ValueError(
                    f"panda_multistage stage '{name}' uses dep_map={dep_map!r}; "
                    "expected 'one2one', 'one2many', 'all2one', or 'many2one'"
                )
            if dep_map == "many2one":
                stage["dep_map"] = "all2one"
            by_name[name] = stage

        for stage in by_name.values():
            for dep_name in _depends_on(stage):
                if dep_name not in by_name:
                    raise ValueError(
                        f"panda_multistage stage '{stage['name']}' depends on unknown stage '{dep_name}'"
                    )

        final_stages = [
            stage["name"]
            for stage in by_name.values()
            if stage.get("produces_objective") or stage.get("final")
        ]
        explicit_final = payload.get("final") or payload.get("final_stage")
        if explicit_final:
            if explicit_final not in by_name:
                raise ValueError(f"panda_multistage final stage '{explicit_final}' is not defined")
            final_stages.append(explicit_final)

        unique_final_stages = list(dict.fromkeys(final_stages))
        if len(unique_final_stages) > 1:
            raise ValueError(
                "panda_multistage payload must identify exactly one final objective-producing stage"
            )
        final_stage = unique_final_stages[0] if unique_final_stages else stages[-1]["name"]
        return cls(stages=list(by_name.values()), final_stage=final_stage, by_name=by_name)


class PanDAMultiStageJob:
    """Submit multi-stage instances with explicit one2one/one2many/all2one maps."""

    def __init__(
        self,
        *,
        scheduler: Any,
        stage_name: str,
        job_definition: Dict[str, Any],
        working_dir: Optional[str] = None,
        poll_interval: float = 5,
    ) -> None:
        self.scheduler = scheduler
        self.stage_name = stage_name
        self.job_definition = job_definition
        self.working_dir = working_dir
        self.poll_interval = poll_interval
        self.logical_job_id = job_definition.get("job_id") or job_definition.get("name") or "panda_multistage"
        self.payload = dict(job_definition.get("payload") or {})
        self.spec = PanDAMultiStageSpec.from_payload(self.payload)
        self.works_by_stage: Dict[str, List[PanDAMultiStageWork]] = {
            stage["name"]: [] for stage in self.spec.stages
        }

    def run(self) -> Dict[str, Any]:
        """Submit stage instances while respecting dependency release mode.

        Dataset-managed PanDA dependencies are submitted as soon as parent work
        metadata exists. PanDA/iDDS keeps those children idle until the parent
        datasets are available. Result-managed dependencies wait here until the
        parent results have been collected.
        """
        submitted_stages = set()
        while len(submitted_stages) < len(self.spec.stages):
            made_progress = False
            for stage in self.spec.stages:
                stage_name = stage["name"]
                if stage_name in submitted_stages:
                    continue
                if not self._stage_ready_for_submission(stage):
                    continue
                self._submit_stage(stage)
                submitted_stages.add(stage_name)
                made_progress = True

            failed = [stage for stage in self._all_stage_works() if stage.status == "failed"]
            if failed:
                break

            poll_progress = self._poll_running_stages() if self._has_running_stages() else False
            if not made_progress and not poll_progress:
                _time.sleep(self.poll_interval)

        while self._has_running_stages():
            made_progress = self._poll_running_stages()
            if not made_progress:
                _time.sleep(self.poll_interval)

        failed = [stage for stage in self._all_stage_works() if stage.status == "failed"]
        if failed:
            return {
                "status": "failed",
                "return_code": -1,
                "stdout": "",
                "stderr": f"panda_multistage stage {failed[0].job_id} failed",
                "outputs": {},
                "metrics": self._metrics(),
            }

        final_results = self._final_results()
        final_details = self._final_details()
        outputs = self.scheduler._normalize_function_outputs(final_results)
        context = self.job_definition.get("job_context")
        if context is not None and hasattr(context, "xcom_push"):
            try:
                if isinstance(final_results, dict):
                    context.xcom_push("objectives", final_results)
                if final_details is not None:
                    context.xcom_push("results_details", final_details)
                context.xcom_push("panda_multistage_results", self._all_results())
            except Exception:
                self.scheduler.logger.debug(
                    "Failed to push panda_multistage results to job context", exc_info=True
                )
        return {
            "status": "completed",
            "return_code": 0,
            "stdout": "",
            "stderr": "",
            "outputs": outputs,
            "metrics": self._metrics(),
        }

    def _stage_ready_for_submission(self, stage: Dict[str, Any]) -> bool:
        deps = _depends_on(stage)
        if not deps:
            return True

        dep_type = stage.get("dep_type", "datasets")
        for dep_name in deps:
            parent_instances = self.works_by_stage.get(dep_name, [])
            if not parent_instances:
                return False
            if dep_type == "results":
                if any(parent.status == "failed" for parent in parent_instances):
                    return True
                if any(parent.status != "completed" for parent in parent_instances):
                    return False
        return True

    def _submit_stage(self, stage: Dict[str, Any]) -> None:
        for instance in self._instances_for_stage(stage):
            instance_key = str(instance.get("key") or instance.get("name") or "default")
            parent_results = self._parent_results_for_instance(stage, instance_key)
            parent_internal_id = self._parent_internal_id_for_instance(stage, instance_key)
            params = self._stage_params(stage, instance, parent_results, instance_key)
            dataset_payload = self._idds_dataset_payload(stage, instance, parent_internal_id, instance_key)
            self._add_dataset_params(params, dataset_payload)
            job_id = self._stage_job_id(stage["name"], instance_key)

            if self._is_local_stage(stage):
                self._run_local_instance(stage, instance_key, job_id, params)
                continue

            child_job = {
                "job_id": job_id,
                "name": f"{self.job_definition.get('name', self.logical_job_id)}.{stage['name']}.{instance_key}",
                "function": stage["python_callable"],
                "params": params,
                "payload": {
                    **self.payload,
                    **dataset_payload,
                    "design_point": self.payload.get("design_point", {}),
                    "stage_name": stage["name"],
                    "instance_key": instance_key,
                },
            }
            context_payload = self._stage_context_payload(job_id, stage["name"])
            if context_payload is not None:
                child_job["context_payload"] = context_payload

            submitted = self.scheduler._submit_callable_work(
                self.stage_name,
                child_job,
                self.working_dir,
            )
            work = submitted["work"]
            internal_id = submitted.get("internal_id") or _work_internal_id(work)
            self.works_by_stage[stage["name"]].append(
                PanDAMultiStageWork(
                    stage_name=stage["name"],
                    instance_key=instance_key,
                    job_id=job_id,
                    work=work,
                    tf_id=submitted["tf_id"],
                    job_key=submitted["work_name"],
                    internal_id=internal_id,
                    execution="panda",
                )
            )

    def _instances_for_stage(self, stage: Dict[str, Any]) -> List[Dict[str, Any]]:
        explicit = stage.get("jobs") or stage.get("children") or stage.get("instances")
        if explicit is not None:
            if not isinstance(explicit, list) or not explicit:
                raise ValueError(f"panda_multistage stage '{stage['name']}' jobs must be a non-empty list")
            return [dict(item) for item in explicit]

        deps = _depends_on(stage)
        dep_map = stage.get("dep_map", "one2one")
        if deps and dep_map == "one2one":
            parent_instances = self._single_parent_instances(stage)
            if len(parent_instances) > 1:
                return [{"key": parent.instance_key} for parent in parent_instances]
        if deps and dep_map == "all2one":
            return [{"key": "default"}]
        if deps and dep_map == "one2many":
            raise ValueError(
                f"panda_multistage stage '{stage['name']}' uses dep_map='one2many' and must define jobs"
            )
        return [{"key": "default"}]

    def _is_local_stage(self, stage: Dict[str, Any]) -> bool:
        runner = stage.get("runner") or stage.get("execution")
        job_type = stage.get("job_type")
        return runner in {"local", "joblib", "JobLibRunner"} or job_type in {"local", "joblib"}

    def _run_local_instance(
        self,
        stage: Dict[str, Any],
        instance_key: str,
        job_id: str,
        params: Dict[str, Any],
    ) -> None:
        stage_work = PanDAMultiStageWork(
            stage_name=stage["name"],
            instance_key=instance_key,
            job_id=job_id,
            work=None,
            tf_id=None,
            job_key=job_id,
            execution="local",
        )
        try:
            stage_work.result = stage["python_callable"](self.job_definition.get("job_context"), **params)
            stage_work.status = "completed"
        except Exception as exc:
            stage_work.status = "failed"
            stage_work.details = {"error": str(exc)}
        self.works_by_stage[stage["name"]].append(stage_work)

    def _single_parent_instances(self, stage: Dict[str, Any]) -> List[PanDAMultiStageWork]:
        deps = _depends_on(stage)
        if len(deps) != 1:
            raise ValueError(f"panda_multistage stage '{stage['name']}' must have exactly one parent")
        return self.works_by_stage.get(deps[0], [])

    def _parent_internal_id_for_instance(self, stage: Dict[str, Any], instance_key: str) -> Any:
        if stage.get("dep_type", "datasets") != "datasets" or not _depends_on(stage):
            return None

        dep_map = stage.get("dep_map", "one2one")
        parent_instances = self._single_parent_instances(stage)
        if not parent_instances:
            raise ValueError(f"panda_multistage stage '{stage['name']}' has no submitted parent instances")

        if dep_map == "all2one":
            ids = [parent.internal_id for parent in parent_instances if parent.internal_id]
            if len(ids) != len(parent_instances):
                raise ValueError(f"panda_multistage stage '{stage['name']}' expected all parent_internal_id values")
            return ids

        if dep_map == "one2many":
            if len(parent_instances) != 1:
                raise ValueError(f"panda_multistage stage '{stage['name']}' expected one parent for one2many")
            return parent_instances[0].internal_id

        if dep_map == "one2one":
            if len(parent_instances) == 1:
                return parent_instances[0].internal_id
            for parent in parent_instances:
                if parent.instance_key == instance_key:
                    return parent.internal_id
            raise ValueError(
                f"panda_multistage stage '{stage['name']}' expected one2one parent_internal_id "
                f"for instance key '{instance_key}'"
            )
        return None

    def _parent_results_for_instance(self, stage: Dict[str, Any], instance_key: str) -> Any:
        if stage.get("dep_type", "datasets") != "results" or not _depends_on(stage):
            return None

        dep_map = stage.get("dep_map", "one2one")
        parent_instances = self._single_parent_instances(stage)
        if dep_map == "all2one":
            return {parent.instance_key: parent.result for parent in parent_instances}
        if dep_map == "one2many":
            if len(parent_instances) != 1:
                raise ValueError(f"panda_multistage stage '{stage['name']}' expected one parent for one2many")
            return parent_instances[0].result
        if dep_map == "one2one":
            if len(parent_instances) == 1:
                return parent_instances[0].result
            for parent in parent_instances:
                if parent.instance_key == instance_key:
                    return parent.result
            raise ValueError(
                f"panda_multistage stage '{stage['name']}' expected one2one parent result "
                f"for instance key '{instance_key}'"
            )
        return None

    def _stage_params(
        self,
        stage: Dict[str, Any],
        instance: Dict[str, Any],
        parent_results: Any,
        instance_key: str,
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {}
        params.update(copy.deepcopy(stage.get("op_kwargs") or {}))
        params.update(copy.deepcopy(stage.get("params") or {}))
        params.update(copy.deepcopy(instance.get("op_kwargs") or {}))
        params.update(copy.deepcopy(instance.get("params") or {}))
        if parent_results is not None:
            parent_key = stage.get("parent_results_key") or stage.get("parent_result_parameter_name")
            params[parent_key or "parent_results"] = parent_results
        return params

    def _idds_dataset_payload(
        self,
        stage: Dict[str, Any],
        instance: Dict[str, Any],
        parent_internal_id: Any,
        instance_key: str,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {}
        for source in (stage, instance):
            for key in (
                "with_output_dataset",
                "output_file",
                "output_file_name",
                "output_dataset",
                "output_dataset_name",
                "num_events",
                "num_events_per_job",
                "with_input_datasets",
                "input_datasets",
            ):
                if key in source:
                    payload[key] = self._resolve_dataset_template(source[key], stage["name"], instance_key)
        if parent_internal_id is not None:
            payload["parent_internal_id"] = parent_internal_id
        return payload

    def _resolve_dataset_template(self, value: Any, stage_name: str, instance_key: str) -> Any:
        if isinstance(value, str):
            tokens = self._dataset_template_tokens(stage_name, instance_key)
            resolved = value
            for token, replacement in tokens.items():
                resolved = resolved.replace(f"{{{token}}}", replacement)
            return (
                resolved.replace("#job_id", tokens["job_id"])
                .replace("#evaluation_id", tokens["evaluation_id"])
                .replace("#panda_scope", tokens["panda_scope"])
                .replace("#panda_username", tokens["panda_username"])
            )
        if isinstance(value, dict):
            return {
                key: self._resolve_dataset_template(item, stage_name, instance_key)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [self._resolve_dataset_template(item, stage_name, instance_key) for item in value]
        return value

    def _dataset_template_tokens(self, stage_name: str, instance_key: str) -> Dict[str, str]:
        context = self.job_definition.get("job_context")
        panda_scope = self._panda_user_scope()
        panda_username = panda_scope.split(".", 1)[1] if panda_scope.startswith("user.") else panda_scope
        workflow_id = getattr(context, "workflow_id", None) or getattr(self.scheduler, "workflow_id", None) or "pandaidds"
        trial_index = (
            self.payload.get("trial_index")
            or getattr(context, "trial_index", None)
            or self.payload.get("design_point", {}).get("trial_index")
            or self.payload.get("design_point", {}).get("trial_id")
            or "trial"
        )
        return {
            "submission_id": self._rucio_safe_token(getattr(self.scheduler, "submission_id", "submission")),
            "workflow_id": self._rucio_safe_token(workflow_id),
            "stage_id": self._rucio_safe_token(stage_name),
            "job_id": self._rucio_safe_token(instance_key),
            "step_name": self._rucio_safe_token(stage_name),
            "child_key": self._rucio_safe_token(instance_key),
            "trial_index": self._rucio_safe_token(trial_index),
            "evaluation_id": self._evaluation_id(),
            "panda_scope": panda_scope,
            "panda_username": panda_username,
        }

    def _evaluation_id(self) -> str:
        context = self.job_definition.get("job_context")
        context_payload = {
            "submission_id": getattr(self.scheduler, "submission_id", None),
            "workflow_id": getattr(context, "workflow_id", None),
            "job_id": self.logical_job_id,
            "design_point": self.payload.get("design_point", {}),
        }
        encoded = json.dumps(context_payload, default=str, sort_keys=True)
        return hashlib.sha1(encoded.encode("utf-8")).hexdigest()[:12]

    def _panda_user_scope(self) -> str:
        name = str(getattr(self.scheduler.config, "name", "") or "")
        parts = name.split(".")
        if len(parts) >= 2 and parts[0] == "user" and parts[1]:
            return f"user.{self._rucio_safe_token(parts[1])}"
        return "user.aid2e"

    def _rucio_safe_token(self, value: Any) -> str:
        token = re.sub(r"[^A-Za-z0-9._-]", "_", str(value))
        token = token.strip("._-")
        return token or "aid2e"

    def _add_dataset_params(self, params: Dict[str, Any], dataset_payload: Dict[str, Any]) -> None:
        for key in (
            "output_file",
            "output_file_name",
            "output_dataset",
            "output_dataset_name",
            "num_events",
            "num_events_per_job",
            "input_datasets",
            "parent_internal_id",
        ):
            if key in dataset_payload and key not in params:
                params[key] = dataset_payload[key]

    def _stage_context_payload(self, job_id: str, logical_stage_name: str) -> Optional[Dict[str, Any]]:
        parent_context = self.job_definition.get("job_context")
        if parent_context is None:
            return None
        return {
            "task_id": job_id,
            "job_id": job_id,
            "stage_id": logical_stage_name,
            "workflow_id": getattr(parent_context, "workflow_id", "pandaidds"),
            "design_point": dict(getattr(parent_context, "design_point", {}) or {}),
            "xcom": dict(getattr(parent_context, "xcom", {}) or {}),
            "artifacts": dict(getattr(parent_context, "artifacts", {}) or {}),
            "logs": list(getattr(parent_context, "logs", []) or []),
            "execution_dir": getattr(parent_context, "execution_dir", self.working_dir),
            "output_dir": getattr(parent_context, "output_dir", self.working_dir),
        }

    def _metrics(self) -> Dict[str, Any]:
        stage_metrics = []
        for stage_work in self._all_stage_works():
            metric = {
                "stage": stage_work.stage_name,
                "instance_key": stage_work.instance_key,
                "job_id": stage_work.job_id,
                "transform_id": stage_work.tf_id,
                "internal_id": stage_work.internal_id,
                "status": stage_work.status,
                "execution": stage_work.execution,
            }
            if stage_work.details is not None:
                metric["details"] = stage_work.details
            stage_metrics.append(metric)
        return {"panda_multistage_stages": stage_metrics}

    def _has_running_stages(self) -> bool:
        return any(stage.status == "running" for stage in self._all_stage_works())

    def _poll_running_stages(self) -> bool:
        made_progress = False
        for stage_work in self._all_stage_works():
            if stage_work.status != "running":
                continue
            try:
                stage_work.work.init_async_result()
            except Exception:
                pass
            status = stage_work.work.get_status()
            if stage_work.work.is_finished(status):
                self._complete_stage(stage_work)
                made_progress = True
            elif stage_work.work.is_failed(status):
                stage_work.status = "failed"
                made_progress = True
        return made_progress

    def _complete_stage(self, stage_work: PanDAMultiStageWork) -> None:
        results = None
        details = None
        try:
            ret = stage_work.work.get_results()
            try:
                results, details = ret.get_result(
                    name=stage_work.work.name,
                    key=stage_work.job_key,
                    verbose=True,
                    with_details=True,
                )
            except Exception:
                results = ret
        except Exception as exc:
            stage_work.status = "failed"
            stage_work.details = {"error": str(exc)}
            return
        stage_work.result = results
        stage_work.details = details
        stage_work.internal_id = _work_internal_id(stage_work.work)
        stage_work.status = "completed"

    def _final_results(self) -> Any:
        final_instances = self.works_by_stage[self.spec.final_stage]
        if len(final_instances) == 1:
            return final_instances[0].result
        return {stage.instance_key: stage.result for stage in final_instances}

    def _final_details(self) -> Any:
        final_instances = self.works_by_stage[self.spec.final_stage]
        if len(final_instances) == 1:
            return final_instances[0].details
        details = {stage.instance_key: stage.details for stage in final_instances if stage.details is not None}
        return details or None

    def _all_results(self) -> Dict[str, Any]:
        results = {}
        for stage_name, instances in self.works_by_stage.items():
            if len(instances) == 1:
                results[stage_name] = instances[0].result
            else:
                results[stage_name] = {stage.instance_key: stage.result for stage in instances}
        return results

    def _all_stage_works(self) -> List[PanDAMultiStageWork]:
        works: List[PanDAMultiStageWork] = []
        for stage_works in self.works_by_stage.values():
            works.extend(stage_works)
        return works

    def _stage_job_id(self, stage_name: str, instance_key: str) -> str:
        if instance_key == "default":
            return f"{self.logical_job_id}:{stage_name}"
        return f"{self.logical_job_id}:{stage_name}:{instance_key}"


def _depends_on(stage: Dict[str, Any]) -> List[str]:
    depends = stage.get("depends_on") or []
    if isinstance(depends, str):
        return [depends]
    if isinstance(depends, dict):
        stage_name = depends.get("stage") or depends.get("parent")
        return [stage_name] if stage_name else []
    return list(depends)
