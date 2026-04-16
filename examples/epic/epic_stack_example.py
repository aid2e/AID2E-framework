"""Example: Configuring and running layers of a stack

This low-level example demonstrates:
1. How to directly configure layers of an experimental
   stack in python
2. Generate a driver script to run configured
   layers
3. Run script as a stage in a worklow

Project: AID2E v0.0.0 - AI assisted Detector Design for EIC
"""

from typing import List, Tuple
import argparse
import os

from aid2e.utilities.configurations import (
    BranchDefinition,
    ObjectiveDirection,
    ObjectiveDefinition,
    ProblemConfiguration,
    WorkflowDefinition,
)
from aid2e.utilities.epic_utils import (
    EpicDesignConfig,
    EpicEnvConfig,
    EpicJobDefinition,
    EpicLayerConfig,
    EpicParameter,
    EpicStack,
    EpicStageDefinition,
)
from aid2e.utilities.workflows import (
    DAGExecutor,
    JobContext,
    modify_xml_files,
)

# constants
CONST = {
    "test_dir" : "epic_example_test",
    "exec_dir" : "epic_example_exec",
    "design"   : {
        "epic_design_parameters" : {
            "bic" : {
                "file_path" : "compact/ecal/bic_default.xml",
                "parameters" : {
                    "EcalBarrel_enable_staves_2" : {
                        "value"     : 0,
                        "choices"   : (0, 1),
                        "xml_path"  : ".//constant[@name='EcalBarrel_enable_staves_2']",
                        "attribute" : "value",
                        "unit"      : "",
                    },
                    "EcalBarrel_enable_staves_4" : {
                        "value"     : 1,
                        "choices"   : (0, 1),
                        "xml_path"  : ".//constant[@name='EcalBarrel_enable_staves_4']",
                        "attribute" : "value",
                        "unit"      : "",
                    },
                    "EcalBarrel_enable_staves_6" : {
                        "value"     : 1,
                        "choices"   : (0, 1),
                        "xml_path"  : ".//constant[@name='EcalBarrel_enable_staves_6']",
                        "attribute" : "value",
                        "unit"      : "",
                    }
                },
            }
        },
        "optimization_groups" : {"default" : [
            "bic.EcalBarrel_enable_staves_2",
            "bic.EcalBarrel_enable_staves_4",
            "bic.EcalBarrel_enable_staves_6"
        ]},
    },
    "enviro" : {
        "epic_environment" : {
            "epic_install" : "epic_example_test/epic",
            "epic_config"  : "epic",
            "eic_shell"    : "/path/to/my/eic-shell",
        },
    },
}


# =============================================================================
# Do template substitution
# =============================================================================
def substitute_templates(layers: List[EpicLayerConfig], context: JobContext):
    """Apply template substitutes (parallels StackExecutionEngie._apply_template_substitution)"""

    def substitute(text, context):
        result = text
        result = result.replace("{{context.job_id}}", str(context.job_id))
        result = result.replace("{{context.execution_dir}}", str(context.execution_dir))
        for key, value in context.design_point.items():
            result = result.replace(f"{{design_point.{key}}}", str(value))
        return result

    new_layers = layers
    for layer in new_layers:
        resolved_inputs = list()
        for layer_input in layer.inputs:
            layer_input = substitute(layer_input, context)
            resolved_inputs.append(layer_input)
        layer.inputs = resolved_inputs

        resolved_outputs = list()
        for layer_output in layer.outputs:
            layer_output = substitute(layer_output, context)
            resolved_outputs.append(layer_output)
        layer.outputs = resolved_outputs

        if layer.arguments is not None:
            resolved_arguments = list()
            for layer_argument in layer.arguments:
                layer_argument = substitute(layer_argument, context)
                resolved_arguments.append(layer_argument)
            layer.arguments = resolved_arguments

    return new_layers

# =============================================================================
# Set up for examples
# =============================================================================

