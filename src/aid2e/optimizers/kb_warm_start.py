"""Warm start from an AgenticWF knowledge base (agenticwf-kb ``hpo`` plugin).

The KB stores finished optimization runs as ``hpo_job`` records and, for a new
run, suggests initial points taken from similar past runs
(``POST /records/suggest``). This module converts between AID2E search spaces
and trials and the KB record format; optimizer backends decide how to inject
the points.

Install the client with ``pip install agenticwf-kb-client`` (or from a
checkout: ``pip install ../agenticwf-kb/client``).

Notes:
    ``hpo_job`` records are single-objective. Uploads write one record per
    objective and, for multi-objective problems, one hypervolume record whose
    trial values are each trial's single-point hypervolume (the volume between
    the trial and the run's reference point; larger is better). Suggestions are
    ranked on one or more objectives, or on that hypervolume
    (``KBWarmStartConfig.rank_by``).

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
from itertools import zip_longest
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator

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
        rank_by: How past trials are ranked. ``"objectives"`` ranks on
            ``objective``; ``"hypervolume"`` ranks on past runs' hypervolume
            records (multi-objective problems only), favouring trials that are
            good in every objective at once.
        objective: With ``rank_by="objectives"``, the objective, or list of
            objectives, the suggestion is ranked on. A list splits the ``n``
            points between the objectives. Defaults to the first objective.
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
            when results are saved: ``u:<user>:<slug>``, ``g:<group>:<slug>``,
            a KB id, or a bare slug for one of your own KBs. ``None`` disables
            upload.
        create_upload_kb: Create ``upload_kb_id`` as a records KB when it does
            not exist (a ``g:`` ref creates a group KB, which needs a group
            admin; anything else creates one of your own KBs). An existing KB
            is used as it is.
        job_id: Record id of this run. Defaults to a timestamped id.
        metadata: Metadata stored with the uploaded record(s), usable in
            ``filter`` by later runs. Values must be strings, numbers or
            booleans (``hpo_job`` rejects nested values).
        upload_hypervolume: For multi-objective runs, also upload the
            hypervolume record that ``rank_by="hypervolume"`` reads.
    """

    model_config = ConfigDict(extra="forbid")

    url: Optional[str] = None
    token: Optional[str] = None
    knowledge_base_ids: Optional[List[str]] = None
    rank_by: Literal["objectives", "hypervolume"] = "objectives"
    objective: Optional[Union[str, List[str]]] = None
    description: str = ""
    n: int = Field(default=5, ge=0)
    include_history: bool = False
    filter: Optional[Dict[str, Any]] = None
    options: Dict[str, Any] = Field(default_factory=dict)
    upload_kb_id: Optional[str] = None
    create_upload_kb: bool = True
    job_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    upload_hypervolume: bool = True

    @field_validator("objective")
    @classmethod
    def _non_empty_objective(cls, objective):
        if isinstance(objective, list) and not objective:
            raise ValueError("objective list must not be empty")
        return objective

    @field_validator("metadata")
    @classmethod
    def _scalar_metadata(cls, metadata: Dict[str, Any]) -> Dict[str, Any]:
        nested = [key for key, value in metadata.items()
                  if not isinstance(value, (str, int, float, bool))]
        if nested:
            raise ValueError(
                f"KB metadata values must be strings, numbers or booleans: {nested}")
        return metadata


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


_UUID = re.compile(r"^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$", re.IGNORECASE)
_GROUP_OWNER = "org:"  # owner_subject prefix of group-owned KBs


def _status(error: Exception) -> Optional[int]:
    """HTTP status of a ``KBClientError``, else ``None``."""
    return getattr(error, "status", None)


def _get_kb(client, ref: str) -> Optional[Dict[str, Any]]:
    """The KB ``ref`` (id or ``<owner>:<slug>``), or ``None`` if the caller cannot see one."""
    try:
        return client.request("GET", f"/knowledge-bases/{ref}")
    except Exception as error:
        if _status(error) == 404:
            return None
        raise


