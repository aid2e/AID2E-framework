"""Configuration loader wrappers for AID2E.

These helpers provide section-level loading APIs on top of the existing
``load_config`` flow so callers can incrementally adopt a declarative
configuration pipeline without restructuring the repository.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from .full_config import _normalize_full_config_data
from .optimization_config import OptimizationConfiguration
from .problem_config import ProblemConfiguration
from .scheduler_config import SchedulerConfiguration
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
    """Normalize legacy/full config content into canonical sections."""
    path = Path(config_file)
    raw = load_raw_config(config_file)
    return _normalize_full_config_data(raw, path)


def load_problem_config(config_file: str) -> ProblemConfiguration:
    """Load only the problem section from a full config file."""
    normalized = _normalize_sections(config_file)
    return normalized["problem"]


def load_optimization_config(config_file: str) -> OptimizationConfiguration:
    """Load only the optimization section from a full config file."""
    normalized = _normalize_sections(config_file)
    return normalized["optimization"]


def load_scheduler_config(config_file: str) -> Optional[SchedulerConfiguration]:
    """Load only the scheduler section from a full config file.

    Supports both canonical scheduler payloads with ``parameters`` and
    legacy payloads that place runner-specific blocks under keys like
    ``joblib`` or ``pandaidds``.
    """
    path = Path(config_file)
    raw = load_raw_config(config_file)
    scheduler_raw = raw.get("scheduler")
    if not scheduler_raw:
        normalized = _normalize_full_config_data(raw, path)
        return normalized.get("scheduler")

    if not isinstance(scheduler_raw, dict):
        raise ValueError("'scheduler' section must be a mapping")

    if "parameters" not in scheduler_raw:
        runner_type = scheduler_raw.get("runner_type")
        if runner_type == "JobLibRunner" and "joblib" in scheduler_raw:
            scheduler_raw = {**scheduler_raw, "parameters": scheduler_raw["joblib"]}
        elif runner_type == "PanDAiDDSRunner":
            panda_payload = (
                scheduler_raw.get("pandaidds")
                or scheduler_raw.get("panda")
                or scheduler_raw.get("panDAiDDS")
            )
            if panda_payload:
                scheduler_raw = {**scheduler_raw, "parameters": panda_payload}

    return SchedulerConfiguration(**scheduler_raw)


def load_workflow_config(config_file: str) -> Optional[WorkflowsConfiguration]:
    """Load workflow configuration from full config if present.

    Accepted layouts:
        - ``workflows: {workflows: [...]}``
        - ``workflows: [...]``
        - ``workflow: {...}`` (single workflow)
    """
    raw = load_raw_config(config_file)

    workflows_raw = raw.get("workflows")
    if workflows_raw is None:
        single = raw.get("workflow")
        if single is None:
            return None
        return WorkflowsConfiguration(workflows=[WorkflowDefinition(**single)])

    if isinstance(workflows_raw, list):
        return WorkflowsConfiguration(
            workflows=[WorkflowDefinition(**item) for item in workflows_raw]
        )

    if isinstance(workflows_raw, dict):
        if "workflows" in workflows_raw:
            return WorkflowsConfiguration(**workflows_raw)
        return WorkflowsConfiguration(workflows=[WorkflowDefinition(**workflows_raw)])

    raise ValueError("'workflows' section must be a list or mapping")


def validate_objective_alignment(
    problem_cfg: ProblemConfiguration,
    optimization_cfg: OptimizationConfiguration,
) -> None:
    """Validate that optimization objectives align with problem objectives.

    Raises:
        ValueError: If optimization references objectives not defined by
            problem configuration.
    """
    problem_names = {obj.name for obj in problem_cfg.objectives}
    opt_names = {obj.name for obj in optimization_cfg.objectives}

    if not opt_names:
        return

    missing = sorted(opt_names - problem_names)
    if missing:
        raise ValueError(
            "Optimization objectives must reference problem objectives. "
            f"Missing in problem section: {missing}"
        )