def setup():
    """Setup to run examples"""

    # create directories for tests
    if os.path.exists(CONST["test_dir"]):
        os.system(f"rm -rf {CONST['test_dir']}")
    os.makedirs(CONST["test_dir"])
    print(f"  -- Made execution directory at {CONST['test_dir']}")

    # create directories to run in
    if os.path.exists(CONST["exec_dir"]):
        os.system(f"rm -rf {CONST['exec_dir']}")
    os.makedirs(CONST["exec_dir"])
    print(f"  -- Made execution directory at {CONST['exec_dir']}")

    # clone epic repo
    os.system(f"git clone git@github.com:eic/epic.git {CONST['test_dir']}/epic")
    print(f"  -- Cloned epic repo:")
    os.system(f"ls {CONST['test_dir']}/epic")


# =============================================================================
# Example 0: Modify ePIC geometry
# =============================================================================
def example_modify_geometry():
    """Modify ePIC geometry"""

    # hard code path to compact file for testing
    design = CONST["design"]
    design["epic_design_parameters"]["bic"]["file_path"] = f"{CONST['test_dir']}/epic/compact/ecal/bic_default.xml"

    # set up design configruation and generate
    # modifications to apply
    configuration = EpicDesignConfig(**design)
    parameters    = configuration.get_flat_parameters()
    modifications = configuration.get_xml_modifications({"bic.EcalBarrel_enable_staves_2" : 1})
    print(f"  -- parameters & modifications:\n    parameters = {parameters}\n    modifications = {modifications}")

    # apply changes to compact files
    modify_xml_files(modifications)
    print("  -- modified files")

    return configuration


# =============================================================================
# Example 1: Configuring Layers Directly
# =============================================================================

def example_configure_layers():
    """Stack layer configuration"""

    # configure desired layers in a stack
    #   --> Note that values in {{ }} will be substituted
    #       during execution
    cfg_geo = EpicLayerConfig(
        name = "geo",
        inputs = ["{{context.execution_dir}}/epic/install/share/epic/epic.xml"],
        outputs = ["{{context.execution_dir}}/epic_geo.overlaps.txt"],
    )
    cfg_sim_A = EpicLayerConfig(
        name = "sim",
        inputs = ["inputs/central_photons_bin0.py"],
        outputs = ["{{context.execution_dir}}/central_photons_bin0.edm4hep.root"],
        command = "ddsim",
    )
    cfg_sim_B = EpicLayerConfig(
        name = "sim",
        inputs = ["inputs/central_photons_bin1.py"],
        outputs = ["{{context.execution_dir}}/central_photons_bin1.edm4hep.root"],
    )
    cfg_sim_C = EpicLayerConfig(
        name = "sim",
        inputs = ["inputs/central_photons_bin2.py"],
        outputs = ["{{context.execution_dir}}/central_photons_bin2.edm4hep.root"],
    )
    cfg_ana_A = EpicLayerConfig(
        name = "ana",
        inputs = [
            "{{context.execution_dir}}/central_photons_bin0.edm4hep.root",
            "{{context.execution_dir}}/central_photons_bin1.edm4hep.root",
            "{{context.execution_dir}}/central_photons_bin2.edm4hep.root"
        ],
        outputs = ["{{context.execution_dir}}/central_photons.edm4hep.root"],
        command = "hadd",
        rule = "{command} -f {outputs} {inputs}"
    )
    cfg_rec = EpicLayerConfig(
        name = "rec",
        inputs = ["{{context.execution_dir}}/central_photons.edm4hep.root"],
        outputs = ["{{context.execution_dir}}/central_photons.edm4eic.root"],
        arguments = ["-Pnthreads=8", "-Peicrecon:LogLevel=debug"],
    )
    cfg_ana_B = EpicLayerConfig(
        name = "ana",
        inputs = ["{{context.execution_dir}}/central_photons.edm4eic.root"],
        outputs = ["{{context.execution_dir}}/central_photon_phi_resolution.hist.root"],
        arguments = ["-c phi", "-s 22"],
        command = "scripts/bic_angular_reso.py",
        rule = "python {command} -i {inputs} -o {outputs} {arguments}",
    )
    cfgs = [cfg_geo, cfg_sim_A, cfg_sim_B, cfg_sim_C, cfg_ana_A, cfg_rec, cfg_ana_B]

    print(f"  -- Configured layers:\n    {cfgs}")
    return cfgs