def _own_kb(client, slug: str, group: Optional[str]) -> Optional[Dict[str, Any]]:
    """The caller's (or, with ``group``, a group's) records KB ``slug``."""
    kbs = client.request("GET", "/knowledge-bases?type=records&page_size=100")
    found = [
        kb for kb in kbs
        if kb.get("slug") == slug
        and str(kb.get("owner_subject", "")).startswith(_GROUP_OWNER) == bool(group)
        and (not group or snake(group) == snake(kb.get("owner_name") or ""))
    ]
    # Private KBs of this slug are the caller's own; shared ones may be someone else's.
    found.sort(key=lambda kb: kb.get("visibility") != "private")
    return found[0] if found else None


def _records_kb(kb: Dict[str, Any], ref: str) -> Dict[str, Any]:
    if kb.get("type", "records") != "records":
        raise ValueError(
            f"KB '{ref}' is a {kb.get('type')} knowledge base; KB warm start needs a records KB."
        )
    return kb


def ensure_kb(client, ref: str, description: str = "") -> Dict[str, Any]:
    """The records KB ``ref``, created first when it does not exist.

    ``ref`` is a KB id, ``u:<user>:<slug>``, ``g:<group>:<slug>``, or a bare
    slug naming one of the caller's own KBs. A missing ``g:`` KB is created
    for that group (the caller must administer it); any other missing KB is
    created as the caller's own, with ``slug`` as its slug and name.

    Returns:
        The KB as the API returns it (``id``, ``ref``, ``slug``, ``type``, ...).
    """
    owner, sep, slug = ref.rpartition(":")
    if not sep and _UUID.match(ref):
        kb = _get_kb(client, ref)
        if kb is None:
            raise ValueError(f"No knowledge base with id '{ref}'.")
        return _records_kb(kb, ref)
    if sep:
        kb = _get_kb(client, ref)
        if kb is not None:
            return _records_kb(kb, ref)
        if not slug:
            raise ValueError(f"KB ref '{ref}' has no slug.")

    group = owner[2:] if owner.startswith("g:") else None
    try:
        kb = client.create_knowledge_base(
            slug,
            group=group,
            slug=slug,
            type="records",
            description=description or "AID2E optimization runs (hpo_job records)",
        )
    except Exception as error:
        if _status(error) != 409:
            raise
        # The slug is taken: the KB exists under a ref spelled differently.
        kb = _own_kb(client, slug, group)
        if kb is None:
            raise
        if sep:
            logger.info("KB '%s' is '%s'.", ref, kb.get("ref"))
        return _records_kb(kb, ref)

    logger.info("Created records KB '%s' (id %s).", kb.get("ref"), kb.get("id"))
    if sep and kb.get("ref") != ref:
        logger.warning(
            "Created KB '%s' for '%s'; use '%s' in the config to name it exactly.",
            kb.get("ref"), ref, kb.get("ref"))
    return kb


def upload_kb_id(client, config: KBWarmStartConfig) -> str:
    """The KB id to upload to: ``config.upload_kb_id``, created when missing
    (unless ``create_upload_kb`` is off, which uses the ref as given)."""
    if not config.create_upload_kb:
        return config.upload_kb_id
    return ensure_kb(client, config.upload_kb_id)["id"]


def direction_of(objective_directions: Dict[str, Any], name: str) -> str:
    """``"maximize"`` or ``"minimize"`` for an objective (enum or string)."""
    direction = objective_directions.get(name, "minimize")
    direction = getattr(direction, "value", direction)
    return "maximize" if str(direction).lower() == "maximize" else "minimize"


def hypervolume_objective_name(objective_names: List[str]) -> str:
    """Objective name of the hypervolume record for this set of objectives.

    Including the objective names keeps hypervolume records of unrelated
    problems apart in the KB.
    """
    return snake("hypervolume_" + "_".join(objective_names))


