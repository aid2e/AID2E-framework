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
from aid2e.utilities.epic_utils.epic_design_config import EpicDesignConfig, EpicDesignConfigLoader
from aid2e.utilities.epic_utils.epic_env_config import EpicEnvConfig, EpicEnvConfigLoader
from aid2e.utilities.epic_utils.epic_problem_config import EpicProblemConfiguration
from aid2e.utilities.epic_utils.epic_stack_config import EpicWorkflowsConfiguration
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
    rule = '{{command}} {{arguments}} -c {{inputs}} {{outputs}}'

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

        checks = [
            f' >& {output}',
            "grep -Eq 'Number of illegal overlaps/extrusions[[:space:]]*"
            rf":[[:space:]]*0[[:space:]]*$' {output} || exit 9",
        ]
        return '\n'.join(checks)


class EpicSimLayer(StackLayer):
    """Simulation layer of ePIC stack"""
    name = "sim"
    command = "npsim"
    rule = '{{command}} --compactFile $DETECTOR_PATH/$DETECTOR_CONFIG.xml {{arguments}} {{inputs}} {{outputs}}'

    def _make_input_arg(self, inputs: List[str]) -> str:
        """
        Formats inputs for ePIC-specific simulation
        layer. Applies appropriate CLI option based
        on file extension of input.
        """
        has_gun = False
        has_macro = False
        formatted_inputs = list()
        for in_file in inputs:
            if in_file.endswith(".py"):
                formatted_inputs.append(f"--steeringFile {in_file}")
                has_gun = True
            if in_file.endswith(".hepmc3.root") or in_file.endswith(".hepmc"):
                formatted_inputs.append(f"-I {in_file}")
            if in_file.endswith(".mac"):
                formatted_inputs.append(f"--macroFile {in_file}")
                has_macro = True

        if has_gun:
            formatted_inputs.insert(0, "-G")
        if has_macro:
            formatted_inputs.insert(0, "--enableG4GPS")
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
    rule = '{{command}} {{arguments}} {{outputs}} {{inputs}}'

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

    def prepare_workflow_geometry(
        self,
        workflow_dir: str,
        design_point: Dict[str, Any],
        problem_config: Any,
        workflow_id: str,
    ) -> str:
        """
        Prepare geometry once for the whole workflow/design point.
        Returns the prepared geometry directory.
        """
        if problem_config is None or problem_config.design_config is None:
            raise AttributeError("DesignConfig not present in workflow context.")
        if not isinstance(problem_config.design_config, EpicDesignConfig):
            raise TypeError("DesignConfig is not an instance of EpicDesignConfig.")

        env_config = problem_config.environment_config
        geometry_mode = getattr(env_config, "geometry_mode", "build") if env_config else "build"
        epic_install = getattr(env_config, "epic_install", None) if env_config else None

        if not epic_install and 'EPIC_INSTALL' not in os.environ:
            raise EnvironmentError("Variable 'EPIC_INSTALL' not set. Must define epic_install.")

        design = problem_config.design_config
        template_geo_dir = epic_install or os.environ['EPIC_INSTALL']

        if geometry_mode == "no_build":
            template_geo_dir = os.path.join(template_geo_dir, "share", "epic")
            trial_geo_dir = os.path.join(workflow_dir, "geometry", "epic")
            if os.path.exists(trial_geo_dir):
                shutil.rmtree(trial_geo_dir)
            shutil.copytree(template_geo_dir, trial_geo_dir)
            os.environ["DETECTOR_PATH"] = trial_geo_dir
            modify_xml_files(design.get_xml_modifications(design_point))
            return trial_geo_dir

        trial_geo_dir = os.path.join(workflow_dir, os.path.basename(template_geo_dir))

        if not os.path.exists(trial_geo_dir):
            shutil.copytree(template_geo_dir, trial_geo_dir)

        original_modifications = design.get_xml_modifications(design_point)

        remapped_modifications = {}
        for src_file, params in original_modifications.items():
            if src_file.startswith(template_geo_dir):
                dst_file = src_file.replace(template_geo_dir, trial_geo_dir, 1)
            else:
                dst_file = src_file
            remapped_modifications[dst_file] = params

        modify_xml_files(remapped_modifications)

        compile_commands = (
            f"cmake -B {trial_geo_dir}/build -S {trial_geo_dir} -DCMAKE_INSTALL_PREFIX={trial_geo_dir}/install\n"
            f"cmake --build {trial_geo_dir}/build\n"
            f"cmake --install {trial_geo_dir}/build\n"
        )
        compile_script = os.path.join(trial_geo_dir, "compile_geo.sh")
        with open(compile_script, "w") as script:
            script.writelines(compile_commands)
        os.chmod(compile_script, 0o777)

        compiled_log = os.path.join(trial_geo_dir, "compiled.log")
        do_compiling = self.make_driver_command(compile_script)
        if not os.path.exists(compiled_log):
            os.system(f"{do_compiling}")
            with open(compiled_log, "w") as f:
                f.write(f"Workflow {workflow_id} geometry compiled\n")

        return trial_geo_dir

    def prepare_for_execution(self, **kwargs) -> Optional[str]:
        context = None
        for _, value in kwargs.items():
            if isinstance(value, JobContext):
                context = value

        if context is None:
            raise RuntimeError("No JobContext provided to EpicStack.prepare_for_execution")

        if context.workflow_context is None:
            raise RuntimeError("No workflow context provided to EpicStack.prepare_for_execution")

        trial_geo_dir = context.workflow_context.parameters.get("prepared_geometry_dir")
        if not trial_geo_dir:
            raise RuntimeError("No prepared geometry directory found in workflow context")

        env_config = context.problem_config.environment_config if context.problem_config else None
        geometry_mode = getattr(env_config, "geometry_mode", "build")
        context.add_log(f"Using {geometry_mode} geometry from {trial_geo_dir}")
        return None

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

        # JobContext, WorkflowContext must be provided to access execution, geoemtry dir
        if context is None:
            raise RuntimeError("No JobContext provided to EpicStack.make_driver_script")
        if context.workflow_context is None:
            raise RuntimeError("No workflow context provided to EpicStack.make_driver_script")

        trial_geo_dir = context.workflow_context.parameters.get("prepared_geometry_dir")
        if not trial_geo_dir:
            raise RuntimeError("No prepared geometry directory found in workflow context")

        env_config = context.problem_config.environment_config if context.problem_config else None
        epic_install = getattr(env_config, "epic_install", None)
        epic_config = getattr(env_config, "epic_config", None) or os.environ.get("EPIC_CONFIG")
        geometry_mode = getattr(env_config, "geometry_mode", "build")
        if not epic_config:
            raise EnvironmentError("Variable 'epic_config' not set. Must define epic_config.")

        if geometry_mode == "no_build":
            if not epic_install:
                raise EnvironmentError("Variable 'epic_install' not set. Must define epic_install.")
            detector_setup = (
                f"source \"{epic_install}/bin/thisepic.sh\" {epic_config}\n"
                f"export EPIC_INSTALL=\"{epic_install}\"\n"
                f"export EPIC_CONFIG=\"{epic_config}\"\n"
                f"export DETECTOR_PATH=\"{trial_geo_dir}\"\n"
                f"export DETECTOR_CONFIG=\"{epic_config}\""
            )
        else:
            detector_setup = (
                f"source \"{trial_geo_dir}/install/bin/thisepic.sh\"\n"
                f"export EPIC_CONFIG=\"{epic_config}\"\n"
                f"export DETECTOR_CONFIG=\"{epic_config}\""
            )

        commands = [
            self._determine_shebang(script),
            "set -euo pipefail",
            detector_setup,
        ]
        if preparations != None:
            commands.append(preparations)
        commands.extend(self._make_commands(configs))

        text = "\n\n".join(commands)
        with open(script, 'w') as driver:
            driver.write(text)
        os.chmod(script, 0o777)

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
    env_config=EpicEnvConfig,
    env_loader=EpicEnvConfigLoader,
    design_config=EpicDesignConfig,
    design_loader=EpicDesignConfigLoader,
    workflow_config=EpicWorkflowsConfiguration,
    experimental_stack=EpicStack,
    problem_config=EpicProblemConfiguration,
)