# =============================================================================
# Example 2: Instantiate Configurations and Context
# =============================================================================
def example_make_configs_and_context():

    design = EpicDesignConfig(**CONST['design'])
    enviro = EpicEnvConfig(**CONST['enviro']['epic_environment'])
    print(f"  -- Created design and environment configs:\n    design = {design}\n    enviro = {enviro}")

    objective = ObjectiveDefinition(
        name = "central_photons_phi_resolution",
        direction = ObjectiveDirection.MINIMIZE,
    )
    print(f"  -- Defined objective:\n    objective = {objective}")

    problem = ProblemConfiguration(
        name = "test_problem",
        output_location = f"{CONST['test_dir']}",
        work_location = f"{CONST['test_dir']}",
        problem_type = "EPIC_TEST",
        design_config = design,
        objectives = [objective],
        environment_config = enviro,
    )
    print(f"  -- Created ProblemConfiguration:\n    problem = {problem}")

    # information like execution directory, ID of current job,
    # etc is available to the stack via the JobContext
    context = JobContext(
        job_id = "make_driver",
        stage_id = "test_stage",
        workflow_id = "test_workflow",
        design_point = {"bic.EcalBarrel_enable_staves_4" : 0},
        xcom = {},  # NOTE empty dict for testing
        artifacts = {},  # NOTE empty dict for testing
        logs = [f"{CONST['test_dir']}/make_test_driver.log"],
        execution_dir =  f"{CONST['test_dir']}",
        problem_config = problem,
    )

    print(f"  -- Created JobContext:\n    context = {context}")
    return (problem, context)


# =============================================================================
# Example 3: Generate Driver Script
# =============================================================================

def example_generate_driver(layers: List[EpicLayerConfig], configs: Tuple[ProblemConfiguration, JobContext]):
    """Generate driver script for configured layers"""

    # grab context and instantiate an ePIC stack
    context = configs[1]
    epic_stack = EpicStack()

    # make sure necessary environment variables are set
    context.problem_config.environment_config.activate()

    # substitute relevant templates
    resolved_layers = substitute_templates(layers, context)

    # prepare for generating script by modifying geometry
    prep = epic_stack.prepare_for_execution(context = context)

    # generate driver script
    drvr_script = f"{CONST['test_dir']}/driver_from_stack.sh"
    epic_stack.make_driver_script(
        script = drvr_script,
        configs = resolved_layers,
        preparations = prep,
        context = context,
    )

    drvr_path = os.path.abspath(drvr_script)
    print(f"  -- Created script at {drvr_path}")

    drvr_command = epic_stack.make_driver_command(drvr_path)
    print(f"  -- Created command:\n    command = {drvr_command}")


# =============================================================================
# Example 4: Run Script in a Workflow
# =============================================================================

