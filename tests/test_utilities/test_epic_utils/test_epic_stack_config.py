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
from aid2e.utilities.workflows.dag_executor import DAGExecutor

def _sample_epic_workflow_payload() -> dict:
    """Build ePIC workflow configuration."""
    return {
       "workflows": [
           {
               "name": "imaging_optimization",
               "description": "Optimize the number of AstroPix layers in the BIC",
               "stack_type": "epic",
               "branches": [
                   {
                       "name": "photon_phi_resolution",
                       "description": "Calculate phi resolution for single photons",
                       "stages": [
                           {
                               "name": "geo",
                               "description": "Check for overlaps in modified geomtry",
                               "jobs" : [
                                   {
                                       "name": "geo_job",
                                       "layers": [
                                           {
                                               "layer": "geo",
                                               "inputs": [
                                                   "{{geometry_dir}}/install/share/epic/epic.xml"
                                               ],
                                               "outputs": [
                                                   "{{execution_dir}}/geo.overlaps.txt"
                                               ]
                                           }
                                       ],
                                       "payload": {
                                           "evaluator_type": "stack",
                                           "stack_type": "epic",
                                           "job_id": "geo"
                                       }
                                   }
                               ]
                           },
                           {
                               "name": "sim",
                               "description": "Simulate single photons",
                               "jobs": [
                                   {
                                       "name": "sim_job",
                                       "layers": [
                                           {
                                               "layer": "sim",
                                               "inputs": [
                                                   "inputs/central_photons.py"
                                               ],
                                               "outputs": [
                                                   "{{execution_dir}}/central_photons.edm4hep.root"
                                               ]
                                           }
                                       ],
                                       "payload": {
                                           "evaluator_type": "stack",
                                           "stack_type": "epic",
                                           "job_id": "sim"
                                       }
                                   }
                               ]
                           },
                           {
                               "name": "rec_and_ana",
                               "description": "Run reconstruction and analysis",
                               "jobs": [
                                   {
                                       "name": "rec_ana_job",
                                       "layers": [
                                           {
                                               "layer": "rec",
                                               "inputs": [
                                                   "{{outputs[sim:sim_job:sim]}}/central_photons.edm4hep.root"
                                               ],
                                               "outputs": [
                                                   "{{execution_dir}}/central_photons.edm4eic.root"
                                               ],
                                               "arguments": [
                                                   "-Pnthreads=8",
                                                   "-Peicrecon:LogLevel=debug"
                                               ]
                                           },
                                           {
                                               "layer": "ana",
                                               "inputs": [
                                                   "{{outputs[rec_and_ana:rec_ana_job:rec]}}/central_photons.edm4eic.root"
                                               ],
                                               "outputs": [
                                                   "{{execution_dir}}/central_photons.hist.root"
                                               ],
                                               "arguments": [
                                                   "-c phi",
                                                   "-s 22"
                                               ],
                                               "command": "scripts/bic_angular_reso.py",
                                               "rule": "python {{command}} -i {{inputs}} -o {{outputs}} {{arguments}}"
                                           }
                                       ],
                                       "payload": {
                                           "evaluator_type": "stack",
                                           "stack_type": "epic",
                                           "job_id": "rec_ana"
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
    assert 1 == len(config.workflows[0].branches[0].stages[0].jobs[0].layers)
    assert 1 == len(config.workflows[0].branches[0].stages[1].jobs[0].layers)
    assert 2 == len(config.workflows[0].branches[0].stages[2].jobs[0].layers)

    # confirm that classes are resolved correctly
    assert isinstance(config, EpicWorkflowsConfiguration)
    assert isinstance(config.workflows[0], EpicWorkflowDefinition)
    assert isinstance(config.workflows[0].branches[0], EpicBranchDefinition)
    assert isinstance(config.workflows[0].branches[0].stages[0], EpicStageDefinition)
    assert isinstance(config.workflows[0].branches[0].stages[0].jobs[0], EpicJobDefinition)
    assert isinstance(config.workflows[0].branches[0].stages[0].jobs[0].layers[0], EpicLayerConfig)

    # check that select info is set correctly
    assert "epic" == config.workflows[0].stack_type
    assert "photon_phi_resolution" == config.workflows[0].branches[0].name
    assert "geo" == config.workflows[0].branches[0].stages[0].name
    assert "epic" == config.workflows[0].branches[0].stages[1].jobs[0].payload["stack_type"]
    assert "rec" == config.workflows[0].branches[0].stages[2].jobs[0].layers[0].layer
    assert "-s 22" == config.workflows[0].branches[0].stages[2].jobs[0].layers[1].arguments[1]

def test_epic_executor_from_config(tmp_path):
    """Create DAGExecutor from epic workflow."""
    config_path = tmp_path / "epic_workflow.config"
    config_path.write_text(yaml.safe_dump(_sample_epic_workflow_payload()))

    payload = None
    with open(config_path, 'r') as data:
        payload = yaml.safe_load(data)
    assert payload is not None

    config = payload["workflows"][0]
    workflow = EpicWorkflowDefinition(**config)
    executor = DAGExecutor(workflow, base_output_dir=tmp_path)
    assert executor is not None
    assert "photon_phi_resolution" == executor.workflow.branches[0].name
