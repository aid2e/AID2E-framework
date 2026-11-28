"""dRICH example workflow payloads and objective calculations."""

from pathlib import Path
import shlex

import numpy as np


# Trial paths and filenames


def sim_reco_files(sim_dir, npart, trial_tag, point, particle, chunk_index=None):
    """Return simulation and reconstruction file paths for one scan point."""
    tag = (
        f"{npart}_{trial_tag}_{particle}_p_{point['p']}_"
        f"eta_{point['eta_min']}_{point['eta_max']}"
    )
    if chunk_index is not None:
        tag += f"_chunk_{chunk_index}"
    return Path(sim_dir) / f"scan_{tag}.root", Path(sim_dir) / f"recon_scan_{tag}.root"


def analysis_result_file(results_dir, npart, trial_tag, point):
    """Return the analysis text output for one scan point."""
    return (
        Path(results_dir)
        / f"recon_scan_{npart}_{trial_tag}_p_{point['p']}_"
        f"eta_{point['eta_min']}_{point['eta_max']}.txt"
    )


def _trial_context(problem_config, workflow_context):
    """Return inputs from the shared workflow context."""
    if problem_config is None:
        raise ValueError("dRICH payloads require problem_config")
    if problem_config.evaluation_config is None:
        raise ValueError("dRICH payloads require problem.evaluation_config")

    eval_config = problem_config.evaluation_config
    trial_index = workflow_context.get("trial_index")
    if trial_index is None:
        raise ValueError("dRICH payloads require trial_index")
    output_dir = Path(workflow_context["output_dir"])
    paths = {
        "results_dir": output_dir / "ana",
        "sim_dir": output_dir / "sim_rec",
    }
    return eval_config, trial_index, paths


# Objective aggregation


def aggregate_objectives(*, problem_config, workflow_context, **_):
    """Return objectives for a framework objective-plan step."""
    eval_config, trial_index, paths = _trial_context(
        problem_config,
        workflow_context,
    )
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
        raise RuntimeError(f"NaN objective for trial {trial_index}")

    return metrics


# Workflow payloads


def sim_rec_payloads(*, problem_config, workflow_context, **_):
    """Return payload records for simulation/reconstruction jobs."""
    eval_config, trial_index, paths = _trial_context(
        problem_config,
        workflow_context,
    )
    trial_tag = str(trial_index)
    particle_count = eval_config["npart"]
    events_per_job = eval_config.get("events_per_job", particle_count)
    for name, value in (("npart", particle_count), ("events_per_job", events_per_job)):
        if type(value) is not int or value <= 0:
            raise ValueError(f"{name} must be a positive integer")
    seed = eval_config.get("simulation_seed", 1)
    if type(seed) is not int or seed <= 0:
        raise ValueError("simulation_seed must be a positive integer")
    n_chunks = (particle_count + events_per_job - 1) // events_per_job
    jobs_per_trial = (
        n_chunks * len(eval_config["scan_points"]) * len(eval_config["particles"])
    )
    records = []
    for scan_index, point in enumerate(eval_config["scan_points"]):
        for particle in eval_config["particles"]:
            for chunk_index in range(n_chunks):
                sim_file, reco_file = sim_reco_files(
                    paths["sim_dir"],
                    particle_count,
                    trial_tag,
                    point,
                    particle,
                    chunk_index if n_chunks > 1 else None,
                )
                records.append(
                    {
                        "npart": min(events_per_job, particle_count - chunk_index * events_per_job),
                        "scan_index": scan_index,
                        "seed": seed + trial_index * jobs_per_trial + len(records),
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
    """Return payload records for analysis jobs."""
    eval_config, trial_index, paths = _trial_context(
        problem_config,
        workflow_context,
    )
    trial_tag = str(trial_index)
    particle_count = eval_config["npart"]
    if sorted(eval_config["particles"]) != ["kaon+", "pi+"]:
        raise ValueError("dRICH analysis requires particles pi+ and kaon+")
    sim_records = sim_rec_payloads(
        problem_config=problem_config, workflow_context=workflow_context
    )

    records = []
    for scan_index, point in enumerate(eval_config["scan_points"]):
        reco_files = [
            [
                record["reco_file"]
                for record in sim_records
                if record["scan_index"] == scan_index and record["particle"] == particle
            ]
            for particle in ("pi+", "kaon+")
        ]
        records.append(
            {
                "radiator": point["radiator"],
                "bootstrap_samples": eval_config["bootstrap_samples"],
                "nbootstraps": eval_config["nbootstraps"],
                "ana_inputs": shlex.join(path for pair in zip(*reco_files, strict=True) for path in pair),
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
