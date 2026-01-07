"""ePIC-specific problem configuration models."""

from typing import Optional
from pydantic import BaseModel
from pathlib import Path
import os


class EpicConfiguration(BaseModel):
    """ePIC-specific environment configuration.
    
    Manages ePIC detector environment variables including singularity image,
    installation paths, and EIC reconstruction settings.
    
    Attributes:
        singularity_image: Path to the EIC shell singularity image
        epic_install: Optional path to ePIC installation directory
        eic_recon_install: Optional path to EIC reconstruction installation
        eic_shell: Optional override for singularity shell environment variable
        eic_recon: Optional override for EIC reconstruction command
        
    Example:
        >>> config = EpicConfiguration(
        ...     singularity_image="/path/to/eic-shell.sif",
        ...     epic_install="/opt/epic",
        ...     eic_recon_install="/opt/eic-recon"
        ... )
        >>> config.activate()  # Sets environment variables
    """
    singularity_image: str
    epic_install: Optional[str] = None
    eic_recon_install: Optional[str] = None
    eic_shell: Optional[str] = None
    eic_recon: Optional[str] = None

    def activate(self):
        """Activate ePIC environment variables.
        
        Sets the following environment variables based on configuration:
        - EPIC_INSTALL: From epic_install path
        - EIC_RECON_INSTALL: From eic_recon_install (defaults to epic_install/local)
        - EIC_SHELL: From singularity_image or eic_shell override
        - EIC_RECON: From eic_recon override if provided
        
        Prints a summary of activated environment variables to stdout.
        """
        if self.epic_install:
            os.environ["EPIC_INSTALL"] = self.epic_install
            if not self.eic_recon_install:
                self.eic_recon_install = str(Path(self.epic_install) / "local")
        if self.eic_recon_install:
            os.environ["EIC_RECON_INSTALL"] = self.eic_recon_install
        if self.singularity_image:
            os.environ["EIC_SHELL"] = self.singularity_image
        if self.eic_recon:
            os.environ["EIC_RECON"] = self.eic_recon

        print("[INFO] ePIC environment variables set:")
        for var in ["EPIC_INSTALL", "EIC_RECON_INSTALL", "EIC_SHELL", "EIC_RECON"]:
            if var in os.environ:
                print(f"  {var} = {os.environ[var]}")
