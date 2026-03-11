"""ePIC environment configuration utilities."""

from typing import Optional
from pydantic import BaseModel, model_validator
from pathlib import Path
import os


class EpicConfiguration(BaseModel):
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
        epic_install: Optional path to ePIC installation directory
        eic_recon_install: Optional path to EIC reconstruction installation
        eic_recon: Optional override for EIC reconstruction command
    """
    eic_shell: Optional[str] = None
    singularity_image: Optional[str] = None
    epic_install: Optional[str] = None
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
            os.environ["EIC_SHELL"] = self.singularity_image
        elif self.eic_shell:
            os.environ["EIC_SHELL"] = self.eic_shell

        # set other variables
        if self.epic_install:
            os.environ["EPIC_INSTALL"] = self.epic_install
            if not self.eic_recon_install:
                self.eic_recon_install = str(Path(self.epic_install) / "local")
        if self.eic_recon_install:
            os.environ["EIC_RECON_INSTALL"] = self.eic_recon_install
        if self.eic_recon:
            os.environ["EIC_RECON"] = self.eic_recon

        print("[INFO] ePIC environment variables set:")
        for var in ["EPIC_INSTALL", "EIC_RECON_INSTALL", "EIC_SHELL", "EIC_RECON"]:
            if var in os.environ:
                print(f"  {var} = {os.environ[var]}")
