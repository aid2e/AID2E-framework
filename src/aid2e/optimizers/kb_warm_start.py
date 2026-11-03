"""Warm start from an AgenticWF knowledge base (agenticwf-kb ``hpo`` plugin).

The KB stores finished optimization runs as ``hpo_job`` records and, for a new
run, suggests initial points taken from similar past runs
(``POST /records/suggest``). This module converts between AID2E search spaces
and trials and the KB record format; optimizer backends decide how to inject
the points.

Install the client with ``pip install agenticwf-kb-client`` (or from a
checkout: ``pip install ../agenticwf-kb/client``).

Notes:
    ``hpo_job`` records are single-objective. For multi-objective problems the
    suggestion is ranked on one objective (``KBWarmStartConfig.objective``), and
    uploads write one record per objective.

    The KB canonicalises parameter names to lowercase ``snake_case``
    (``DTLZ2.x1`` -> ``dtlz2_x1``). Names are mapped back with the same rule, so
    two AID2E parameters must not share a canonical name, and the KB must not
    alias AID2E parameters to other names.
"""

from __future__ import annotations

import datetime
import logging
import math
import re
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from aid2e.utilities.configurations.base_models import ChoiceParameter, RangeParameter

logger = logging.getLogger(__name__)

RECORD_TYPE = "hpo_job"

# AID2E trial status -> hpo_job trial status.
_TRIAL_STATUS = {
    "completed": "complete",
    "failed": "fail",
    "aborted": "pruned",
    "cancelled": "pruned",
}


class KBWarmStartConfig(BaseModel):
    """Configure warm start from, and upload to, an AgenticWF knowledge base.

    Attributes:
        url: KB base URL ending in ``/kb``, e.g.
            ``https://host/app/kb``. Defaults to ``AGENTICWF_KB_URL``, else
            ``AGENTICWF_API_URL`` + ``/kb``.
        token: A standalone KB's own token. Defaults to
            ``AGENTICWF_KB_TOKEN``; without one, the AgenticWF sign-in is used
            (``agenticwf login`` or ``AGENTICWF_TOKEN``; needs
            agenticwf-auth-client).
        knowledge_base_ids: Records KBs to draw past runs from. ``None``
            searches every records KB the caller can read.
        objective: Objective the suggestion is ranked on. Defaults to the first
            objective.
        description: Free text describing this run; the KB matches it against
            past runs' descriptions.
        n: Number of warm-start points. Initialization samples beyond ``n``
            come from the optimizer's own initializer.
        include_history: Also import past trials as completed trials when a
            past run has the identical search space and objective
            (single-objective problems only).
        filter: KB query-language filter on past runs, e.g.
            ``{"field": "metadata.detector", "op": "eq", "value": "bic"}``.
        options: Extra ``suggest`` options (``min_similarity``, ``seed``, ...).
        upload_kb_id: Records KB to store this run in as ``hpo_job`` record(s)
            when results are saved. ``None`` disables upload.
        job_id: Record id of this run. Defaults to a timestamped id.
        metadata: Metadata stored with the uploaded record(s), usable in
            ``filter`` by later runs.
    """

    model_config = ConfigDict(extra="forbid")

    url: Optional[str] = None
    token: Optional[str] = None
    knowledge_base_ids: Optional[List[str]] = None
    objective: Optional[str] = None
    description: str = ""
    n: int = Field(default=5, ge=0)
    include_history: bool = False
    filter: Optional[Dict[str, Any]] = None
    options: Dict[str, Any] = Field(default_factory=dict)
    upload_kb_id: Optional[str] = None
    job_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


def snake(name: str) -> str:
    """The KB's parameter-name canonicalisation (agenticwf-kb hpo ``snake``)."""
    name = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", str(name).strip())
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def make_client(config: KBWarmStartConfig):
    """Build a ``KBClient`` from the config or the environment."""
    try:
        from agenticwf.kb.client import KBClient
    except ImportError as error:
        raise ImportError(
            "KB warm start needs agenticwf-kb-client: pip install agenticwf-kb-client"
        ) from error

    # AGENTICWF_KB_TOKEN (a standalone KB's token) when set, else the AgenticWF
    # sign-in (agenticwf login, AGENTICWF_TOKEN, or a machine client), refreshed
    # as it expires; the URL is AGENTICWF_KB_URL, else AGENTICWF_API_URL + /kb.
    return KBClient.from_env(url=config.url, token=config.token)


def direction_of(objective_directions: Dict[str, Any], name: str) -> str:
    """``"maximize"`` or ``"minimize"`` for an objective (enum or string)."""
    direction = objective_directions.get(name, "minimize")
    direction = getattr(direction, "value", direction)
    return "maximize" if str(direction).lower() == "maximize" else "minimize"