def example_run_script(layers: List[EpicLayerConfig], configs: Tuple[ProblemConfiguration, JobContext]):
    """Run driver script in a workflow"""

    # update output/work location to execution dir
    problem = configs[0]
    problem.output_location = CONST['exec_dir']
    problem.work_location = CONST['exec_dir']

    # As an example, workflow will consist of 3 stages:
    #   1. run overlap check (geo)
    #   2. run sim A, B, C in parallel
    #   3. run ana A + rec + ana B in sequence

    # -------------------------------------------------------------------------
    # Stage 1
    # -------------------------------------------------------------------------

    job_1 = EpicJobDefinition(
        name = "geo_job",
        layers = [layers[0]],
        payload = {
            "evaluator_type": "stack",  # FIXME this should be set by default
            "stack_type": "epic",  # FIXME this should be set by default
            "job_id": "geo",
        },
    )

    stage_1 = EpicStageDefinition(
        name = "geo_stage",
        jobs = [job_1],
    )
    print(f"  -- Defined stage 1:\n    {stage_1}")

    # -------------------------------------------------------------------------
    # Stage 2
    # -------------------------------------------------------------------------

    job_2A = EpicJobDefinition(
        name = "sim_job_0",
        layers = [layers[1]],
        payload = {
            "evaluator_type": "stack", # FIXME this should be set by default
            "stack_type": "epic",  # FIXME this should be set by default
            "job_id": "sim_0",
        },
    )

    job_2B = EpicJobDefinition(
        name = "sim_job_1",
        layers = [layers[2]],
        payload = {
            "evaluator_type": "stack", # FIXME this should be set by default
            "stack_type": "epic", # FIXME this should be set by default
            "job_id": "sim_1",
        },
    )
    job_2C = EpicJobDefinition(
        name = "sim_job_2",
        layers = [layers[3]],
        payload = {
            "evaluator_type": "stack", # FIXME this should be set by default
            "stack_type": "epic", # FIXME this should be set by default
            "job_id": "sim_2",
        },
    )

    stage_2 = EpicStageDefinition(
        name = "sim_stage",
        jobs = [job_2A, job_2B, job_2C],
    )
    print(f"  -- Defined stage 2:\n    {stage_2}")

    # -------------------------------------------------------------------------
    # Stage 3
    # -------------------------------------------------------------------------

    job_3 = EpicJobDefinition(
        name = "merge_rec_ana_job",
        layers = [layers[4], layers[5], layers[6]],
        payload = {
            "evaluator_type": "stack",  # FIXME this should be set by default
            "stack_type": "epic",  # FIXME this should be set by default
            "job_id": "merge_rec_ana",
        },
    )

    stage_3 = EpicStageDefinition(
        name = "merge_rec_ana_stage",
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
        name = "epic_workflow",
        description = "An ePIC pipeline: check geometry → run simulations → run reco + ana",
        branches = [branch],
        objectives = [],
    )
    print(f"  -- Defined workflow:\n    {branch}\n    {workflow}")

    # -------------------------------------------------------------------------
    # Run workflow
    # -------------------------------------------------------------------------

    executor = DAGExecutor(
        workflow,
        base_output_dir = f"{CONST['exec_dir']}",
        log_level = "INFO",
        problem_config = problem,
    )
    design_point = {"bic.EcalBarrel_enable_staves_6" : 0}

    print(f"\n  -- Running ePIC workflow...")
    objectives = executor.execute(design_point)

    print(f"\n✅ ePIC workflow completed!")


# =============================================================================
# Main
# =============================================================================

if __name__ == '__main__':

    parser = argparse.ArgumentParser()
    parser.add_argument('-s', '--setup', action = 'store_true', help = 'Set up for running')

    args = parser.parse_args()
    if args.setup:
        print("\nSetting up for running")
        print("-" * 70)
        setup()
    else:
        if not os.path.exists(CONST["exec_dir"]):
            print("\nRun directory not found, setting up for running")
            print("-" * 70)
            setup()

    print("\nExample 0: modify geometry")
    print("-" * 70)
    design = example_modify_geometry()

    print("\nExample 1: configure layers")
    print("-" * 70)
    layers = example_configure_layers()

    print("\nExample 2: make configurations and context")
    print("-" * 70)
    configs = example_make_configs_and_context()

    print("\nExample 3: generate driver script")
    print("-" * 70)
    example_generate_driver(layers, configs)

    print("\nExample 4: run driver script")
    print("-" * 70)
    example_run_script(layers, configs)
