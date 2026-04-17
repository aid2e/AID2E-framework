"""Slurm-backed scheduler for command jobs."""

from __future__ import annotations

import json
import logging
import shlex
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from aid2e.schedulers.Slurm.config import SlurmRunnerConfig
from aid2e.schedulers.base import BaseScheduler, JobStatus, StageExecutionResult, StageStatus


TERMINAL_STATUSES = {"completed", "failed", "cancelled"}

STATE_MAP = {
    "PENDING": "queued",
    "CONFIGURING": "queued",
    "RUNNING": "running",
    "COMPLETING": "running",
    "COMPLETED": "completed",
    "FAILED": "failed",
    "TIMEOUT": "failed",
    "OUT_OF_MEMORY": "failed",
    "NODE_FAIL": "failed",
    "PREEMPTED": "failed",
    "BOOT_FAIL": "failed",
    "DEADLINE": "failed",
    "REVOKED": "failed",
    "CANCELLED": "cancelled",
}

RESOURCE_KEYS = (
    "partition",
    "account",
    "qos",
    "time",
    "nodes",
    "ntasks",
    "cpus_per_task",
    "mem",
    "gres",
    "constraint",
)


class SlurmScheduler(BaseScheduler):
    """Execute workflow stage jobs on Slurm using generated batch scripts."""

    def __init__(self, config: Optional[SlurmRunnerConfig] = None) -> None:
        super().__init__(config)
        self.config = config or SlurmRunnerConfig()
        self.logger = logging.getLogger("SlurmScheduler")
        self.stages: Dict[str, Dict[str, Any]] = {}
        self.jobs: Dict[str, Dict[str, Any]] = {}

    def run_stage(
        self,
        stage_name: str,
        job_definitions: List[Dict[str, Any]],
        parallelism_policy: Optional[Dict[str, Any]] = None,
        working_dir: Optional[str] = None,
    ) -> StageExecutionResult:
        """Submit a stage and block until it reaches a terminal state."""

        stage_id = self.submit_stage(stage_name, job_definitions, parallelism_policy, working_dir)
        poll_interval = int((parallelism_policy or {}).get("poll_interval", self.config.poll_interval))

        while True:
            status = self.check_stage_status(stage_id)
            if status.status in TERMINAL_STATUSES:
                return self.get_stage_results(stage_id)
            time.sleep(poll_interval)

    def submit_stage(
        self,
        stage_name: str,
        job_definitions: List[Dict[str, Any]],
        parallelism_policy: Optional[Dict[str, Any]] = None,
        working_dir: Optional[str] = None,
    ) -> str:
        """Create scripts, submit them to Slurm, and return a stage id."""

        stage_id = uuid.uuid4().hex
        stage_root = self._resolve_submit_root(working_dir) / f"{stage_name}_{stage_id}"
        stage_root.mkdir(parents=True, exist_ok=True)

        stage_state: Dict[str, Any] = {
            "stage_id": stage_id,
            "stage_name": stage_name,
            "status": "queued",
            "created_at": time.time(),
            "parallelism_policy": dict(parallelism_policy or {}),
            "working_dir": str(stage_root),
            "job_ids": [],
            "result": None,
        }
        self.stages[stage_id] = stage_state

        for index, job_def in enumerate(job_definitions):
            self._validate_job_definition(job_def)
            job_name = job_def.get("name", f"job_{index}")
            job_id = job_def.get("job_id") or f"{stage_name}_{job_name}_{index}"
            job_root = stage_root / job_id
            job_root.mkdir(parents=True, exist_ok=True)

            script_path = job_root / "job.sbatch"
            stdout_path = job_root / "stdout.log" if self.config.capture_stdout else None
            stderr_path = job_root / "stderr.log" if self.config.capture_stderr else None
            runtime_dir = self._resolve_runtime_dir(job_def, job_root)
            runtime_dir.mkdir(parents=True, exist_ok=True)

            script_text = self._build_batch_script(
                job_id=job_id,
                job_name=job_name,
                job_def=job_def,
                runtime_dir=runtime_dir,
                stdout_path=stdout_path,
                stderr_path=stderr_path,
            )
            script_path.write_text(script_text, encoding="utf-8")

            slurm_job_id = self._submit_script(script_path, stage_root)
            job_state = {
                "stage_id": stage_id,
                "job_id": job_id,
                "job_name": job_name,
                "job_root": str(job_root),
                "runtime_dir": str(runtime_dir),
                "script_path": str(script_path),
                "stdout_path": str(stdout_path) if stdout_path else None,
                "stderr_path": str(stderr_path) if stderr_path else None,
                "slurm_job_id": slurm_job_id,
                "status": "queued",
                "raw_state": "PENDING",
                "return_code": None,
                "command": job_def.get("command", ""),
                "outputs": list(job_def.get("outputs", [])),
                "artifact_cache": None,
                "last_update": time.time(),
            }
            self.jobs[job_id] = job_state
            stage_state["job_ids"].append(job_id)

        self._refresh_stage_status(stage_id)
        return stage_id

    def check_stage_status(self, stage_id: str) -> StageStatus:
        """Poll Slurm and return a stage-level status summary."""

        if stage_id not in self.stages:
            raise KeyError(f"Unknown stage_id: {stage_id}")

        self._refresh_stage_status(stage_id)
        stage_state = self.stages[stage_id]
        job_statuses = [self._job_status_from_state(self.jobs[job_id]) for job_id in stage_state["job_ids"]]
        completed_jobs = sum(1 for status in job_statuses if status.status in TERMINAL_STATUSES)
        total_jobs = len(job_statuses)
        progress = float(completed_jobs) / float(total_jobs) if total_jobs else 1.0

        return StageStatus(
            stage_id=stage_id,
            status=stage_state["status"],
            completed_jobs=completed_jobs,
            total_jobs=total_jobs,
            progress=progress,
            job_statuses=job_statuses,
        )

    def get_stage_results(self, stage_id: str) -> StageExecutionResult:
        """Return final stage results after collecting logs and artifacts."""

        if stage_id not in self.stages:
            raise KeyError(f"Unknown stage_id: {stage_id}")

        self._refresh_stage_status(stage_id)
        stage_state = self.stages[stage_id]
        if stage_state["status"] not in TERMINAL_STATUSES:
            raise RuntimeError(f"Stage {stage_id} is not yet finished (status={stage_state['status']})")

        cached = stage_state.get("result")
        if cached is not None:
            return cached

        job_statuses: List[JobStatus] = []
        artifacts: Dict[str, Any] = {}
        stage_success = True

        for job_id in stage_state["job_ids"]:
            job_state = self.jobs[job_id]
            job_outputs = self._collect_job_outputs(job_state)
            stdout = self._read_text(job_state.get("stdout_path"))
            stderr = self._read_text(job_state.get("stderr_path"))
            status = self._job_status_from_state(
                job_state,
                stdout=stdout,
                stderr=stderr,
                outputs=job_outputs,
            )
            job_statuses.append(status)
            if job_outputs:
                artifacts.update(job_outputs)
            if status.status != "completed":
                stage_success = False

        result = StageExecutionResult(
            stage_name=stage_state["stage_name"],
            job_statuses=job_statuses,
            artifacts=artifacts,
            success=stage_success,
            error_message=None if stage_success else f"Some jobs failed in stage '{stage_state['stage_name']}'",
        )
        stage_state["result"] = result
        return result

    def check_status(self, job_id: str) -> JobStatus:
        """Return the most recent cached job status."""

        if job_id not in self.jobs:
            raise KeyError(f"Unknown job_id: {job_id}")
        self._refresh_job_state(self.jobs[job_id])
        return self._job_status_from_state(self.jobs[job_id])

    def cancel_job(self, job_id: str) -> bool:
        """Request job cancellation through scancel."""

        if job_id not in self.jobs:
            self.logger.warning("Cannot cancel unknown job %s", job_id)
            return False

        job_state = self.jobs[job_id]
        slurm_job_id = job_state["slurm_job_id"]
        proc = subprocess.run(
            ["scancel", str(slurm_job_id)],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            self.logger.warning("scancel failed for job %s (%s): %s", job_id, slurm_job_id, proc.stderr.strip())
            return False

        job_state["status"] = "cancelled"
        job_state["raw_state"] = "CANCELLED"
        job_state["return_code"] = -1
        self._refresh_stage_status(job_state["stage_id"])
        return True

    def _validate_job_definition(self, job_def: Dict[str, Any]) -> None:
        if job_def.get("function") is not None or job_def.get("params") is not None:
            raise ValueError("SlurmScheduler v1 supports command jobs only")
        command = str(job_def.get("command", "")).strip()
        if not command:
            raise ValueError("Job definition must include a non-empty 'command'")

    def _resolve_submit_root(self, working_dir: Optional[str]) -> Path:
        submit_root = self.config.submit_working_dir or working_dir or str(Path.cwd())
        return Path(submit_root).expanduser().resolve()

    def _resolve_runtime_dir(self, job_def: Dict[str, Any], default_job_root: Path) -> Path:
        if self.config.runtime_working_dir:
            return Path(self.config.runtime_working_dir).expanduser().resolve()

        payload = job_def.get("payload") or {}
        execution_dir = payload.get("execution_dir")
        if execution_dir:
            return Path(str(execution_dir)).expanduser().resolve()

        return default_job_root.resolve()

    def _resolve_job_resources(self, job_def: Dict[str, Any]) -> Dict[str, Any]:
        resolved: Dict[str, Any] = {key: getattr(self.config, key) for key in RESOURCE_KEYS}
        for key, value in (job_def.get("resources") or {}).items():
            if key in RESOURCE_KEYS and value is not None:
                resolved[key] = value
        return resolved

    def _build_batch_script(
        self,
        job_id: str,
        job_name: str,
        job_def: Dict[str, Any],
        runtime_dir: Path,
        stdout_path: Optional[Path],
        stderr_path: Optional[Path],
    ) -> str:
        resources = self._resolve_job_resources(job_def)
        slurm_job_name = f"{self.config.job_name_prefix}_{job_name}"
        lines = ["#!/bin/bash", f"#SBATCH --job-name={slurm_job_name}"]

        if stdout_path is not None:
            lines.append(f"#SBATCH --output={stdout_path}")
        if stderr_path is not None:
            lines.append(f"#SBATCH --error={stderr_path}")

        directive_map = {
            "partition": "--partition",
            "account": "--account",
            "qos": "--qos",
            "time": "--time",
            "nodes": "--nodes",
            "ntasks": "--ntasks",
            "cpus_per_task": "--cpus-per-task",
            "mem": "--mem",
            "gres": "--gres",
            "constraint": "--constraint",
        }
        for key, flag in directive_map.items():
            value = resources.get(key)
            if value is not None:
                lines.append(f"#SBATCH {flag}={value}")

        lines.extend(["", "set -euo pipefail"])
        lines.extend(self.config.setup_commands)
        lines.append(f"cd {shlex.quote(str(runtime_dir))}")
        lines.append(str(job_def["command"]))
        lines.append("")
        return "\n".join(lines)

    def _submit_script(self, script_path: Path, submit_root: Path) -> str:
        command = ["sbatch", "--parsable", *self.config.sbatch_extra_args, str(script_path)]
        proc = subprocess.run(
            command,
            cwd=str(submit_root),
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError(
                f"sbatch failed for {script_path}: {proc.stderr.strip() or proc.stdout.strip()}"
            )

        stdout = proc.stdout.strip()
        job_id = stdout.split(";", 1)[0].strip()
        if not job_id:
            raise RuntimeError(f"Could not parse Slurm job id from sbatch output: {stdout!r}")
        return job_id

    def _refresh_stage_status(self, stage_id: str) -> None:
        stage_state = self.stages[stage_id]
        statuses = []
        for job_id in stage_state["job_ids"]:
            self._refresh_job_state(self.jobs[job_id])
            statuses.append(self.jobs[job_id]["status"])

        if not statuses:
            stage_state["status"] = "completed"
        elif all(status == "completed" for status in statuses):
            stage_state["status"] = "completed"
        elif any(status == "failed" for status in statuses):
            stage_state["status"] = "failed"
        elif any(status == "cancelled" for status in statuses):
            stage_state["status"] = "cancelled"
        elif any(status == "running" for status in statuses):
            stage_state["status"] = "running"
        else:
            stage_state["status"] = "queued"

    def _refresh_job_state(self, job_state: Dict[str, Any]) -> None:
        if job_state["status"] in TERMINAL_STATUSES:
            return

        slurm_job_id = job_state["slurm_job_id"]
        active_state = self._query_squeue_state(slurm_job_id)
        if active_state is not None:
            job_state["raw_state"] = active_state
            job_state["status"] = self._normalize_state(active_state)
            job_state["last_update"] = time.time()
            return

        account_state = self._query_sacct_state(slurm_job_id)
        if account_state is None:
            job_state["last_update"] = time.time()
            return

        raw_state = account_state["state"]
        job_state["raw_state"] = raw_state
        job_state["status"] = self._normalize_state(raw_state)
        job_state["return_code"] = self._parse_exit_code(account_state.get("exit_code"), job_state["status"])
        job_state["last_update"] = time.time()

    def _query_squeue_state(self, slurm_job_id: str) -> Optional[str]:
        proc = subprocess.run(
            ["squeue", "-h", "-j", str(slurm_job_id), "--format=%i|%T"],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            self.logger.debug("squeue failed for %s: %s", slurm_job_id, proc.stderr.strip())
            return None

        for line in proc.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            job_id, state = (line.split("|", 1) + [""])[:2]
            if job_id.strip() == str(slurm_job_id):
                return state.strip()
        return None

    def _query_sacct_state(self, slurm_job_id: str) -> Optional[Dict[str, str]]:
        proc = subprocess.run(
            ["sacct", "-n", "-P", "-j", str(slurm_job_id), "--format=JobIDRaw,State,ExitCode"],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            self.logger.debug("sacct failed for %s: %s", slurm_job_id, proc.stderr.strip())
            return None

        best_match: Optional[Dict[str, str]] = None
        for line in proc.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split("|")
            if len(parts) < 3:
                continue
            job_id_raw, state, exit_code = parts[0].strip(), parts[1].strip(), parts[2].strip()
            if job_id_raw == str(slurm_job_id):
                best_match = {"state": state, "exit_code": exit_code}
                break
        return best_match

    def _normalize_state(self, raw_state: Optional[str]) -> str:
        if not raw_state:
            return "unknown"
        token = raw_state.strip().upper().split()[0].rstrip("+")
        return STATE_MAP.get(token, "unknown")

    def _parse_exit_code(self, exit_code: Optional[str], normalized_status: str) -> Optional[int]:
        if normalized_status == "completed":
            return 0
        if not exit_code:
            return -1 if normalized_status in {"failed", "cancelled"} else None
        token = exit_code.split(":", 1)[0].strip()
        try:
            return int(token)
        except ValueError:
            return -1 if normalized_status in {"failed", "cancelled"} else None

    def _job_status_from_state(
        self,
        job_state: Dict[str, Any],
        stdout: Optional[str] = None,
        stderr: Optional[str] = None,
        outputs: Optional[Dict[str, Any]] = None,
    ) -> JobStatus:
        return JobStatus(
            job_id=job_state["job_id"],
            status=job_state["status"],
            return_code=job_state.get("return_code"),
            stdout=stdout,
            stderr=stderr,
            outputs=outputs,
            metrics={"slurm_job_id": job_state["slurm_job_id"], "raw_state": job_state.get("raw_state")},
        )

    def _collect_job_outputs(self, job_state: Dict[str, Any]) -> Dict[str, Any]:
        cached = job_state.get("artifact_cache")
        if cached is not None:
            return cached

        runtime_dir = Path(job_state["runtime_dir"])
        collected: Dict[str, Any] = {}
        for output_spec in job_state.get("outputs", []):
            output_path = self._get_output_spec_value(output_spec, "path")
            if not output_path:
                continue

            path_obj = Path(str(output_path))
            full_path = path_obj if path_obj.is_absolute() else runtime_dir / path_obj
            if not full_path.exists():
                self.logger.warning("Expected output artifact missing for %s: %s", job_state["job_id"], full_path)
                continue

            fmt = str(self._get_output_spec_value(output_spec, "format") or "").lower()
            if fmt == "json":
                with full_path.open("r", encoding="utf-8") as handle:
                    collected.update(json.load(handle))
            else:
                collected[str(output_path)] = full_path.read_text(encoding="utf-8")

        job_state["artifact_cache"] = collected
        return collected

    def _get_output_spec_value(self, output_spec: Any, key: str) -> Any:
        if isinstance(output_spec, dict):
            return output_spec.get(key)
        return getattr(output_spec, key, None)

    def _read_text(self, path_str: Optional[str]) -> Optional[str]:
        if not path_str:
            return None
        path = Path(path_str)
        if not path.exists():
            return None
        return path.read_text(encoding="utf-8")
