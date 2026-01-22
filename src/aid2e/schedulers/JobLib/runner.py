"""JobLib-based scheduler for local parallel job execution."""

import json
import logging
import os
import subprocess
from typing import Dict, Any, List, Optional

import joblib

from aid2e.schedulers.base import BaseScheduler, JobStatus, StageExecutionResult
from aid2e.schedulers.JobLib.config import JobLibRunnerConfig


class JobLibScheduler(BaseScheduler):
    """Execute workflow stage jobs in parallel using joblib."""

    def __init__(self, config: Optional[JobLibRunnerConfig] = None) -> None:
        """Initialize JobLib scheduler with the provided configuration."""

        super().__init__(config)
        self.config = config or JobLibRunnerConfig()
        self.logger = logging.getLogger("JobLibScheduler")
        self.running_jobs: Dict[str, Dict[str, Any]] = {}

    def _execute_job(self, job_def: Dict[str, Any], working_dir: Optional[str] = None) -> Dict[str, Any]:
        """Execute a single job command and collect outputs."""

        job_name = job_def.get("name", "unknown_job")
        command = job_def.get("command", "")
        payload = job_def.get("payload", {})
        output_specs = job_def.get("outputs", [])

        try:
            env = os.environ.copy()
            env["JOB_PAYLOAD"] = json.dumps(payload)

            cwd = working_dir or os.getcwd()
            self.logger.info("Executing job '%s': %s", job_name, command)

            timeout_sec = self.config.timeout if self.config.timeout else None
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                cwd=cwd,
                env=env,
                timeout=timeout_sec,
            )

            artifacts: Dict[str, Any] = {}
            for spec in output_specs:
                output_path = spec.get("path", "")
                if not output_path:
                    continue
                full_path = os.path.join(cwd, output_path)
                if os.path.exists(full_path):
                    with open(full_path, "r", encoding="utf-8") as handle:
                        artifacts[output_path] = handle.read()
                else:
                    self.logger.warning("Expected output file not found: %s", full_path)

            return {
                "stdout": result.stdout,
                "stderr": result.stderr,
                "return_code": result.returncode,
                "outputs": artifacts,
            }

        except subprocess.TimeoutExpired:
            self.logger.error("Job '%s' timed out after %ss", job_name, self.config.timeout)
            return {
                "stdout": "",
                "stderr": f"Job timed out after {self.config.timeout}s",
                "return_code": -1,
                "outputs": {},
            }
        except Exception as exc:  # pragma: no cover - catch-all safety
            self.logger.error("Job '%s' raised exception: %s", job_name, exc)
            return {
                "stdout": "",
                "stderr": str(exc),
                "return_code": -1,
                "outputs": {},
            }

    def run_stage(
        self,
        stage_name: str,
        job_definitions: List[Dict[str, Any]],
        parallelism_policy: Optional[Dict[str, Any]] = None,
        working_dir: Optional[str] = None,
    ) -> StageExecutionResult:
        """Execute all jobs in a stage using joblib.Parallel."""

        policy = parallelism_policy or {}
        max_concurrent = policy.get("max_concurrent", self.config.n_jobs)
        retry_max = policy.get("retry_max", 2)

        self.logger.info("Running stage '%s' with %d jobs", stage_name, len(job_definitions))
        self.logger.info("  Max concurrent: %s, Max retries: %s", max_concurrent, retry_max)

        n_jobs = max_concurrent if max_concurrent and max_concurrent > 0 else self.config.n_jobs

        try:
            parallel = joblib.Parallel(
                n_jobs=n_jobs,
                backend=self.config.backend,
                verbose=self.config.verbose,
            )

            job_results = parallel(
                joblib.delayed(self._execute_job)(job_def, working_dir)
                for job_def in job_definitions
            )

            job_statuses: List[JobStatus] = []
            all_artifacts: Dict[str, Any] = {}
            all_success = True

            for index, (job_def, result) in enumerate(zip(job_definitions, job_results)):
                job_name = job_def.get("name", f"job_{index}")
                job_id = f"{stage_name}_{job_name}_{index}"

                return_code = result.get("return_code", -1)
                success = return_code == 0
                status = "completed" if success else "failed"

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
                    self.logger.warning("Job '%s' failed with code %s", job_id, return_code)

            return StageExecutionResult(
                stage_name=stage_name,
                job_statuses=job_statuses,
                artifacts=all_artifacts,
                success=all_success,
                error_message=None if all_success else f"Some jobs failed in stage '{stage_name}'",
            )

        except Exception as exc:  # pragma: no cover - safety net
            self.logger.error("Stage '%s' execution failed: %s", stage_name, exc)
            return StageExecutionResult(
                stage_name=stage_name,
                job_statuses=[],
                artifacts={},
                success=False,
                error_message=str(exc),
            )

    def check_status(self, job_id: str) -> JobStatus:
        """Return cached status (JobLib is synchronous, so jobs finish in run_stage)."""

        if job_id in self.running_jobs:
            cached = self.running_jobs[job_id]
            return JobStatus(
                job_id=job_id,
                status=cached.get("status", "unknown"),
                return_code=cached.get("return_code"),
            )

        return JobStatus(job_id=job_id, status="unknown", return_code=None)

    def cancel_job(self, job_id: str) -> bool:
        """Indicate that cancellation is not supported for synchronous JobLib jobs."""

        self.logger.warning("Cannot cancel job '%s' (JobLib execution is synchronous)", job_id)
        return False

    def shutdown(self) -> None:
        """No-op shutdown hook for JobLib scheduler."""

        self.logger.debug("JobLibScheduler shutdown complete")
        return None
