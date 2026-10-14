#!/usr/bin/env python3
"""Inspect AID2E PanDA/iDDS requests, transforms, tasks, and jobs.

Source ``setup_aid2e.sh`` and ``setup_panda.sh`` before using this script. The
script performs read-only queries through ``panda-client`` and never reads or
prints authentication tokens.

Examples::

    python check_panda_jobs.py --request-id 3665
    python check_panda_jobs.py --request-id 3665 --transform-id 32469
    python check_panda_jobs.py --task-id 40758
    python check_panda_jobs.py --runtaskid 40758
    python check_panda_jobs.py --job-id 4878999 --job-id 4879000
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict, Iterable, List, Optional, Sequence


TRANSFORM_FIELDS = (
    "transform_id",
    "status",
    "substatus",
    "workload_id",
    "internal_id",
    "parent_transform_id",
    "parent_internal_id",
    "errors",
)

TASK_FIELDS = (
    "jediTaskID",
    "status",
    "taskName",
    "parent_tid",
    "errordialog",
    "processingType",
    "taskType",
    "site",
    "nFiles",
    "nFilesFinished",
    "nFilesFailed",
)

JOB_FIELDS = (
    "PandaID",
    "jediTaskID",
    "jobStatus",
    "jobSubStatus",
    "jobName",
    "attemptNr",
    "computingSite",
    "creationTime",
    "startTime",
    "endTime",
    "transExitCode",
    "pilotErrorCode",
    "pilotErrorDiag",
    "ddmErrorCode",
    "ddmErrorDiag",
    "exeErrorCode",
    "exeErrorDiag",
    "taskBufferErrorCode",
    "taskBufferErrorDiag",
)


class QueryError(RuntimeError):
    """A read-only PanDA/iDDS query failed."""


def _display_value(value: Any) -> Any:
    """Convert PanDA/iDDS values into compact JSON-compatible values."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        # iDDS values passed through panda-client can be encoded enum records.
        attributes = value.get("attributes")
        if isinstance(attributes, dict) and attributes.get("_name_"):
            return attributes["_name_"]
        return {str(key): _display_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_display_value(item) for item in value]
    enum_name = getattr(value, "name", None)
    if enum_name:
        return str(enum_name)
    return str(value)


def _select_mapping_fields(mapping: Dict[str, Any], fields: Iterable[str]) -> Dict[str, Any]:
    return {
        field: _display_value(mapping[field])
        for field in fields
        if field in mapping and mapping[field] is not None
    }


def _select_object_fields(obj: Any, fields: Iterable[str]) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    for field in fields:
        value = getattr(obj, field, None)
        if value is not None:
            result[field] = _display_value(value)
    return result


def _unwrap_idds_response(response: Any, operation: str) -> Any:
    """Unwrap panda-client's ``(status, (success, data))`` response."""
    if not isinstance(response, (list, tuple)) or len(response) < 2:
        raise QueryError(f"{operation} returned an unexpected response")
    status, payload = response[0], response[1]
    if status != 0:
        raise QueryError(f"{operation} failed with panda-client status {status}")
    if not isinstance(payload, (list, tuple)) or len(payload) < 2:
        raise QueryError(f"{operation} returned an unexpected payload")
    success, data = payload[0], payload[1]
    if not success:
        raise QueryError(f"{operation} failed: {_display_value(data)}")

    # Some manager calls, including get_transforms in released client versions,
    # add a second ``(success, data)`` envelope and leave the data JSON encoded.
    while (
        isinstance(data, (list, tuple))
        and len(data) == 2
        and isinstance(data[0], bool)
    ):
        nested_success, data = data
        if not nested_success:
            raise QueryError(f"{operation} failed: {_display_value(data)}")
    if isinstance(data, str) and data.lstrip().startswith(("[", "{")):
        try:
            data = json.loads(data)
        except json.JSONDecodeError as exc:
            raise QueryError(f"{operation} returned invalid JSON data") from exc
    return data


def _get_idds_api(verbose: bool = False) -> Any:
    try:
        import idds.common.utils as idds_utils
        import pandaclient.idds_api as idds_api
    except ImportError as exc:
        raise QueryError(
            "PanDA/iDDS client packages are unavailable; source setup_aid2e.sh first"
        ) from exc

    return idds_api.get_api(
        idds_utils.json_dumps,
        compress=True,
        manager=True,
        verbose=verbose,
    )


def query_transforms(
    request_id: int,
    transform_id: Optional[int] = None,
    *,
    verbose: bool = False,
) -> List[Dict[str, Any]]:
    """Return compact transform records for an iDDS request."""
    api = _get_idds_api(verbose=verbose)
    if transform_id is not None:
        raw = _unwrap_idds_response(
            api.get_transform(request_id=request_id, transform_id=transform_id),
            "get_transform",
        )
        raw_transforms = [raw] if raw else []
    else:
        # The bulk get_transforms call is incompatible with some released
        # iDDS manager/client combinations. Detailed request rows reliably
        # expose transform IDs, which can then be queried individually.
        request_rows = _unwrap_idds_response(
            api.get_requests(
                request_id=request_id,
                with_detail=True,
                with_metadata=False,
            ),
            "get_requests",
        ) or []
        transform_ids = sorted(
            {
                int(row["transform_id"])
                for row in request_rows
                if isinstance(row, dict) and row.get("transform_id") is not None
            }
        )
        raw_transforms = [
            _unwrap_idds_response(
                api.get_transform(request_id=request_id, transform_id=item),
                f"get_transform({item})",
            )
            for item in transform_ids
        ]

    return [
        _select_mapping_fields(transform, TRANSFORM_FIELDS)
        for transform in raw_transforms
        if isinstance(transform, dict)
    ]


