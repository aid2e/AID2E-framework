"""Example: Configuring and running layers of a stack

This example demonstrates:
1. How to directly configure layers of an experimental
   stack in python
2. Generate a driver script to run configured
   layers
3. Run script as a stage in a worklow [IN PROGRESS]

Project: AID2E v0.0.0
"""

import argparse
import os

from aid2e.utilities.configurations import (
    BranchDefinition,
    StackLayerConfig,
    StackJobDefinition,
    StackStageDefinition,
    WorkflowDefinition,
)
from aid2e.utilities.epic_utils import (
    EpicStack,
)
from aid2e.utilities.workflows import (
    DAGExecutor,
)

# constants
CONST = {
    "run_dir" : "./epic_example_run",
    "out_dir" : "./epic_example_out",
}


# =============================================================================
# Set up for examples
# =============================================================================

def setup():
    """Setup to run examples"""

    # create directory to run in
    if os.path.exists(CONST["run_dir"]):
        os.system(f"rm -rf {CONST['run_dir']}")
    os.makedirs(CONST["run_dir"])
    print(f"  -- Made run directory at {CONST['run_dir']}")

    # clone epic repo
    os.system(f"git clone git@github.com:eic/epic.git {CONST['run_dir']}/epic")
    print(f"  -- Cloned epic repo:")
    os.system(f"ls {CONST['run_dir']}/epic")


# =============================================================================
# Example 1: Configuring Layers Directly
# =============================================================================

def example_configure_layers():
    """Stack layer configuration"""

    # configure desired layers in a stack
    cfg_geo = StackLayerConfig(
        name = "geo",
        inputs = ["my_geo.xml"],
        outputs = ["my_geo.overlaps.txt"],
    )
    cfg_sim_A = StackLayerConfig(
        name = "sim",
        inputs = ["steer.py", "macro.mac"],
        outputs = ["testA.edm4hep.root"],
        arguments = ["--enableOpticalPhotons 0"],
        command = "ddsim",
    )
    cfg_sim_B = StackLayerConfig(
        name = "sim",
        inputs = ["steer.py", "macro.mac"],
        outputs = ["testB.edm4hep.root"],
    )
    cfg_rec = StackLayerConfig(
        name = "rec",
        inputs = ["testA.edm4hep.root", "testB.edm4hep.root"],
        outputs = ["test.edm4eic.root"],
        arguments = ["-Pjana:ncores=8", "-Pjana:loglevel=debug"],
    )
    cfg_ana = StackLayerConfig(
        name = "ana",
        inputs = ["test.edm4eic.root"],
        outputs = ["test.hist.root"],
        arguments = ["-c phi", "-p 11"],
        command = "my_ana.py",
        rule = "python {command} -i {inputs} -o {outputs} {arguments}",
    )
    cfgs = [cfg_geo, cfg_sim_A, cfg_sim_B, cfg_rec, cfg_ana]

    print(f"  -- Configured layers:\n    {cfgs}")
    return cfgs


# =============================================================================
# Example 2: Generate Driver Script
# =============================================================================

def example_generate_driver(cfgs: List[StackLayerConfig]):
    """Generate driver script for configured layers"""

    # Metadata about a trial like the path to modified
    # geometry will (most likely) be available via a
    # dictionary somehow
    meta = {
        'det_path'   : f"{CONST['run_dir']}/epic",
        'det_config' : 'epic_full'
    }

    # instantiate a stack and generate river script
    drvr_script = f"{CONST['run_dir']}/driver_from_stack.sh"
    epic_stack  = EpicStack()
    epic_stack.make_driver_script(drvr_script, cfgs, meta)

    drvr_path = os.path.abspath(drvr_script)
    print(f"  -- Created script at {drvr_path}")
    return drvr_path


# =============================================================================
# Example 3: Run Script in a Workflow
# =============================================================================

def example_run_script(cfgs: List[StackLayerConfig]):
    """Run driver script in a workflow"""

    # As an example, workflow will consist of 3 stages:
    #   1. run overlap check (geo)
    #   2. run sim A, B in parallel
    #   3. run rec + ana

    # -------------------------------------------------------------------------
    # Stage 1
    # -------------------------------------------------------------------------

    job_1 = StackJobDefinition(
        name = "geo_job",
        layers = [cfgs[0]],
        payload = {
            "evaluator_type": "bash",
            "job_id": "geo",
        },
    )

    stage_1 = StackStageDefinition(
        name = "geo_stage",
        jobs = [job_1],
    )
    print(f"  -- Defined stage 1:\n    {stage_1}")

    # -------------------------------------------------------------------------
    # Stage 2
    # -------------------------------------------------------------------------

    job_2A = StackJobDefinition(
        name = "sim_job_A",
        layers = [cfgs[1]],
        payload = {
            "evaluator_type": "bash",
            "job_id": "sim_A",
        },
    )

    job_2B = StackJobDefinition(
        name = "sim_job_B",
        layers = [cfgs[2]],
        payload = {
            "evaluator_type": "bash",
            "job_id": "sim_B",
        },
    )

    stage_2 = StackStageDefinition(
        name = "sim_stage",
        jobs = [job_2A, job_2B],
    )
    print(f"  -- Defined stage 2:\n    {stage_2}")

    # -------------------------------------------------------------------------
    # Stage 3
    # -------------------------------------------------------------------------

    job_3 = StackJobDefinition(
        name = "rec_ana_job",
        layers = [cfgs[3], cfgs[4]],
        payload = {
            "evaluator_type": "bash",
            "job_id": "rec_ana",
        },
    )

    stage_3 = StackStageDefinition(
        name = "rec_ana_stage",
        jobs = [job_3],
    )
    print(f"  -- Defined stage 3:\n    {stage_3}")

    # -------------------------------------------------------------------------
    # Organize stages into a workflow
    # -------------------------------------------------------------------------

    branch = BranchDefinition(
        name = "main",
        stages = [stage_1, stage_2, stage_3],
    )

    workflow = WorkflowDefinition(
        name = "stack_workflow",
        description = "An experimental pipeline: check geometry → run simulations → run reco + ana",
        branches = [branch],
        objectives = [],
    )
    print(f"  -- Defined workflow:\n    {branch}\n    {workflow}")

    # -------------------------------------------------------------------------
    # Run workflow
    # -------------------------------------------------------------------------

    executor = DAGExecutor(workflow, base_output_dir = "/tmp/aid2e_examples", log_level = "INFO")
    design_point = {"nozzle_length" : 55.1, "ecal_absorber_thickness" : 4.3}

    print(f"\n  -- Running experimental workflow...")
    objectives = executor.execute(design_point)

    print(f"\n✅ Experimental workflow completed!")


# =============================================================================
# Main
# =============================================================================

if __name__ == '__main__':

    print("Example 1: configure layers")
    print("-" * 70)
    cfgs = example_configure_layers()

    print("\nExample 2: generate driver script")
    print("-" * 70)
    path = example_generate_driver(cfgs)

    print("\nExample 3: run driver script")
    print("-" * 70)
    example_run_script(cfgs)
