"""JobLib-based scheduler for local parallel job execution."""

import json
import logging
import os
import pickle
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

        # Check if this is a Python callable job
        python_callable = job_def.get("function")
        if python_callable and callable(python_callable):
            return self._execute_python_callable(job_def, python_callable, working_dir)

        try:
            env = os.environ.copy()
            
            # Try to serialize payload with pickle first (handles more types including functions)
            try:
                import base64
                pickled_payload = pickle.dumps(payload)
                env["JOB_PAYLOAD_PICKLE"] = base64.b64encode(pickled_payload).decode('ascii')
                env["JOB_PAYLOAD_TYPE"] = "pickle"
            except Exception as pickle_err:
                self.logger.debug("Cannot pickle payload, falling back to JSON: %s", pickle_err)
                # Fall back to JSON for simple payloads
                serializable_payload = {}
                for key, value in payload.items():
                    if not callable(value):
                        try:
                            # Test if it's JSON serializable
                            json.dumps(value)
                            serializable_payload[key] = value
                        except (TypeError, ValueError):
                            # Skip non-serializable values
                            self.logger.debug("Skipping non-serializable payload key: %s", key)
                
                env["JOB_PAYLOAD"] = json.dumps(serializable_payload)
                env["JOB_PAYLOAD_TYPE"] = "json"

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

    def _execute_python_callable(
        self, job_def: Dict[str, Any], python_callable, working_dir: Optional[str] = None
    ) -> Dict[str, Any]:
        """Execute a Python callable directly (for function-based jobs).
        
        Args:
            job_def: Job definition dict.
            python_callable: The Python function to call.
            working_dir: Working directory (unused for Python callables).
            
        Returns:
            Dict with execution results.
        """
        job_name = job_def.get("name", "unknown_job")
        params = job_def.get("params", {})
        
        try:
            self.logger.info("Executing Python callable for job '%s'", job_name)
            
            # Extract the context if provided
            context = params.get("context")
            if context:
                # Call with context as first argument
                result = python_callable(context, **{k: v for k, v in params.items() if k != "context"})
            else:
                # Call with just kwargs
                result = python_callable(**params)
            
            # Convert result to string for stdout
            result_str = str(result) if result is not None else ""
            
            # Extract xcom data from context (if context was provided)
            outputs = {"result": result}
            if context and hasattr(context, 'xcom'):
                # Extract xcom entries pushed by the callable
                # XCom keys are in format "job_id:key", extract just the key part
                for xcom_key, xcom_value in context.xcom.items():
                    # Extract the key after the job_id prefix
                    if ':' in xcom_key:
                        key = xcom_key.split(':', 1)[1]
                        outputs[key] = xcom_value
            
            return {
                "stdout": result_str,
                "stderr": "",
                "return_code": 0,
                "outputs": outputs,
            }
            
        except Exception as exc:
            self.logger.exception("Python callable '%s' raised exception", job_name)
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
                        outputs=result.get("outputs"),
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

    def submit_stage(
        self,
        stage_name: str,
        job_definitions: List[Dict[str, Any]],
        parallelism_policy: Optional[Dict[str, Any]] = None,
        working_dir: Optional[str] = None,
    ) -> str:
        """Submit a stage for execution.
        
        For JobLib (synchronous execution), this immediately runs the stage
        and returns a stage_id for the completed stage.
        """
        import uuid
        
        stage_id = uuid.uuid4().hex
        self.logger.info("Submitting stage '%s' as %s (synchronous execution)", stage_name, stage_id)
        
        # Execute the stage immediately (JobLib is synchronous)
        result = self.run_stage(stage_name, job_definitions, parallelism_policy, working_dir)
        
        # Cache the result
        if not hasattr(self, '_stage_results'):
            self._stage_results = {}
        self._stage_results[stage_id] = {
            'stage_name': stage_name,
            'result': result,
            'status': 'completed' if result.success else 'failed',
        }
        
        return stage_id

    def check_stage_status(self, stage_id: str):
        """Return status for a submitted stage.
        
        Since JobLib is synchronous, stages are always completed by the time this is called.
        """
        from aid2e.schedulers.base import StageStatus
        
        if not hasattr(self, '_stage_results'):
            self._stage_results = {}
        
        if stage_id not in self._stage_results:
            raise KeyError(f"Unknown stage_id: {stage_id}")
        
        stage_data = self._stage_results[stage_id]
        result = stage_data['result']
        
        return StageStatus(
            stage_id=stage_id,
            status=stage_data['status'],
            completed_jobs=len(result.job_statuses),
            total_jobs=len(result.job_statuses),
            progress=1.0,  # Always complete for synchronous execution
            job_statuses=result.job_statuses,
        )

    def get_stage_results(self, stage_id: str) -> StageExecutionResult:
        """Return results for a completed stage.
        
        Since JobLib is synchronous, results are available immediately after submit_stage.
        """
        if not hasattr(self, '_stage_results'):
            self._stage_results = {}
        
        if stage_id not in self._stage_results:
            raise KeyError(f"Unknown stage_id: {stage_id}")
        
        stage_data = self._stage_results[stage_id]
        return stage_data['result']

    def shutdown(self) -> None:
        """No-op shutdown hook for JobLib scheduler."""

        self.logger.debug("JobLibScheduler shutdown complete")
        return None
