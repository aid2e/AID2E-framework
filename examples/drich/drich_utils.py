"""
dRICH optimization utilities and AID2E workflow components.
"""

import json
import re
from pathlib import Path

import numpy as np
import uncertainties

from aid2e.utilities.configurations import ObjectiveDirection, load_config, load_raw_config



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


def apply_overlap_policy(overlap_log, penalty_file, eval_config, error=None):
    """Apply overlap failure policy and return a penalty marker if needed."""

    overlap_log = Path(overlap_log)
    penalty_file = Path(penalty_file)
    overlap_text = overlap_log.read_text() if overlap_log.exists() else ""
    match = re.search(r"Number of illegal overlaps/extrusions\s*:\s*(\d+)", overlap_text)
    overlaps = int(match.group(1)) if match is not None else None
    ok_value = eval_config["overlap_ok_value"]
    use_penalty = eval_config["failure_policy"] == "penalty"

    def penalty(**payload):
        penalty_file.parent.mkdir(parents=True, exist_ok=True)
        penalty_file.write_text(json.dumps({"penalty": True, **payload}, indent=2))
        return {"ok": 1.0}

    if error is not None:
        if not use_penalty:
            raise error
        payload = {"reason": "checkOverlaps command failed", "return_code": error.returncode}
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


def collect_objectives(
    results_dir,
    npart=None,
    trial_tag=None,
    scan_points=None,
    failed_objectives=None,
    failure_policy=None,
    penalty=False,
):
    """Collect dRICH analysis outputs or return configured penalty objective metrics."""

    failed_metrics = {}
    for name, value in failed_objectives.items():
        failed_metrics[name] = float(value)
        failed_metrics[f"{name}_sem"] = 0.0
    if penalty:
        return failed_metrics

    nsigma, eff, momenta = [], [], []
    for point in scan_points:
        p, eta_min, eta_max = point["p"], point["eta_min"], point["eta_max"]
        result = np.loadtxt(
            Path(results_dir) / f"recon_scan_{npart}_{trial_tag}_p_{p}_eta_{eta_min}_{eta_max}.txt"
        )
        nsigma.append(uncertainties.ufloat(result[2], result[3]))
        eff.append(uncertainties.ufloat(result[0], result[1]))
        momenta.append(p)

    nsigma = np.array(nsigma)
    eff = np.array(eff)
    momenta = np.array(momenta)

    def metric(value):
        return float(value.n), float(value.s)

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
        if failure_policy != "penalty":
            raise RuntimeError(f"retrieve_results failed: NaN objective for trial {trial_tag}")
        return {name: failed_metrics.get(name, value) for name, value in metrics.items()}

    return metrics


def load_drich_config(config_path):
    """Load typed AID2E config plus dRICH evaluation_config."""

    config_path = Path(config_path).resolve()
    raw_cfg = load_raw_config(str(config_path))
    return config_path, load_config(str(config_path)), raw_cfg["problem"]["evaluation_config"]


def failed_trials_from_stage_result(result):
    """Map failed scheduler job names back to Ax trial indices."""

    failed_trials = set()
    for status in result.job_statuses:
        match = re.search(r"trial_(\d+)", status.job_id)
        if status.status != "completed" and match:
            failed_trials.add(int(match.group(1)))
    return failed_trials


def metrics_for_ax(optimizer_metrics, objectives, directions):
    """Apply Ax's minimization sign convention to dRICH optimizer metrics."""

    return {
        name: -optimizer_metrics[name]
        if directions[name] == ObjectiveDirection.MAXIMIZE
        else optimizer_metrics[name]
        for name in objectives
    }
