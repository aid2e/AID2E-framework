"""AID2E-owned PanDA/iDDS multi-step callable coordinator.

The public payload surface intentionally matches AID2E's single-step PanDA
callable style: workflow jobs use ``payload.evaluator_type`` and steps use
importable ``python_callable`` entries.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set
import copy
import hashlib
import json
import re
import time as _time



@dataclass
class PanDAMultiStepChildJob:
    """One submitted child work inside a logical multi-step job."""

    step_name: str
    child_key: str
    job_id: str
    work: Any
    tf_id: Any
    job_key: str
    internal_id: Optional[str] = None
    status: str = "running"
    result: Any = None
    details: Any = None
    monitor_results: bool = True


@dataclass
class PanDAMultiStepFunctionSpec:
    """Validated AID2E-native multi-step function payload."""

    steps: List[Dict[str, Any]]
    final_step: str
    by_name: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    @classmethod
    def from_payload(cls, payload: Dict[str, Any]) -> "PanDAMultiStepFunctionSpec":
        steps = _payload_steps(payload)
        if not isinstance(steps, list) or not steps:
            raise ValueError("panda_multistep payload must define a non-empty 'steps' list")

        by_name: Dict[str, Dict[str, Any]] = {}
        for index, raw_step in enumerate(steps):
            if not isinstance(raw_step, dict):
                raise ValueError(f"panda_multistep step at index {index} must be a mapping")
            step = _normalize_step(dict(raw_step))
            name = step.get("name")
            if not name:
                raise ValueError(f"panda_multistep step at index {index} is missing 'name'")
            if name in by_name:
                raise ValueError(f"Duplicate panda_multistep step name: {name}")
            if step.get("python_callable") is None:
                raise ValueError(f"panda_multistep step '{name}' is missing 'python_callable'")
            dep_type = step.get("dep_type", "results")
            if dep_type not in {"results", "datasets"}:
                raise ValueError(
                    f"panda_multistep step '{name}' uses dep_type={dep_type!r}; expected 'results' or 'datasets'"
                )
            dep_map = step.get("dep_map", "one2one")
            if dep_map not in {"one2one", "all2one"}:
                raise ValueError(
                    f"panda_multistep step '{name}' uses dep_map={dep_map!r}; expected 'one2one' or 'all2one'"
                )
            if dep_type == "datasets" and dep_map != "one2one":
                raise ValueError(
                    f"panda_multistep step '{name}' uses dep_type='datasets'; only dep_map='one2one' is supported"
                )
            by_name[name] = step

        for step in by_name.values():
            for dep_name in _depends_on(step):
                if dep_name not in by_name:
                    raise ValueError(
                        f"panda_multistep step '{step['name']}' depends on unknown step '{dep_name}'"
                    )

        final_steps = [
            step["name"]
            for step in by_name.values()
            if step.get("produces_objective") or step.get("final")
        ]
        explicit_final = payload.get("final") or payload.get("final_step")
        if explicit_final:
            if explicit_final not in by_name:
                raise ValueError(f"panda_multistep final step '{explicit_final}' is not defined")
            final_steps.append(explicit_final)

        unique_final_steps = list(dict.fromkeys(final_steps))
        if len(unique_final_steps) > 1:
            raise ValueError(
                "panda_multistep payload must identify exactly one final objective-producing step"
            )
        final_step = unique_final_steps[0] if unique_final_steps else steps[-1]["name"]
        return cls(steps=list(by_name.values()), final_step=final_step, by_name=by_name)


class PanDAMultiStepJob:
    """Coordinate one logical AID2E multi-step job using PanDA/iDDS child works."""

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
        self.logical_job_id = job_definition.get("job_id") or job_definition.get("name") or "panda_multistep"
        self.payload = dict(job_definition.get("payload") or {})
        self.spec = PanDAMultiStepFunctionSpec.from_payload(self.payload)
        self.children_by_step: Dict[str, List[PanDAMultiStepChildJob]] = {
            step["name"]: [] for step in self.spec.steps
        }
        self.submitted_steps: Set[str] = set()
        self.completed_steps: Set[str] = set()
        self.failed_child: Optional[PanDAMultiStepChildJob] = None

    def run(self) -> Dict[str, Any]:
        """Run child works until the final step has completed or a child fails."""
        while not self._is_complete():
            made_progress = self._submit_ready_steps()
            made_progress = self._poll_running_children() or made_progress
            if self.failed_child is not None:
                self._cancel_running_children()
                return self._failed_result()
            if not made_progress and not self._has_running_children():
                return {
                    "status": "failed",
                    "return_code": -1,
                    "stdout": "",
                    "stderr": "panda_multistep made no progress; dependency graph may be invalid",
                    "outputs": {},
                    "metrics": self._metrics(),
                }
            if not made_progress:
                _time.sleep(self.poll_interval)

        final_results = self._final_results()
        outputs = self.scheduler._normalize_function_outputs(final_results)
        context = self.job_definition.get("job_context")
        if context is not None and hasattr(context, "xcom_push"):
            try:
                if isinstance(final_results, dict):
                    context.xcom_push("objectives", final_results)
                context.xcom_push("panda_multistep_results", self._all_results())
            except Exception:
                self.scheduler.logger.debug(
                    "Failed to push panda_multistep results to job context", exc_info=True
                )
        return {
            "status": "completed",
            "return_code": 0,
            "stdout": "",
            "stderr": "",
            "outputs": outputs,
            "metrics": self._metrics(),
        }

    def _submit_ready_steps(self) -> bool:
        submitted_any = False
        for step in self.spec.steps:
            step_name = step["name"]
            if step_name in self.submitted_steps:
                continue
            if all(dep_name in self.completed_steps for dep_name in _depends_on(step)):
                self._submit_step(step)
                self.submitted_steps.add(step_name)
                submitted_any = True
        return submitted_any

    def _submit_step(self, step: Dict[str, Any]) -> None:
        step_name = step["name"]
        monitor_results = bool(step.get("return_func_results", True))
        for child in self._children_for_step(step):
            child_key = str(child.get("key") or child.get("name") or "default")
            child_job_id = self._child_job_id(step_name, child_key)
            parent_results = self._parent_results_for_child(step, child_key)
            parent_internal_id = self._parent_internal_id_for_child(step, child_key)
            params = self._step_params(step, child, parent_results, child_key)
            dataset_payload = self._idds_dataset_payload(step, child, parent_internal_id, child_key)
            self._add_dataset_params(params, dataset_payload)
            if self._is_local_step(step):
                self._run_local_child(step, child_key, child_job_id, params)
                continue

            child_job = {
                "job_id": child_job_id,
                "name": f"{self.job_definition.get('name', self.logical_job_id)}.{step_name}.{child_key}",
                "function": step["python_callable"],
                "params": params,
                "payload": {
                    **self.payload,
                    **dataset_payload,
                    "design_point": self.payload.get("design_point", {}),
                    "step_name": step_name,
                    "child_key": child_key,
                },
            }
            context_payload = self._child_context_payload(child_job_id)
            if context_payload is not None:
                child_job["context_payload"] = context_payload
            submitted = self.scheduler._submit_callable_work(
                self.stage_name,
                child_job,
                self.working_dir,
            )
            self.children_by_step[step_name].append(
                PanDAMultiStepChildJob(
                    step_name=step_name,
                    child_key=child_key,
                    job_id=child_job_id,
                    work=submitted["work"],
                    tf_id=submitted["tf_id"],
                    job_key=submitted["work_name"],
                    internal_id=submitted.get("internal_id"),
                    status="running" if monitor_results else "submitted",
                    monitor_results=monitor_results,
                )
            )
        if not monitor_results:
            self.completed_steps.add(step_name)

    def _run_local_child(
        self,
        step: Dict[str, Any],
        child_key: str,
        child_job_id: str,
        params: Dict[str, Any],
    ) -> None:
        child = PanDAMultiStepChildJob(
            step_name=step["name"],
            child_key=child_key,
            job_id=child_job_id,
            work=None,
            tf_id=None,
            job_key=child_job_id,
        )
        try:
            child.result = step["python_callable"](self.job_definition.get("job_context"), **params)
            child.status = "completed"
        except Exception as exc:
            child.status = "failed"
            child.details = {"error": str(exc)}
            self.failed_child = child
        self.children_by_step[step["name"]].append(child)

    def _children_for_step(self, step: Dict[str, Any]) -> List[Dict[str, Any]]:
        explicit_children = step.get("children") or step.get("chunks")
        if explicit_children is not None:
            return _step_children(step)

        deps = _depends_on(step)
        if step.get("dep_map", "one2one") == "one2one" and len(deps) == 1:
            parent_children = self.children_by_step[deps[0]]
            if parent_children:
                return [{"key": child.child_key} for child in parent_children]

        return [{"key": "default"}]

    def _is_local_step(self, step: Dict[str, Any]) -> bool:
        runner = step.get("runner") or step.get("execution")
        job_type = step.get("job_type")
        return runner in {"local", "joblib", "JobLibRunner"} or job_type in {"local", "joblib"}

    def _parent_internal_id_for_child(self, step: Dict[str, Any], child_key: str) -> Optional[str]:
        if step.get("dep_type", "results") != "datasets":
            return None
        deps = _depends_on(step)
        if len(deps) != 1:
            raise ValueError(f"panda_multistep dataset step '{step['name']}' must have exactly one parent")
        parent_children = self.children_by_step[deps[0]]
        for child in parent_children:
            if child.child_key == child_key:
                return child.internal_id
        raise ValueError(
            f"panda_multistep dataset step '{step['name']}' expected parent internal id "
            f"for child key '{child_key}'"
        )

    def _idds_dataset_payload(
        self,
        step: Dict[str, Any],
        child: Dict[str, Any],
        parent_internal_id: Optional[str],
        child_key: str,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {}
        for source in (step, child):
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
                    payload[key] = self._resolve_dataset_template(source[key], child_key)
        if parent_internal_id is not None:
            payload["parent_internal_id"] = parent_internal_id
        return payload

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

    def _resolve_dataset_template(self, value: Any, child_key: str) -> Any:
        if isinstance(value, str):
            safe_child_key = self._rucio_safe_token(child_key)
            panda_scope = self._panda_user_scope()
            panda_username = panda_scope.split(".", 1)[1] if panda_scope.startswith("user.") else panda_scope
            evaluation_id = self._evaluation_id()
            return (
                value.replace("#job_id", safe_child_key)
                .replace("{child_key}", safe_child_key)
                .replace("#evaluation_id", evaluation_id)
                .replace("{evaluation_id}", evaluation_id)
                .replace("#panda_scope", panda_scope)
                .replace("{panda_scope}", panda_scope)
                .replace("#panda_username", panda_username)
                .replace("{panda_username}", panda_username)
            )
        if isinstance(value, dict):
            return {
                key: self._resolve_dataset_template(item, child_key)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [self._resolve_dataset_template(item, child_key) for item in value]
        return value

    def _evaluation_id(self) -> str:
        context = self.job_definition.get("job_context")
        context_payload = {
            "submission_id": getattr(self.scheduler, "submission_id", None),
            "workflow_id": getattr(context, "workflow_id", None),
            "task_id": getattr(context, "task_id", None),
            "job_id": getattr(context, "job_id", self.logical_job_id),
            "execution_dir": getattr(context, "execution_dir", None),
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

    def _rucio_safe_token(self, value: str) -> str:
        token = re.sub(r"[^A-Za-z0-9._-]", "_", str(value))
        token = token.strip("._-")
        return token or "child"

    def _step_params(
        self,
        step: Dict[str, Any],
        child: Dict[str, Any],
        parent_results: Any,
        child_key: str,
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {}
        params.update(copy.deepcopy(step.get("op_kwargs") or {}))
        params.update(copy.deepcopy(step.get("params") or {}))
        params.update(copy.deepcopy(child.get("op_kwargs") or {}))
        params.update(copy.deepcopy(child.get("params") or {}))
        params.setdefault("design_point", self.payload.get("design_point", {}))
        params.setdefault("step_name", step["name"])
        params.setdefault("child_key", child_key)
        if parent_results is not None:
            parent_key = step.get("parent_results_key") or step.get("parent_result_parameter_name")
            params[parent_key or "parent_results"] = parent_results
        return params

    def _child_context_payload(self, child_job_id: str) -> Optional[Dict[str, Any]]:
        parent_context = self.job_definition.get("job_context")
        if parent_context is None:
            return None
        return {
            "task_id": child_job_id,
            "job_id": child_job_id,
            "stage_id": getattr(parent_context, "stage_id", self.stage_name),
            "workflow_id": getattr(parent_context, "workflow_id", "pandaidds"),
            "design_point": dict(getattr(parent_context, "design_point", {}) or {}),
            "xcom": dict(getattr(parent_context, "xcom", {}) or {}),
            "artifacts": dict(getattr(parent_context, "artifacts", {}) or {}),
            "logs": list(getattr(parent_context, "logs", []) or []),
            "execution_dir": getattr(parent_context, "execution_dir", self.working_dir),
            "output_dir": getattr(parent_context, "output_dir", self.working_dir),
        }

    def _poll_running_children(self) -> bool:
        made_progress = False
        for child in self._running_children():
            try:
                child.work.init_async_result()
            except Exception:
                pass
            status = child.work.get_status()
            if child.work.is_finished(status):
                self._complete_child(child)
                made_progress = True
            elif child.work.is_failed(status):
                child.status = "failed"
                self.failed_child = child
                made_progress = True
        self._mark_completed_steps()
        return made_progress

    def _complete_child(self, child: PanDAMultiStepChildJob) -> None:
        results = None
        details = None
        try:
            ret = child.work.get_results()
            try:
                results, details = ret.get_result(
                    name=child.work.name,
                    key=child.job_key,
                    verbose=True,
                    with_details=True,
                )
            except Exception:
                results = ret
        except Exception as exc:
            child.status = "failed"
            child.details = {"error": str(exc)}
            self.failed_child = child
            return
        child.result = results
        child.details = details
        child.internal_id = _work_internal_id(child.work)
        child.status = "completed"

    def _mark_completed_steps(self) -> None:
        for step in self.spec.steps:
            step_name = step["name"]
            if step_name in self.completed_steps:
                continue
            children = self.children_by_step[step_name]
            if children and all(child.status == "completed" for child in children):
                self.completed_steps.add(step_name)

    def _parent_results_for_child(self, step: Dict[str, Any], child_key: str) -> Any:
        deps = _depends_on(step)
        if not deps:
            return None
        dep_map = step.get("dep_map", "one2one")
        if dep_map == "all2one":
            if len(deps) == 1:
                return {
                    child.child_key: child.result
                    for child in self.children_by_step[deps[0]]
                }
            return {
                dep_name: {
                    child.child_key: child.result
                    for child in self.children_by_step[dep_name]
                }
                for dep_name in deps
            }

        if len(deps) == 1:
            children = self.children_by_step[deps[0]]
            if len(children) == 1:
                return children[0].result
            for child in children:
                if child.child_key == child_key:
                    return child.result
            raise ValueError(
                f"panda_multistep step '{step['name']}' expected one2one parent result "
                f"for child key '{child_key}'"
            )
        return {
            dep_name: self._single_or_keyed_results(dep_name)
            for dep_name in deps
        }

    def _single_or_keyed_results(self, step_name: str) -> Any:
        children = self.children_by_step[step_name]
        if len(children) == 1:
            return children[0].result
        return {child.child_key: child.result for child in children}

    def _final_results(self) -> Any:
        return self._single_or_keyed_results(self.spec.final_step)

    def _all_results(self) -> Dict[str, Any]:
        return {
            step_name: self._single_or_keyed_results(step_name)
            for step_name in self.children_by_step
            if self.children_by_step[step_name]
        }

    def _metrics(self) -> Dict[str, Any]:
        child_metrics = []
        for child in self._all_children():
            metric = {
                "step": child.step_name,
                "child_key": child.child_key,
                "job_id": child.job_id,
                "transform_id": child.tf_id,
                "internal_id": child.internal_id,
                "status": child.status,
                "execution": "local" if child.work is None else "panda",
            }
            if child.details is not None:
                metric["details"] = child.details
            child_metrics.append(metric)
        return {"panda_multistep_children": child_metrics}

    def _failed_result(self) -> Dict[str, Any]:
        child = self.failed_child
        stderr = "panda_multistep child failed"
        if child is not None:
            stderr = f"panda_multistep child {child.job_id} failed"
        return {
            "status": "failed",
            "return_code": -1,
            "stdout": "",
            "stderr": stderr,
            "outputs": {},
            "metrics": self._metrics(),
        }

    def _cancel_running_children(self) -> None:
        for child in self._running_children():
            try:
                if child.work and not child.work.is_terminated():
                    child.work.cancel()
                    child.status = "cancelled"
            except Exception:
                self.scheduler.logger.debug(
                    "Failed to cancel panda_multistep child %s", child.job_id, exc_info=True
                )

    def _is_complete(self) -> bool:
        return self.spec.final_step in self.completed_steps

    def _has_running_children(self) -> bool:
        return any(True for _ in self._running_children())

    def _running_children(self) -> List[PanDAMultiStepChildJob]:
        return [
            child
            for child in self._all_children()
            if child.status == "running" and child.monitor_results
        ]

    def _all_children(self) -> List[PanDAMultiStepChildJob]:
        children: List[PanDAMultiStepChildJob] = []
        for step_children in self.children_by_step.values():
            children.extend(step_children)
        return children

    def _child_job_id(self, step_name: str, child_key: str) -> str:
        if child_key == "default":
            return f"{self.logical_job_id}:{step_name}"
        return f"{self.logical_job_id}:{step_name}:{child_key}"




def _work_internal_id(work: Any) -> Optional[str]:
    if work is None:
        return None
    value = getattr(work, "internal_id", None)
    if value is not None:
        return str(value)
    getter = getattr(work, "get_internal_id", None)
    if callable(getter):
        try:
            value = getter()
        except Exception:
            return None
        if value is not None:
            return str(value)
    return None

def _payload_steps(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    steps = payload.get("steps")
    if steps is None:
        return []
    return list(steps)


def _normalize_step(step: Dict[str, Any]) -> Dict[str, Any]:
    return step


def _depends_on(step: Dict[str, Any]) -> List[str]:
    depends = step.get("depends_on") or []
    if isinstance(depends, str):
        return [depends]
    return list(depends)


def _step_children(step: Dict[str, Any]) -> List[Dict[str, Any]]:
    children = step.get("children") or step.get("chunks")
    if children is None:
        return [{"key": "default"}]
    if not isinstance(children, list) or not children:
        raise ValueError(f"panda_multistep step '{step['name']}' children must be a non-empty list")
    return [dict(child) for child in children]
