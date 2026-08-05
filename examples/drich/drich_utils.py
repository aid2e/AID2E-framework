"""dRICH optimization utilities and AID2E workflow components."""

import json
import re
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import uncertainties

from aid2e.utilities.configurations import load_config, load_raw_config


def make_paths(output_dir):
    """Return the shared output directories used by the dRICH example."""

    output_root = Path(output_dir).resolve()
    log_dir = output_root / "log"
    return SimpleNamespace(
        output_root=output_root,
        log_dir=log_dir,
        results_dir=log_dir / "results",
        sim_dir=log_dir / "sim_files",
    )


def build_sim_arguments(npart, point, particle):
    """Return npsim gun arguments for one dRICH scan point and particle."""

    return [
        "-G",
        f"-N {npart}",
        f"--gun.etaMax {point['eta_max']}",
        f"--gun.etaMin {point['eta_min']}",
        "--gun.phiMin 0",
        "--gun.phiMax 6.2831853",
        f"--gun.momentumMax '{point['p']}*GeV'",
        f"--gun.momentumMin '{point['p']}*GeV'",
        f"--gun.particle {particle}",
        "--gun.distribution eta",
    ]


def build_reco_arguments(trial_xml):
    """Return dRICH reconstruction arguments."""

    reco_collections = (
        "DRICHHits,MCParticles,DRICHRawHits,DRICHRawHitsAssociations,"
        "DRICHAerogelTracks,DRICHGasTracks,"
        "DRICHAerogelIrtCherenkovParticleID,DRICHGasIrtCherenkovParticleID,"
        "DRICHMergedIrtCherenkovParticleID"
    )
    return [
        f"-Pdd4hep:xml_files={trial_xml}",
        f"-Ppodio:output_include_collections={reco_collections}",
    ]


def build_analysis_arguments(point, eval_config):
    """Return dRICH analysis arguments for one scan point."""

    return [
        str(point["radiator"]),
        str(eval_config["bootstrap_samples"]),
        str(eval_config["nbootstraps"]),
    ]


def sim_reco_files(sim_dir, npart, trial_tag, point, particle):
    """Return dRICH simulation and reconstruction file paths for one scan point."""

    tag = f"{npart}_{trial_tag}_{particle}_p_{point['p']}_eta_{point['eta_min']}_{point['eta_max']}"
    return Path(sim_dir) / f"scan_{tag}.root", Path(sim_dir) / f"recon_scan_{tag}.root"


def stage_scan_work(layer_names, job_index, eval_config):
    """Map one worker job index to the dRICH scan point and particles it should run."""

    particles = eval_config["particles"]
    scan_points = eval_config["scan_points"]
    if "ana" in layer_names:
        return scan_points[job_index], particles

    point_index, particle_index = divmod(job_index, len(particles))
    return scan_points[point_index], [particles[particle_index]]


def apply_overlap_policy(overlap_log, penalty_file, failure_policy, ok_value=0, error=None):
    """Apply overlap failure policy and return a penalty marker if needed."""

    overlap_log = Path(overlap_log)
    penalty_file = Path(penalty_file)
    overlap_text = overlap_log.read_text() if overlap_log.exists() else ""
    match = re.search(r"Number of illegal overlaps/extrusions\s*:\s*(\d+)", overlap_text)
    overlaps = int(match.group(1)) if match is not None else None
    use_penalty = failure_policy == "penalty"

    def penalty(**payload):
        # Later stages check this marker and skip expensive work for failed geometry.
        penalty_file.parent.mkdir(parents=True, exist_ok=True)
        penalty_file.write_text(json.dumps({"penalty": True, **payload}, indent=2))
        return {"ok": 1.0}

    if error is not None:
        if not use_penalty:
            raise error
        payload = {"reason": "checkOverlaps command failed", "return_code": getattr(error, "returncode", 1)}
        if overlaps is not None and overlaps != ok_value:
            payload = {"overlaps": overlaps}
        return penalty(**payload)

    if overlaps is None:
        if use_penalty:
            return penalty(reason="checkOverlaps did not print overlap count")
        raise RuntimeError("Overlap check failed: no overlap count found")

    if overlaps != ok_value:
        if use_penalty:
            return penalty(overlaps=overlaps)
        raise RuntimeError(f"Overlap check failed: overlaps={overlaps}")

    return None


def compute_drich_objectives(
    results_dir,
    trial_tag,
    eval_config,
    penalty=False,
):
    """Compute dRICH objective metrics from per-scan analysis outputs."""

    failed_metrics = {
        key: metric_value
        for name, failed_value in eval_config["failed_objectives"].items()
        for key, metric_value in ((name, float(failed_value)), (f"{name}_sem", 0.0))
    }
    if penalty:
        return failed_metrics

    results_dir = Path(results_dir)
    npart = eval_config["npart"]
    nsigma, eff, momenta = [], [], []
    # dRICHAna_bootstrap writes one text file per scan point.
    for point in eval_config["scan_points"]:
        p, eta_min, eta_max = point["p"], point["eta_min"], point["eta_max"]
        result = np.loadtxt(results_dir / f"recon_scan_{npart}_{trial_tag}_p_{p}_eta_{eta_min}_{eta_max}.txt")
        nsigma.append(uncertainties.ufloat(result[2], result[3]))
        eff.append(uncertainties.ufloat(result[0], result[1]))
        momenta.append(p)

    nsigma = np.array(nsigma)
    eff = np.array(eff)
    momenta = np.array(momenta)

    def metric(value):
        return float(value.n), float(value.s)

    # These final objective definitions are dRICH-specific physics choices.
    piKsep_etalow, piKsep_etalow_sem = metric(np.mean(nsigma[momenta == 15]))
    piKsep_etahigh, piKsep_etahigh_sem = metric(np.mean(nsigma[momenta == 45]))
    acceptance, acceptance_sem = metric(np.mean(eff[1:]))
    metrics = {
        "piKsep_etalow": piKsep_etalow,
        "piKsep_etalow_sem": piKsep_etalow_sem,
        "piKsep_etahigh": piKsep_etahigh,
        "piKsep_etahigh_sem": piKsep_etahigh_sem,
        "acceptance": acceptance,
        "acceptance_sem": acceptance_sem,
    }

    if any(np.isnan(value) for value in metrics.values()):
        if eval_config["failure_policy"] != "penalty":
            raise RuntimeError(f"retrieve_results failed: NaN objective for trial {trial_tag}")
        return {name: failed_metrics.get(name, value) for name, value in metrics.items()}

    return metrics


def load_drich_config(config_path):
    """Load typed AID2E config plus dRICH evaluation_config."""

    config_path = Path(config_path).resolve()
    raw_cfg = load_raw_config(str(config_path))
    return config_path, load_config(str(config_path)), raw_cfg["problem"]["evaluation_config"]
