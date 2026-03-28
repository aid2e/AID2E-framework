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
    _config_models: Dict[str, Type[BaseModel]] = {}
    _experimental_stacks: Dict[str, Type[Any]] = {}

    @classmethod
    def register_stack(
        cls,
        name: str,
        config_model: Type[BaseModel],
        experimental_stack: Type[Any],
    ) -> None:
        """Register a stack type and its configuration/implementation pair."""
        cls._config_models[name] = config_model
        cls._experimental_stacks[name] = experimental_stack

    @classmethod
    def get_config_model(cls, name: str) -> Type[BaseModel]:
        """Get the config model class for a stack name."""
        if name not in cls._config_models:
            raise KeyError(f"Stack config model not registered: {name}")
        return cls._config_models[name]

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
                "config_model": cls._config_models[name],
                "experimental_stack": cls._experimental_stacks[name],
            }
            for name in cls._config_models
        }
