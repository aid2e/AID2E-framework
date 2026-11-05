#!/usr/bin/env python3
"""Run DTLZ2 evaluations directly through the JobLib scheduler registry.

Run: python examples/dtlz2/python_api/dtlz2_scheduler.py
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from aid2e.schedulers import get_scheduler
from aid2e.utilities.configurations.scheduler_config import SchedulerConfiguration
from examples.dtlz2.dtlz2_evaluator import dtlz2_both_objectives


def example_stage_execution():
    """Configure JobLib, retrieve it from the registry, and run three designs."""
    scheduler_config = SchedulerConfiguration(
        runner_type="JobLibRunner",
        parameters={"n_jobs": 3, "backend": "threading"},
    )
    scheduler_class = get_scheduler("joblib")
    scheduler = scheduler_class(config=scheduler_config.parse_runner_params())

    jobs = [
        {
            "name": f"design_{index}",
            "function": dtlz2_both_objectives,
            "params": {"x": [x1] + [0.5] * 9},
        }
        for index, x1 in enumerate((0.2, 0.5, 0.8))
    ]
    result = scheduler.run_stage(
        stage_name="evaluate_designs",
        job_definitions=jobs,
        parallelism_policy={"max_concurrent": 3},
    )

    print(f"Scheduler: {scheduler_class.__name__}")
    print(f"Stage: {result.stage_name}")
    print(f"Success: {result.success}")
    print(f"Jobs completed: {sum(status.status == 'completed' for status in result.job_statuses)}")
    for status in result.job_statuses:
        print(f"  {status.job_id}: {status.status} (exit code: {status.return_code})")
        print(f"    Objectives: {status.outputs}")
    return result


if __name__ == "__main__":
    raise SystemExit(0 if example_stage_execution().success else 1)
