"""AID2E-owned PanDA/iDDS multi-step callable coordinator.

This module adapts the scheduler_epic multi-step job pattern to AID2E's
scheduler interface without importing or depending on scheduler_epic. The first
milestone is intentionally narrow: Python callable child works, result-based
step dependencies, explicit child fan-out, and final result aggregation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set
import copy
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
    status: str = "running"
    result: Any = None
    details: Any = None


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
            raise ValueError(
                "panda_multistep payload must define a non-empty 'steps' list "
                "or scheduler_epic-style 'objective_funcs' mapping"
            )

        deps = payload.get("deps") or {}
        by_name: Dict[str, Dict[str, Any]] = {}
        for index, raw_step in enumerate(steps):
            if not isinstance(raw_step, dict):
                raise ValueError(f"panda_multistep step at index {index} must be a mapping")
            step = _normalize_step(dict(raw_step), deps)
            name = step.get("name")
            if not name:
                raise ValueError(f"panda_multistep step at index {index} is missing 'name'")
            if name in by_name:
                raise ValueError(f"Duplicate panda_multistep step name: {name}")
            if step.get("python_callable") is None:
                raise ValueError(f"panda_multistep step '{name}' is missing 'python_callable'")
            dep_type = step.get("dep_type", "results")
            if dep_type != "results":
                raise ValueError(
                    f"panda_multistep step '{name}' uses dep_type={dep_type!r}; only 'results' is supported"
                )
            dep_map = step.get("dep_map", "one2one")
            if dep_map not in {"one2one", "all2one"}:
                raise ValueError(
                    f"panda_multistep step '{name}' uses dep_map={dep_map!r}; expected 'one2one' or 'all2one'"
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
        parent_results = self._parent_results_for_step(step)
        for child in _step_children(step):
            child_key = str(child.get("key") or child.get("name") or "default")
            child_job_id = self._child_job_id(step_name, child_key)
            params = self._step_params(step, child, parent_results, child_key)
            child_job = {
                "job_id": child_job_id,
                "name": f"{self.job_definition.get('name', self.logical_job_id)}.{step_name}.{child_key}",
                "function": step["python_callable"],
                "params": params,
                "payload": {
                    **self.payload,
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
                )
            )

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
        child.status = "completed"

    def _mark_completed_steps(self) -> None:
        for step in self.spec.steps:
            step_name = step["name"]
            children = self.children_by_step[step_name]
            if children and all(child.status == "completed" for child in children):
                self.completed_steps.add(step_name)

    def _parent_results_for_step(self, step: Dict[str, Any]) -> Any:
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
            return {child.child_key: child.result for child in children}
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
                "status": child.status,
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
        return [child for child in self._all_children() if child.status == "running"]

    def _all_children(self) -> List[PanDAMultiStepChildJob]:
        children: List[PanDAMultiStepChildJob] = []
        for step_children in self.children_by_step.values():
            children.extend(step_children)
        return children

    def _child_job_id(self, step_name: str, child_key: str) -> str:
        if child_key == "default":
            return f"{self.logical_job_id}:{step_name}"
        return f"{self.logical_job_id}:{step_name}:{child_key}"



def _payload_steps(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    steps = payload.get("steps")
    if steps is not None:
        return list(steps)

    objective_funcs = payload.get("objective_funcs")
    if not isinstance(objective_funcs, dict):
        return []

    converted = []
    for step_name, raw_step in objective_funcs.items():
        if not isinstance(raw_step, dict):
            raise ValueError(f"panda_multistep objective_funcs step '{step_name}' must be a mapping")
        step = dict(raw_step)
        step.setdefault("name", step_name)
        if "func" in step and "python_callable" not in step:
            step["python_callable"] = step["func"]
        converted.append(step)
    return converted


def _normalize_step(step: Dict[str, Any], deps: Dict[str, Any]) -> Dict[str, Any]:
    if "func" in step and "python_callable" not in step:
        step["python_callable"] = step["func"]

    name = step.get("name")
    dep_spec = deps.get(name) if isinstance(deps, dict) else None
    if isinstance(dep_spec, dict):
        parent = dep_spec.get("parent")
        if parent is not None and not step.get("depends_on"):
            step["depends_on"] = parent if isinstance(parent, list) else [parent]
        for key in ("dep_type", "dep_map", "parent_result_parameter_name"):
            if key in dep_spec and key not in step:
                step[key] = dep_spec[key]

    return step

def _depends_on(step: Dict[str, Any]) -> List[str]:
    depends = step.get("depends_on") or step.get("deps") or []
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
