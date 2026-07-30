"""Full configuration loader for canonical AID2E config files."""

from pathlib import Path
import sys
from typing import Dict, Optional, Any, List

import yaml
from pydantic import BaseModel

from .problem_config import ProblemConfiguration, ProblemConfigLoader
from .optimizer_config import OptimizerConfiguration
from .scheduler_config import SchedulerConfiguration
from .stack_registry import StackRegistry
from .workflow_config import WorkflowDefinition, WorkflowsConfiguration


class FullConfig(BaseModel):
    """Complete configuration combining problem, optimizer, scheduler, and workflows."""
    problem: ProblemConfiguration
    optimizer: OptimizerConfiguration
    scheduler: Optional[SchedulerConfiguration] = None
    workflows: Optional[WorkflowsConfiguration] = None




def _ensure_config_import_path(base_dir: Path) -> None:
    """Allow workflow callables to be imported from beside the config file."""
    resolved = str(base_dir.resolve())
    if resolved not in sys.path:
        sys.path.insert(0, resolved)

def _load_init_env_file(file_path: str, base_dir: Path) -> str:
    """Load PanDA init_env commands from a YAML list or plain text file."""
    path = Path(file_path).expanduser()
    if not path.is_absolute():
        path = (base_dir / path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"PanDA init_env_file not found: {path}")

    if path.suffix.lower() in {".yml", ".yaml"}:
        with path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or []
        if isinstance(data, dict):
            data = data.get("init_env", [])
        if isinstance(data, str):
            return data
        if not isinstance(data, list) or not all(isinstance(item, str) for item in data):
            raise ValueError(
                "PanDA init_env_file YAML must contain a string list or an "
                "init_env string/list field"
            )
        commands: List[str] = data
    else:
        commands = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                command = line.strip()
                if command and not command.startswith("#"):
                    commands.append(command)

    return " ".join(commands)


def _normalize_scheduler_data(
    scheduler_raw: Dict[str, Any],
    base_dir: Path,
) -> SchedulerConfiguration:
    """Normalize canonical scheduler payloads before model validation."""
    normalized = dict(scheduler_raw)
    params = dict(normalized.get("parameters") or {})
    init_env_file = params.pop("init_env_file", None)
    if init_env_file is not None:
        if "init_env" in params:
            raise ValueError(
                "Use only one of scheduler.parameters.init_env or "
                "scheduler.parameters.init_env_file"
            )
        params["init_env"] = _load_init_env_file(str(init_env_file), base_dir)
    normalized["parameters"] = params
    return SchedulerConfiguration(**normalized)

def _normalize_workflows_data(data: Dict[str, Any]) -> Optional[WorkflowsConfiguration]:
    """Normalize canonical workflow payloads to a WorkflowsConfiguration model."""
    if "workflow" in data:
        raise ValueError(
            "Legacy top-level 'workflow' is no longer supported. Use "
            "'workflows: { workflows: [...] }'."
        )

    workflows_raw = data.get("workflows")
    if workflows_raw is None:
        return None

    if not isinstance(workflows_raw, dict) or "workflows" not in workflows_raw:
        raise ValueError(
            "'workflows' must use the canonical wrapper form "
            "'workflows: { workflows: [...] }'."
        )

    # if any worklows are stack-based (indicated by the presence of `stack_type`),
    # validate workflows against stack-specific models
    #   --> FIXME this can be improved! We should allow for multiple
    #       stacks to be run within a single set of workflows
    stack = None
    for workflow in workflows_raw["workflows"]:
        if "stack_type" in workflow:
            stack = workflow["stack_type"]

    if stack is not None:
        registry = StackRegistry.list_registered_stacks()
        if stack not in registry:
            raise KeyError(f"Stack {stack} not listed in StackRegistry")
        else:
            workflows_config = registry[stack]['workflow_config']
            return workflows_config(**workflows_raw)
    else:
        return WorkflowsConfiguration(**workflows_raw)


def _normalize_full_config_data(data: Dict[str, Any], config_path: Path) -> Dict[str, Any]:
    """Normalize canonical YAML into a FullConfig-friendly dict."""
    if "problem" not in data:
        raise ValueError("Config must contain a 'problem' section")
    if "optimization" in data:
        raise ValueError(
            "Config uses retired 'optimization' section. "
            "Use top-level 'optimizer' with fields 'name', 'type', and 'parameters'."
        )
    if "optimizer" not in data:
        raise ValueError("Config must contain a top-level 'optimizer' section")

    base_dir = config_path.parent
    _ensure_config_import_path(base_dir)
    problem_raw = dict(data.get("problem", {}))

    if "type" in problem_raw:
        raise ValueError(
            "Config uses retired 'problem.type'. Use 'problem.problem_type'."
        )
    if "design_space" in problem_raw:
        raise ValueError(
            "Config uses retired 'problem.design_space'. Use "
            "'design_parameters_file' or 'inline_design'."
        )

    problem_raw.setdefault("output_location", str(base_dir / "output"))
    problem_raw.setdefault("work_location", str(base_dir / "work"))

    problem_cfg = ProblemConfigLoader.from_dict(problem_raw, base_dir=str(base_dir))

    optimizer_cfg = OptimizerConfiguration(**data["optimizer"])

    # Load scheduler configuration if present
    scheduler_cfg = None
    if "scheduler" in data:
        scheduler_cfg = _normalize_scheduler_data(data["scheduler"], base_dir)
    workflows_cfg = _normalize_workflows_data(data)

    return {
        "problem": problem_cfg,
        "optimizer": optimizer_cfg,
        "scheduler": scheduler_cfg,
        "workflows": workflows_cfg,
    }


def load_config(config_file: str) -> FullConfig:
    """
    Load complete configuration from a YAML file.
    
    Args:
        config_file: Path to YAML configuration file
        
    Returns:
        FullConfig object with all configurations loaded
        
    Raises:
        FileNotFoundError: If config file doesn't exist
        ValueError: If configuration is invalid
    """
    config_path = Path(config_file)
    
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_file}")
    
    with open(config_path, 'r') as f:
        data = yaml.safe_load(f)

    normalized = _normalize_full_config_data(data or {}, config_path)

    return FullConfig(**normalized)
