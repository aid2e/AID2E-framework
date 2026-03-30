"""ePIC environment configuration utilities."""

from typing import Optional
from pydantic import BaseModel, model_validator
from pathlib import Path
import os
import pathlib
import yaml

from aid2e.utilities.configurations.env_config import (
    EnvironmentConfig,
    EnvironmentConfigLoader,
)


class EpicEnvConfig(EnvironmentConfig):
    """ePIC-specific environment configuration.
    
    Manages ePIC detector environment variables including singularity image,
    installation paths, and EIC reconstruction settings. If both singularity
    image and EIC shell script paths are provided, defaults to singularity
    image.
    
    Attributes:
        eic_shell: Path to the EIC shell script (usually named eic-shell),
                   either this OR singularity_image must be provided
        singularity_image: Path to the EIC shell singularity image, either
                           this OR eic_shell must be provided
        epic_install: Optional path to ePIC installation directory, will be
                      used as template for modifying geometry
        epic_config: ePIC geometry configuration to use (e.g. epic, epic_full)
        eic_recon_install: Optional path to EIC reconstruction installation
        eic_recon: Optional override for EIC reconstruction command
    """
    epic_install:Optional[str]
    epic_config: Optional[str]
    eic_shell: Optional[str] = None
    singularity_image: Optional[str] = None
    eic_recon_install: Optional[str] = None
    eic_recon: Optional[str] = None

    @model_validator(mode='before')
    @classmethod
    def ensure_shell_or_image(cls, data):
        """
        Ensure that either eic_shell or singularity_image
        were provided
        """
        is_shell_there = 'eic_shell' in data
        is_image_there = 'singularity_image' in data
        assert is_shell_there or is_image_there
        return data

    def activate(self) -> None:
        """Activate ePIC environment variables and print a summary."""

        # default to singularity image over eic-shell
        if self.singularity_image:
            os.environ["EIC_SINGULARITY_IMAGE"] = self.singularity_image
        elif self.eic_shell:
            os.environ["EIC_SHELL"] = self.eic_shell

        # set other variables
        if self.epic_install:
            os.environ["EPIC_INSTALL"] = self.epic_install
            if not self.eic_recon_install:
                self.eic_recon_install = str(Path(self.epic_install) / "local")
        if self.epic_config:
            os.environ["EPIC_CONFIG"] = self.epic_config
        if self.eic_recon_install:
            os.environ["EIC_RECON_INSTALL"] = self.eic_recon_install
        if self.eic_recon:
            os.environ["EIC_RECON"] = self.eic_recon

        print("[INFO] ePIC environment variables set:")
        for var in ["EPIC_INSTALL", "EIC_RECON_INSTALL", "EIC_SHELL", "EIC_RECON"]:
            if var in os.environ:
                print(f"  {var} = {os.environ[var]}")


class EpicConfiguration(EpicEnvConfig):
    """
    Alias of EpicEnvConfig for backwards compatibility.
    """
    pass


class EpicEnvConfigLoader(EnvironmentConfigLoader):
    """
    Loader for ePIC environment configuration. Loads YAML
    files, instantiates EpicEnvConfig.
    """

    @staticmethod
    def load(file_path: str) -> "EpicEnvConfig":
        """
        Load ePIC environment configuration.

        Args:
            file_path: Path to YAML configuration file
        Returns:
            EpicEnvConfig instance
        """
        path = pathlib.Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Configuration file not found: {file_path}")

        with open(path, 'r') as file:
            data = yaml.safe_load(file)

        if 'epic_environment' not in data:
            raise ValueError(f"Invalid data configuration: missing 'epic_environment' in {file_path}")

        return EpicEnvConfig(**data)
