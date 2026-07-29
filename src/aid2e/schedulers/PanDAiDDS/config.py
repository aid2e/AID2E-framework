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
    - source_dir: Auto-sets to cwd/src if it exists, otherwise cwd
                  Override via PANDA_SOURCE_DIR environment variable

    Fields:
    - name: str (auto-generated)
    - init_env: any
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
            "Passed through unchanged when provided."
        ),
    )
    post_script: Optional[Any] = Field(
        default="rm -fr .local .venv src examples tests docs",
        description=(
            "Post-execution script (callable, dict, or other) to clean up after remote jobs. "
            "If not provided, defaults to 'rm -fr .local .venv src examples tests docs'. "
            "If a string is provided, it will be executed after the job completes."
        ),
    )
    
    @model_validator(mode='after')
    def validate_and_set_defaults(self) -> 'PanDAiDDSRunnerConfig':
        """Validate or generate PanDA job name and set source_dir defaults.
        
        The name must start with 'user.<username>'. If not provided, it will be
        auto-generated using the system username (or PANDA_USERNAME env var).
        
        The source_dir defaults to cwd/src when present, otherwise the current
        working directory. Can be overridden via PANDA_SOURCE_DIR environment
        variable.
        
        Returns:
            Self with validated/generated name and source_dir.
            
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
        
        # Set source_dir to cwd/src when present, otherwise cwd, if not provided.
        if self.source_dir is None:
            # Check environment variable first
            env_source = os.environ.get("PANDA_SOURCE_DIR")
            if env_source:
                self.source_dir = env_source
            else:
                cwd = os.getcwd()
                src_dir = os.path.join(cwd, "src")
                self.source_dir = src_dir if os.path.isdir(src_dir) else cwd
        
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
    source_dir: Optional[str] = Field(
        default=None,
        description=(
            "Directory whose contents should be uploaded to PanDA for remote jobs. "
            "If not provided, defaults to cwd/src when present, otherwise cwd. "
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
            r"^doc",
            r"^DTLZ2",
            r".*json$",
            r".*log$",
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
            ".local",
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
