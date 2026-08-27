#!/usr/bin/env python
"""Submit ten Slurm jobs together, monitor them, and collect per-job outputs."""

from __future__ import annotations

import json
import sys
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, List


REPO_ROOT = Path(__file__).resolve().parents[3]
SRC_ROOT = REPO_ROOT / "src"
for candidate in (str(REPO_ROOT), str(SRC_ROOT)):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

from aid2e.optimizers.base import Trial
from aid2e.schedulers.Slurm import SlurmRunnerConfig, SlurmScheduler


DEFAULT_SETUP_COMMANDS = [
    "module load miniforge3/24.9.2-0",
    "conda activate env_AID2E",
]


def build_dtlz2_point(index: int) -> Dict[str, float]:
    return {
        "DTLZ2_variables.x1": 0.10 + 0.05 * index,
        "DTLZ2_variables.x2": 0.65 - 0.02 * index,
        "DTLZ2_variables.x3": 0.35 + 0.01 * index,
        "DTLZ2_variables.x4": 0.58 - 0.01 * index,
        "DTLZ2_variables.x5": 0.42 + 0.01 * index,
    }


def make_scheduler(run_dir: Path) -> SlurmScheduler:
    return SlurmScheduler(
        config=SlurmRunnerConfig(
            job_name_prefix="aid2e_multi10",
            setup_commands=list(DEFAULT_SETUP_COMMANDS),
            submit_working_dir=str(run_dir),
            runtime_working_dir=str(REPO_ROOT),
            poll_interval=2,
        )
    )


def main() -> int:
    run_dir = REPO_ROOT / "experimental_tests" / "output" / (
        f"slurm_ten_simultaneous_jobs_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}"
    )
    run_dir.mkdir(parents=True, exist_ok=True)

    scheduler = make_scheduler(run_dir)
    job_definitions: List[Dict[str, Any]] = []
    expected_outputs: Dict[str, Path] = {}

    for index in range(10):
        design_point = build_dtlz2_point(index)
        job_name = f"dtlz2_design_{index}"
        design_path = run_dir / "designs" / f"{job_name}.json"
        output_path = run_dir / "results" / f"{job_name}.json"
        Trial(index=index, parameters=design_point, status="pending").save_to_json(design_path)

        job_definitions.append(
            {
                "name": job_name,
                "command": (
                    "python examples/dtlz2/schedulers/slurm_dtlz2_from_design_json.py "
                    f"--design {design_path} "
                    f"--output {output_path} "
                    f"--label {job_name} "
                    "--sleep-sec 0.6 "
                    "--repeat 3"
                ),
                "payload": {"execution_dir": str(run_dir / "runtime" / job_name)},
                "outputs": [{"path": str(output_path), "format": "json"}],
                "resources": {"time": "00:05:00"},
            }
        )
        expected_outputs[job_name] = output_path

    stage_id = scheduler.submit_stage(
        "ten_dtlz2_designs",
        job_definitions,
        parallelism_policy={"poll_interval": 1},
        working_dir=str(run_dir / "scheduler"),
    )

    history: List[Dict[str, Any]] = []
    while True:
        stage_status = scheduler.check_stage_status(stage_id)
        counts = Counter(job.status for job in stage_status.job_statuses or [])
        snapshot = {
            "timestamp_utc": datetime.now(UTC).isoformat(),
            "stage_status": stage_status.status,
            "completed_jobs": stage_status.completed_jobs,
            "total_jobs": stage_status.total_jobs,
            "status_counts": dict(counts),
        }
        history.append(snapshot)
        print(f"[ten-jobs] {snapshot}")
        if stage_status.status in {"completed", "failed", "cancelled"}:
            break
        time.sleep(1)

    result = scheduler.get_stage_results(stage_id)
    if not result.success:
        raise RuntimeError(f"Expected all 10 jobs to succeed, got: {result.error_message}")
    if len(result.job_statuses) != 10:
        raise RuntimeError(f"Expected 10 job statuses, got {len(result.job_statuses)}")
    if any(job.status != "completed" for job in result.job_statuses):
        raise RuntimeError("Expected all ten jobs to complete successfully")

    per_job_outputs = {}
    for job_status in result.job_statuses:
        if not job_status.outputs or "f1" not in job_status.outputs or "f2" not in job_status.outputs:
            raise RuntimeError(f"Missing objective outputs for job {job_status.job_id}: {job_status.outputs}")
        per_job_outputs[job_status.job_id] = job_status.outputs

    for job_name, output_path in expected_outputs.items():
        if not output_path.exists():
            raise RuntimeError(f"Expected output file missing for {job_name}: {output_path}")

    summary = {
        "stage_id": stage_id,
        "history": history,
        "jobs": [
            {
                "job_id": job_status.job_id,
                "status": job_status.status,
                "return_code": job_status.return_code,
                "slurm_job_id": (job_status.metrics or {}).get("slurm_job_id"),
                "outputs": job_status.outputs,
            }
            for job_status in result.job_statuses
        ],
        "design_files": sorted(str(path) for path in (run_dir / "designs").glob("*.json")),
        "result_files": sorted(str(path) for path in (run_dir / "results").glob("*.json")),
    }
    summary_path = run_dir / "run_slurm_ten_simultaneous_jobs.summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
