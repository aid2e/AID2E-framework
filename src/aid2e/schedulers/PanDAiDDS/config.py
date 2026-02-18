"""Pydantic configuration model for the PanDAiDDS scheduler.

This module defines a Pydantic model that mirrors the expected PanDAiDDS
attributes used when submitting jobs to the PanDA system. The fields are
inferred from the example `panda_attrs` dictionary used by the EPIC/PanDA
integration.

The model is registered with the scheduler configuration registry so the
framework can discover and validate PanDA runner configurations.
"""

from typing import List, Optional, Any
from pydantic import BaseModel, Field

from aid2e.utilities.configurations.scheduler_registry import register as register_runner_config


class PanDAiDDSRunnerConfig(BaseModel):
    """Configuration for the PanDAiDDS scheduler.

    Example keys (from the upstream example):
    - name: str
    - init_env: any (callable or dict describing environment setup)
    - cloud: str
    - queue: str
    - source_dir: Optional[str]
    - source_dir_parent_level: int
    - exclude_source_files: List[str]
    - max_walltime: int (seconds)
    - core_count: int
    - total_memory: int (MB)
    - enable_separate_log: bool
    - job_dir: Optional[str]
    """

    name: Optional[str] = Field(
        default=None,
        description="PanDA job name, e.g. 'user.<username>.<experiment>'",
    )
    init_env: Optional[Any] = Field(
        default=None,
        description="Initialization environment (callable, dict, or other) to prepare remote jobs",
    )
    cloud: Optional[str] = Field(
        default=None,
        description="Cloud/region for the PanDA submission (e.g. 'US')",
    )
    queue: Optional[str] = Field(
        default=None,
        description="PanDA queue name to submit jobs to",
    )
    source_dir: Optional[str] = Field(
        default=None,
        description=(
            "Directory whose contents should be uploaded to PanDA for remote jobs. ``None`` means current dir"
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