def point_hypervolume(
    metrics: Dict[str, Any],
    objective_names: List[str],
    objective_directions: Dict[str, Any],
    reference_point: Dict[str, float],
) -> Optional[float]:
    """Hypervolume of the box between one trial and the reference point.

    Returns ``0.0`` when the trial does not improve on the reference point in
    every objective, and ``None`` when an objective value is missing or not
    finite.
    """
    volume = 1.0
    for name in objective_names:
        value = (metrics or {}).get(name)
        if value is None or not math.isfinite(value):
            return None
        gain = float(reference_point[name]) - float(value)
        if direction_of(objective_directions, name) == "maximize":
            gain = -gain
        if gain <= 0:
            return 0.0
        volume *= gain
    return volume


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
    knowledge_base_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Ask the KB for warm-start points.

    ``knowledge_base_ids`` overrides ``config.knowledge_base_ids`` (e.g. with
    refs resolved to ids).

    Returns:
        ``{"points": [...], "history": [...], "source_jobs": [...]}`` where each
        point and history entry has ``params`` in AID2E names. ``history`` is
        empty unless ``include_history`` applies. Each point keeps the KB's
        ``source`` and ``score`` and gains ``ranked_on``, the KB objective it
        was ranked on.

    Raises:
        ValueError: ``objective`` names an unknown objective, or
            ``rank_by="hypervolume"`` is used with a single objective.
    """
    rankings = _rankings(config, objective_names, objective_directions)

    include_history = config.include_history
    if include_history and len(objective_names) > 1:
        logger.warning("KB include_history needs a single objective; ignored.")
        include_history = False

    mapping = name_map(parameters)
    kb_ids = config.knowledge_base_ids if knowledge_base_ids is None else knowledge_base_ids
    space = kb_search_space(parameters)

    per_ranking: List[List[Dict[str, Any]]] = []
    history: List[Dict[str, Any]] = []
    source_jobs: List[Dict[str, Any]] = []
    # Each ranking asks for all n points, so a ranking that finds fewer leaves
    # room for the others.
    for ranking in rankings:
        body: Dict[str, Any] = {
            "objective": ranking,
            "search_space": space,
            "description": config.description,
            "n": config.n,
            "n_total": config.n,
            "options": {**config.options, "include_history": include_history},
        }
        if kb_ids:
            body["knowledge_base_ids"] = kb_ids
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
                points.append({**point, "params": params, "ranked_on": ranking["name"]})
        per_ranking.append(points)

        for past in (data.get("history") or []) if include_history else []:
            value = past.get("value")
            if value is None or not math.isfinite(value):
                continue
            params = to_aid2e_params(past["params"], mapping, parameters)
            if params is not None:
                history.append({**past, "params": params, "objective": ranking["name"]})

        for job in data.get("source_jobs", []):
            logger.info(
                "KB source run %s (ranked on %s): similarity %.2f %s",
                job.get("job_id"),
                ranking["name"],
                job.get("similarity", 0.0),
                job.get("breakdown", {}),
            )
        source_jobs.extend(data.get("source_jobs", []))

    return {
        "points": _interleave(per_ranking, config.n),
        "history": history,
        "source_jobs": source_jobs,
    }


def _rankings(
    config: KBWarmStartConfig,
    objective_names: List[str],
    objective_directions: Dict[str, Any],
) -> List[Dict[str, str]]:
    """The KB objectives (``{"name", "direction"}``) to rank past trials on."""
    if config.rank_by == "hypervolume":
        if len(objective_names) < 2:
            raise ValueError(
                "KB warm start rank_by='hypervolume' needs two or more objectives.")
        if config.objective is not None:
            logger.warning("KB warm start ranks on hypervolume; 'objective' is ignored.")
        name = hypervolume_objective_name(objective_names)
        logger.info("KB warm start ranks past runs on hypervolume ('%s').", name)
        return [{"name": name, "direction": "maximize"}]

    if config.objective is None:
        objectives = [objective_names[0]]
        if len(objective_names) > 1:
            logger.info("KB warm start ranks past runs on objective '%s'.", objectives[0])
    elif isinstance(config.objective, str):
        objectives = [config.objective]
    else:
        objectives = list(dict.fromkeys(config.objective))
    unknown = [name for name in objectives if name not in objective_names]
    if unknown:
        raise ValueError(
            f"KB warm-start objective '{unknown[0]}' is not one of {objective_names}."
        )
    return [{"name": name, "direction": direction_of(objective_directions, name)}
            for name in objectives]


def _interleave(per_ranking: List[List[Dict[str, Any]]], n: int) -> List[Dict[str, Any]]:
    """Up to ``n`` points taken from each ranking in turn, without repeats."""
    points: List[Dict[str, Any]] = []
    seen = set()
    for round_points in zip_longest(*per_ranking):
        for point in round_points:
            if point is None:
                continue
            key = tuple(sorted((k, repr(v)) for k, v in point["params"].items()))
            if key in seen:
                continue
            seen.add(key)
            points.append(point)
            if len(points) >= n:
                return points
    return points


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
    hypervolume: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """``hpo_job`` records for this run, one per objective, plus a hypervolume record.

    The hypervolume record is added when ``hypervolume`` (as returned by
    ``BaseOptimizer.get_hypervolume()``) is given, the run has two or more
    objectives, and ``config.upload_hypervolume`` is on. Its trial values are
    each trial's single-point hypervolume against ``hypervolume``'s reference
    point; the run's front hypervolume is stored in its metadata.

    Trials imported by a warm start (``warm_started`` metadata) are left out:
    they belong to the runs they came from.
    """
    space = kb_search_space(parameters)
    own = [t for t in trials if t is not None and not (t.metadata or {}).get("warm_started")]
    finished_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    metadata = {
        "framework": framework,
        # hpo_job metadata values must be scalars.
        "objectives": ",".join(objective_names),
        **config.metadata,
    }

    def record(record_id, objective, direction, value_of, extra_metadata=None):
        record_trials = []
        for trial in own:
            value = value_of(trial)
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
        return {
            "job_id": record_id,
            "record_name": record_id,
            "description": config.description,
            "finished_at": finished_at,
            "objective": {"name": objective, "direction": direction},
            "search_space": space,
            "trials": record_trials,
            "metadata": {**metadata, **(extra_metadata or {})},
        }

    records = [
        record(
            job_id if len(objective_names) == 1 else f"{job_id}:{objective}",
            objective,
            direction_of(objective_directions, objective),
            lambda trial, objective=objective: (trial.metrics or {}).get(objective),
        )
        for objective in objective_names
    ]

    if hypervolume and len(objective_names) > 1 and config.upload_hypervolume:
        reference = hypervolume["reference_point"]
        records.append(
            record(
                f"{job_id}:hypervolume",
                hypervolume_objective_name(objective_names),
                "maximize",
                lambda trial: point_hypervolume(
                    trial.metrics, objective_names, objective_directions, reference),
                {
                    "hypervolume": float(hypervolume["value"]),
                    "hypervolume_reference_point": ",".join(
                        f"{name}={reference[name]:.6g}" for name in objective_names),
                    "hypervolume_reference_point_source":
                        hypervolume.get("reference_point_source", ""),
                },
            )
        )
    return records


def upload(client, kb_id: str, records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Upsert ``records`` into KB ``kb_id`` (by ``job_id``).

    Raises:
        ValueError: The KB rejected records. It answers a batch with
            per-record outcomes rather than an HTTP error, so a rejection
            would otherwise pass silently.
    """
    report = client.upsert_records(kb_id, records, record_type=RECORD_TYPE)
    invalid = [o for o in report.get("outcomes", []) if o.get("outcome") == "invalid"]
    if invalid:
        details = "; ".join(
            f"{records[o['index']]['job_id']}: {', '.join(map(str, o.get('errors', [])))}"
            if isinstance(o.get("index"), int) and o["index"] < len(records)
            else ", ".join(map(str, o.get("errors", [])))
            for o in invalid)
        raise ValueError(f"KB rejected {len(invalid)} of {len(records)} record(s): {details}")
    return report
