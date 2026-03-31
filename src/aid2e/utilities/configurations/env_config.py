"""Base environment configuration model

Defines generic base model for configuring environment variables.

Project: AID2E v0.0.0 - AI assisted Detector Design for EIC
Homepage: https://aid2e.github.io/aid2e-framework
Repository: https://github.com/aid2e/AID2E-framework.git
"""

from abc import ABC, abstractmethod
from pydantic import BaseModel
from typing import Generic, TypeVar


class EnvironmentConfig(ABC, BaseModel):
    """Configures environment variables

    Generic base model for configuring environment variables. Must
    be specialized for specific for specifc contexts such as
    EpicConfiguration.

    Example:
        >>> class MyEnvConfig(EnvironmentConfiguration):
        ...     geometry_install: str
        ...     def activate(self) -> None:
        ...         os.environ['GEOMETRY_INSTALL'] = self.geometry_install
        ...         print(f"[INFO] Set $GEOMETRY_INSTALL to {self.geometry_install}")
    """
    @property
    @abstractmethod
    def key(self) -> str:
        """YAML key associated with model (e.g. epic_environment_config)
        """
        pass

    @abstractmethod
    def activate(self) -> None:
        """
        Activate environment variables. Must be implemented
        by subclasses.
        """
        pass


class EnvironmentConfigLoader(ABC):
    """Loader for environment variables

    Generic base class for loading environment config
    models.  Must be specialized for specific contexts
    like EnvironmentConfig.

    Example:
        >>> class MyEnvConfigLoader(EnvironmentConfigLoader[MyEnvConfig]):
        ...     @staticmethod
        ...     def load(file_path: str) -> MyEnvConfigLoader:
        ...         with open(file_path, 'r') as file:
        ...             data = yaml.safe_load(file)
        ...         return MyEnvConfigLoader(**data)
    """

    @staticmethod
    @abstractmethod
    def load(file_path: str) -> "EnvironmentConfig":
        """
        Load an environment configuration from a YAML file.
        Must instantiate and return a subclass of
        EnvironmentConfig.
        """
        pass
