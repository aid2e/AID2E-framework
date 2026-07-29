"""Mocked PanDA/iDDS runner contract tests."""

import sys
import types

from aid2e.schedulers.PanDAiDDS.config import PanDAiDDSRunnerConfig
from aid2e.schedulers.PanDAiDDS.runner import PanDAiDDSScheduler


def panda_test_evaluator(context=None, **kwargs):
    return {"unused": True}


class DummyContext:
    def __init__(self):
        self.pushed = {}

    def xcom_push(self, key, value):
        self.pushed[key] = value


def install_fake_idds(monkeypatch, *, status="finished", result=None, details=None):
    state = {}
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

        def builder(**params):
            state["work_params"] = params
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
    assert state["work_params"] == {"context": context, "x": [0.5, 0.5, 0.5]}

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
