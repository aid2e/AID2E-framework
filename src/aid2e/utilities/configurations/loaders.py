"""Configuration loader wrappers for AID2E.

These helpers provide section-level loading APIs on top of the existing
``load_config`` flow so callers can load canonical config sections directly.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from .full_config import _normalize_full_config_data
from .optimizer_config import OptimizerConfiguration
from .problem_config import ProblemConfiguration
from .scheduler_config import SchedulerConfigLoader, SchedulerConfiguration
from .workflow_config import WorkflowDefinition, WorkflowsConfiguration


def load_raw_config(config_file: str) -> Dict[str, Any]:
    """Load raw YAML/JSON configuration content from disk.

    Args:
        config_file: Path to YAML or JSON config.

    Returns:
        Raw top-level configuration dictionary.

    Raises:
        FileNotFoundError: If the config file does not exist.
        ValueError: If the extension is unsupported.
    """
    path = Path(config_file)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {config_file}")

    text = path.read_text(encoding="utf-8")
    suffix = path.suffix.lower()
    if suffix in {".yaml", ".yml"}:
        return yaml.safe_load(text) or {}
    if suffix == ".json":
        return json.loads(text)

    raise ValueError(
        f"Unsupported config extension '{suffix}'. "
        "Use .yaml, .yml, or .json."
    )


def _normalize_sections(config_file: str) -> Dict[str, Any]:
    """Normalize full config content into canonical sections."""
    path = Path(config_file)
    raw = load_raw_config(config_file)
    return _normalize_full_config_data(raw, path)


def load_problem_config(config_file: str) -> ProblemConfiguration:
    """Load only the problem section from a full config file."""
    normalized = _normalize_sections(config_file)
    return normalized["problem"]


def load_optimizer_config(config_file: str) -> OptimizerConfiguration:
    """Load only the optimizer section from a full config file."""
    normalized = _normalize_sections(config_file)
    return normalized["optimizer"]


def load_scheduler_config(config_file: str) -> Optional[SchedulerConfiguration]:
    """Load only the scheduler section from a full config file.

    Accepts only canonical scheduler payloads with ``parameters``.
    """
    path = Path(config_file)
    raw = load_raw_config(config_file)
    scheduler_raw = raw.get("scheduler")
    if not scheduler_raw:
        normalized = _normalize_full_config_data(raw, path)
        return normalized.get("scheduler")

    if not isinstance(scheduler_raw, dict):
        raise ValueError("'scheduler' section must be a mapping")

    return SchedulerConfigLoader.from_dict(scheduler_raw, base_dir=str(path.parent))


def load_workflow_config(config_file: str) -> Optional[WorkflowsConfiguration]:
    """Load workflow configuration from full config if present.

    Accepted layout:
        - ``workflows: {workflows: [...]}``
    """
    normalized = _normalize_sections(config_file)
    return normalized.get("workflows")
