"""Full configuration loader - combines problem and optimization payloads."""

from pathlib import Path
from typing import Dict, Optional, Any

import yaml
from pydantic import BaseModel

from .problem_config import ProblemConfiguration, ProblemConfigLoader
from .optimization_config import OptimizationConfiguration


class FullConfig(BaseModel):
    """Complete configuration combining problem and optimization."""
    problem: ProblemConfiguration
    optimization: OptimizationConfiguration


def _normalize_full_config_data(data: Dict[str, Any], config_path: Path) -> Dict[str, Any]:
    """Normalize loosely structured YAML into a FullConfig-friendly dict."""
    if "problem" not in data:
        raise ValueError("Config must contain a 'problem' section")

    base_dir = config_path.parent
    problem_raw = dict(data.get("problem", {}))

    type_val = problem_raw.get("type") or problem_raw.get("problem_type") or ""
    problem_raw["type"] = type_val
    problem_raw["problem_type"] = type_val

    problem_raw.setdefault("output_location", str(base_dir / "output"))
    problem_raw.setdefault("work_location", str(base_dir / "work"))

    if "design_parameters_file" not in problem_raw:
        design_space = problem_raw.get("design_space") or {}
        if isinstance(design_space, dict) and design_space.get("path"):
            problem_raw["design_parameters_file"] = design_space["path"]

    if "design_space" in problem_raw:
        problem_raw.pop("design_space", None)

    problem_cfg = ProblemConfigLoader.from_dict(problem_raw, base_dir=str(base_dir))

    if "optimization" in data:
        opt_cfg = OptimizationConfiguration(**data["optimization"])
    else:
        optimizer_block = data.get("optimizer", {})
        objectives_raw = problem_raw.get("objectives", [])
        bo_params = optimizer_block.get("bo", {}).get("parameters", {}) if isinstance(optimizer_block, dict) else {}
        opt_cfg = OptimizationConfiguration(
            name=data.get("metadata", {}).get("project", "optimization"),
            description=data.get("metadata", {}).get("description", ""),
            optimizer={
                "name": optimizer_block.get("kind", ""),
                "type": optimizer_block.get("kind", ""),
                "parameters": bo_params,
            },
            objectives=[
                f"{'minimize' if obj.get('minimize', True) else 'maximize'}:{obj['name']}"
                for obj in objectives_raw
                if isinstance(obj, dict) and "name" in obj
            ],
            constraints=[],
            n_iterations=optimizer_block.get("max_iterations", 0),
            n_initial_samples=bo_params.get("n_initial_samples", 0),
            parallel_evaluations=bo_params.get("parallel_evaluations", 1),
        )

    return {"problem": problem_cfg, "optimization": opt_cfg}


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
