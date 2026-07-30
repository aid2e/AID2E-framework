#!/usr/bin/env python3
"""
Example: running one stage of an AID2E detector-optimization workflow.
This stage runner is invoked by the workflow commands in workflow.yml.
"""

import argparse
import contextlib
from pathlib import Path

from aid2e.utilities.epic_utils import EpicLayerConfig
from aid2e.utilities.workflows import JobContext, StackExecutionEngine, WorkflowSharedContext
from drich_utils import (
    apply_overlap_policy,
    build_analysis_arguments,
    build_reco_arguments,
    build_sim_arguments,
    load_drich_config,
    make_paths,
    sim_reco_files,
    stage_scan_work,
)


# Stage runner
def run_stack_job(layers, context):
    # This worker process reconstructs the minimum AID2E context needed by
    # StackExecutionEngine after DAGExecutor has already prepared geometry.
    workflow_context = WorkflowSharedContext(
        workflow_id=context["workflow_id"],
        parameters={"prepared_geometry_dir": str(context["prepared_geometry_dir"])},
    )
    job_context = JobContext(
        task_id=f"{context['stage']}:{context['run_name']}",
        job_id=context["run_name"],
        stage_id=context["stage"],
        workflow_id=context["workflow_id"],
        execution_dir=str(context["output_root"]),
        problem_config=context["problem"],
        workflow_context=workflow_context,
    )

    try:
        return StackExecutionEngine(
            engine_id=context["run_name"],
            stack_type="epic",
            layers=layers,
        ).execute(job_context)
    except Exception as error:
        payload = job_context.xcom_pull(job_context.task_id) or {}
        error.returncode = payload.get("returncode", 1)
        raise


def run_stack(context, layer_names):
    eval_config = context["eval_config"]
    layer_names = set(layer_names)

    # geo layer: checkOverlaps failures can become configured penalty metrics.
    if "geo" in layer_names:
        overlap_log = context["overlap_log"]
        penalty_file = context["penalty_file"]
        penalty_file.unlink(missing_ok=True)
        stack_layers = [
            EpicLayerConfig(
                layer="geo",
                inputs=[context["detector_xml_ref"]],
                outputs=[str(overlap_log)],
            )
        ]
        try:
            run_stack_job(stack_layers, context)
            return apply_overlap_policy(overlap_log, penalty_file, eval_config["failure_policy"]) or {"ok": 1.0}
        except Exception as error:
            return apply_overlap_policy(overlap_log, penalty_file, eval_config["failure_policy"], error=error) or {
                "ok": 1.0
            }

    npart = eval_config["npart"]
    particles = eval_config["particles"]
    trial_tag = context["trial_tag"]
    trial_xml = context["detector_xml_ref"]
    point, stage_particles = stage_scan_work(layer_names, context["job_index"], eval_config)

    stack_layers = []
    for particle in stage_particles:
        sim_file, reco_file = sim_reco_files(context["sim_dir"], npart, trial_tag, point, particle)
        if "sim" in layer_names:
            stack_layers.append(
                EpicLayerConfig(
                    layer="sim",
                    inputs=[],
                    outputs=[str(sim_file)],
                    arguments=["--compactFile", trial_xml, *build_sim_arguments(npart, point, particle)],
                    rule="{{command}} {{arguments}} {{inputs}} {{outputs}}",
                )
            )
        if "rec" in layer_names:
            stack_layers.append(
                EpicLayerConfig(
                    layer="rec",
                    inputs=[str(sim_file)],
                    outputs=[str(reco_file)],
                    arguments=build_reco_arguments(trial_xml),
                )
            )

    if "ana" in layer_names:
        analysis_binary = Path(context["config_path"]).parent / eval_config["analysis_executable"]
        analysis_output = (
            context["results_dir"]
            / f"recon_scan_{npart}_{trial_tag}_p_{point['p']}_eta_{point['eta_min']}_{point['eta_max']}.txt"
        )
        stack_layers.append(
            EpicLayerConfig(
                layer="ana",
                inputs=[
                    str(sim_reco_files(context["sim_dir"], npart, trial_tag, point, particle)[1])
                    for particle in particles
                ],
                outputs=[str(analysis_output)],
                arguments=build_analysis_arguments(point, eval_config),
                command=str(analysis_binary),
                rule="{{command}} {{inputs}} {{outputs}} {{arguments}}",
            )
        )

    run_stack_job(stack_layers, context)
    return {"ok": 1.0}


def evaluate_design_point(trial_index, output_dir, config_path, stage, job_index, prepared_geometry_dir=None):
    config_path, cfg, eval_config = load_drich_config(config_path)
    paths = make_paths(output_dir)
    for path in (paths.log_dir, paths.results_dir):
        path.mkdir(parents=True, exist_ok=True)

    trial_tag = str(trial_index)
    penalty_file = paths.log_dir / f"penalty_{trial_tag}.json"
    workflow_id = cfg.workflows.workflows[0].name

    layer_names = stage.split("_")
    if not all(layer_name in {"geo", "sim", "rec", "ana"} for layer_name in layer_names):
        raise ValueError(f"Unsupported stage: {stage}")
    if stage != "geo" and penalty_file.exists():
        return {"ok": 1.0}
    if prepared_geometry_dir is None:
        raise ValueError("--prepared-geometry-dir is required for stack stages")

    for path in (paths.log_dir, paths.sim_dir):
        path.mkdir(parents=True, exist_ok=True)

    run_name = f"{stage}_{trial_tag}_{job_index}"
    problem = cfg.problem
    with (
        (paths.log_dir / f"{run_name}.log").open("a") as log,
        contextlib.redirect_stdout(log),
        contextlib.redirect_stderr(log),
    ):
        # Activation sets EIC_SHELL/EPIC_INSTALL values used by EpicStack.
        problem.environment_config.activate()

    context = {
        "output_root": paths.output_root,
        "config_path": config_path,
        "workflow_id": workflow_id,
        "stage": stage,
        "job_index": job_index,
        "problem": problem,
        "eval_config": eval_config,
        "trial_tag": trial_tag,
        "run_name": run_name,
        "results_dir": paths.results_dir,
        "sim_dir": paths.sim_dir,
        "prepared_geometry_dir": Path(prepared_geometry_dir),
        "detector_xml_ref": "{{geometry_dir}}/${DETECTOR_CONFIG}.xml",
        "overlap_log": paths.log_dir / f"overlap_log_{trial_tag}.txt",
        "penalty_file": penalty_file,
    }
    return run_stack(context, layer_names)


# Main

def main(argv=None):
    parser = argparse.ArgumentParser(description="Run one detector worker stage")
    parser.add_argument("--trial-index", type=int, required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--config-path", required=True)
    parser.add_argument("--stage", required=True)
    parser.add_argument("--job-index", type=int, default=0)
    parser.add_argument("--prepared-geometry-dir")
    args = parser.parse_args(argv)

    evaluate_design_point(
        args.trial_index,
        args.output_dir,
        args.config_path,
        args.stage,
        args.job_index,
        args.prepared_geometry_dir,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
