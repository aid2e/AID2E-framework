"""Registry for stack-specific configuration and stack implementation classes.

Project: AID2E v0.0.0 - AI assisted Detector Design for EIC
Homepage: https://aid2e.github.io/aid2e-framework
Repository: https://github.com/aid2e/AID2E-framework.git
"""

from typing import Dict, Type, Any
from pydantic import BaseModel


class StackRegistry:
    """
    Unified registry for experimental stack configuration models + interfaces
     """
    _env_configs: Dict[str, Type[BaseModel]] = {}
    _env_loaders: Dict[str, Type[Any]] = {}
    _design_configs: Dict[str, Type[BaseModel]] = {}
    _design_loaders: Dict[str, Type[Any]] = {}
    _experimental_stacks: Dict[str, Type[Any]] = {}

    @classmethod
    def register_stack(
        cls,
        name: str,
        env_config: Type[BaseModel],
        env_loader: Type[Any],
        design_config: Type[BaseModel],
        design_loader: Type[Any],
        experimental_stack: Type[Any],
    ) -> None:
        """Register a stack type and its configuration/implementation pair."""
        cls._env_configs[name] = env_config
        cls._env_loaders[name] = env_loader
        cls._design_configs[name] = design_config
        cls._design_loaders[name] = design_loader
        cls._experimental_stacks[name] = experimental_stack

    @classmethod
    def get_env_config(cls, name: str) -> Type[BaseModel]:
        """Get the environment config model for a stack."""
        if name not in cls._env_configs:
            raise KeyError(f"Stack config model not registered: {name}")
        return cls._env_configs[name]

    @classmethod
    def get_env_loader(cls, nmae: str) -> Type[Any]:
        """Get the environment config loader for a stack."""
        if name not in cls._env_configs:
            raise KeyError(f"Stack config loader not registered: {name}")
        return cls._env_loaders[name]

    @classmethod
    def get_design_config(cls, name: str) -> Type[BaseModel]:
        """Get the design config model for a stack."""
        if name not in cls._design_configs:
            raise KeyError(f"Stack config model not registered: {name}")
        return cls._design_configs[name]

    @classmethod
    def get_design_loader(cls, nmae: str) -> Type[Any]:
        """Get the design config loader for a stack."""
        if name not in cls._design_configs:
            raise KeyError(f"Stack config loader not registered: {name}")
        return cls._design_loaders[name]

    @classmethod
    def get_experimental_stack(cls, name: str) -> Type[Any]:
        """Get the stack implementation class for a stack name."""
        if name not in cls._experimental_stacks:
            raise KeyError(f"Experimental stack not registered: {name}")
        return cls._experimental_stacks[name]

    @classmethod
    def list_registered_stacks(cls) -> Dict[str, Dict[str, Type[Any]]]:
        return {
            name: {
                "env_config": cls._env_configs[name],
                "env_loader": cls._env_loaders[name],
                "design_config" : cls._design_configs[name],
                "design_loader" : cls._design_loaders[name],
                "experimental_stack": cls._experimental_stacks[name],
            }
            for name in cls._env_configs
        }
