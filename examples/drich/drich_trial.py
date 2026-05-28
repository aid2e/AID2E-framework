#!/usr/bin/env python3
"""
Example: run one complete dRICH trial with AID2E DAGExecutor.
This trial-level runner demonstrates the AID2E workflow inside one optimizer
trial: build a WorkflowDefinition, run it with DAGExecutor, and the
configured scheduler execute dRICH stage commands.
"""

import argparse
import contextlib
import json
import shlex
import sys
from pathlib import Path

from aid2e.utilities import build_scheduler_runtime_config
from aid2e.utilities.configurations import BranchDefinition, JobDefinition, StageDefinition, WorkflowDefinition
from aid2e.utilities.workflows import DAGExecutor
from drich_utils import load_drich_config


def load_trial_context(config_path, output_dir, trial_index):
    """Load the optimizer-written design point and prepare DAGExecutor paths."""

    config_path, cfg, eval_config = load_drich_config(config_path)
    output_root = Path(output_dir).resolve()
    trial_tag = f"{trial_index:03d}"
    params_path = output_root / "trial_scripts" / f"jobconfig_job{trial_index}.json"
    design_point = json.loads(params_path.read_text())

    cfg.problem.output_location = str(output_root / "trial_workflows" / "output")
    cfg.problem.work_location = str(output_root / "trial_workflows" / "work")
    return config_path, cfg, eval_config, output_root, trial_tag, design_point


# Build one trial workflow
def build_trial_workflow(cfg, config_path, eval_config, output_root, trial_index):
    """Create the one-trial DAG in the stage order from workflow.yml."""

    source_stages = cfg.workflows.workflows[0].branches[0].stages
    trial_tag = f"{trial_index:03d}"
    result_json = output_root / "log" / "results" / f"drich-out_{trial_tag}.json"

    def worker_command(stage_name, job_index=None):
        parts = [
            sys.executable,
            str(Path(__file__).with_name("drich_eval.py")),
            "--stage",
            stage_name,
            "--trial-index",
            str(trial_index),
            "--output-dir",
            str(output_root),
            "--config-path",
            str(config_path),
        ]
        if job_index is not None:
            parts.extend(["--job-index", str(job_index)])
        return " ".join(shlex.quote(part) for part in parts)

    # dRICH subjob counts depend on scan points and particles
    def job_count(stage_name):
        if stage_name == "sim_rec":
            return len(eval_config["scan_points"]) * len(eval_config["particles"])
        if stage_name == "ana":
            return len(eval_config["scan_points"])
        return 1

    def make_stage(source):
        count = job_count(source.name)
        outputs = [{"path": str(result_json), "format": "json"}] if source.name == "retrieve_results" else []
        jobs = [
            JobDefinition(
                name=f"drich_{source.name}_{job_index}" if count > 1 else f"drich_{source.name}",
                command=worker_command(source.name, job_index if count > 1 else None),
                resources=dict(source.scheduler.parameters) if source.scheduler else {},
                outputs=outputs,
            )
            for job_index in range(count)
        ]
        return StageDefinition(name=source.name, jobs=jobs, parallelism=source.parallelism)

    return WorkflowDefinition(
        name=f"drich_trial_{trial_tag}",
        branches=[BranchDefinition(name="main", stages=[make_stage(stage) for stage in source_stages])],
        objectives=[],
    )


# Run one trial workflow and collect results
def run_trial(config_path, output_dir, trial_index):
    """Execute one dRICH trial workflow and return its objective metrics."""

    config_path, cfg, eval_config, output_root, trial_tag, design_point = load_trial_context(
        config_path,
        output_dir,
        trial_index,
    )
    stage_log = output_root / "log" / "job_output" / f"trial_{trial_tag}.log"
    stage_log.parent.mkdir(parents=True, exist_ok=True)

    workflow = build_trial_workflow(cfg, config_path, eval_config, output_root, trial_index)
    with stage_log.open("a") as log, contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
        DAGExecutor(
            workflow=workflow,
            base_output_dir=str(output_root / "trial_workflows"),
            log_level="WARNING",
            problem_config=cfg.problem,
            scheduler_config=build_scheduler_runtime_config(cfg.scheduler),
        ).execute(design_point)

    result_path = output_root / "log" / "results" / f"drich-out_{trial_tag}.json"
    return json.loads(result_path.read_text())


# Main

def main(argv=None):
    parser = argparse.ArgumentParser(description="Run one dRICH trial workflow")
    parser.add_argument("--trial-index", type=int, required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--config-path", required=True)
    args = parser.parse_args(argv)

    run_trial(args.config_path, args.output_dir, args.trial_index)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
