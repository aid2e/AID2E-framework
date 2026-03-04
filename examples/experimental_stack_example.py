"""Example: Configuring and running layers of a stack

This example demonstrates:
1. How to directly configure layers of an experimental
   stack in python
2. Generate a driver script to run configured
   layers
3. Run script as a stage in a worklow [TODO]

Project: AID2E v0.0.0
"""

import os

from aid2e.utilities.configurations import (
    StackLayerConfiguration,
)
from aid2e.utilities.epic_utils import (
    EpicStack,
)


# =============================================================================
# Example 1: Configuring Layers Directly
# =============================================================================

def example_configure_layers():
    """Stack layer configuration"""

    # configure desired layers in a stack
    cfg_geo = StackLayerConfiguration(
        name = "geo",
        inputs = ["my_geo.xml"],
        outputs = ["my_geo.overlaps.txt"],
    )
    cfg_sim_A = StackLayerConfiguration(
        name = "sim",
        inputs = ["steer.py", "macro.mac"],
        outputs = ["testA.edm4hep.root"],
        arguments = ["--enableOpticalPhotons 0"],
        command = "ddsim",
    )
    cfg_sim_B = StackLayerConfiguration(
        name = "sim",
        inputs = ["steer.py", "macro.mac"],
        outputs = ["testB.edm4hep.root"],
        arguments = ["--enableOpticalPhotons 0"],
        command = "ddsim",
    )
    cfg_rec = StackLayerConfiguration(
        name = "rec",
        inputs = ["testA.edm4hep.root", "testB.edm4hep.root"],
        outputs = ["test.edm4eic.root"],
        arguments = ["-Pjana:ncores=8", "-Peicrecon:loglevel=debug"],
    )
    cfg_ana = StackLayerConfiguration(
        name = "ana",
        inputs = ["test.edm4eic.root"],
        outputs = ["test.hist.root"],
        arguments = ["-c phi", "-p 11"],
        command = "my_ana.py",
        rule = "python {command} -i {inputs} -o {outputs} {arguments}",
    )
    cfgs = [cfg_geo, cfg_sim_A, cfg_sim_B, cfg_rec, cfg_ana]

    print(f"  -- Configured layers:\n{cfgs}")
    return cfgs


# =============================================================================
# Example 2: Generate Driver Script
# =============================================================================

def example_generate_driver(cfgs: List[StackLayerConfiguration]):
    """Generate driver script for configured layers"""

    # metadata about a trial like the path to modified
    # geometry available as a dictionary
    #   -- TODO CONFIRM
    meta = {
        'det_path'   : 'run/trial_0/epic',
        'det_config' : 'epic_full'
    }

    # instantiate a stack and generate river script
    drvr_script = "driver.sh"
    epic_stack  = EpicStack()
    epic_stack.make_driver_script("driver.sh", cfgs, meta)

    drvr_path = os.path.abspath(drvr_script)
    print(f"  -- Created script at {drvr_path}")
    return drvr_path


# =============================================================================
# Example 3: Run Script in a Workflow
# =============================================================================
def example_run_script():
    """Run driver script in a workflow"""
    print(f"  -- TODO")


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
    example_run_script()
