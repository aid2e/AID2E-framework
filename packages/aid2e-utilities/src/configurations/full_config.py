"""Full configuration loader - combines all configurations."""

from pydantic import BaseModel
from typing import Optional
import yaml
from pathlib import Path

from .problem_config import ProblemConfiguration
from .optimization_config import OptimizationConfiguration


class FullConfig(BaseModel):
    """Complete configuration combining problem and optimization."""
    problem: ProblemConfiguration
    optimization: OptimizationConfiguration


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
    
    return FullConfig(**data)
