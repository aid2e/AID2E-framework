"""Base environment configuration model

Defines generic base model for configuring environment variables.

Project: AID2E v0.0.0 - AI assisted Detector Design for EIC
Homepage: https://aid2e.github.io/aid2e-framework
Repository: https://github.com/aid2e/AID2E-framework.git
"""

from abc import ABC, abstractmethod
from pydantic import BaseModel


class EnvironmentConfig(ABC, BaseModel):
    """Configures environment variables

    Generic base model for configuring environment variables. Can
    be specialized for specific for specifc contexts such as
    EpicConfiguration.

    Example:
        >>> class MyEnvConfig(EnvironmentConfiguration):
        ...     geometry_install: str
        ...     def activate(self) -> None:
        ...         os.environ['GEOMETRY_INSTALL'] = self.geometry_install
        ...         print(f"[INFO] Set $GEOMETRY_INSTALL to {self.geometry_install}")
    """

    @abstractmethod
    def activate(self) -> None:
        """
        Activate environment variables. Must be implemented
        by subclasses.
        """
        pass
