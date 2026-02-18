
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
from typing import Dict, Any, List, Optional, Tuple

import threading
import uuid
from time import time
import time as _time

from aid2e.schedulers.base import BaseScheduler, JobStatus, StageExecutionResult
from aid2e.schedulers.PanDAiDDS.config import PanDAiDDSRunnerConfig


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

		# Create a simple stage id for bookkeeping
		stage_id = uuid.uuid4().hex
		self.running_stages[stage_id] = {"status": "running", "jobs": [], "result": None}

		# Phase 1: Submit all jobs
		submitted_job_ids = []
		local_job_results = {}

		for index, job_def in enumerate(job_definitions):
			job_name = job_def.get("name", f"job_{index}")
			job_id = f"{stage_name}_{job_name}_{index}"

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
		while submitted_job_ids:
			_time.sleep(poll_interval)
			self.logger.debug("Polling %d remaining jobs", len(submitted_job_ids))
			
			# check status of all remaining jobs
			for job_id in list(submitted_job_ids):
				try:
					self.check_single_job_status({"job_id": job_id, "stage_name": stage_name})
				except Exception as exc:
					# if job still running, check_single_job_status may raise until finished
					self.logger.debug("Job %s not finished yet: %s", job_id, exc)

				# if running_funcs no longer contains job_id, it's done or failed
				stage_funcs = self.running_funcs.get(stage_name, {})
				if job_id not in stage_funcs:
					self.logger.info("Job %s finished", job_id)
					submitted_job_ids.remove(job_id)
					# store a placeholder result; detailed results are in self.jobs mapping
					local_job_results[job_id] = {
						"status": "completed",
						"return_code": 0,
						"stdout": "",
						"stderr": "",
						"outputs": {},
					}

		# Phase 3: Consolidate results
		for index, job_def in enumerate(job_definitions):
			job_name = job_def.get("name", f"job_{index}")
			job_id = f"{stage_name}_{job_name}_{index}"
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

		# create a work object depending on job content
		params = job.get("params", {})
		work_builder = work_def(
			func=func,
			workflow=workflow,
			return_work=True,
			map_results=True,
			name=work_name,
			job_key=work_name,
			log_dataset_name=f"{work_name}.log/",
		)
		work = work_builder(**params)

		# apply resource hints
		try:
			work.core_count = int(getattr(self.config, "core_count", 1))
		except Exception:
			pass

		tf_id = work.submit()
		self.logger.info("Submitted work %s to PanDA/iDDS, transform id %s", work_name, tf_id)
		if not tf_id:
			raise RuntimeError(f"Failed to submit {work_name} to PanDA")

		# store mapping under stage_name
		self.running_funcs[stage_name][job_id][func_name] = {"work": work, "tf_id": tf_id, "status": "New", "results": None}
		self.jobs[stage_name][job_id] = tf_id

	def check_single_job_status(self, job: Dict[str, Any]) -> None:
		"""Check status of a single submitted job and update running_funcs state.

		Expects job dict with 'job_id' and optionally 'stage_name'. 
		If stage_name is not provided, searches all stages.
		Raises on irrecoverable errors.
		"""
		job_id = job.get("job_id")
		if not job_id:
			raise ValueError("job must contain 'job_id'")

		# Extract stage_name from job_id if not provided (format: stage_name_job_name_index)
		stage_name = job.get("stage_name")
		if not stage_name:
			# Try to extract from job_id
			parts = job_id.split("_")
			if len(parts) >= 1:
				# Assume first part is stage_name
				stage_name = parts[0]
			else:
				# Fallback: search all stages
				for sname, stage_jobs in self.running_funcs.items():
					if job_id in stage_jobs:
						stage_name = sname
						break
		
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
			try:
				ret = work.get_results()
				# try to extract mapped results
				results = None
				try:
					results, _details = ret.get_result(name=work.name, key=info.get("job_key", work.name), verbose=True, with_details=True)
				except Exception:
					results = ret
				info["results"] = results
			except Exception:
				self.logger.exception("Failed to fetch results for job %s", job_id)
			info["status"] = "finished"
			# cleanup bookkeeping from stage
			self.running_funcs[stage_name].pop(job_id, None)
		elif work.is_failed(status):
			self.logger.info("Job %s failed (transform %s)", job_id, tf_id)
			info["status"] = "failed"
			self.running_funcs[stage_name].pop(job_id, None)

	def check_job_status(self, job: Dict[str, Any]) -> None:
		"""Wrapper around check_single_job_status that throttles verbose logs."""
		if self.num_checks % 60 == 0:
			self.logger.info("Check job %s status", job.get("job_id"))
		self.check_single_job_status(job)
		self.num_checks += 1

	def cancel_job(self, job: Dict[str, Any]) -> None:
		"""Attempt to cancel a running job submitted via PanDA/iDDS.

		If idds is not installed or cancel fails, this is best-effort and logs
		the exception.
		"""
		job_id = job.get("job_id")
		if not job_id:
			return
		
		# Extract stage_name from job or search
		stage_name = job.get("stage_name")
		if not stage_name:
			parts = job_id.split("_")
			if len(parts) >= 1:
				stage_name = parts[0]
			else:
				# Search all stages
				for sname, stage_jobs in self.running_funcs.items():
					if job_id in stage_jobs:
						stage_name = sname
						break
		
		if not stage_name or stage_name not in self.running_funcs:
			self.logger.warning("Cannot cancel job %s: stage not found", job_id)
			return
			
		entry = self.running_funcs[stage_name].get(job_id, {})
		for func_name, g in entry.get("funcs", {}).items():
			work = g.get("work")
			try:
				if work and not work.is_terminated():
					work.cancel()
			except Exception:
				self.logger.exception("Failed to cancel work for job %s", job_id)

	# convenience alias for upstream name
	submit_workflow = submit_idds_workflow

