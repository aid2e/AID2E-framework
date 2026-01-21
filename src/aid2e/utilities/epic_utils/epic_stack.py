"""
ePIC software stack definitions. Define concrete classes inheriting
from abstract base StackLayer and ExperimentStack from the workflows
module.
"""

from dataclasses import dataclass, field
from typing import List

from aid2e.utilities.workflows.experimental_stack import (
    AnaLayer,
    ExperimentStack,
    StackLayer
)


class EpicGeoLayer(StackLayer):
    """Geometry layer of ePIC stack"""
    name = "geo"
    command = "checkOverlaps"
    rule = '{command} {arguments} {inputs} {outputs}'

    def _make_input_arg(self, inputs: List[str]) -> str:
        """
        Formats inputs for ePIC-specific geometry
        layer. There should be exactly one input,
        the geometry configuration file to run
        overlap check on.
        """
        if len(inputs) != 1:
            raise ValueError(f"EpicGeoLayer takes one input, got {len(inputs)}")
        return inputs[0]

    def _make_output_arg(self, outputs: List[str]) -> str:
        """
        Formats outputs for ePIC-specific geometry
        layer. There should be exactly one output,
        the log file to store the results of the
        check.

        Also adds shell code to check for overlaps/
        extrusions and exit if any found.
        """
        if len(outputs) != 1:
            raise ValueError(f"EpicGeoLayer takes one output, got {len(outputs)}")
        output = outputs[0]

        # get output and check, exit if there were any overlaps
        checks = [
          f' >& {output}',
          f'grep -F "Number of illegal overlaps/extrusions : " {output} | while IFS= read -r line; do',
          '  lastChar="${line: -1}"',
          '  if [[ $lastChar =~ ^[0-9]$ ]]; then',
          '    if (( lastChar > 0 )); then',
          '      exit 9',
          '    fi',
          '  fi',
          'done'
        ]
        return '\n'.join(checks)


class EpicSimLayer(StackLayer):
    """Simulation layer of ePIC stack"""
    name = "sim"
    command = "npsim"
    rule = '{command} {arguments} {inputs} {outputs}'

    def _make_input_arg(self, inputs: List[str]) -> str:
        """
        Formats inputs for ePIC-specific simulation
        layer. Applies appropriate CLI option based
        on file extension of input.
        """
        formatted_inputs = list()
        for in_file in inputs:
            if in_file.endswith(".py"):
                formatted_inputs.append(f"--steeringFile {in_file}")
            if in_file.endswith(".hepmc3.root") or in_file.endswith(".hepmc"):
                formatted_inputs.append(f"-I {in_file}")
            if in_file.endswith(".mac"):
                formatted_inputs.append(f"--macroFile {in_file}")
        return ' '.join(formatted_inputs)

    def _make_output_arg(self, outputs: List[str]) -> str:
        """
        Formats outputs for ePIC-specific simulation
        layer.
        """
        out_arg = ' '.join(outputs)
        return f"--outputFile {out_arg}"


class EpicRecLayer(StackLayer):
    """Reconstruction layer of ePIC stack"""
    name = "rec"
    command = "eicrecon"
    rule = '{command} {arguments} {outputs} {inputs}'

    def _make_input_arg(self, inputs: List[str]) -> str:
        """
        Formats inputs for ePIC-specific reconstruction
        layer.
        """
        in_arg = ' '.join(inputs)
        return in_arg

    def _make_output_arg(self, outputs: List[str]) -> str:
        """
        Formats outputs for ePIC-specific reconstruction
        layer.
        """
        formatted_outputs = list()
        for out_file in outputs:
            formatted_outputs.append(f"-Ppodio:output_file={out_file}")
        return ' '.join(formatted_outputs)


class EpicAnaLayer(AnaLayer):
    """Analysis layer of ePIC stack"""
    pass


@dataclass
class EpicStack(ExperimentStack):
    """The ePIC software stack"""
    geo: EpicGeoLayer = field(default_factory = EpicGeoLayer)
    sim: EpicSimLayer = field(default_factory = EpicSimLayer)
    rec: EpicRecLayer = field(default_factory = EpicRecLayer)
    ana: EpicAnaLayer = field(default_factory = EpicAnaLayer)
