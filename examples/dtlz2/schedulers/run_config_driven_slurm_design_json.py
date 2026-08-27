#!/usr/bin/env python
"""Run the config-driven Slurm design-JSON workflow example end to end."""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SRC_ROOT = REPO_ROOT / "src"
for candidate in (str(REPO_ROOT), str(SRC_ROOT)):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

from aid2e.utilities import build_workflow_executor_from_config
from aid2e.utilities.configurations import load_config


def main() -> int:
    config_path = REPO_ROOT / "examples" / "dtlz2" / "schedulers" / "workflow_example_slurm_design_json.yml"
    run_dir = REPO_ROOT / "experimental_tests" / "output" / (
        f"slurm_design_json_example_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}"
    )
    run_dir.mkdir(parents=True, exist_ok=True)
    (REPO_ROOT / "experimental_tests" / "output" / "slurm_v2_output").mkdir(parents=True, exist_ok=True)
    (REPO_ROOT / "experimental_tests" / "output" / "slurm_v2_work").mkdir(parents=True, exist_ok=True)

    config = load_config(str(config_path))
    if config.scheduler is None or config.workflows is None:
        raise RuntimeError("Expected scheduler and workflows sections in the Slurm design-JSON example")

    executor = build_workflow_executor_from_config(
        config.workflows,
        problem_cfg=config.problem,
        scheduler_cfg=config.scheduler,
        workflow_name="dtlz2_slurm_design_json_eval",
        base_output_dir=str(run_dir),
        log_level="INFO",
    )

    design_point = {
        "DTLZ2_variables.x1": 0.22,
        "DTLZ2_variables.x2": 0.61,
        "DTLZ2_variables.x3": 0.41,
        "DTLZ2_variables.x4": 0.56,
        "DTLZ2_variables.x5": 0.44,
    }
    objectives = executor.execute(design_point)
    if not objectives or "f1" not in objectives or "f2" not in objectives:
        raise RuntimeError(f"Expected f1/f2 objectives, got: {objectives}")

    design_files = sorted(str(path) for path in executor.work_dir.glob("*/*/design_point.json"))
    result_files = sorted(str(path) for path in executor.output_dir.glob("*/*/objectives.json"))
    stdout_logs = sorted(str(path) for path in executor.output_dir.glob("*/*/stdout.log"))
    stderr_logs = sorted(str(path) for path in executor.output_dir.glob("*/*/stderr.log"))
    if not design_files:
        raise RuntimeError("Expected the Slurm workflow to materialize at least one design_point.json file")
    if not result_files:
        raise RuntimeError("Expected the Slurm workflow to produce at least one objectives.json file")

    summary = {
        "config_path": str(config_path),
        "design_point": design_point,
        "objectives": objectives,
        "work_dir": str(executor.work_dir),
        "output_dir": str(executor.output_dir),
        "design_files": design_files,
        "result_files": result_files,
        "stdout_logs": stdout_logs,
        "stderr_logs": stderr_logs,
        "global_xcom_keys": sorted(executor.global_xcom.keys()),
    }
    summary_path = run_dir / "run_config_driven_slurm_design_json.summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
