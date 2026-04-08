"""
ePIC software stack configurations. Narrows/extends StackLayerConfig, StackJobDefintion,
and StackStageDefinition from the configurations module to be ePIC-specific.

Project: AID2E v0.0.0 - AI assisted Detector Design for EIC
Homepage: https://aid2e.github.io/aid2e-framework
Repository: https://github.com/aid2e/AID2E-framework.git
"""

from pydantic import Field, model_validator
from typing import List

from aid2e.utilities.configurations.experimental_stack_config import (
    StackLayerConfig,
    StackJobDefinition,
    StackStageDefinition
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
