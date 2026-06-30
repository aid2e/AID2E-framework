#!/usr/bin/env python3
"""
Example: running one stage of the AID2E workflow for dRICH optimization.
This stage runner is invoked by the workflow commands in workflow.yml.
"""

import argparse
import contextlib
import json
import subprocess
from pathlib import Path

from aid2e.utilities.epic_utils import EpicJobDefinition, EpicLayerConfig
from aid2e.utilities.workflows import JobContext, StackExecutionEngine, WorkflowSharedContext
from drich_utils import (
    apply_overlap_policy,
    build_sim_arguments,
    collect_objectives,
    load_drich_config,
)


# Stage runner
def run_stack_job(job, context):
    workflow_context = WorkflowSharedContext()
    workflow_context.parameters["prepared_geometry_dir"] = str(context["prepared_geometry_dir"])
    job_context = JobContext(
        job_id=context["run_name"],
        stage_id=context["stage"],
        workflow_id="drich_eval",
        design_point=context["design_point"],
        execution_dir=str(context["output_root"]),
        output_dir=str(context["output_root"]),
        problem_config=context["problem"],
        workflow_context=workflow_context,
    )

    try:
        StackExecutionEngine(
            job_id=context["run_name"],
            stack_type="epic",
            layers=job.layers,
        ).execute(job_context)
    except Exception as error:
        payload = job_context.xcom.get(
            f"{context['run_name']}:return_value",
            {"stdout": "", "stderr": str(error), "returncode": 1},
        )
        raise subprocess.CalledProcessError(
            payload.get("returncode", 1),
            context["run_name"],
            output=payload.get("stdout", ""),
            stderr=payload.get("stderr", str(error)),
        ) from error


# Geometry stage with overlap policy
def run_geo(context):
    overlap_log = context["overlap_log"]
    penalty_file = context["penalty_file"]
    penalty_file.unlink(missing_ok=True)

    overlap_job = EpicJobDefinition(
        name="drich_geo",
        layers=[
            EpicLayerConfig(
                name="geo",
                inputs=[context["trial_epic_xml_ref"]],
                outputs=[str(overlap_log)],
            )
        ],
    )

    try:
        run_stack_job(overlap_job, context)
        return apply_overlap_policy(overlap_log, penalty_file, context["eval_config"]) or {"ok": 1.0}
    except subprocess.CalledProcessError as error:
        return apply_overlap_policy(overlap_log, penalty_file, context["eval_config"], error=error) or {"ok": 1.0}


# Run ePIC stack layers (rec, sim, ana)

def run_stack(context, layer_names):
    eval_config = context["eval_config"]
    layer_names = set(layer_names)
    npart = eval_config["npart"]
    particles = eval_config["particles"]
    scan_points = eval_config["scan_points"]
    trial_tag = context["trial_tag"]
    trial_xml = context["trial_epic_xml_ref"]
    analysis_binary = Path(context["config_path"]).parent / eval_config["analysis_executable"]

    def sim_reco_files(point, particle):
        tag = f"{npart}_{trial_tag}_{particle}_p_{point['p']}_eta_{point['eta_min']}_{point['eta_max']}"
        return context["sim_dir"] / f"scan_{tag}.root", context["sim_dir"] / f"recon_scan_{tag}.root"

    def sim_layer(point, particle):
        sim_file, _ = sim_reco_files(point, particle)
        return EpicLayerConfig(
            name="sim",
            inputs=[],
            outputs=[str(sim_file)],
            arguments=build_sim_arguments(npart, point, particle),
            rule=f"{{command}} --compactFile {trial_xml} {{arguments}} {{inputs}} {{outputs}}",
        )

    def rec_layer(point, particle):
        sim_file, reco_file = sim_reco_files(point, particle)
        return EpicLayerConfig(
            name="rec",
            inputs=[str(sim_file)],
            outputs=[str(reco_file)],
            arguments=[
                f"-Pdd4hep:xml_files={trial_xml}",
                f"-Ppodio:output_include_collections={eval_config['reco_collections']}",
            ],
        )

    def ana_layer(point):
        return EpicLayerConfig(
            name="ana",
            inputs=[str(sim_reco_files(point, particle)[1]) for particle in particles],
            outputs=[
                str(
                    context["results_dir"]
                    / f"recon_scan_{npart}_{trial_tag}_p_{point['p']}_eta_{point['eta_min']}_{point['eta_max']}.txt"
                )
            ],
            arguments=[str(point["radiator"]), str(eval_config["bootstrap_samples"]), str(eval_config["nbootstraps"])],
            command=str(analysis_binary),
            rule="{command} {inputs} {outputs} {arguments}",
        )

    if "ana" in layer_names:
        point = scan_points[context["job_index"]]
        stage_particles = particles
    else:
        point_index, particle_index = divmod(context["job_index"], len(particles))
        point = scan_points[point_index]
        stage_particles = [particles[particle_index]]

    stack_layers = []
    for particle in stage_particles:
        if "sim" in layer_names:
            stack_layers.append(sim_layer(point, particle))
        if "rec" in layer_names:
            stack_layers.append(rec_layer(point, particle))
    if "ana" in layer_names:
        stack_layers.append(ana_layer(point))

    run_stack_job(EpicJobDefinition(name=f"drich_{context['stage']}", layers=stack_layers), context)
    return {"ok": 1.0}


