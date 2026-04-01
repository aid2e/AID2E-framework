"""Experimental software stack configuration models

Defines models necessary for wiring experimental software stacks into workflows.
Allows users to specify layers of a pre-defined stack as part of a workflow.

Key Classes:
    - StackLayerConfig, configures a stack layer

Project: AID2E v0.0.0 - AI assisted Detector Design for EIC
Homepage: https://aid2e.github.io/aid2e-framework
Repository: https://github.com/aid2e/AID2E-framework.git
"""

from pydantic import AliasChoices, BaseModel, Field, model_validator
from typing import List, Optional

from aid2e.utilities.configurations.workflow_config import JobDefinition, StageDefinition


class StackLayerConfig(BaseModel):
    """Configures layer of an experimental stack

    A job may consist of 1 or many layers from an experimental
    software stack. Sanitizes provided data to make sure
    singular vs. plural inputs/outputs are handled consistently.

    Attributes:
        name: Layer name (e.g. "sim")
        inputs: List of inputs to layer
        outputs: List of outputs from layer
        arguments: Optional list of any additional arguments to apply
        command: Optional command to be run. Can be used to
                 override default of layer.
        rule: Optional recipe for combining inputs, outputs, arguments,
              and command. Can be used to override default of layer.

    Notes:
        - rule supports template substitutions for {inputs}, {outputs},
          {arguments}, and {command}. See StackLayer for more details.
    """
    name: str = Field(..., description="Layer name")
    inputs: List[str] = Field(..., description="List of inputs", validation_alias=AliasChoices('inputs', 'input'))
    outputs: List[str] = Field(..., description="List of outputs", validation_alias=AliasChoices('outputs', 'output'))
    arguments: Optional[List[str]] = Field(default=None, description="List of arguments")
    command: Optional[str] = Field(default=None, description="Executable command")
    rule: Optional[str] = Field(default=None, description="Recipe for combining arguments")

    @classmethod
    def pluralize_strings(cls, data, singular, plural):
        """Pluralize strings in data

         Sanitize input by data by ensuring that
         'singular' keys are always 'plural' and
         that their values are wrapped in lists.

         Args:
             data: the to be sanitized
             singular: the singular case of the key
                       (e.g. 'input')
             plural: the plural case of the key
                     (e.g. 'inputs')

         Returns:
             Sanitized data
         """
        if singular in data and plural not in data:
            data[singular] = data[plural]
        if isinstance(data.get(plural), str):
            data[plural] = [data[plural]]
        return data

    @model_validator(mode='before')
    @classmethod
    def handle_input_variants(cls, data):
        """
        Handles cases where (1) 'input' vs. 'inputs' was used in key,
        and (2) only 1 string was provided.
        """
        return cls.pluralize_strings(data, "input", "inputs")

    @model_validator(mode='before')
    @classmethod
    def handle_output_variants(cls, data):
        """
        Handles cases where (1) 'output' vs. 'outputs' was used in key,
        and (2) only 1 string was provided.
        """
        return cls.pluralize_strings(data, "output", "outputs")


class StackJobDefinition(JobDefinition):
    """
    Extends the base JobDefinition with a list of stack
    layers to utilize built-in commands of an experimental
    stack.

    Extensions:
        script: Name of driver script to generate
        layers: Layer configurations to run in this job
    """
    command: Optional[str] = Field(default="./{script}", description="Executable command")
    script: Optional[str] = Field(default="do_job_{{context.job_id}}.sh", description="Driver script name")
    layers: List[StackLayerConfig]


class StackStageDefinition(StageDefinition):

    """
    Definition of a workflow stage narrowed to jobs from
    an experimental software stack.
    """
    jobs: List[StackJobDefinition] = Field(default_factory=list, description="Software stack job definitions")
