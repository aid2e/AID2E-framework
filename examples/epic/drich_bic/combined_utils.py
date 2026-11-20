"""dRICH and BIC example workflow payloads and objective calculations."""

from pathlib import Path
from itertools import product
import json
import shlex

import numpy as np


# dRICH payloads

# sim


def drich_sim_payloads(*, problem_config, workflow_context, **_):
    """Return dRICH particle simulation payloads."""
    eval_config = problem_config.evaluation_config
    trial_tag = str(workflow_context["trial_index"])
    output_dir = Path(workflow_context["output_dir"]) / "drich" / "sim"
    output_dir.mkdir(parents=True, exist_ok=True)
    records = []
    for scan_index, point in enumerate(eval_config["drich_scan_points"]):
        for particle in eval_config["drich_particles"]:
            tag = (
                f"{trial_tag}_{particle}_p_{point['p']}_"
                f"eta_{point['eta_min']}_{point['eta_max']}"
            )
            records.append(
                {
                    "scan_index": scan_index,
                    "particle": particle,
                    "sim_file": str(output_dir / f"scan_{tag}.root"),
                    "sim_arguments": shlex.join([
                        "-G",
                        "--gun.etaMax", str(point["eta_max"]),
                        "--gun.etaMin", str(point["eta_min"]),
                        "--gun.momentumMax", f"{point['p']}*GeV",
                        "--gun.momentumMin", f"{point['p']}*GeV",
                        "--gun.particle", particle,
                        "--gun.multiplicity", "1",
                        "--gun.position", "0.0 0.0 0.0",
                        "--gun.direction", "0.0 0.0 1.0",
                        "--gun.distribution", "eta",
                        "--gun.phiMin", "0",
                        "--gun.phiMax", "6.2831853",
                    ]),
                }
            )
    return records


# rec


def drich_rec_payloads(*, problem_config, workflow_context, **_):
    """Return dRICH reconstruction payloads."""
    output_dir = Path(workflow_context["output_dir"]) / "drich" / "rec"
    output_dir.mkdir(parents=True, exist_ok=True)
    sim_records = drich_sim_payloads(
        problem_config=problem_config, workflow_context=workflow_context
    )
    records = []
    for record in sim_records:
        records.append(
            {
                **record,
                "reco_file": str(output_dir / f"recon_{Path(record['sim_file']).name}"),
                "rec_arguments": "-Pnthreads=1 -Ppodio:output_include_collections=DRICHHits,MCParticles,DRICHRawHits,DRICHRawHitsAssociations,DRICHAerogelTracks,DRICHGasTracks,DRICHAerogelIrtCherenkovParticleID,DRICHGasIrtCherenkovParticleID,DRICHMergedIrtCherenkovParticleID",
            }
        )
    return records


# ana


def drich_ana_payloads(*, problem_config, workflow_context, **_):
    """Return payload records for dRICH analysis jobs."""
    eval_config = problem_config.evaluation_config
    trial_tag = str(workflow_context["trial_index"])
    output_dir = Path(workflow_context["output_dir"]) / "drich" / "ana"
    output_dir.mkdir(parents=True, exist_ok=True)
    if sorted(eval_config["drich_particles"]) != ["kaon+", "pi+"]:
        raise ValueError("dRICH analysis requires particles pi+ and kaon+")
    rec_records = drich_rec_payloads(
        problem_config=problem_config, workflow_context=workflow_context
    )

    records = []
    for scan_index, point in enumerate(eval_config["drich_scan_points"]):
        reco_files = [
            record["reco_file"]
            for particle in ("pi+", "kaon+")
            for record in rec_records
            if record["scan_index"] == scan_index and record["particle"] == particle
        ]
        records.append(
            {
                "radiator": point["radiator"],
                "ana_inputs": shlex.join(reco_files),
                "analysis_output": str(
                    output_dir / f"recon_scan_{trial_tag}_p_{point['p']}_"
                    f"eta_{point['eta_min']}_{point['eta_max']}.txt"
                ),
            }
        )
    return records


# BIC payloads

# sim


def bic_sim_payloads(*, problem_config, workflow_context, **_):
    """Return BIC photon simulation payloads."""
    eval_config = problem_config.evaluation_config
    output_dir = Path(workflow_context["output_dir"]) / "bic" / "sim"
    output_dir.mkdir(parents=True, exist_ok=True)
    records = []
    for index, (particle, energy) in enumerate(product(
        eval_config["bic_particles"], eval_config["bic_energies"]
    )):
        records.append(
            {
                "particle": particle,
                "sim_file": str(output_dir / f"central_photons_bin{index}.edm4hep.root"),
                "sim_arguments": shlex.join([
                    "-G",
                    "--gun.energy", f"{energy}*GeV",
                    "--gun.multiplicity", "1",
                    "--gun.position", "0.0 0.0 0.0",
                    "--gun.direction", "0.0 0.0 1.0",
                    "--gun.particle", particle,
                    "--gun.distribution", "cos(theta)",
                    "--gun.thetaMin", "45*degree",
                    "--gun.thetaMax", "135*degree",
                ]),
            }
        )
    return records


# rec


def bic_rec_payloads(*, problem_config, workflow_context, **_):
    """Return BIC reconstruction payloads, merging simulation files first."""
    output_dir = Path(workflow_context["output_dir"]) / "bic" / "rec"
    output_dir.mkdir(parents=True, exist_ok=True)
    sim_file = output_dir.parent / "sim" / "central_photons.edm4hep.root"
    sim_records = bic_sim_payloads(
        problem_config=problem_config, workflow_context=workflow_context
    )
    bic_files = [record["sim_file"] for record in sim_records]
    records = [
        {
            "sim_file": str(sim_file),
            "reco_file": str(output_dir / "central_photons.edm4eic.root"),
            "rec_arguments": "-Pnthreads=1 -Peicrecon:LogLevel=debug",
            "merge_command": shlex.join(["hadd", "-f", str(sim_file), *bic_files]),
        }
    ]
    return records


# ana


def bic_ana_payloads(*, workflow_context, **_):
    """Return BIC analysis payloads."""
    output_dir = Path(workflow_context["output_dir"]) / "bic" / "ana"
    output_dir.mkdir(parents=True, exist_ok=True)
    records = [
        {
            "job_name": "bic_ana",
            "analysis_output": str(output_dir / "central_photons.hist.root"),
            "analysis_arguments": "-c phi -s 22",
        }
    ]
    return records


# Collect objectives


def collect_objectives(*, problem_config, workflow_context, extra_args, **_):
    """Return objectives for a framework objective-plan step."""
    # dRICH separation, acceptance, and uncertainties.
    eval_config = problem_config.evaluation_config
    trial_index = workflow_context["trial_index"]
    scan_points = eval_config["drich_scan_points"]
    ana_records = drich_ana_payloads(
        problem_config=problem_config, workflow_context=workflow_context
    )
    results = np.array([np.loadtxt(record["analysis_output"]) for record in ana_records])
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

    # BIC photon phi resolution.
    with open(extra_args["file"].replace(".root", ".json"), "r") as f:
        metrics[extra_args["key"]] = json.load(f)[extra_args["key"]]
    return metrics
