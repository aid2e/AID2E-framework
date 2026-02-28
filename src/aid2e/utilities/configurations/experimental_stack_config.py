"""Experimental software stack configuration models

Defines models necessary for wiring experimental software stacks into workflows.
Allows users to specify layers of a pre-defined stack as part of a workflow.

Key Classes:
    - StackLayerConfiguration, configures a stack layer

Project: AID2E v0.0.0 - AI assisted Detector Design for EIC
Homepage: https://aid2e.github.io/aid2e-framework
Repository: https://github.com/aid2e/AID2E-framework.git
"""

from pydantic import BaseModel, Field
from typing import List, Optional

class StackLayerConfiguration(BaseModel):
    """Configures layer of an experimental stack

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
    inputs: List[str] = Field(..., description="List of inputs")
    outputs: List[str] = Field(..., description="List of outputs")
    arguments: Optional[List[str]] = Field(default=None, description="List of arguments")
    command: Optional[str] = Field(default=None, description="Command to run")
    rule: Optional[str] = Field(default=None, description=

# TODO
#   - Stack Layer Job Definition (creates a job definition from a stack layer)
#   - Stack Stage Definition (creates a stage)
#   - Stack layer loader
#   - Stack stage loader
