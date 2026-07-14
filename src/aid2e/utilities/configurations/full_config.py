"""Full configuration loader for canonical AID2E config files."""

from pathlib import Path
from typing import Dict, Optional, Any

import yaml
from pydantic import BaseModel

from .problem_config import ProblemConfiguration, ProblemConfigLoader
from .optimizer_config import OptimizerConfiguration
from .scheduler_config import (
    SchedulerConfigLoader,
    SchedulerConfiguration,
)
from .stack_registry import StackRegistry
from .workflow_config import WorkflowDefinition, WorkflowsConfiguration


class FullConfig(BaseModel):
    """Complete configuration combining problem, optimizer, scheduler, and workflows."""
    problem: ProblemConfiguration
    optimizer: OptimizerConfiguration
    scheduler: Optional[SchedulerConfiguration] = None
    workflows: Optional[WorkflowsConfiguration] = None


def _normalize_workflow_schedulers(data: Any, base_dir: Path) -> Any:
    """Normalize scheduler mappings nested inside workflow payloads."""
    if isinstance(data, list):
        return [_normalize_workflow_schedulers(item, base_dir) for item in data]
    if not isinstance(data, dict):
        return data

    normalized = {}
    for key, value in data.items():
        if (
            key in {"scheduler", "global_scheduler"}
            and isinstance(value, dict)
            and "runner_type" in value
        ):
            normalized[key] = SchedulerConfigLoader.from_dict(
                value,
                base_dir=str(base_dir),
            )
        else:
            normalized[key] = _normalize_workflow_schedulers(value, base_dir)
    return normalized


def _normalize_workflows_data(
    data: Dict[str, Any],
    base_dir: Path,
) -> Optional[WorkflowsConfiguration]:
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
    workflows_raw = _normalize_workflow_schedulers(workflows_raw, base_dir)

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
        scheduler_cfg = SchedulerConfigLoader.from_dict(
            data["scheduler"],
            base_dir=str(base_dir),
        )

    workflows_cfg = _normalize_workflows_data(data, base_dir)

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
