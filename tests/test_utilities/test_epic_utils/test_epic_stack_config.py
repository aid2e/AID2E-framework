"""Test ePIC stack/workflow configuration."""

import yaml

from aid2e.utilities.epic_utils.epic_stack_config import (
    EpicLayerConfig,
    EpicJobDefinition,
    EpicStageDefinition,
    EpicBranchDefinition,
    EpicWorkflowDefinition,
    EpicWorkflowsConfiguration,
)

def _sample_epic_workflow_payload() -> dict:
    """Build ePIC workflow configuration."""
    return {
       "workflows": [
           {
               "name": "imaging_optimization",
               "description": "Optimize the number of AstroPix layers in the BIC",
               "branches": [
                   {
                       "name": "photon_phi_resolution",
                       "description": "Calculate phi resolution for single photons",
                       "stages": [
                           {
                               "name": "geo", # FIXME <==== I think I need add a "job" layer to the data
                               "description": "Check for overlaps in modified geomtry",
                               "layers": [
                                   {
                                       "epic_geo": {
                                           "inputs": ["{{context.geometry_dir}}/install/share/epic/epic.xml"],
                                           "outputs": ["{{context.execution_dir}}/geo.overlaps.txt"]
                                       }
                                   }
                               ]
                           },
                           {
                               "name": "sim",
                               "description": "Simulate single photons",
                               "layers": [
                                   {
                                       "epic_sim": {
                                           "inputs": ["inputs/central_photons_bin0.py"],
                                           "outputs": ["{{context.execution_dir}}/central_photons_bin0.edm4hep.root"]
                                       }
                                   }
                               ]
                           },
                           {
                               "name": "rec_and_ana",
                               "description": "Run reconstruction and analysis",
                               "layers": [
                                   {
                                       "epic_rec": {
                                           "inputs": ["{{context.exeuction_dir}}/central_photons_bin0.edm4hep.root"],
                                           "outputs": ["{{context.execution_dir}}/central_photons_bin0.edm4eic.root"],
                                           "arguments": ["-Pnthreads=8", "-Peicrecon:LogLevel=debug"]
                                       }
                                   },
                                   {
                                       "epic_ana": {
                                           "inputs": ["{{context.execution_dir}}/central_photons_bin0.edm4eic.root"],
                                           "outputs": ["{{context.execution_dir}}/central_photons_bin0.hist.root"],
                                           "arguments": ["-c phi", "-s 22"],
                                           "command": "scripts/bic_angular_reso.py",
                                           "rule": "python {command} -i {inputs} -o {outputs} {arguments}"
                                       }
                                   }
                               ]
                           }
                       ]
                   }
               ]
           }
       ]
   }

def test_epic_workflows_validation(tmp_path):
    """Validate workflow model."""
    config_path = tmp_path / "epic_workflow.config"
    config_path.write_text(yaml.safe_dump(_sample_epic_workflow_payload()))

    payload = None
    with open(config_path, 'r') as data:
        payload = yaml.safe_load(data)
    assert payload is not None

    config = EpicWorkflowsConfiguration(**payload)
    assert 1 == len(config.workflows)
    assert 1 == len(config.workflows[0].branches)
    assert 3 == len(config.workflows[0].branches[0].stages)
    assert 1 == len(config.workflows[0].branches[0].stages[0].jobs)
    assert 1 == len(config.workflows[0].branches[0].stages[1].jobs)
    assert 1 == len(config.workflows[0].branches[0].stages[2].jobs)

    # TODO add the following tests
    #   - confirm models are the right classes
    #   - check some select info (names, inputs, etc)
