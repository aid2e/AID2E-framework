"""Experimental software stack base classes

This module defines a framework for interfacing with a generic experimental
software stack. Components of the stack are represented as layers defined
by a name, a command to be run, and a rule dictating how arguments are
combined. These are layers are collected into a thin container, which
represents the stack.

Key Classes:
    - StackLayer: Abstract base class representing a component of a stack
    - ExperimentStack: Base container to hold layers representing the stack

Project: AID2E v0.0.0 - AI assisted Detector Design for EIC
Homepage: https://aid2e.github.io/aid2e-framework
Repository: https://github.com/aid2e/AID2E-framework.git
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, fields, field, replace
from typing import Any, Dict, List
import pathlib

from aid2e.utilities.configurations.experimental_stack_config import (
    StackLayerConfig
)


@dataclass
class StackLayer(ABC):
    """Represents a layer of a software stack

    Abstract base class that represents a layer of an experimental software
    stack. A layer is defined by a unique name, a specific command to be run,
    and a rule which dictates how arguments are combined.

    Properties:
        name: Unique name for the layer.
        command: Command to be run (e.g. npsim)
        rule: Recipe for combining the command and provided arguments
              using keywords, e.g. '{command} {arguments} {inputs} {outputs}'

    Example:
        >>> def ExperimentLayer(StackLayer):
        ...     name="sim"
        ...     command="npsim"
        ...     rule='{command} {arguments} {inputs} {outputs}"
        >>> layer = ExperimentLayer()
        >>> run_layer = layer.make_command(
        ...     inputs,
        ...     outputs,
        ...     arguments
        ... )
    """
    @property
    @abstractmethod
    def name(self):
        """Name of this layer (e.g. Sim)
        """
        pass

    @property
    @abstractmethod
    def command(self):
        """Command to be run (e.g. npsim)
        """
        pass

    @property
    @abstractmethod
    def rule(self):
        """Recipe for combining command and arguments
        """
        pass

    @abstractmethod
    def _make_input_arg(self, inputs: List[str]) -> str:
        """Make input argument

        Converts provided list of input filee into string of properly formatted
        inputs for command.

        Args:
            inputs: List of input files
        Returns:
            String of formatted input files
        """
        pass

    @abstractmethod
    def _make_output_arg(self, outputs: List[str]) -> str:
        """Make output argument

        Converts provided list of output files into string of properly formatted
        outputs for command.

        Args:
            outputs: List of output files
        Returns:
            String of formatted outputs
        """
        pass

    def _make_other_arg(self, arguments: List[str]) -> str:
        """Make other arguments

        By default, joins provided list of arguments into a space-separated
        string. Can be overwritten for behavior unique to specific layers.

        Args:
            arguments: List of arguments to join
        Returns:
            String of formatted arguments
        """
        return ' '.join(arguments)

    def make_command(self, inputs: str, outputs: str, arguments:str = None) -> str:
        """Make command

        Returns command to run with all inputs outputs, and arguments formatted
        according to layer rule.

        Args:
            inputs: List of input files
            outputs: List of output files
            arguments: Optional ist of additional arguments
        """
        # format and sub in inputs/outputs
        in_arg = self._make_input_arg(inputs)
        out_arg = self._make_output_arg(outputs)
        command = self.rule.replace('{command}', self.command)
        command = command.replace('{inputs}', in_arg)
        command = command.replace('{outputs}', out_arg)

        # if needed, sub in any other arguments
        if arguments != None:
            other_arg = self._make_other_arg(arguments)
            command = command.replace('{arguments}', other_arg)
        else:
            command = command.replace('{arguments}', '')

        # return formatted command without any
        # stray double spaces
        return command.replace('  ', ' ')

class AnaLayer(StackLayer):
    """Represents a generic analysis layer of a software stack

    Subclass derived from the abstract StackLayer to represent a generic
    analysis layer of an experimental software stack, in which users will
    run code they provide.

    Example:
        >>> layer = AnaLayer()
        >>> layer.command="do_my_analysis.py"
        >>> layer.rule='{command} {arguments} -i {inputs} -o {outputs}'
        >>> run_layer = layer.make_command(
        ...     inputs,
        ...     outputs,
        ...     arguments
        ... )
    """
    name = "ana"
    command = ""
    rule = ''

    # FIXME should allow for users to specify how to
    # handle multiple inputs
    def _make_input_arg(self, inputs: List[str]) -> str:
        """Formats inputs for generic analysis layer"""
        return ' '.join(inputs)

    # FIXME should allow for users to specify how to
    # handle multiple outputs
    def _make_output_arg(self, outputs: List[str]) -> str:
        """Formats outputs for generic analysis layer"""
        return ' '.join(outputs)


@dataclass
class ExperimentStack(ABC):
    """Represents an experimental software stack

    Abstract base class that represents an experimental software as a
    dictionary of layers keyed on the layer names.

    Properties:
        layers: Dictionary of layers

    Example:
        >>> def MySimLayer(StackLayer):
        ...     name="sim"
        ...     command="dosim"
        ...     rule='{command} {arguments} -I {inputs} -O {outputs}'
        ... @dataclass
        >>> def MyExperimentStack(ExperimentStack):
        ...     sim: MySimLayer = field(default_factory = MySimLayer)
        >>> stack = MyExperimentStack()
        >>> dosim = stack["sim"].make_command(
        ...     inputs,
        ...     outputs,
        ...     arguments
        ... )
    """
    layers: Dict[str, StackLayer] = field(init = False, repr = False)

    def __post_init__(self):
        """
        Automatically adds fields that are StackLayer instances
        and adds them to the dictionary.
        """
        self.layers = {
            obj.name: obj
            for f in fields(self)
            if f.init and isinstance((obj := getattr(self, f.name)), StackLayer)
        }

    def __getitem__(self, key) -> StackLayer:
        """Retrieve the layer identified by key"""
        return self.layers[key]

    def _determine_shebang(self, script):
        """
        Determine appropriate shebang based on extension
        of provided script name.

        Args:
            script: script name
        Returns:
            appropriate shebang (e.g. '#!/bin/bash')
        """
        extension = pathlib.Path(script).suffix
        shebang   = ''
        match extension:
            case ".csh":
                shebang = '#!/bin/csh'
            case ".py":
                shebang = '#!/usr/bin/env python'
            case ".sh":
                shebang = '#!/bin/bash'
            case _:
                shebang = '#!/bin/sh'
        return shebang

    def _make_commands(self, configs: List[StackLayerConfig]) -> List[str]:
        """
        Makes list of commands to be run based on provided list
        of stack layer configurations.
        """
        commands = []
        for config in configs:
             layer = replace(self[config.name]) # clone layer to avoid rule/command overrides sticking
             if config.command is not None:
                 layer.command = config.command
             if config.rule is not None:
                 layer.rule = config.rule
             commands.append(
                 layer.make_command(
                     config.inputs, config.outputs, config.arguments
                  )
             )
        return commands

    def make_driver_script(self, script: str, configs: List[StackLayerConfig], metadata: Dict[str, Any] = None) -> None:
        """Make driver script

        Writes driver script at specified path to run a sequence of
        commands based on provided list of layer configurations. Can
        be overwritten for behavior unique to specific stacks.

        Args:
            script: full path of driver script
            configs: list of layer configurations
            metadata: dictionary of metadata about trial (e.g. 'job_id')
        """
        commands = self._make_commands(configs)
        commands.insert(0, self._determine_shebang(script))

        text = "\n\n".join(commands)
        with open(script, 'w') as driver:
            driver.write(text)
