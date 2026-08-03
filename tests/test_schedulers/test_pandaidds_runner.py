"""Mocked PanDA/iDDS runner contract tests."""

import sys
import types

from aid2e.schedulers.PanDAiDDS.config import PanDAiDDSRunnerConfig
from aid2e.schedulers.PanDAiDDS.runner import (
    PanDAiDDSScheduler,
    _remote_python_callable_entrypoint,
)


def panda_test_evaluator(context=None, **kwargs):
    return {"unused": True}


def panda_adapter_test_evaluator(context=None, **kwargs):
    context.add_log("remote adapter ran")
    context.xcom_push("seen", kwargs.get("label"))
    return {
        "job_id": context.job_id,
        "design": context.design_point,
        "label": kwargs.get("label"),
        "xcom": context.xcom,
    }


class DummyContext:
    def __init__(self):
        self.pushed = {}

    def xcom_push(self, key, value):
        self.pushed[key] = value


def install_fake_idds(monkeypatch, *, status="finished", result=None, details=None):
    state = {"work_kwargs_history": [], "work_params_history": []}
    result = {"f1": 1.2, "f2": 0.4} if result is None else result
    details = {"attempt": 1} if details is None else details

    idds_module = types.ModuleType("idds")
    iworkflow_module = types.ModuleType("idds.iworkflow")
    workflow_module = types.ModuleType("idds.iworkflow.workflow")
    work_module = types.ModuleType("idds.iworkflow.work")

    class FakeWorkflow:
        def pre_run(self):
            state["workflow_pre_run"] = True

        def prepare(self):
            state["workflow_prepare"] = True

        def submit(self):
            state["workflow_submitted"] = True
            return "req-1"

    class FakeResult:
        def get_result(self, name, key, verbose=False, with_details=False):
            state["result_lookup"] = {
                "name": name,
                "key": key,
                "verbose": verbose,
                "with_details": with_details,
            }
            return result, details

    class FakeWork:
        def __init__(self, name):
            self.name = name
            self.core_count = None
            self.init_async_result_called = False

        def submit(self):
            state["work_submitted"] = True
            return "tf-1"

        def init_async_result(self):
            self.init_async_result_called = True

        def get_status(self):
            return status

        def is_finished(self, value):
            return value == "finished"

        def is_failed(self, value):
            return value == "failed"

        def get_results(self):
            return FakeResult()

    def workflow_def(**kwargs):
        state["workflow_kwargs"] = kwargs

        def builder():
            return FakeWorkflow()

        return builder

    def work_def(**kwargs):
        state["work_kwargs"] = kwargs
        state["work_kwargs_history"].append(kwargs)

        def builder(**params):
            state["work_params"] = params
            state["work_params_history"].append(params)
            work = FakeWork(kwargs["name"])
            state["work"] = work
            return work

        return builder

    workflow_module.workflow = workflow_def
    work_module.work = work_def

    monkeypatch.setitem(sys.modules, "idds", idds_module)
    monkeypatch.setitem(sys.modules, "idds.iworkflow", iworkflow_module)
    monkeypatch.setitem(sys.modules, "idds.iworkflow.workflow", workflow_module)
    monkeypatch.setitem(sys.modules, "idds.iworkflow.work", work_module)

    return state


def test_run_stage_preserves_job_id_and_returns_idds_outputs(monkeypatch, tmp_path):
    state = install_fake_idds(monkeypatch, result={"f1": 1.2, "f2": 0.4})
    context = DummyContext()
    scheduler = PanDAiDDSScheduler(
        PanDAiDDSRunnerConfig(
            name="user.test.panda",
            cloud="US",
            queue="BNL",
            init_env="setup_panda.sh",
            source_dir=str(tmp_path),
        )
    )

    result = scheduler.run_stage(
        "evaluate",
        [
            {
                "job_id": "evaluate:dtlz2:0001",
                "name": "dtlz2",
                "function": panda_test_evaluator,
                "params": {"context": context, "x": [0.5, 0.5, 0.5]},
                "job_context": context,
            }
        ],
        parallelism_policy={"poll_interval": 0},
        working_dir=str(tmp_path),
    )

    assert result.success is True
    assert result.artifacts == {"objectives": {"f1": 1.2, "f2": 0.4}}
    assert len(result.job_statuses) == 1

    status = result.job_statuses[0]
    assert status.job_id == "evaluate:dtlz2:0001"
    assert status.status == "completed"
    assert status.return_code == 0
    assert status.outputs == {"objectives": {"f1": 1.2, "f2": 0.4}}
    assert status.metrics == {"transform_id": "tf-1"}

    assert context.pushed["objectives"] == {"f1": 1.2, "f2": 0.4}
    assert context.pushed["results_details"] == {"attempt": 1}
    assert state["work_kwargs"]["func"] is _remote_python_callable_entrypoint
    assert state["work_params"]["callable_ref"] == (
        "tests.test_schedulers.test_pandaidds_runner:panda_test_evaluator"
    )
    assert state["work_params"]["op_kwargs"] == {"x": [0.5, 0.5, 0.5]}
    assert state["work_params"]["context_payload"]["job_id"] == "evaluate:dtlz2:0001"
    assert state["work_kwargs"]["name"] == state["work_kwargs"]["job_key"]
    assert state["work_kwargs"]["name"].startswith("user.test.panda.")
    assert state["work_kwargs"]["name"].endswith(
        ".evaluate.evaluate:dtlz2:0001.panda_test_evaluator.000001"
    )
    assert state["work_kwargs"]["log_dataset_name"] == f'{state["work_kwargs"]["name"]}.log/'

    cached = scheduler.check_status("evaluate:dtlz2:0001")
    assert cached.status == "completed"
    assert cached.outputs == {"objectives": {"f1": 1.2, "f2": 0.4}}