def kb_search_space(parameters: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """An ``hpo_job`` search space from AID2E design parameters."""
    space: Dict[str, Dict[str, Any]] = {}
    for name, param in parameters.items():
        if isinstance(param, RangeParameter):
            low, high = param.bounds
            spec: Dict[str, Any] = {"type": "float", "low": float(low), "high": float(high)}
            if param.value is not None and low <= param.value <= high:
                spec["default"] = float(param.value)
        elif isinstance(param, ChoiceParameter):
            spec = {"type": "categorical", "choices": list(param.choices)}
            if param.value in param.choices:
                spec["default"] = param.value
        else:
            raise ValueError(
                f"Unsupported parameter type for KB warm start: {param.__class__.__name__}"
            )
        space[name] = spec
    return space


def name_map(parameter_names) -> Dict[str, str]:
    """``{canonical KB name: AID2E name}``; rejects names that collide."""
    mapping: Dict[str, str] = {}
    for name in parameter_names:
        key = snake(name)
        if key in mapping:
            raise ValueError(
                f"Parameters '{mapping[key]}' and '{name}' share the KB name '{key}'; "
                "rename one to use KB warm start."
            )
        mapping[key] = name
    return mapping


def to_aid2e_params(
    kb_params: Dict[str, Any], mapping: Dict[str, str], parameters: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    """Map a KB point back to AID2E names and types; ``None`` if incomplete."""
    params: Dict[str, Any] = {}
    for key, value in kb_params.items():
        name = mapping.get(snake(key))
        if name is None:
            continue
        if isinstance(parameters[name], RangeParameter):
            value = float(value)
        params[name] = value
    if set(params) != set(parameters):
        logger.warning(
            "KB point is missing parameters %s (renamed by KB aliases?); skipped.",
            sorted(set(parameters) - set(params)),
        )
        return None
    return params


def suggest(
    client,
    config: KBWarmStartConfig,
    parameters: Dict[str, Any],
    objective_names: List[str],
    objective_directions: Dict[str, Any],
) -> Dict[str, Any]:
    """Ask the KB for warm-start points.

    Returns:
        ``{"points": [...], "history": [...], "source_jobs": [...]}`` where each
        point and history entry has ``params`` in AID2E names. ``history`` is
        empty unless ``include_history`` applies. Each point keeps the KB's
        ``source`` and ``score``.
    """
    objective = config.objective or objective_names[0]
    if objective not in objective_names:
        raise ValueError(
            f"KB warm-start objective '{objective}' is not one of {objective_names}."
        )
    if config.objective is None and len(objective_names) > 1:
        logger.info("KB warm start ranks past runs on objective '%s'.", objective)

    include_history = config.include_history
    if include_history and len(objective_names) > 1:
        logger.warning("KB include_history needs a single objective; ignored.")
        include_history = False

    mapping = name_map(parameters)
    body: Dict[str, Any] = {
        "objective": {
            "name": objective,
            "direction": direction_of(objective_directions, objective),
        },
        "search_space": kb_search_space(parameters),
        "description": config.description,
        "n": config.n,
        "n_total": config.n,
        "options": {**config.options, "include_history": include_history},
    }
    if config.knowledge_base_ids:
        body["knowledge_base_ids"] = config.knowledge_base_ids
    if config.filter:
        body["filter"] = config.filter
    data = client.suggest(**body)

    points = []
    for point in data.get("points", []):
        # The KB pads missing warm points with Halton points; the optimizer's
        # own initializer covers the space instead.
        if "job_id" not in point.get("source", {}):
            continue
        params = to_aid2e_params(point["params"], mapping, parameters)
        if params is not None:
            points.append({**point, "params": params})

    history = []
    for past in (data.get("history") or []) if include_history else []:
        value = past.get("value")
        if value is None or not math.isfinite(value):
            continue
        params = to_aid2e_params(past["params"], mapping, parameters)
        if params is not None:
            history.append({**past, "params": params, "objective": objective})

    for job in data.get("source_jobs", []):
        logger.info(
            "KB source run %s: similarity %.2f %s",
            job.get("job_id"),
            job.get("similarity", 0.0),
            job.get("breakdown", {}),
        )
    return {"points": points, "history": history, "source_jobs": data.get("source_jobs", [])}


def default_job_id(name: Optional[str] = None) -> str:
    """A timestamped record id for this run."""
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"aid2e-{snake(name) if name else 'run'}-{stamp}"


def job_records(
    trials,
    config: KBWarmStartConfig,
    job_id: str,
    parameters: Dict[str, Any],
    objective_names: List[str],
    objective_directions: Dict[str, Any],
    framework: str,
) -> List[Dict[str, Any]]:
    """``hpo_job`` records for this run, one per objective.

    Trials imported by a warm start (``warm_started`` metadata) are left out:
    they belong to the runs they came from.
    """
    space = kb_search_space(parameters)
    own = [t for t in trials if t is not None and not (t.metadata or {}).get("warm_started")]
    finished_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    records = []
    for objective in objective_names:
        record_id = job_id if len(objective_names) == 1 else f"{job_id}:{objective}"
        record_trials = []
        for trial in own:
            value = (trial.metrics or {}).get(objective)
            if value is not None and not math.isfinite(value):
                value = None
            status = _TRIAL_STATUS.get(trial.status, "running")
            if status == "complete" and value is None:
                status = "fail"
            record_trials.append(
                {
                    "number": trial.index,
                    "params": dict(trial.parameters),
                    "value": float(value) if status == "complete" else None,
                    "status": status,
                }
            )
        records.append(
            {
                "job_id": record_id,
                "record_name": record_id,
                "description": config.description,
                "finished_at": finished_at,
                "objective": {
                    "name": objective,
                    "direction": direction_of(objective_directions, objective),
                },
                "search_space": space,
                "trials": record_trials,
                "metadata": {
                    "framework": framework,
                    "objectives": list(objective_names),
                    **config.metadata,
                },
            }
        )
    return records


def upload(client, config: KBWarmStartConfig, records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Upsert ``records`` into ``config.upload_kb_id`` (by ``job_id``)."""
    return client.upsert_records(config.upload_kb_id, records, record_type=RECORD_TYPE)
