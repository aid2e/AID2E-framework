"""Tests for the read-only PanDA/iDDS workflow inspection helper."""

from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT_PATH = (
    Path(__file__).parents[2]
    / "examples"
    / "schedulers"
    / "panda-idds"
    / "check_panda_jobs.py"
)
SPEC = importlib.util.spec_from_file_location("check_panda_jobs", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
check_panda_jobs = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(check_panda_jobs)


def test_task_id_means_idds_workflow_and_jedi_task_id_is_explicit():
    parser = check_panda_jobs.build_parser()

    workflow_args = parser.parse_args(["--task-id", "3672"])
    jedi_args = parser.parse_args(["--jedi-task-id", "40788"])

    assert workflow_args.request_id == 3672
    assert workflow_args.task_ids == []
    assert jedi_args.request_id is None
    assert jedi_args.task_ids == [40788]


def test_workflow_report_groups_jobs_under_their_transforms(monkeypatch):
    transforms = [
        {
            "transform_id": 32497,
            "internal_id": "parent",
            "workload_id": 40788,
            "status": "Finished",
        },
        {
            "transform_id": 32500,
            "internal_id": "child",
            "parent_internal_id": "parent",
            "workload_id": 40790,
            "status": "Finished",
        },
    ]
    tasks = {
        40788: {"jediTaskID": 40788, "status": "done", "panda_ids": [4879043]},
        40790: {"jediTaskID": 40790, "status": "done", "panda_ids": [4879047]},
    }
    jobs = [
        {"PandaID": 4879043, "jediTaskID": 40788, "jobStatus": "finished"},
        {"PandaID": 4879047, "jediTaskID": 40790, "jobStatus": "finished"},
    ]

    monkeypatch.setattr(
        check_panda_jobs,
        "query_transforms",
        lambda request_id, transform_id, verbose=False: transforms,
    )
    monkeypatch.setattr(
        check_panda_jobs,
        "query_workflow",
        lambda request_id, verbose=False: {
            "request_id": request_id,
            "task_id": request_id,
            "status": "Finished",
        },
    )
    monkeypatch.setattr(
        check_panda_jobs,
        "query_task",
        lambda task_id, verbose=False: tasks[task_id],
    )
    monkeypatch.setattr(
        check_panda_jobs,
        "query_jobs",
        lambda job_ids, verbose=False: [
            job for job in jobs if job["PandaID"] in job_ids
        ],
    )

    report = check_panda_jobs.inspect_identifiers(
        request_id=3672,
        transform_id=None,
        task_ids=[],
        job_ids=[],
        max_jobs=100,
        verbose=False,
    )

    workflow = report["workflow"]
    assert workflow["summary"] == {
        "transforms": 2,
        "jedi_tasks": 2,
        "panda_jobs": 2,
        "job_statuses": {"finished": 2},
    }
    assert workflow["transforms"][0]["jedi_task"] == tasks[40788]
    assert workflow["transforms"][0]["jobs"] == [jobs[0]]
    assert workflow["transforms"][1]["parent_internal_id"] == "parent"
    assert workflow["transforms"][1]["jobs"] == [jobs[1]]