def test_run_stage_marks_failed_idds_work_failed(monkeypatch, tmp_path):
    install_fake_idds(monkeypatch, status="failed")
    scheduler = PanDAiDDSScheduler(
        PanDAiDDSRunnerConfig(name="user.test.panda", source_dir=str(tmp_path))
    )

    result = scheduler.run_stage(
        "evaluate",
        [
            {
                "job_id": "evaluate:failed:0001",
                "name": "failed_eval",
                "function": panda_test_evaluator,
                "params": {},
            }
        ],
        parallelism_policy={"poll_interval": 0},
        working_dir=str(tmp_path),
    )

    assert result.success is False
    assert result.error_message == "Some jobs failed in stage 'evaluate'"
    assert result.artifacts == {}

    status = result.job_statuses[0]
    assert status.job_id == "evaluate:failed:0001"
    assert status.status == "failed"
    assert status.return_code == -1
    assert "failed" in status.stderr
    assert status.outputs == {}

    cached = scheduler.check_status("evaluate:failed:0001")
    assert cached.status == "failed"
    assert cached.return_code == -1



def test_repeated_logical_job_submissions_get_distinct_panda_work_names(monkeypatch, tmp_path):
    state = install_fake_idds(monkeypatch, status="running")
    scheduler = PanDAiDDSScheduler(
        PanDAiDDSRunnerConfig(name="user.test.panda", source_dir=str(tmp_path))
    )
    job = {
        "job_id": "dtlz2",
        "name": "dtlz2",
        "function": panda_test_evaluator,
        "params": {},
    }

    scheduler.submit_job("evaluate", job, str(tmp_path))
    scheduler.submit_job("evaluate", job, str(tmp_path))
    scheduler.submit_job("evaluate", job, str(tmp_path))

    names = [kwargs["name"] for kwargs in state["work_kwargs_history"]]
    assert len(names) == 3
    assert len(set(names)) == 3
    assert all(name.startswith(f"user.test.panda.{scheduler.submission_id}.") for name in names)
    assert names[0].endswith(".evaluate.dtlz2.panda_test_evaluator.000001")
    assert names[1].endswith(".evaluate.dtlz2.panda_test_evaluator.000002")
    assert names[2].endswith(".evaluate.dtlz2.panda_test_evaluator.000003")
    assert [kwargs["job_key"] for kwargs in state["work_kwargs_history"]] == names
    assert [kwargs["log_dataset_name"] for kwargs in state["work_kwargs_history"]] == [
        f"{names[0]}.log/",
        f"{names[1]}.log/",
        f"{names[2]}.log/",
    ]


def test_distinct_scheduler_instances_do_not_reuse_panda_work_names(tmp_path):
    first = PanDAiDDSScheduler(
        PanDAiDDSRunnerConfig(name="user.test.panda", source_dir=str(tmp_path))
    )
    second = PanDAiDDSScheduler(
        PanDAiDDSRunnerConfig(name="user.test.panda", source_dir=str(tmp_path))
    )

    first_name = first._next_work_name("evaluate", "dtlz2", "panda_test_evaluator")
    second_name = second._next_work_name("evaluate", "dtlz2", "panda_test_evaluator")

    assert first_name != second_name
    assert first_name.endswith(".evaluate.dtlz2.panda_test_evaluator.000001")
    assert second_name.endswith(".evaluate.dtlz2.panda_test_evaluator.000001")


def test_cancel_job_finds_preserved_job_id(tmp_path):
    class CancellableWork:
        def __init__(self):
            self.cancelled = False

        def is_terminated(self):
            return False

        def cancel(self):
            self.cancelled = True

    scheduler = PanDAiDDSScheduler(
        PanDAiDDSRunnerConfig(name="user.test.panda", source_dir=str(tmp_path))
    )
    work = CancellableWork()
    scheduler.running_funcs["evaluate"] = {
        "evaluate:dtlz2:0001": {"funcs": {"panda_test_evaluator": {"work": work}}}
    }

    assert scheduler.cancel_job("evaluate:dtlz2:0001") is True
    assert work.cancelled is True


def test_remote_python_callable_entrypoint_runs_only_configured_callable():
    result = _remote_python_callable_entrypoint(
        "tests.test_schedulers.test_pandaidds_runner:panda_adapter_test_evaluator",
        {
            "task_id": "evaluate:dtlz2",
            "job_id": "dtlz2",
            "stage_id": "evaluate",
            "workflow_id": "wf",
            "design_point": {"x": 0.5},
            "xcom": {},
            "execution_dir": "/tmp/work",
            "output_dir": "/tmp/out",
        },
        {"label": "callable-only"},
    )

    assert result["job_id"] == "dtlz2"
    assert result["design"] == {"x": 0.5}
    assert result["label"] == "callable-only"
    assert result["xcom"] == {"evaluate:dtlz2:seen": "callable-only"}
