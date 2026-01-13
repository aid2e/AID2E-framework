"""
TODO docstring goes here
"""

from typing import List

from aid2e.utilities.workflows.experimental_stack import AnaLayer, StackLayer


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

    def make_overlap_check_command(self) -> str:
        """Make command to check overlaps

        Makes command to run overlap check on
        ePIC geometry specified by $DETECTOR_PATH/
        $DETECTOR_CONFIG.xml. If overlaps are
        detectored exit subprocess if an overlap is
        found.
        """

        # command to do overlap check
        # TODO how to handle logging overlap output?

        # command(s) to exit if there were any overlaps
        checks = [
          f'grep -F "Number of illegal overlaps/extrusions : " {log} | while IFS= read -r line; do',
          '  lastChar="${line: -1}"',
          '  if [[ $lastChar =~ ^[0-9]$ ]]; then',
          '    if (( lastChar > 0 )); then',
          '      exit 9',
          '    fi',
          '  fi',
          'done'
        ]
        check = ""
        for line in checks:
            check += line + "\n"

        # return full command
        return run + "\n" + check


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
