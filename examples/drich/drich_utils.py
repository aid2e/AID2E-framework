"""dRICH-specific workflow payloads and objective calculations."""

import json
import re
from pathlib import Path

import numpy as np


# Trial paths and filenames


def sim_reco_files(sim_dir, npart, trial_tag, point, particle):
    """Return dRICH simulation and reconstruction file paths for one scan point."""
    tag = (
        f"{npart}_{trial_tag}_{particle}_p_{point['p']}_"
        f"eta_{point['eta_min']}_{point['eta_max']}"
    )
    return Path(sim_dir) / f"scan_{tag}.root", Path(sim_dir) / f"recon_scan_{tag}.root"


def analysis_result_file(results_dir, npart, trial_tag, point):
    """Return the dRICH analysis text output for one scan point."""
    return (
        Path(results_dir)
        / f"recon_scan_{npart}_{trial_tag}_p_{point['p']}_"
        f"eta_{point['eta_min']}_{point['eta_max']}.txt"
    )


def _trial_context(problem_config, workflow_context):
    """Return dRICH inputs from the shared workflow context."""
    if problem_config is None:
        raise ValueError("dRICH payloads require problem_config")
    if problem_config.evaluation_config is None:
        raise ValueError("dRICH payloads require problem.evaluation_config")

    eval_config = problem_config.evaluation_config
    trial_index = workflow_context.get("trial_index")
    if trial_index is None:
        raise ValueError("dRICH payloads require trial_index")
    paths = {
        "results_dir": Path(workflow_context["results_dir"]),
        "sim_dir": Path(workflow_context["artifacts_dir"]),
        "overlap_log": Path(workflow_context["log_dir"])
        / f"overlap_log_{trial_index}.txt",
        "penalty_file": Path(workflow_context["log_dir"])
        / f"penalty_{trial_index}.json",
    }
    return eval_config, trial_index, paths


# Objective aggregation and failure policy


def apply_overlap_policy(paths, eval_config):
    """Apply the dRICH geometry-overlap policy and write a penalty marker."""
    penalty_file = paths["penalty_file"]
    if penalty_file.exists():
        return

    failure_policy = eval_config["failure_policy"]
    if failure_policy not in {"penalty", "fail"}:
        raise ValueError(f"Unsupported dRICH failure policy: {failure_policy}")

    overlap_log = paths["overlap_log"]
    overlap_text = overlap_log.read_text() if overlap_log.exists() else ""
    match = re.search(
        r"Number of illegal overlaps/extrusions\s*:\s*(\d+)",
        overlap_text,
    )
    overlaps = int(match.group(1)) if match is not None else None

    if overlaps is None:
        message = "Overlap check failed: no overlap count found"
        payload = {"reason": "checkOverlaps did not print overlap count"}
    elif overlaps:
        message = f"Overlap check failed: overlaps={overlaps}"
        payload = {"overlaps": overlaps}
    else:
        return

    if failure_policy == "fail":
        raise RuntimeError(message)
    penalty_file.write_text(json.dumps({"penalty": True, **payload}, indent=2))


def aggregate_objectives(*, problem_config, workflow_context, **_):
    """Return dRICH objectives for a framework objective-plan step."""
    eval_config, trial_index, paths = _trial_context(
        problem_config,
        workflow_context,
    )
    apply_overlap_policy(paths, eval_config)
    failed_metrics = {
        key: value
        for name, failed_value in eval_config["failed_objectives"].items()
        for key, value in ((name, float(failed_value)), (f"{name}_err", 0.0))
    }
    if paths["penalty_file"].exists():
        return failed_metrics

    particle_count = eval_config["npart"]
    scan_points = eval_config["scan_points"]
    results = np.array(
        [
            np.loadtxt(
                analysis_result_file(
                    paths["results_dir"],
                    particle_count,
                    str(trial_index),
                    point,
                )
            )
            for point in scan_points
        ]
    )
    momenta = np.array([point["p"] for point in scan_points])
    metric_values = (
        ("piKsep_etalow", results[momenta == 15, 2], results[momenta == 15, 3]),
        ("piKsep_etahigh", results[momenta == 45, 2], results[momenta == 45, 3]),
        ("acceptance", results[1:, 0], results[1:, 1]),
    )
    metrics = {}
    for name, values, errors in metric_values:
        metrics[name] = float(np.mean(values))
        metrics[f"{name}_err"] = float(np.linalg.norm(errors) / len(errors))

    if any(np.isnan(value) for value in metrics.values()):
        if eval_config["failure_policy"] != "penalty":
            raise RuntimeError(
                f"objective merge failed: NaN objective for trial {trial_index}"
            )
        return {name: failed_metrics.get(name, value) for name, value in metrics.items()}

    return metrics


# Workflow payloads


def sim_rec_payloads(*, problem_config, workflow_context, **_):
    """Return payload records for dRICH simulation/reconstruction jobs."""
    eval_config, trial_index, paths = _trial_context(
        problem_config,
        workflow_context,
    )
    apply_overlap_policy(paths, eval_config)
    if paths["penalty_file"].exists():
        return []

    trial_tag = str(trial_index)
    particle_count = eval_config["npart"]
    records = []
    for point in eval_config["scan_points"]:
        for particle in eval_config["particles"]:
            sim_file, reco_file = sim_reco_files(
                paths["sim_dir"],
                particle_count,
                trial_tag,
                point,
                particle,
            )
            records.append(
                {
                    "npart": particle_count,
                    "particle": particle,
                    "p": point["p"],
                    "eta_min": point["eta_min"],
                    "eta_max": point["eta_max"],
                    "sim_file": str(sim_file),
                    "reco_file": str(reco_file),
                }
            )
    return records


def ana_payloads(*, problem_config, workflow_context, **_):
    """Return payload records for dRICH analysis jobs."""
    eval_config, trial_index, paths = _trial_context(
        problem_config,
        workflow_context,
    )
    apply_overlap_policy(paths, eval_config)
    if paths["penalty_file"].exists():
        return []

    trial_tag = str(trial_index)
    particle_count = eval_config["npart"]

    records = []
    for point in eval_config["scan_points"]:
        records.append(
            {
                "radiator": point["radiator"],
                "bootstrap_samples": eval_config["bootstrap_samples"],
                "nbootstraps": eval_config["nbootstraps"],
                "ana_inputs": " ".join(
                    str(
                        sim_reco_files(
                            paths["sim_dir"],
                            particle_count,
                            trial_tag,
                            point,
                            particle,
                        )[1]
                    )
                    for particle in eval_config["particles"]
                ),
                "analysis_output": str(
                    analysis_result_file(
                        paths["results_dir"],
                        particle_count,
                        trial_tag,
                        point,
                    )
                ),
            }
        )
    return records
