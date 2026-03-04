#!/usr/bin/env python3
"""
Self-contained dRICH objective evaluator for AID2E

This script reproduces dRICH-MOBO logic:
  1) Geometry XML edit
  2) Overlap check (checkOverlaps)
  3) Simulation (npsim)
  4) Reconstruction (eicrecon)
  5) Analysis (dRICHAna_bootstrap)
  6) Save objective result
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Dict, Any
import yaml
import shutil
import xml.etree.ElementTree as ET
import sys


SCAN_POINTS = [
    {"p": 15, "eta_min": 1.5, "eta_max": 2.0, "radiator": 0},
    {"p": 15, "eta_min": 2.0, "eta_max": 2.5, "radiator": 0},
    {"p": 45, "eta_min": 2.5, "eta_max": 3.0, "radiator": 1},
    {"p": 45, "eta_min": 3.0, "eta_max": 3.5, "radiator": 1},
]
PARTICLES = ["pi+", "kaon+"]

##--------------- func from editxml.py-------------
def getPath(param, configfile):
    if(os.path.isfile(configfile) == False):
        raise FileNotFoundError(f"parameter config file does not exist: {configfile}")
    with open(configfile, "r") as f:
        data = yaml.safe_load(f) or {}
        groups = data.get("design_space", {}).get("design_parameters", {})
        for group in groups.values():
            params = group.get("parameters", {})
            if param in params:
                info = params[param]
                path = info.get("xml_path")
                units = info.get("unit", info.get("units", ""))
                name = info.get("element")
                if not name:
                    if path and "[@" in path and "]" in path:
                        name = path[path.rfind("[@") + 2:path.rfind("]")]
                    else:
                        name = "value"
                if path:
                    return path, name, units
    raise KeyError(f"could not find parameter info for '{param}' in {configfile}")


def editGeom(param, value, jobid, parameters, configfile):
    if jobid == -1:
        xmlfile = str(os.environ["DETECTOR_PATH"] + "/compact/pid/drich.xml")
    else:
        xmlfile = str(os.environ["DETECTOR_PATH"] + "/compact/pid/drich_{}.xml".format(jobid))

    tree = ET.parse(xmlfile)
    root = tree.getroot()

    path, elementToEdit, units = getPath(param, configfile)
    if path == -1:
        print("ERROR: element path not found/defined")
        return

    element = root.find(path)
    if element is None:
        raise ValueError(f"could not find xml path for parameter '{param}': {path}")
    current_val = element.get(elementToEdit)

    '''
    if ("radius" in param) and ("mirror" in param):
        # set center z based on mirror radius
        z_path = path.replace('radius','centerz')
        z_element = root.find(z_path)
        z_elementToEdit = elementToEdit.replace('radius','centerz')
        # fix position to drich backplane
        z_element.set(z_elementToEdit,"{}*{}".format(314 - value, units))
    else:
    '''
    if units != '':
        element.set(elementToEdit, "{}*{}".format(value, units))
    else:
        element.set(elementToEdit, "{}".format(value))

    tree.write(xmlfile)
    return
    
def editEPIC(xml, jobid):
    # load drich_{jobid}.xml in the epic_craterlake_{jobid}.xml
    path = "${DETECTOR_PATH}/compact/pid/"
    drich_old = "drich.xml"
    drich_new = "drich_{}.xml".format(jobid)
    tree = ET.parse(xml)
    root = tree.getroot()

    for element in root.findall('.//include'):
        if element.get("ref") == str(path + drich_old):
            element.set("ref", str(path + drich_new))
            tree.write(xml)
            return
    raise ValueError(f"failed to update to new drich geo in {xml}")


def create_xml(
    parameters: Dict[str, float],
    trial_index: int,
    config_path: str) -> Path:

    cfg = yaml.safe_load(Path(config_path).read_text()) or {}
    ds_rel = cfg.get("problem", {}).get("design_space", {}).get("path")
    if not ds_rel:
        raise ValueError("Missing problem.design_space.path in workflow config")
    ds_path = Path(str(ds_rel))
    if not ds_path.is_absolute():
        ds_path = (Path(config_path).resolve().parent / ds_path).resolve()
    design_params_file = str(ds_path)

    #create new epic xml    
    epic_xml = "{}/{}.xml".format(os.environ['DETECTOR_PATH'],os.environ['DETECTOR_CONFIG'])
    epic_xml_job = "{}/{}_{}.xml".format(os.environ['DETECTOR_PATH'], os.environ['DETECTOR_CONFIG'], trial_index)
    shutil.copyfile(epic_xml, epic_xml_job)
    #change drich.xml -> drich_{jobid}.xml
    editEPIC(epic_xml_job, trial_index)
    
    #create and edit drich xml
    drich_xml = str(os.environ['DETECTOR_PATH']+"/compact/pid/drich.xml")
    drich_xml_job = str(os.environ['DETECTOR_PATH'] + "/compact/pid/drich_{}.xml".format(trial_index))
    shutil.copyfile(drich_xml, drich_xml_job)

    for param in parameters:        
        short = str(param).split(".")[-1]
        editGeom(short, parameters[param], trial_index, parameters, design_params_file)  
    return Path(epic_xml_job)

#-----------------

def evaluate_design_point(
    design_point: Dict[str, float],
    trial_index: int,
    output_dir: str,
    config_path: str,
) -> Dict[str, float]:

    #Output paths
    output_root = Path(output_dir).resolve()
    trial_tag = f"{trial_index:03d}"
    trial_dir = output_root / f"trial_{trial_tag}"
    log_dir = output_root / "log"

    # TODO 1) edit geometry xml
    # Write trial-specific detector XML files and the trial-level command script:
    # - {trial_scripts_dir}/jobconfig_{trial_index}
    # - detector XML outputs: drich_{trial_tag}.xml and <detector_config>_{trial_tag}.xml

    edit_epic_xml = create_xml(
        parameters=design_point,
        trial_index=trial_index,
        config_path=config_path,
    )

    # TODO 2) overlap check
    # Run checkOverlaps for trial XML and write:
    # - {overlaps_dir}/overlap_log_{trial_tag}.txt
    # - {job_output_dir}/trial_{trial_tag}.out / .err
    # - penalty decision

    # TODO 3) simulation
    # For each scan point and particle, write simulation outputs:
    # - {sim_dir}/scan_<npart>_{trial_tag}_<particle>_p_<p>_eta_<eta_min>_<eta_max>.root
    # - per-job scripts in {trial_scripts_dir}:
    #   jobconfig_job{trial_index}_<particle>_p_<p>_eta_<eta_min>_<eta_max>

    # TODO 4) reconstruction
    # For each scan point and particle, write reconstruction outputs:
    # - {reco_dir}/recon_scan_<npart>_{trial_tag}_<particle>_p_<p>_eta_<eta_min>_<eta_max>.root

    # TODO 5) analysis + collect results
    # Write per-scan analysis text outputs and final aggregate:
    # - {results_dir}/recon_scan_<npart>_{trial_tag}_p_<p>_eta_<eta_min>_<eta_max>.txt
    # - {results_dir}/drich-mobo-out_{trial_tag}.txt
    # Return JSON metrics for run_optimization.py in the output_file path

    # Test placeholder metrics (replace))
    metrics = {
        "piKsep_etalow": 0.0,
        "piKsep_etahigh": 0.0,
        "acceptance": 0.0,
    }
    metrics["combined_objective"] = (
        metrics["acceptance"] * 0.5 * (metrics["piKsep_etalow"] + metrics["piKsep_etahigh"])
    )
    return metrics


def main():
    parser = argparse.ArgumentParser(description="Evaluate one dRICH design point")
    parser.add_argument("--design_params_file", required=True)  
    parser.add_argument("--trial-index", type=int, required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--config-path", required=True)
    parser.add_argument("--output_file", required=True)  
    args = parser.parse_args()

    design = json.loads(Path(args.design_params_file).read_text(encoding="utf-8"))
    metrics = evaluate_design_point(
        design_point=design,
        trial_index=args.trial_index,
        output_dir=args.output_dir,
        config_path=args.config_path,
    )

    out_path = Path(args.output_file)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")

if __name__ == "__main__":
    raise SystemExit(main())