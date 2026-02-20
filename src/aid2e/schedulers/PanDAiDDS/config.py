"""Pydantic configuration model for the PanDAiDDS scheduler.

This module defines a Pydantic model that mirrors the expected PanDAiDDS
attributes used when submitting jobs to the PanDA system. The fields are
inferred from the example `panda_attrs` dictionary used by the EPIC/PanDA
integration.

The model is registered with the scheduler configuration registry so the
framework can discover and validate PanDA runner configurations.
"""

import os
import getpass
from typing import List, Optional, Any
from pydantic import BaseModel, Field, field_validator, model_validator

from aid2e.utilities.configurations.scheduler_registry import register as register_runner_config


class PanDAiDDSRunnerConfig(BaseModel):
    """Configuration for the PanDAiDDS scheduler.

    Auto-generation behavior:
    - name: Auto-generates as 'user.<username>.aid2e_job' if not provided
            Override username via PANDA_USERNAME environment variable
    - source_dir: Auto-sets to project root directory if not provided
                  Override via PANDA_SOURCE_DIR environment variable
    - init_env: Auto-sets to 'source setup_aid2e.sh' if not provided
                If provided as string, appends ' && source setup_aid2e.sh'

    Fields:
    - name: str (auto-generated)
    - init_env: any (auto-set to source setup script, or prepended if string)
    - cloud: str
    - queue: str
    - working_group: str
    - task_type: str
    - source_dir: str (auto-set to project root)
    - source_dir_parent_level: int
    - exclude_source_files: List[str] (includes .venv, venv, .git)
    - max_walltime: int (seconds)
    - core_count: int
    - total_memory: int (MB)
    - enable_separate_log: bool
    - job_dir: Optional[str]
    """

    name: Optional[str] = Field(
        default=None,
        description=(
            "PanDA job name, must start with 'user.<username>'. "
            "If not provided, will be auto-generated from username. "
            "Set PANDA_USERNAME environment variable to override system username."
        ),
    )
    init_env: Optional[Any] = Field(
        default=None,
        description=(
            "Initialization environment (callable, dict, or other) to prepare remote jobs. "
            "If not provided, defaults to 'source setup_aid2e.sh'. "
            "If a string is provided, 'source setup_aid2e.sh' will be appended to it."
        ),
    )
    
    @model_validator(mode='after')
    def validate_and_set_defaults(self) -> 'PanDAiDDSRunnerConfig':
        """Validate or generate PanDA job name and set source_dir defaults.
        
        The name must start with 'user.<username>'. If not provided, it will be
        auto-generated using the system username (or PANDA_USERNAME env var).
        
        The source_dir defaults to the project root directory. Can be overridden
        via PANDA_SOURCE_DIR environment variable.
        
        The init_env defaults to sourcing setup_aid2e.sh. If a string value is
        already provided, the setup script will be appended to it.
        
        Returns:
            Self with validated/generated name, source_dir, and init_env.
            
        Raises:
            ValueError: If the provided name doesn't start with 'user.'.
        """
        # Validate and generate name
        if self.name is not None and self.name != "":
            if not self.name.startswith("user."):
                raise ValueError(
                    f"PanDA job name must start with 'user.<username>', got: {self.name}"
                )
        else:
            # Auto-generate name from username
            # Check environment variable first, then fall back to system username
            username = os.environ.get("PANDA_USERNAME") or getpass.getuser()
            self.name = f"user.{username}.aid2e_job"
        
        # Set source_dir to project root if not provided
        if self.source_dir is None:
            # Check environment variable first
            env_source = os.environ.get("PANDA_SOURCE_DIR")
            if env_source:
                self.source_dir = env_source
            else:
                # Default to project root directory
                # Navigate from this config file: .../src/aid2e/schedulers/PanDAiDDS/config.py
                # Go up to project root: ../../../.. from this file
                config_file_dir = os.path.dirname(os.path.abspath(__file__))
                project_root = os.path.abspath(os.path.join(config_file_dir, "..", "..", "..", ".."))
                self.source_dir = project_root
        
        # Set init_env to source setup_aid2e.sh, or append to existing
        if self.init_env is None:
            self.init_env = "source setup_aid2e.sh"
        else:
            # If init_env is already set, append the setup script after it
            if isinstance(self.init_env, str):
                self.init_env = f"{self.init_env} && source setup_aid2e.sh"
            # Note: If init_env is a callable or other type, leave it as-is
        
        return self

    cloud: Optional[str] = Field(
        default=None,
        description="Cloud/region for the PanDA submission (e.g. 'US')",
    )
    queue: Optional[str] = Field(
        default=None,
        description="PanDA queue name to submit jobs to",
    )
    working_group: Optional[str] = Field(
        default="AID2E",
        description="Working group for the PanDA submission (e.g. 'wg_epic', 'AID2E')",
    )
    task_type: Optional[str] = Field(
        default="AID2E",
        description="Task type for PanDA job classification (e.g. 'test', 'prod', 'analysis', 'AID2E')",
    )
    source_dir: str = Field(
        default=None,
        description=(
            "Directory whose contents should be uploaded to PanDA for remote jobs. "
            "If not provided, defaults to project root directory. "
            "Set PANDA_SOURCE_DIR environment variable to override."
        ),
    )
    source_dir_parent_level: int = Field(
        default=1,
        description="How many parent levels above the source_dir should be included when uploading",
    )
    exclude_source_files: List[str] = Field(
        default_factory=lambda: [
            r"(^|/)\.[^/]+",
            "doc*",
            "DTLZ2*",
            ".*json",
            ".*log",
            "work",
            "log",
            "OUTDIR",
            "calibrations",
            "fieldmaps",
            "gdml",
            "EICrecon-drich-mobo",
            "eic-software",
            "epic-geom-drich-mobo",
            "irt",
            "share",
            "back*",
            "__pycache__",
            ".venv",
            "venv",
            ".git",
        ],
        description="Filename patterns to exclude when packaging source_dir",
    )
    max_walltime: Optional[int] = Field(
        default=None,
        description="Maximum walltime in seconds for a PanDA job",
    )
    core_count: int = Field(
        default=1,
        description="Number of CPU cores requested per job",
    )
    total_memory: int = Field(
        default=4000,
        description="Total memory in MB requested per job",
    )
    enable_separate_log: bool = Field(
        default=True,
        description="Whether to enable separate log files for each remote job",
    )
    job_dir: Optional[str] = Field(
        default=None,
        description="Remote job working directory (if applicable)",
    )


# Register with the runner-config registry for lookup by runner_type
register_runner_config("PanDAiDDSRunner", PanDAiDDSRunnerConfig)