def query_task(task_id: int, *, verbose: bool = False) -> Dict[str, Any]:
    """Return task details and all discoverable PanDA IDs."""
    try:
        from pandaclient import Client
    except ImportError as exc:
        raise QueryError("panda-client is unavailable; source setup_aid2e.sh first") from exc

    status, task = Client.getJediTaskDetails(
        {"jediTaskID": int(task_id)},
        False,
        True,
        verbose=verbose,
    )
    if status != 0 or not isinstance(task, dict):
        raise QueryError(f"getJediTaskDetails({task_id}) failed with status {status}")

    job_status, panda_ids = Client.getPandaIDsWithTaskID(int(task_id), verbose=verbose)
    if job_status != 0:
        raise QueryError(f"getPandaIDsWithTaskID({task_id}) failed with status {job_status}")

    result = _select_mapping_fields(task, TASK_FIELDS)
    result.setdefault("jediTaskID", int(task_id))
    result["panda_ids"] = [int(job_id) for job_id in (panda_ids or [])]
    return result


def query_jobs(job_ids: Sequence[int], *, verbose: bool = False) -> List[Dict[str, Any]]:
    """Return compact job records, including archived jobs when available."""
    if not job_ids:
        return []
    try:
        from pandaclient import Client
    except ImportError as exc:
        raise QueryError("panda-client is unavailable; source setup_aid2e.sh first") from exc

    status, jobs = Client.getFullJobStatus([int(job_id) for job_id in job_ids], verbose=verbose)
    if status != 0 or jobs is None:
        raise QueryError(f"getFullJobStatus failed with status {status}")
    return [
        _select_object_fields(job, JOB_FIELDS)
        for job in jobs
        if job is not None
    ]


def inspect_identifiers(
    *,
    request_id: Optional[int],
    transform_id: Optional[int],
    task_ids: Sequence[int],
    job_ids: Sequence[int],
    max_jobs: int,
    verbose: bool,
) -> Dict[str, Any]:
    """Resolve identifiers down the request → transform → task → job chain."""
    report: Dict[str, Any] = {}
    discovered_task_ids = {int(task_id) for task_id in task_ids}

    if request_id is not None:
        transforms = query_transforms(request_id, transform_id, verbose=verbose)
        report["request_id"] = int(request_id)
        report["transforms"] = transforms
        discovered_task_ids.update(
            int(transform["workload_id"])
            for transform in transforms
            if transform.get("workload_id") not in (None, "")
        )

    tasks = [query_task(task_id, verbose=verbose) for task_id in sorted(discovered_task_ids)]
    if tasks:
        report["tasks"] = tasks

    discovered_job_ids = {int(job_id) for job_id in job_ids}
    for task in tasks:
        discovered_job_ids.update(task.get("panda_ids", []))

    selected_job_ids = sorted(discovered_job_ids)
    if len(selected_job_ids) > max_jobs:
        report["job_limit"] = {
            "discovered": len(selected_job_ids),
            "queried": max_jobs,
        }
        selected_job_ids = selected_job_ids[:max_jobs]
    if selected_job_ids:
        report["jobs"] = query_jobs(selected_job_ids, verbose=verbose)

    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Inspect PanDA/iDDS execution by request ID, transform ID, JEDI task ID, "
            "or PanDA job ID. Queries are read-only."
        )
    )
    parser.add_argument("--request-id", type=int, help="iDDS request/workflow ID")
    parser.add_argument(
        "--transform-id",
        type=int,
        help="iDDS transform ID; requires --request-id",
    )
    parser.add_argument(
        "--task-id",
        "--jedi-task-id",
        "--runtaskid",
        dest="task_ids",
        action="append",
        type=int,
        default=[],
        help="JEDI/run task ID; may be supplied more than once",
    )
    parser.add_argument(
        "--job-id",
        "--panda-id",
        dest="job_ids",
        action="append",
        type=int,
        default=[],
        help="PanDA job ID; may be supplied more than once",
    )
    parser.add_argument(
        "--max-jobs",
        type=int,
        default=100,
        help="maximum number of discovered jobs to query (default: 100)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="enable panda-client request diagnostics",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.transform_id is not None and args.request_id is None:
        parser.error("--transform-id requires --request-id")
    if args.max_jobs < 1:
        parser.error("--max-jobs must be at least 1")
    if args.request_id is None and not args.task_ids and not args.job_ids:
        parser.error("provide --request-id, --task-id/--runtaskid, or --job-id")

    try:
        report = inspect_identifiers(
            request_id=args.request_id,
            transform_id=args.transform_id,
            task_ids=args.task_ids,
            job_ids=args.job_ids,
            max_jobs=args.max_jobs,
            verbose=args.verbose,
        )
    except QueryError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