def evaluate_design_point(design_point, trial_index, output_dir, config_path, stage, job_index, prepared_geometry_dir=None):
    config_path, cfg, eval_config = load_drich_config(config_path)
    output_root = Path(output_dir).resolve()
    log_dir = output_root / "log"
    results_dir = log_dir / "results"
    overlaps_dir = log_dir / "overlaps"
    for path in (results_dir, overlaps_dir):
        path.mkdir(parents=True, exist_ok=True)

    trial_tag = f"{trial_index:03d}"
    penalty_file = overlaps_dir / f"penalty_{trial_tag}.json"

    if stage == "retrieve_results":
        if penalty_file.exists():
            return collect_objectives(
                results_dir,
                trial_tag=trial_tag,
                failed_objectives=eval_config["failed_objectives"],
                penalty=True,
            )
        return collect_objectives(
            results_dir,
            eval_config["npart"],
            trial_tag,
            eval_config["scan_points"],
            eval_config["failed_objectives"],
            eval_config["failure_policy"],
        )

    if stage != "geo" and penalty_file.exists():
        return {"ok": 1.0}
    if prepared_geometry_dir is None:
        raise ValueError("--prepared-geometry-dir is required for dRICH stack stages")

    layer_names = stage.split("_")
    if stage != "geo" and not all(layer_name in {"sim", "rec", "ana"} for layer_name in layer_names):
        raise ValueError(f"Unsupported stage: {stage}")

    sim_dir = log_dir / "sim_files"
    job_output_dir = log_dir / "job_output"
    for path in (sim_dir, job_output_dir):
        path.mkdir(parents=True, exist_ok=True)

    run_name = f"{stage}_{trial_tag}_{job_index}"
    problem = cfg.problem
    with (
        (job_output_dir / f"{run_name}.log").open("a") as log,
        contextlib.redirect_stdout(log),
        contextlib.redirect_stderr(log),
    ):
        problem.environment_config.activate()

    context = {
        "design_point": design_point,
        "output_root": output_root,
        "config_path": config_path,
        "stage": stage,
        "job_index": job_index,
        "problem": problem,
        "eval_config": eval_config,
        "trial_tag": trial_tag,
        "run_name": run_name,
        "results_dir": results_dir,
        "sim_dir": sim_dir,
        "prepared_geometry_dir": Path(prepared_geometry_dir),
        "trial_epic_xml_ref": "${DETECTOR_PATH}/${DETECTOR_CONFIG}.xml",
        "overlap_log": overlaps_dir / f"overlap_log_{trial_tag}.txt",
        "penalty_file": penalty_file,
    }
    return run_geo(context) if stage == "geo" else run_stack(context, layer_names)


# Main

def main(argv=None):
    parser = argparse.ArgumentParser(description="Run one dRICH worker stage")
    parser.add_argument("--trial-index", type=int, required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--config-path", required=True)
    parser.add_argument("--stage", required=True)
    parser.add_argument("--job-index", type=int, default=0)
    parser.add_argument("--prepared-geometry-dir")
    args = parser.parse_args(argv)

    output_root = Path(args.output_dir)
    design_file = output_root / "trial_scripts" / f"jobconfig_job{args.trial_index}.json"
    metrics = evaluate_design_point(
        json.loads(design_file.read_text()),
        args.trial_index,
        args.output_dir,
        args.config_path,
        args.stage,
        args.job_index,
        args.prepared_geometry_dir,
    )

    if args.stage == "retrieve_results":
        out_path = output_root / "log" / "results" / f"drich-out_{args.trial_index:03d}.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(metrics, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
