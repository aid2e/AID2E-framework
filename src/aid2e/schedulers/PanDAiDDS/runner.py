
"""PanDA / iDDS-backed scheduler runner.

This runner integrates with the iDDS workflow API when available to submit
function-based work to PanDA. For simpler command-based jobs it falls back
to local execution (previously done with joblib) so the scheduler remains
usable without iDDS installed.

The implementation favors clarity and conservative behavior:
- If a job dict contains a "function" key, we try to submit it via iDDS.
- Otherwise we execute the provided "command" locally and collect outputs.

This file intentionally keeps iDDS imports inside functions so the module
can be imported even when iDDS is not installed.
"""

import json
import logging
import os
import subprocess
import datetime
import importlib
from typing import Dict, Any, List, Optional, Tuple

import threading
import uuid
from time import time
import time as _time

from aid2e.schedulers.base import BaseScheduler, JobStatus, StageExecutionResult
from aid2e.schedulers.PanDAiDDS.config import PanDAiDDSRunnerConfig
from aid2e.utilities.workflows.execution_engine import JobContext


def _callable_reference(func: Any) -> str:
	"""Return an importable ``module:qualname`` reference for a Python callable."""
	module = getattr(func, "__module__", None)
	qualname = getattr(func, "__qualname__", None)
	if not module or not qualname:
		raise RuntimeError(f"Cannot submit non-importable callable to PanDA/iDDS: {func!r}")
	if module == "__main__" or "<locals>" in qualname:
		raise RuntimeError(
			f"Function '{getattr(func, '__name__', func)}' must be defined in an "
			"importable module for remote PanDA/iDDS execution."
		)
	return f"{module}:{qualname}"


def _resolve_callable_reference(callable_ref: str) -> Any:
	"""Resolve a ``module:qualname`` reference without invoking scheduler code."""
	module_name, qualname = callable_ref.split(":", 1)
	target = importlib.import_module(module_name)
	for attr in qualname.split("."):
		target = getattr(target, attr)
	return target


def _remote_python_callable_entrypoint(
	callable_ref: str,
	context_payload: Dict[str, Any],
	op_kwargs: Optional[Dict[str, Any]] = None,
) -> Any:
	"""Worker-side PanDA entrypoint that only runs the requested Python callable.

	The client submits this adapter to iDDS/PanDA instead of submitting the
	user callable and local JobContext directly. The remote worker reconstructs
	a minimal JobContext, imports the configured evaluator, executes it, and
	returns the evaluator result. It does not construct PanDA/iDDS scheduler
	objects or submit additional PanDA work.
	"""
	func = _resolve_callable_reference(callable_ref)
	context = JobContext(**context_payload)
	return func(context, **(op_kwargs or {}))


