"""
ePIC software stack definitions. Define concrete classes inheriting
from abstract base StackLayer and ExperimentStack from the workflows
module.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import os
import shutil

from aid2e.utilities.configurations.experimental_stack_config import (
    StackLayerConfig
)
from aid2e.utilities.configurations.stack_registry import StackRegistry
from aid2e.utilities.epic_utils.epic_design_config import EpicDesignConfig
from aid2e.utilities.epic_utils.epic_env_config import EpicEnvConfig, EpicEnvConfigLoader
from aid2e.utilities.workflows.execution_engine import JobContext
from aid2e.utilities.workflows.experimental_stack import (
    AnaLayer,
    ExperimentStack,
    StackLayer,
)
from aid2e.utilities.workflows.geometry_utils import modify_xml_files


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

    def prepare_for_execution(self, **kwargs) -> Optional[str]:
        """
        Prepare for running ePIC driver script.
        """
        context = None
        for arg, value in kwargs.items():
            if isinstance(value, JobContext):
                context = value

        # JobContext must be provided to access execution dir
        if context is None:
            raise RuntimeError("No JobContext provided to EpicStack.prepare_for_execution")

        # Need EpicDesignConfig to determine geometry modifications
        if context.design is None:
            raise AttributeError("DesignConfig not present in job context. Must define a DesignConfig")
        if not isinstance(context.design, EpicDesignConfig):
            raise TypeError("DesignConfig is not an instance of EpicDesignConfig. Must use EpicDesignConfig if running with ePIC stack")

        # make sure a geometry directory has been defined as a template
        if 'EPIC_INSTALL' not in os.environ:
            raise EnvironmentError("Variable 'EPIC_INSTALL' not set. Must define epic_install.")

        template_geo_dir = os.environ['EPIC_INSTALL']
        trial_geo_dir = '/'.join([context.execution_dir, os.path.basename(template_geo_dir)])
        if not os.path.exists(trial_geo_dir):
            shutil.copytree(template_geo_dir, trial_geo_dir)

        modifications = context.design.get_xml_modifications(context.design_point)
        modify_xml_files(modifications)
        context.add_log(f"Modified geometry in job {context.job_id}")

        # list of commands to execute at start of driver script
        commands = "\n".join([
            "set -e\n",
            f"if [ ! -f {trial_geo_dir}/compiled.log]; then",
            f"  cmake -B {trial_geo_dir}/build -S {trial_geo_dir} -DCMAKE_INSTALL_PREFIX={trial_geo_dir}/install",
            f"  cmake --build {trial_geo_dir}/build",
            f"  cmake --install {trial_geo_dir}/build\n",
            "  time=$(date -u)",
            f'  Job {context.job_id} ' + 'geometry compiled at ${time}" > ' + f"{trial_geo_dir}/compiled.log",
            "fi\n",
        ])
        return commands

    def make_driver_script(
        self,
        script: str,
        configs: List[StackLayerConfig],
        preparations: str = None,
        **kwargs
    ) -> None:
        """
        Create a driver script to run ePIC layers.
        """
        context = None
        for arg, value in kwargs.items():
            if isinstance(value, JobContext):
                context = value

        # JobContext must be provided to access execution dir
        if context is None:
            raise RuntimeError("No JobContext provided to EpicStack.make_driver_script")

        commands = self._make_commands(configs)
        commands.insert(0, self._determine_shebang(script))
        if preprations != None:
            commands.insert(1, preparations)

        # reconstruct geometry dir for job
        #   - FIXME this can be improved! We can likely make use
        #     of xcom to retrieve this
        template_geo_dir = os.environ['EPIC_INSTALL']
        trial_geo_dir = '/'.join([context.execution_dir, os.path.basename(template_geo_dir)])

        # make sure a geometry config has been specififed
        if 'EPIC_CONFIG' not in os.environ:
            raise EnvironmentError("Variable 'EPIC_CONFIG' not set. Must define epic_config.")

        # ensure detector path is set
        detector = f"source {trial_geo_dir}/install/bin/thisepic.sh\n" \
                   f"export DETECTOR_CONFIG={os.environ['EPIC_CONFIG']}"
        commands.insert(2, detector)

        text = "\n\n".join(commands)
        with open(script, 'w') as driver:
            driver.write(text)

    def make_driver_command(self, script: str, **kwargs) -> str:
        """
        Form command to run ePIC driver script.
        """
        if 'EIC_SINGULARITY_IMAGE' in os.environ:
            return f"singularity exec {os.environ['EIC_SINGULARITY_IMAGE']} {script}"
        elif 'EIC_SHELL' in os.environ:
            return f"{os.environ['EIC_SHELL']} -- {script}"
        else:
            raise EnvironmentError("Neither 'EIC_SINGULARITY_IMAGE' nor 'EIC_SHELL' set. Must define eic_shell or singularity image.")


# Register ePIC stack config & implementation in stack registry
StackRegistry.register_stack(
    name="epic",
    config_model=EpicEnvConfig,
    config_loader=EpicEnvConfigLoader,
    experimental_stack=EpicStack,
)
