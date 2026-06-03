"""
ePIC software stack configurations. Narrows/extends StackLayerConfig, StackJobDefintion,
and StackStageDefinition from the configurations module to be ePIC-specific.

Project: AID2E v0.0.0 - AI assisted Detector Design for EIC
Homepage: https://aid2e.github.io/aid2e-framework
Repository: https://github.com/aid2e/AID2E-framework.git
"""

from pydantic import Field, model_validator
from typing import List, Optional

from aid2e.utilities.configurations.experimental_stack_config import (
    StackLayerConfig,
    StackJobDefinition,
    StackStageDefinition,
    StackBranchDefinition,
    StackWorkflowDefinition,
    StackWorkflowsConfiguration,
)


class EpicLayerConfig(StackLayerConfig):
    """Configuration of a layer of ePIC stack"""
    pass


class EpicJobDefinition(StackJobDefinition):
    """
    Definition a job to run 1 or more ePIC stack
    layers. If no command provided, will set
    default based on specified evaluator_type.
    """
    layers: List[EpicLayerConfig]


class EpicStageDefinition(StackStageDefinition):
    """
    Definition of an ePIC stage in a workflow.
    Jobs are restricted to ePIC jobs.
    """
    jobs: List[EpicJobDefinition] = Field(default_factory = list, description="ePIC stack job definitions")


class EpicBranchDefinition(StackBranchDefinition):
    """
    Definition of an ePIC branch in a workflow.
    Stages are restricted to ePIC stages.
    """
    stages: List[EpicStageDefinition] = Field(default_factory = list, description="ePIC stack branch definitions")


class EpicWorkflowDefinition(StackWorkflowDefinition):
    """
    Definition of an ePIC workflow.
    """
    stack_type: Optional[str] = Field(default="epic", description="Experimental stack type for workflow-level geometry prep")

    def get_implicit_branch(self) -> StackBranchDefinition:
        """
        Get or create single implicit branch if branches list is empty.
        Overrides StackWorkflowDefinition.get_implicit_branch to return
        EpicBranchDefinition.
        """
        if self.branches:
            raise ValueError("Branches already defined; cannot use implicit branch")
        return EpicBranchDefinition(name="implicit")


class EpicWorkflowsConfiguration(StackWorkflowsConfiguration):
    """
    Container for ePIC workflows.
    """
    workflows: List[EpicWorkflowDefinition] = Field(..., min_items=1, description="List of workflows")