class PanDAiDDSScheduler(BaseScheduler):
	"""Scheduler that prefers PanDA/iDDS for function-style work.

	Notes:
	- This is a pragmatic adapter. To enable full iDDS capabilities you must
	  install the `idds` package and ensure any function objects submitted are
	  importable in the remote environment used by PanDA.
	"""

	def __init__(self, config: Optional[PanDAiDDSRunnerConfig] = None) -> None:
		super().__init__(config)
		self.config = config or PanDAiDDSRunnerConfig()
		self.logger = logging.getLogger("PanDAiDDSScheduler")

		# in-memory bookkeeping organized by stage_name
		self.running_jobs: Dict[str, Dict[str, Any]] = {}
		self.running_stages: Dict[str, Dict[str, Any]] = {}
		# running_funcs: stage_name -> job_id -> func_name -> {work, tf_id, status, results}
		self.running_funcs: Dict[str, Dict[str, Any]] = {}
		# jobs: stage_name -> job_id -> tf_id
		self.jobs: Dict[str, Dict[str, Any]] = {}
		self.num_checks: int = 0
		self.workflow = None
		self.workflow_id = None
		self.lock = threading.Lock()
		# Cache workflows per stage_name to ensure one workflow per stage
		self.stage_workflows: Dict[str, Any] = {}
		self.completed_jobs: Dict[str, Dict[str, Any]] = {}


	# --- Run stage (synchronous convenience wrapper) -----------------------
	def run_stage(
		self,
		stage_name: str,
		job_definitions: List[Dict[str, Any]],
		parallelism_policy: Optional[Dict[str, Any]] = None,
		working_dir: Optional[str] = None,
	) -> StageExecutionResult:
		"""Execute a stage: prefer iDDS submissions for function-jobs, fallback to local commands.

		This method runs synchronously: it will submit all jobs first, then poll
		until all jobs complete, and finally return a StageExecutionResult.
		"""
		policy = parallelism_policy or {}
		poll_interval = policy.get("poll_interval", 5)

		self.logger.info("Running stage '%s' with %d jobs", stage_name, len(job_definitions))

		job_statuses: List[JobStatus] = []
		all_artifacts: Dict[str, Any] = {}
		all_success = True

        # Map job_id to job_def for easy lookup during polling
		job_id_to_job_def: Dict[str, Dict[str, Any]] = {}

		# Create a simple stage id for bookkeeping
		stage_id = uuid.uuid4().hex
		self.running_stages[stage_id] = {"status": "running", "jobs": [], "result": None}

		# Phase 1: Submit all jobs
		submitted_job_ids = []
		local_job_results = {}

		for index, job_def in enumerate(job_definitions):
			job_name = job_def.get("name", f"job_{index}")
			job_id = job_def.get("job_id") or f"{stage_name}_{job_name}_{index}"
			job_id_to_job_def[job_id] = job_def

			# If the job provides a function object, try to submit to iDDS.
			if job_def.get("function") is not None:
				try:
					self.logger.info("Submitting function job %s to iDDS/PanDA", job_id)
					# normalize job to the shape expected by submit_job
					job_dict = job_def.copy()
					job_dict.setdefault("job_id", job_id)
					self.submit_job(stage_name, job_dict, working_dir)
					submitted_job_ids.append(job_id)
				except RuntimeError as exc:
					self.logger.exception("Failed to submit function job %s: %s", job_id, exc)
					# mark as failed immediately
					local_job_results[job_id] = {
						"status": "failed",
						"return_code": -1,
						"stdout": "",
						"stderr": str(exc),
						"outputs": {},
					}
					all_success = False
			else:
				# Fallback: execute the command locally
				self.logger.info("Executing local job %s", job_id)
				result = self._execute_job(job_def, working_dir)
				local_job_results[job_id] = result

		# Phase 2: Poll all submitted iDDS jobs until they finish
		poll_count = 0
		while submitted_job_ids:
			_time.sleep(poll_interval)
			poll_count += 1
			# Only log polling message every 10th iteration to reduce noise
			if poll_count % 60 == 1:
				self.logger.info("Polling %d remaining jobs (poll #%d)", len(submitted_job_ids), poll_count)
			
			# check status of all remaining jobs
			for job_id in list(submitted_job_ids):
				try:
					# Find job_def for this job_id to extract job_context
					job_def = job_id_to_job_def.get(job_id, None)
					job_context = job_def.get("job_context") if job_def else None
					self.check_single_job_status({"job_id": job_id, "stage_name": stage_name}, job_context)
				except Exception as exc:
					# if job still running, check_single_job_status may raise until finished
					self.logger.debug("Job %s not finished yet: %s", job_id, exc)

				# if running_funcs no longer contains job_id, it's done or failed
				stage_funcs = self.running_funcs.get(stage_name, {})
				if job_id not in stage_funcs:
					self.logger.info("Job %s finished", job_id)
					submitted_job_ids.remove(job_id)
					local_job_results[job_id] = self.completed_jobs.get(
						job_id,
						{
							"status": "completed",
							"return_code": 0,
							"stdout": "",
							"stderr": "",
							"outputs": {},
						},
					)

		# Phase 3: Consolidate results
		for index, job_def in enumerate(job_definitions):
			job_name = job_def.get("name", f"job_{index}")
			job_id = job_def.get("job_id") or f"{stage_name}_{job_name}_{index}"
			result = local_job_results.get(job_id, {})

			return_code = result.get("return_code", -1)
			success = return_code == 0
			status = result.get("status", "completed" if success else "failed")

			job_statuses.append(
				JobStatus(
					job_id=job_id,
					status=status,
					return_code=return_code,
					stdout=result.get("stdout", ""),
					stderr=result.get("stderr", ""),
					outputs=result.get("outputs"),
					metrics=result.get("metrics"),
				)
			)

			if result.get("outputs"):
				all_artifacts.update(result["outputs"])

			if not success:
				all_success = False

		self.running_stages[stage_id]["status"] = "completed" if all_success else "failed"
		result = StageExecutionResult(
			stage_name=stage_name,
			job_statuses=job_statuses,
			artifacts=all_artifacts,
			success=all_success,
			error_message=None if all_success else f"Some jobs failed in stage '{stage_name}'",
		)
		self.running_stages[stage_id]["result"] = result

		return result

	def get_stage_results(self, stage_id: str) -> StageExecutionResult:
		"""Return stored StageExecutionResult for a stage.

		Raises KeyError if unknown, RuntimeError if not finished.
		"""
		if stage_id not in self.running_stages:
			raise KeyError(f"Unknown stage_id: {stage_id}")
		state = self.running_stages[stage_id]
		if state.get("status") in ("queued", "running"):
			raise RuntimeError(f"Stage {stage_id} is not yet finished (status={state.get('status')})")
		result = state.get("result")
		if result is None:
			raise RuntimeError(f"Stage {stage_id} completed but no result is available")
		return result

	def _normalize_function_outputs(self, results: Any) -> Dict[str, Any]:
		"""Convert an iDDS function return value into scheduler outputs."""
		if isinstance(results, dict):
			return {"objectives": results}
		if results is None:
			return {}
		return {"result": results}

	def _find_running_stage_for_job(self, job_id: str) -> Optional[str]:
		for stage_name, stage_jobs in self.running_funcs.items():
			if job_id in stage_jobs:
				return stage_name
		return None

	def check_status(self, job_id: str) -> JobStatus:
		"""Check the status of a previously submitted job.

		Args:
			job_id: Unique job identifier.

		Returns:
			JobStatus with current state and metrics.
		"""
		if job_id in self.completed_jobs:
			cached = self.completed_jobs[job_id]
			return JobStatus(
				job_id=job_id,
				status=cached.get("status", "completed"),
				return_code=cached.get("return_code"),
				stdout=cached.get("stdout", ""),
				stderr=cached.get("stderr", ""),
				outputs=cached.get("outputs"),
				metrics=cached.get("metrics"),
			)

		if self._find_running_stage_for_job(job_id):
			return JobStatus(
				job_id=job_id,
				status="running",
				return_code=None,
			)

		return JobStatus(
			job_id=job_id,
			status="unknown",
			return_code=None,
		)

	def cancel_job(self, job_id: str) -> bool:
		"""Cancel a job if it is still running.

		Args:
			job_id: Unique job identifier.

		Returns:
			True if the job was cancelled, False otherwise.
		"""
		stage_name = self._find_running_stage_for_job(job_id)

		if not stage_name:
			self.logger.warning("Cannot cancel job %s: stage not found", job_id)
			return False

		entry = self.running_funcs[stage_name].get(job_id, {})
		cancelled = False
		for func_name, g in entry.get("funcs", {}).items():
			work = g.get("work")
			try:
				if work and not work.is_terminated():
					work.cancel()
					cancelled = True
			except Exception:
				self.logger.exception("Failed to cancel work for job %s", job_id)

		return cancelled

	def submit_stage(
		self,
		stage_name: str,
		job_definitions: List[Dict[str, Any]],
		parallelism_policy: Optional[Dict[str, Any]] = None,
		working_dir: Optional[str] = None,
	) -> str:
		"""Submit a stage for asynchronous execution and return a stage_id.

		This schedules the full `run_stage` call in a background thread and
		stores the `StageExecutionResult` in memory for later retrieval.
		"""
		stage_id = uuid.uuid4().hex
		self.logger.info("Submitting stage '%s' as %s", stage_name, stage_id)

		# state holder
		state: Dict[str, Any] = {
			"thread": None,
			"status": "queued",
			"result": None,
			"submitted_at": time(),
			"job_count": len(job_definitions),
		}

		def _target() -> None:
			try:
				state["status"] = "running"
				result = self.run_stage(stage_name, job_definitions, parallelism_policy, working_dir)
				state["result"] = result
				state["status"] = "completed" if result.success else "failed"
			except Exception as exc:  # pragma: no cover - background safety
				self.logger.exception("Asynchronous stage execution failed: %s", exc)
				state["result"] = StageExecutionResult(
					stage_name=stage_name, job_statuses=[], artifacts={}, success=False, error_message=str(exc)
				)
				state["status"] = "failed"

		thread = threading.Thread(target=_target, name=f"PanDAiDDS-stage-{stage_id}", daemon=True)
		state["thread"] = thread
		self.running_stages[stage_id] = state
		thread.start()

		return stage_id

	def check_stage_status(self, stage_id: str):
		"""Return a StageStatus summarizing progress for a submitted stage.

		If the stage_id is unknown, raises KeyError.
		"""
		from aid2e.schedulers.base import StageStatus

		if stage_id not in self.running_stages:
			raise KeyError(f"Unknown stage_id: {stage_id}")

		state = self.running_stages[stage_id]
		status = state.get("status", "unknown")
		result: Optional[StageExecutionResult] = state.get("result")
		total = state.get("job_count")
		completed_jobs = 0
		job_statuses = None

		if result is not None:
			job_statuses = result.job_statuses
			completed_jobs = len(job_statuses)

		progress = None
		if total and total > 0:
			progress = float(completed_jobs) / float(total) if total else None

		return StageStatus(
			stage_id=stage_id,
			status=status,
			completed_jobs=completed_jobs,
			total_jobs=total,
			progress=progress,
			job_statuses=job_statuses,
		)

	# --- IDDS / PanDA integration helpers (best-effort, optional) ---------
	def submit_idds_workflow(self, stage_name: str):
		"""Define and submit an iDDS workflow for a stage. Returns the workflow object.

		This method is idempotent per stage_name: if a workflow for the given
		stage has already been submitted, it returns the cached workflow.
		Otherwise, it creates, submits, and caches a new workflow.

		Raises RuntimeError if iDDS is not available.
		"""
		# Check cache first
		if stage_name in self.stage_workflows:
			self.logger.debug("Returning cached workflow for stage '%s'", stage_name)
			return self.stage_workflows[stage_name]

		try:
			from idds.iworkflow.workflow import workflow as workflow_def  # type: ignore
		except Exception as exc:  # pragma: no cover - optional dependency
			raise RuntimeError("idds.iworkflow is not available; install idds to use PanDA runner") from exc

		workflow_name = f"{self.config.name or 'aid2e'}.{stage_name}.{datetime.datetime.now().strftime('%Y%m%d_%H_%M_%S')}"
		self.logger.info("Defining workflow for experiment %s", workflow_name)

		wf_builder = workflow_def(
			func=lambda: None,
			name=workflow_name,
			service="panda",
			cloud=self.config.cloud,
			queue=self.config.queue,
			init_env=self.config.init_env,
			source_dir=self.config.source_dir,
			source_dir_parent_level=self.config.source_dir_parent_level,
			exclude_source_files=self.config.exclude_source_files,
			max_walltime=self.config.max_walltime,
			core_count=self.config.core_count,
			total_memory=self.config.total_memory,
			enable_separate_log=self.config.enable_separate_log,
			local=True,
			return_workflow=True,
			post_script=self.config.post_script,
		)

		workflow = wf_builder()
		workflow.pre_run()
		workflow.prepare()
		req_id = workflow.submit()
		self.logger.info("Workflow id for experiment %s: %s", workflow_name, req_id)
		if not req_id:
			raise RuntimeError(f"Failed to submit workflow for experiment {workflow_name} to PanDA")

		# store for potential future use
		self.workflow = workflow
		self.workflow_id = req_id
		# Cache the workflow per stage_name
		self.stage_workflows[stage_name] = workflow
		return workflow

	def submit_job(self, stage_name: str, job_definition: Dict[str, Any], working_dir: Optional[str] = None) -> None:
		"""Submit a single function-based job to iDDS/PanDA.

		The method expects job_definition to contain at least a 'function' key.
		This mirrors the upstream runner but intentionally keeps the interface
		loose: any missing integration points raise a RuntimeError describing
		the problem.
		"""
		try:
			from idds.iworkflow.work import work as work_def  # type: ignore
		except Exception as exc:  # pragma: no cover - optional dependency
			raise RuntimeError("idds.iworkflow.work is not available; install idds to use PanDA runner") from exc

		# ensure workflow exists
		workflow = self.submit_idds_workflow(stage_name)

		job = job_definition
		job_id = job.get("job_id") or uuid.uuid4().hex

		func = job.get("function")
		if func is None:
			raise ValueError("Job dict must contain 'function' to submit to PanDA/iDDS")

		callable_ref = _callable_reference(func)
		func_name = getattr(func, "__name__", str(func))
		work_name = f"{self.config.name or 'aid2e'}.{stage_name}.{job_id}.{func_name}"
		self.logger.info("Defining work %s", work_name)

		# Initialize stage-level tracking if needed
		if stage_name not in self.running_funcs:
			self.running_funcs[stage_name] = {}
		if stage_name not in self.jobs:
			self.jobs[stage_name] = {}

		# simple bookkeeping entry for this job
		self.running_funcs[stage_name][job_id] = {"funcs": {}}

		# Submit a scheduler-owned worker adapter. The remote side imports and
		# executes only the configured evaluator callable; it does not construct
		# another PanDA scheduler or submit nested work.
		params = dict(job.get("params", {}))
		context = params.pop("context", None) or job.get("job_context")
		if context is None:
			context_payload = {
				"task_id": job_id,
				"job_id": job_id,
				"stage_id": stage_name,
				"workflow_id": job.get("workflow_id", "pandaidds"),
				"design_point": job.get("payload", {}).get("design_point", {}),
				"xcom": {},
				"execution_dir": working_dir,
				"output_dir": working_dir,
			}
		else:
			context_payload = {
				"task_id": getattr(context, "task_id", job_id),
				"job_id": getattr(context, "job_id", job_id),
				"stage_id": getattr(context, "stage_id", stage_name),
				"workflow_id": getattr(context, "workflow_id", "pandaidds"),
				"design_point": dict(getattr(context, "design_point", {}) or {}),
				"xcom": dict(getattr(context, "xcom", {}) or {}),
				"artifacts": dict(getattr(context, "artifacts", {}) or {}),
				"logs": list(getattr(context, "logs", []) or []),
				"execution_dir": getattr(context, "execution_dir", None),
				"output_dir": getattr(context, "output_dir", None),
			}
		work_params = {
			"callable_ref": callable_ref,
			"context_payload": context_payload,
			"op_kwargs": params,
		}
		work_builder = work_def(
			func=_remote_python_callable_entrypoint,
			workflow=workflow,
			return_work=True,
			map_results=True,
			name=work_name,
			job_key=work_name,
			log_dataset_name=f"{work_name}.$WORKFLOWID.log/",
		)
		work = work_builder(**work_params)

		# apply resource hints
		try:
			work.core_count = int(getattr(self.config, "core_count", 1))
		except Exception:
			pass

		tf_id = work.submit()
		self.logger.info("Submitted work %s to PanDA/iDDS, transform id %s", work_name, tf_id)
		if not tf_id:
			raise RuntimeError(f"Failed to submit {work_name} to PanDA")

		# store mapping under stage_name -> job_id -> funcs -> func_name
		self.running_funcs[stage_name][job_id]["funcs"][func_name] = {"work": work, "tf_id": tf_id, "status": "New", "results": None}
		self.jobs[stage_name][job_id] = tf_id

	def check_single_job_status(self, job: Dict[str, Any], job_context: Any = None) -> None:
		"""Check status of a single submitted job and update running_funcs state.

		Expects job dict with 'job_id' and optionally 'stage_name'. 
		If stage_name is not provided, searches all stages.
		Optionally accepts job_context for passing execution context.
		Raises on irrecoverable errors.
		"""
		job_id = job.get("job_id")
		if not job_id:
			raise ValueError("job must contain 'job_id'")

		stage_name = job.get("stage_name") or self._find_running_stage_for_job(job_id)
		
		if not stage_name or stage_name not in self.running_funcs:
			raise RuntimeError(f"No running entry for job {job_id} (stage not found)")

		# find the job entry in the stage
		entry = self.running_funcs[stage_name].get(job_id)
		if not entry:
			raise RuntimeError(f"No running entry for job {job_id} in stage {stage_name}")

		# entry may have multiple func names; pick the first
		func_name, info = next(iter(entry.get("funcs", {}).items()), (None, None))
		if func_name is None:
			# older-style storage format
			func_name = next(iter(entry.keys()))
			info = entry[func_name]

		work = info.get("work")
		tf_id = info.get("tf_id")
		if not work or not tf_id:
			raise RuntimeError(f"Job {job_id} has no work or no transform id")

		# ensure async result initialized if available
		try:
			work.init_async_result()
		except Exception:
			pass

		status = work.get_status()
		if work.is_finished(status):
			self.logger.info("Job %s finished (transform %s)", job_id, tf_id)
			results = None
			details = None
			try:
				ret = work.get_results()
				try:
					results, details = ret.get_result(
						name=work.name,
						key=info.get("job_key", work.name),
						verbose=True,
						with_details=True,
					)
					self.logger.debug("Extracted results for job %s: %s, details: %s", job_id, results, details)
				except Exception:
					results = ret
				info["results"] = results
			except Exception as exc:
				self.logger.exception("Failed to fetch results for job %s", job_id)
				self.completed_jobs[job_id] = {
					"status": "failed",
					"return_code": -1,
					"stdout": "",
					"stderr": str(exc),
					"outputs": {},
					"metrics": {"transform_id": tf_id},
				}
			else:
				outputs = self._normalize_function_outputs(results)
				if job_context is not None and hasattr(job_context, "xcom_push"):
					try:
						if isinstance(results, dict):
							job_context.xcom_push("objectives", results)
						if details is not None:
							job_context.xcom_push("results_details", details)
					except Exception:
						self.logger.debug("Failed to push iDDS results to job context", exc_info=True)
				self.completed_jobs[job_id] = {
					"status": "completed",
					"return_code": 0,
					"stdout": "",
					"stderr": "",
					"outputs": outputs,
					"metrics": {"transform_id": tf_id},
				}
			info["status"] = "finished"
			self.running_funcs[stage_name].pop(job_id, None)
		elif work.is_failed(status):
			self.logger.info("Job %s failed (transform %s)", job_id, tf_id)
			info["status"] = "failed"
			self.completed_jobs[job_id] = {
				"status": "failed",
				"return_code": -1,
				"stdout": "",
				"stderr": f"PanDA/iDDS work failed with status {status}",
				"outputs": {},
				"metrics": {"transform_id": tf_id},
			}
			self.running_funcs[stage_name].pop(job_id, None)

	def check_job_status(self, job: Dict[str, Any]) -> None:
		"""Wrapper around check_single_job_status that throttles verbose logs."""
		if self.num_checks % 60 == 0:
			self.logger.info("Check job %s status", job.get("job_id"))
		self.check_single_job_status(job, job.get("job_context"))
		self.num_checks += 1

	# convenience alias for upstream name
	submit_workflow = submit_idds_workflow

