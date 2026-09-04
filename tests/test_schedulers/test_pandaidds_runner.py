"""Mocked PanDA/iDDS runner contract tests."""

import sys
import types

import pytest

from aid2e.schedulers.PanDAiDDS.config import PanDAiDDSRunnerConfig
from aid2e.schedulers.PanDAiDDS.multistage_graph import PanDAMultiStageGraphBuilder
from aid2e.schedulers.PanDAiDDS.multistage import PanDAMultiStageJob, PanDAMultiStageSpec
from aid2e.schedulers.PanDAiDDS.multistep import PanDAMultiStepFunctionSpec
from aid2e.utilities.runtime_builders import run_trial_workflow
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
        "input_file_names": kwargs.get("input_file_names"),
        "xcom": context.xcom,
    }


def panda_prepare_evaluator(context=None, **kwargs):
    return {"prepared": kwargs.get("scale", 1)}


def panda_evaluate_from_parent(context=None, **kwargs):
    parent = kwargs["parent_results"]
    return {"f1": parent["prepared"] + 1, "f2": parent["prepared"] + 2}


def panda_chunk_evaluator(context=None, **kwargs):
    return {"chunk": kwargs.get("child_key"), "value": kwargs.get("value", 0)}


def panda_analyze_chunks(context=None, **kwargs):
    parent = kwargs["parent_results"]
    return {"total": sum(item["value"] for item in parent.values())}


def panda_ana_one2one(context=None, **kwargs):
    parent = kwargs["simreco_result"]
    return {"analyzed": parent["value"] + 1}


def panda_local_final_from_ana(context=None, **kwargs):
    ana_result = kwargs["ana_result"]
    return {"objective": ana_result.get("total", ana_result.get("analyzed")) + 1}


class DummyContext:
    def __init__(self):
        self.pushed = {}

    def xcom_push(self, key, value):
        self.pushed[key] = value


def install_fake_idds(
    monkeypatch,
    *,
    status="finished",
    result=None,
    details=None,
    result_sequence=None,
    details_sequence=None,
    status_sequence=None,
):
    state = {
        "work_kwargs_history": [],
        "work_params_history": [],
        "result_lookup_history": [],
        "work_history": [],
    }
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
        def __init__(self, index):
            self.index = index

        def get_result(self, name, key, verbose=False, with_details=False):
            lookup = {
                "name": name,
                "key": key,
                "verbose": verbose,
                "with_details": with_details,
            }
            state["result_lookup"] = lookup
            state["result_lookup_history"].append(lookup)
            selected_result = (
                result_sequence[self.index]
                if result_sequence is not None
                else result
            )
            selected_details = (
                details_sequence[self.index]
                if details_sequence is not None
                else details
            )
            return selected_result, selected_details

    class FakeWork:
        def __init__(self, name, index):
            self.name = name
            self.index = index
            self.internal_id = f"internal-{index + 1}"
            self.core_count = None
            self.init_async_result_called = False
            self.cancelled = False

        def submit(self):
            state["work_submitted"] = True
            return f"tf-{self.index + 1}"

        def init_async_result(self):
            self.init_async_result_called = True

        def get_status(self):
            if status_sequence is not None:
                return status_sequence[self.index]
            return status

        def is_finished(self, value):
            return value == "finished"

        def is_failed(self, value):
            return value == "failed"

        def is_terminated(self):
            return self.cancelled

        def cancel(self):
            self.cancelled = True

        def get_results(self):
            return FakeResult(self.index)

    def workflow_def(**kwargs):
        state["workflow_kwargs"] = kwargs

        def builder():
            return FakeWorkflow()

        return builder

    def work_def(**kwargs):
        state["work_kwargs"] = kwargs
        state["work_kwargs_history"].append(kwargs)
        index = len(state["work_kwargs_history"]) - 1

        def builder(**params):
            state["work_params"] = params
            state["work_params_history"].append(params)
            work = FakeWork(kwargs["name"], index)
            state["work"] = work
            state["work_history"].append(work)
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
    assert state["work_kwargs"]["name"].startswith("user.test.a2e.")
    assert len(state["work_kwargs"]["name"]) <= 64
    assert state["work_kwargs"]["name"].split(".")[-2] == "000001"
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
    assert all(name.startswith("user.test.a2e.") for name in names)
    assert all(len(name) <= 64 for name in names)
    assert names[0].split(".")[-2] == "000001"
    assert names[1].split(".")[-2] == "000002"
    assert names[2].split(".")[-2] == "000003"
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
    assert first_name.startswith("user.test.a2e.")
    assert second_name.startswith("user.test.a2e.")
    assert first_name.split(".")[-2] == "000001"
    assert second_name.split(".")[-2] == "000001"
    assert len(first_name) <= 64
    assert len(second_name) <= 64


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


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({}, "non-empty 'steps' list"),
        ({"steps": []}, "non-empty 'steps' list"),
        ({"steps": ["prepare"]}, "must be a mapping"),
        ({"steps": [{"python_callable": panda_prepare_evaluator}]}, "missing 'name'"),
        (
            {
                "steps": [
                    {"name": "prepare", "python_callable": panda_prepare_evaluator},
                    {"name": "prepare", "python_callable": panda_prepare_evaluator},
                ]
            },
            "Duplicate panda_multistep step name",
        ),
        ({"steps": [{"name": "prepare"}]}, "missing 'python_callable'"),
        (
            {
                "steps": [
                    {"name": "prepare", "python_callable": panda_prepare_evaluator},
                    {
                        "name": "evaluate",
                        "python_callable": panda_evaluate_from_parent,
                        "depends_on": ["missing"],
                    },
                ]
            },
            "depends on unknown step",
        ),
        (
            {
                "steps": [
                    {
                        "name": "prepare",
                        "python_callable": panda_prepare_evaluator,
                        "dep_type": "files",
                    }
                ]
            },
            "expected 'results' or 'datasets'",
        ),
        (
            {
                "steps": [
                    {
                        "name": "prepare",
                        "python_callable": panda_prepare_evaluator,
                        "dep_map": "many2one",
                    }
                ]
            },
            "expected 'one2one' or 'all2one'",
        ),
        (
            {
                "steps": [
                    {"name": "prepare", "python_callable": panda_prepare_evaluator},
                    {
                        "name": "evaluate",
                        "python_callable": panda_evaluate_from_parent,
                        "depends_on": ["prepare"],
                        "dep_type": "datasets",
                        "dep_map": "all2one",
                    },
                ]
            },
            "only dep_map='one2one' is supported",
        ),
        (
            {
                "final": "missing",
                "steps": [{"name": "prepare", "python_callable": panda_prepare_evaluator}],
            },
            "final step 'missing' is not defined",
        ),
        (
            {
                "steps": [
                    {
                        "name": "prepare",
                        "python_callable": panda_prepare_evaluator,
                        "produces_objective": True,
                    },
                    {
                        "name": "evaluate",
                        "python_callable": panda_evaluate_from_parent,
                        "final": True,
                    },
                ]
            },
            "exactly one final objective-producing step",
        ),
    ],
)
def test_panda_multistep_spec_rejects_malformed_payloads(payload, message):
    with pytest.raises(ValueError, match=message):
        PanDAMultiStepFunctionSpec.from_payload(payload)


def test_panda_multistep_failure_cancels_running_children(monkeypatch, tmp_path):
    state = install_fake_idds(
        monkeypatch,
        status_sequence=["running", "failed"],
        result_sequence=[{"value": 1}, {"value": 2}],
    )
    scheduler = PanDAiDDSScheduler(
        PanDAiDDSRunnerConfig(name="user.test.panda", source_dir=str(tmp_path))
    )

    result = scheduler.run_stage(
        "evaluate",
        [
            {
                "job_id": "logical:cancel",
                "name": "cancel_multistep",
                "payload": {
                    "evaluator_type": "panda_multistep",
                    "steps": [
                        {
                            "name": "simreco",
                            "python_callable": panda_chunk_evaluator,
                            "children": [
                                {"key": "running", "op_kwargs": {"value": 1}},
                                {"key": "failed", "op_kwargs": {"value": 2}},
                            ],
                        },
                        {
                            "name": "final",
                            "python_callable": panda_analyze_chunks,
                            "depends_on": "simreco",
                            "dep_type": "results",
                            "dep_map": "all2one",
                            "produces_objective": True,
                        },
                    ],
                },
            }
        ],
        parallelism_policy={"poll_interval": 0},
        working_dir=str(tmp_path),
    )

    assert result.success is False
    assert len(state["work_history"]) == 2
    assert state["work_history"][0].cancelled is True
    assert state["work_history"][1].cancelled is False
    child_metrics = result.job_statuses[0].metrics["panda_multistep_children"]
    assert [child["status"] for child in child_metrics] == ["cancelled", "failed"]


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
    assert result["input_file_names"] is None
    assert result["xcom"] == {"evaluate:dtlz2:seen": "callable-only"}


def test_remote_python_callable_entrypoint_accepts_idds_injected_kwargs():
    result = _remote_python_callable_entrypoint(
        "tests.test_schedulers.test_pandaidds_runner:panda_adapter_test_evaluator",
        {
            "task_id": "dtlz2",
            "job_id": "dtlz2",
            "stage_id": "evaluate",
            "workflow_id": "wf",
            "design_point": {},
            "xcom": {},
        },
        {"label": "dataset-ana"},
        input_file_names=["a.json", "b.json"],
    )

    assert result["label"] == "dataset-ana"
    assert result["input_file_names"] == ["a.json", "b.json"]






def test_panda_multistage_spec_rejects_unknown_dependency_map():
    with pytest.raises(ValueError, match="expected 'one2one'"):
        PanDAMultiStageSpec.from_payload(
            {
                "stages": [
                    {
                        "name": "simreco",
                        "python_callable": panda_prepare_evaluator,
                        "dep_map": "scatter",
                    }
                ]
            }
        )


def test_panda_multistage_dataset_dependency_is_managed_by_panda(monkeypatch, tmp_path):
    state = install_fake_idds(
        monkeypatch,
        result_sequence=[{"simreco": "done"}, {"f1": 3, "f2": 4}],
        details_sequence=[{"stage": "simreco"}, {"stage": "ana"}],
    )
    context = DummyContext()
    scheduler = PanDAiDDSScheduler(
        PanDAiDDSRunnerConfig(name="user.test.panda", source_dir=str(tmp_path))
    )

    result = scheduler.run_stage(
        "evaluate",
        [
            {
                "job_id": "logical:multistage",
                "name": "dataset_stage_job",
                "payload": {
                    "evaluator_type": "panda_multistage",
                    "stages": [
                        {
                            "name": "simreco",
                            "python_callable": panda_prepare_evaluator,
                            "with_output_dataset": True,
                            "output_file": "my_test.txt",
                            "output_dataset": "user.test.simreco.dataset",
                            "num_events": 200,
                            "num_events_per_job": 100,
                        },
                        {
                            "name": "ana",
                            "python_callable": panda_test_evaluator,
                            "depends_on": "simreco",
                            "dep_type": "datasets",
                            "dep_map": "one2one",
                            "with_input_datasets": True,
                            "input_datasets": {
                                "input_file_names": "user.test.simreco.dataset"
                            },
                            "produces_objective": True,
                        },
                    ],
                },
                "job_context": context,
            }
        ],
        parallelism_policy={"poll_interval": 0},
        working_dir=str(tmp_path),
    )

    assert result.success is True
    assert result.artifacts == {"objectives": {"f1": 3, "f2": 4}}
    assert result.job_statuses[0].outputs == {"objectives": {"f1": 3, "f2": 4}}
    assert context.pushed["objectives"] == {"f1": 3, "f2": 4}
    assert context.pushed["results_details"] == {"stage": "ana"}

    simreco_kwargs = state["work_kwargs_history"][0]
    ana_kwargs = state["work_kwargs_history"][1]
    assert simreco_kwargs["output_file_name"] == "my_test.txt"
    assert simreco_kwargs["output_dataset_name"] == "user.test.simreco.dataset/"
    assert simreco_kwargs["num_events"] == 200
    assert simreco_kwargs["num_events_per_job"] == 100
    assert ana_kwargs["input_datasets"] == {
        "input_file_names": "user.test.simreco.dataset"
    }
    assert ana_kwargs["parent_internal_id"] == "internal-1"
    assert [kwargs["name"] for kwargs in state["work_kwargs_history"]] == [
        state["work_kwargs_history"][0]["job_key"],
        state["work_kwargs_history"][1]["job_key"],
    ]
    assert state["result_lookup_history"][-1] == {
        "name": state["work_kwargs_history"][1]["name"],
        "key": state["work_kwargs_history"][1]["job_key"],
        "verbose": True,
        "with_details": True,
    }

    metrics = result.job_statuses[0].metrics["panda_multistage_stages"]
    assert [item["stage"] for item in metrics] == ["simreco", "ana"]
    assert [item["internal_id"] for item in metrics] == ["internal-1", "internal-2"]


def test_panda_multistage_one2many_local_to_remote(monkeypatch, tmp_path):
    state = install_fake_idds(
        monkeypatch,
        result_sequence=[{"child": "a", "f1": 1}, {"child": "b", "f1": 2}],
    )
    scheduler = PanDAiDDSScheduler(
        PanDAiDDSRunnerConfig(name="user.test.panda", source_dir=str(tmp_path))
    )

    result = scheduler.run_stage(
        "evaluate",
        [
            {
                "job_id": "logical:one2many",
                "name": "one2many_stage_job",
                "payload": {
                    "evaluator_type": "panda_multistage",
                    "stages": [
                        {
                            "name": "prepare",
                            "python_callable": panda_prepare_evaluator,
                            "runner": "local",
                            "dep_type": "results",
                            "op_kwargs": {"scale": 5},
                        },
                        {
                            "name": "simreco",
                            "python_callable": panda_chunk_evaluator,
                            "depends_on": "prepare",
                            "dep_type": "results",
                            "dep_map": "one2many",
                            "jobs": [
                                {"key": "a", "op_kwargs": {"value": 1}},
                                {"key": "b", "op_kwargs": {"value": 2}},
                            ],
                            "parent_result_parameter_name": "prepared_result",
                            "produces_objective": True,
                        },
                    ],
                },
            }
        ],
        parallelism_policy={"poll_interval": 0},
        working_dir=str(tmp_path),
    )

    assert result.success is True
    assert len(state["work_kwargs_history"]) == 2
    assert state["work_params_history"][0]["op_kwargs"]["prepared_result"] == {"prepared": 5}
    assert state["work_params_history"][1]["op_kwargs"]["prepared_result"] == {"prepared": 5}
    assert state["work_params_history"][0]["op_kwargs"]["instance_key"] == "a"
    assert state["work_params_history"][1]["op_kwargs"]["instance_key"] == "b"
    metrics = result.job_statuses[0].metrics["panda_multistage_stages"]
    assert [item["execution"] for item in metrics] == ["local", "panda", "panda"]


def test_panda_multistage_submits_remote_children_before_parent_completion(monkeypatch, tmp_path):
    state = install_fake_idds(monkeypatch, status_sequence=["running", "running", "running"])
    scheduler = PanDAiDDSScheduler(
        PanDAiDDSRunnerConfig(name="user.test.panda", source_dir=str(tmp_path))
    )
    coordinator = PanDAMultiStageJob(
        scheduler=scheduler,
        stage_name="evaluate",
        job_definition={
            "job_id": "logical:submit-first",
            "name": "submit_first",
            "payload": {
                "evaluator_type": "panda_multistage",
                "stages": [
                    {
                        "name": "simreco",
                        "python_callable": panda_prepare_evaluator,
                        "with_output_dataset": True,
                        "output_file": "my_test.txt",
                        "jobs": [
                            {"key": "a", "output_dataset": "user.test.simreco.a"},
                            {"key": "b", "output_dataset": "user.test.simreco.b"},
                        ],
                    },
                    {
                        "name": "ana",
                        "python_callable": panda_test_evaluator,
                        "depends_on": "simreco",
                        "dep_type": "datasets",
                        "dep_map": "all2one",
                        "with_input_datasets": True,
                        "input_datasets": {
                            "input_file_names": [
                                "user.test.simreco.a",
                                "user.test.simreco.b",
                            ]
                        },
                        "produces_objective": True,
                    },
                ],
            },
        },
        working_dir=str(tmp_path),
        poll_interval=0,
    )

    coordinator._submit_stage(coordinator.spec.stages[0])
    assert [work.status for work in coordinator.works_by_stage["simreco"]] == ["running", "running"]

    coordinator._submit_stage(coordinator.spec.stages[1])

    assert len(state["work_kwargs_history"]) == 3
    assert state["work_kwargs_history"][2]["parent_internal_id"] == ["internal-1", "internal-2"]
    assert state["work_kwargs_history"][2]["input_datasets"] == {
        "input_file_names": ["user.test.simreco.a", "user.test.simreco.b"]
    }
    assert [work.status for work in coordinator.works_by_stage["simreco"]] == ["running", "running"]
    assert coordinator.works_by_stage["ana"][0].status == "running"



def test_panda_multistage_all2one_dataset_remote_to_remote(monkeypatch, tmp_path):
    state = install_fake_idds(
        monkeypatch,
        result_sequence=[{"sim": "a"}, {"sim": "b"}, {"f1": 3, "f2": 4}],
    )
    scheduler = PanDAiDDSScheduler(
        PanDAiDDSRunnerConfig(name="user.test.panda", source_dir=str(tmp_path))
    )

    result = scheduler.run_stage(
        "evaluate",
        [
            {
                "job_id": "logical:all2one",
                "name": "all2one_stage_job",
                "payload": {
                    "evaluator_type": "panda_multistage",
                    "stages": [
                        {
                            "name": "simreco",
                            "python_callable": panda_prepare_evaluator,
                            "with_output_dataset": True,
                            "output_file": "my_test.txt",
                            "jobs": [
                                {"key": "a", "output_dataset": "user.test.simreco.a"},
                                {"key": "b", "output_dataset": "user.test.simreco.b"},
                            ],
                        },
                        {
                            "name": "ana",
                            "python_callable": panda_test_evaluator,
                            "depends_on": "simreco",
                            "dep_type": "datasets",
                            "dep_map": "all2one",
                            "with_input_datasets": True,
                            "input_datasets": {
                                "input_file_names": [
                                    "user.test.simreco.a",
                                    "user.test.simreco.b",
                                ]
                            },
                            "produces_objective": True,
                        },
                    ],
                },
            }
        ],
        parallelism_policy={"poll_interval": 0},
        working_dir=str(tmp_path),
    )

    assert result.success is True
    assert result.artifacts == {"objectives": {"f1": 3, "f2": 4}}
    assert len(state["work_kwargs_history"]) == 3
    assert state["work_kwargs_history"][0]["output_dataset_name"] == "user.test.simreco.a/"
    assert state["work_kwargs_history"][1]["output_dataset_name"] == "user.test.simreco.b/"
    assert state["work_kwargs_history"][2]["input_datasets"] == {
        "input_file_names": ["user.test.simreco.a", "user.test.simreco.b"]
    }
    assert state["work_kwargs_history"][2]["parent_internal_id"] == ["internal-1", "internal-2"]
    metrics = result.job_statuses[0].metrics["panda_multistage_stages"]
    assert [item["execution"] for item in metrics] == ["panda", "panda", "panda"]


def test_panda_multistage_one2one_result_local_to_remote(monkeypatch, tmp_path):
    state = install_fake_idds(monkeypatch, result_sequence=[{"f1": 6, "f2": 7}])
    scheduler = PanDAiDDSScheduler(
        PanDAiDDSRunnerConfig(name="user.test.panda", source_dir=str(tmp_path))
    )

    result = scheduler.run_stage(
        "evaluate",
        [
            {
                "job_id": "logical:one2one-local-remote",
                "name": "one2one_local_remote",
                "payload": {
                    "evaluator_type": "panda_multistage",
                    "stages": [
                        {
                            "name": "prepare",
                            "python_callable": panda_prepare_evaluator,
                            "runner": "local",
                            "dep_type": "results",
                            "op_kwargs": {"scale": 4},
                        },
                        {
                            "name": "ana",
                            "python_callable": panda_evaluate_from_parent,
                            "depends_on": "prepare",
                            "dep_type": "results",
                            "dep_map": "one2one",
                            "produces_objective": True,
                        },
                    ],
                },
            }
        ],
        parallelism_policy={"poll_interval": 0},
        working_dir=str(tmp_path),
    )

    assert result.success is True
    assert state["work_params_history"][0]["op_kwargs"]["parent_results"] == {"prepared": 4}
    metrics = result.job_statuses[0].metrics["panda_multistage_stages"]
    assert [item["execution"] for item in metrics] == ["local", "panda"]




def test_panda_multistage_graph_builder_builds_all2one_dataset_payload():
    payload = PanDAMultiStageGraphBuilder().build_payload(
        [
            {
                "name": "simreco",
                "jobs": [
                    {
                        "name": "sim_a",
                        "payload": {
                            "python_callable": panda_prepare_evaluator,
                            "with_output_dataset": True,
                            "output_file": "my_test.txt",
                            "output_dataset": "user.test.sim.a",
                            "op_kwargs": {"particle": "pi+"},
                        },
                    },
                    {
                        "name": "sim_b",
                        "payload": {
                            "python_callable": panda_prepare_evaluator,
                            "with_output_dataset": True,
                            "output_file": "my_test.txt",
                            "output_dataset": "user.test.sim.b",
                            "op_kwargs": {"particle": "kaon+"},
                        },
                    },
                ],
            },
            {
                "name": "ana",
                "jobs": [
                    {
                        "name": "ana_all",
                        "payload": {
                            "python_callable": panda_test_evaluator,
                            "depends_on": {"stage": "simreco", "jobs": "*"},
                            "dep_type": "datasets",
                            "dep_map": "many2one",
                            "with_input_datasets": True,
                            "input_datasets": {
                                "input_file_names": ["user.test.sim.a", "user.test.sim.b"]
                            },
                            "produces_objective": True,
                        },
                    }
                ],
            },
        ],
        final_stage="ana",
        trial_index=7,
    )

    assert payload["evaluator_type"] == "panda_multistage"
    assert payload["final_stage"] == "ana"
    assert payload["trial_index"] == 7
    assert [stage["name"] for stage in payload["stages"]] == ["simreco", "ana"]
    assert payload["stages"][0]["python_callable"] is panda_prepare_evaluator
    assert payload["stages"][0]["jobs"] == [
        {
            "key": "sim_a",
            "op_kwargs": {"particle": "pi+"},
            "with_output_dataset": True,
            "output_file": "my_test.txt",
            "output_dataset": "user.test.sim.a",
        },
        {
            "key": "sim_b",
            "op_kwargs": {"particle": "kaon+"},
            "with_output_dataset": True,
            "output_file": "my_test.txt",
            "output_dataset": "user.test.sim.b",
        },
    ]
    assert payload["stages"][1]["depends_on"] == {"stage": "simreco", "jobs": "*"}
    assert payload["stages"][1]["dep_map"] == "many2one"
    assert payload["stages"][1]["jobs"] == [
        {
            "key": "ana_all",
            "with_input_datasets": True,
            "input_datasets": {
                "input_file_names": ["user.test.sim.a", "user.test.sim.b"]
            },
        }
    ]



def test_panda_runner_converts_optimizer_trial_wrapper_to_multistage_graph(monkeypatch, tmp_path):
    design_file = tmp_path / "design.params"
    design_file.write_text(
        "design_space:\n"
        "  design_parameters:\n"
        "    test_variables:\n"
        "      parameters:\n"
        "        x1:\n"
        "          value: 0.5\n"
        "          bounds: [0.0, 1.0]\n"
    )
    config_file = tmp_path / "trial_graph.yml"
    config_file.write_text(
        f"""
problem:
  name: "trial graph smoke"
  problem_type: "DTLZ2"
  output_location: "{tmp_path / 'out'}"
  work_location: "{tmp_path / 'work'}"
  design_parameters_file: "{design_file}"
  objectives:
    - name: "objective"
      direction: "minimize"

optimizer:
  name: "ax"
  type: "bayesian"
  parameters:
    n_iterations: 1
    n_initial_samples: 1
    batch_size: 1

scheduler:
  runner_type: "PanDAiDDSRunner"
  parameters:
    name: "user.test.panda"
    source_dir: "{tmp_path}"

workflows:
  workflows:
    - name: "trial_graph_eval"
      branches:
        - name: "main"
          stages:
            - name: "simreco"
              jobs:
                - name: "sim_a"
                  command: ""
                  payload:
                    evaluator_type: "python"
                    python_callable: "tests.test_schedulers.test_pandaidds_runner:panda_prepare_evaluator"
                    panda_stage: "simreco"
                    with_output_dataset: true
                    output_file: "my_test.txt"
                    output_dataset: "user.test.trial.sim.a"
                - name: "sim_b"
                  command: ""
                  payload:
                    evaluator_type: "python"
                    python_callable: "tests.test_schedulers.test_pandaidds_runner:panda_prepare_evaluator"
                    panda_stage: "simreco"
                    with_output_dataset: true
                    output_file: "my_test.txt"
                    output_dataset: "user.test.trial.sim.b"
            - name: "ana"
              jobs:
                - name: "ana_all"
                  command: ""
                  payload:
                    evaluator_type: "python"
                    python_callable: "tests.test_schedulers.test_pandaidds_runner:panda_test_evaluator"
                    depends_on: "simreco"
                    dep_type: "datasets"
                    dep_map: "all2one"
                    with_input_datasets: true
                    input_datasets:
                      input_file_names:
                        - "user.test.trial.sim.a"
                        - "user.test.trial.sim.b"
            - name: "final"
              scheduler:
                runner_type: "JobLibRunner"
                parameters:
                  n_jobs: 1
              jobs:
                - name: "final_objective"
                  command: ""
                  payload:
                    evaluator_type: "python"
                    python_callable: "tests.test_schedulers.test_pandaidds_runner:panda_local_final_from_ana"
                    depends_on: "ana"
                    dep_type: "results"
                    dep_map: "one2one"
                    parent_result_parameter_name: "ana_result"
                    final: true
"""
    )
    state = install_fake_idds(
        monkeypatch,
        result_sequence=[{"sim": "a"}, {"sim": "b"}, {"total": 5}],
    )
    scheduler = PanDAiDDSScheduler(
        PanDAiDDSRunnerConfig(name="user.test.panda", source_dir=str(tmp_path))
    )

    result = scheduler.run_stage(
        "optimizer_batch_1_trials",
        [
            {
                "job_id": "0",
                "name": "trial_0",
                "function": run_trial_workflow,
                "params": {
                    "config_path": str(config_file),
                    "run_dir": str(tmp_path / "out"),
                    "run_work_dir": str(tmp_path / "work"),
                    "trial_index": 0,
                    "design_point": {"x1": 0.2},
                    "workflow_name": None,
                    "log_level": "WARNING",
                },
            }
        ],
        parallelism_policy={"poll_interval": 0},
        working_dir=str(tmp_path / "work"),
    )

    assert result.success is True
    assert result.job_statuses[0].outputs == {"objectives": {"objective": 6}}
    assert len(state["work_kwargs_history"]) == 3
    assert state["work_kwargs_history"][0]["output_dataset_name"] == "user.test.trial.sim.a/"
    assert state["work_kwargs_history"][1]["output_dataset_name"] == "user.test.trial.sim.b/"
    assert state["work_kwargs_history"][2]["parent_internal_id"] == ["internal-1", "internal-2"]
    assert state["work_kwargs_history"][2]["input_datasets"] == {
        "input_file_names": ["user.test.trial.sim.a", "user.test.trial.sim.b"]
    }


def test_panda_multistage_graph_job_runs_stage_records(monkeypatch, tmp_path):
    state = install_fake_idds(
        monkeypatch,
        result_sequence=[{"sim": "a"}, {"sim": "b"}, {"f1": 8, "f2": 9}],
    )
    scheduler = PanDAiDDSScheduler(
        PanDAiDDSRunnerConfig(name="user.test.panda", source_dir=str(tmp_path))
    )

    result = scheduler.run_stage(
        "evaluate",
        [
            {
                "job_id": "logical:graph",
                "name": "graph_job",
                "payload": {
                    "evaluator_type": "panda_multistage_graph",
                    "final_stage": "ana",
                    "stage_records": [
                        {
                            "name": "simreco",
                            "jobs": [
                                {
                                    "name": "sim_a",
                                    "payload": {
                                        "python_callable": panda_prepare_evaluator,
                                        "with_output_dataset": True,
                                        "output_file": "my_test.txt",
                                        "output_dataset": "user.test.graph.sim.a",
                                    },
                                },
                                {
                                    "name": "sim_b",
                                    "payload": {
                                        "python_callable": panda_prepare_evaluator,
                                        "with_output_dataset": True,
                                        "output_file": "my_test.txt",
                                        "output_dataset": "user.test.graph.sim.b",
                                    },
                                },
                            ],
                        },
                        {
                            "name": "ana",
                            "jobs": [
                                {
                                    "name": "ana_all",
                                    "payload": {
                                        "python_callable": panda_test_evaluator,
                                        "depends_on": "simreco",
                                        "dep_type": "datasets",
                                        "dep_map": "all2one",
                                        "with_input_datasets": True,
                                        "input_datasets": {
                                            "input_file_names": [
                                                "user.test.graph.sim.a",
                                                "user.test.graph.sim.b",
                                            ]
                                        },
                                        "produces_objective": True,
                                    },
                                }
                            ],
                        },
                    ],
                },
            }
        ],
        parallelism_policy={"poll_interval": 0},
        working_dir=str(tmp_path),
    )

    assert result.success is True
    assert result.artifacts == {"objectives": {"f1": 8, "f2": 9}}
    assert len(state["work_kwargs_history"]) == 3
    assert state["work_kwargs_history"][2]["parent_internal_id"] == ["internal-1", "internal-2"]
    assert state["work_kwargs_history"][2]["input_datasets"] == {
        "input_file_names": ["user.test.graph.sim.a", "user.test.graph.sim.b"]
    }
    metrics = result.job_statuses[0].metrics["panda_multistage_stages"]
    assert [item["stage"] for item in metrics] == ["simreco", "simreco", "ana"]


def test_panda_multistep_two_step_results_handoff(monkeypatch, tmp_path):
    state = install_fake_idds(
        monkeypatch,
        result_sequence=[{"prepared": 2}, {"f1": 3, "f2": 4}],
        details_sequence=[{"step": "prepare"}, {"step": "evaluate"}],
    )
    context = DummyContext()
    scheduler = PanDAiDDSScheduler(
        PanDAiDDSRunnerConfig(name="user.test.panda", source_dir=str(tmp_path))
    )

    result = scheduler.run_stage(
        "evaluate",
        [
            {
                "job_id": "logical:0001",
                "name": "dtlz2_multistep",
                "payload": {
                    "evaluator_type": "panda_multistep",
                    "steps": [
                        {
                            "name": "prepare",
                            "python_callable": panda_prepare_evaluator,
                            "op_kwargs": {"scale": 2},
                        },
                        {
                            "name": "evaluate",
                            "python_callable": panda_evaluate_from_parent,
                            "depends_on": ["prepare"],
                            "produces_objective": True,
                        },
                    ],
                },
                "job_context": context,
            }
        ],
        parallelism_policy={"poll_interval": 0},
        working_dir=str(tmp_path),
    )

    assert result.success is True
    assert result.artifacts == {"objectives": {"f1": 3, "f2": 4}}
    assert result.job_statuses[0].outputs == {"objectives": {"f1": 3, "f2": 4}}
    cached = scheduler.check_status("logical:0001")
    assert cached.status == "completed"
    assert cached.outputs == {"objectives": {"f1": 3, "f2": 4}}
    assert context.pushed["objectives"] == {"f1": 3, "f2": 4}
    assert context.pushed["panda_multistep_results"] == {
        "prepare": {"prepared": 2},
        "evaluate": {"f1": 3, "f2": 4},
    }

    assert len(state["work_kwargs_history"]) == 2
    names = [kwargs["name"] for kwargs in state["work_kwargs_history"]]
    assert names[0] == state["work_kwargs_history"][0]["job_key"]
    assert names[1] == state["work_kwargs_history"][1]["job_key"]
    assert state["work_kwargs_history"][0]["log_dataset_name"] == f"{names[0]}.log/"
    assert state["work_kwargs_history"][1]["log_dataset_name"] == f"{names[1]}.log/"
    assert state["work_params_history"][1]["op_kwargs"]["parent_results"] == {"prepared": 2}
    assert state["work_params_history"][0]["context_payload"]["job_id"] == "logical:0001:prepare"
    assert state["work_params_history"][1]["context_payload"]["job_id"] == "logical:0001:evaluate"


def test_panda_multistep_all2one_result_fanin(monkeypatch, tmp_path):
    state = install_fake_idds(
        monkeypatch,
        result_sequence=[
            {"chunk": "a", "value": 10},
            {"chunk": "b", "value": 15},
            {"total": 25},
        ],
    )
    scheduler = PanDAiDDSScheduler(
        PanDAiDDSRunnerConfig(name="user.test.panda", source_dir=str(tmp_path))
    )

    result = scheduler.run_stage(
        "analysis",
        [
            {
                "job_id": "logical:fan",
                "name": "fan_in",
                "payload": {
                    "evaluator_type": "panda_multistep",
                    "steps": [
                        {
                            "name": "simulate",
                            "python_callable": panda_chunk_evaluator,
                            "children": [
                                {"key": "a", "op_kwargs": {"value": 10}},
                                {"key": "b", "op_kwargs": {"value": 15}},
                            ],
                        },
                        {
                            "name": "analyze",
                            "python_callable": panda_analyze_chunks,
                            "depends_on": ["simulate"],
                            "dep_map": "all2one",
                            "produces_objective": True,
                        },
                    ],
                },
            }
        ],
        parallelism_policy={"poll_interval": 0},
        working_dir=str(tmp_path),
    )

    assert result.success is True
    assert result.artifacts == {"objectives": {"total": 25}}
    assert state["work_params_history"][2]["op_kwargs"]["parent_results"] == {
        "a": {"chunk": "a", "value": 10},
        "b": {"chunk": "b", "value": 15},
    }
    assert state["work_params_history"][0]["op_kwargs"]["child_key"] == "a"
    assert state["work_params_history"][1]["op_kwargs"]["child_key"] == "b"


def test_panda_multistep_failure_blocks_dependents(monkeypatch, tmp_path):
    state = install_fake_idds(monkeypatch, status_sequence=["failed"])
    scheduler = PanDAiDDSScheduler(
        PanDAiDDSRunnerConfig(name="user.test.panda", source_dir=str(tmp_path))
    )

    result = scheduler.run_stage(
        "evaluate",
        [
            {
                "job_id": "logical:failed",
                "name": "failed_multistep",
                "payload": {
                    "evaluator_type": "panda_multistep",
                    "steps": [
                        {"name": "prepare", "python_callable": panda_prepare_evaluator},
                        {
                            "name": "evaluate",
                            "python_callable": panda_evaluate_from_parent,
                            "depends_on": ["prepare"],
                            "produces_objective": True,
                        },
                    ],
                },
            }
        ],
        parallelism_policy={"poll_interval": 0},
        working_dir=str(tmp_path),
    )

    assert result.success is False
    assert result.job_statuses[0].status == "failed"
    assert "logical:failed:prepare" in result.job_statuses[0].stderr
    assert len(state["work_kwargs_history"]) == 1



def test_panda_multistep_dataset_one2one_passes_parent_internal_id(monkeypatch, tmp_path):
    state = install_fake_idds(
        monkeypatch,
        result_sequence=[{"prepared": 2}, {"f1": 3, "f2": 4}],
    )
    scheduler = PanDAiDDSScheduler(
        PanDAiDDSRunnerConfig(name="user.test.panda", source_dir=str(tmp_path))
    )

    result = scheduler.run_stage(
        "evaluate",
        [
            {
                "job_id": "logical:dataset-dep",
                "name": "dataset_dep",
                "payload": {
                    "evaluator_type": "panda_multistep",
                    "steps": [
                        {
                            "name": "simreco",
                            "python_callable": panda_prepare_evaluator,
                            "return_func_results": False,
                            "with_output_dataset": True,
                            "output_file": "my_test.txt",
                            "output_dataset": "#panda_scope.simreco.#evaluation_id.#job_id",
                            "children": [{"key": "eta:0.1/pi+"}],
                            "num_events": 200,
                            "num_events_per_job": 100,
                        },
                        {
                            "name": "ana",
                            "python_callable": panda_evaluate_from_parent,
                            "depends_on": "simreco",
                            "dep_type": "datasets",
                            "dep_map": "one2one",
                            "with_input_datasets": True,
                            "input_datasets": {"input_file_names": "#panda_scope.simreco.#evaluation_id.#job_id"},
                            "produces_objective": True,
                        },
                    ],
                },
            }
        ],
        parallelism_policy={"poll_interval": 0},
        working_dir=str(tmp_path),
    )

    assert result.success is True
    simreco_kwargs = state["work_kwargs_history"][0]
    ana_kwargs = state["work_kwargs_history"][1]
    assert "with_output_dataset" not in simreco_kwargs
    assert simreco_kwargs["output_file_name"] == "my_test.txt"
    assert simreco_kwargs["output_dataset_name"].startswith("user.test.simreco.")
    assert simreco_kwargs["output_dataset_name"].endswith(".eta_0.1_pi/")
    assert "#evaluation_id" not in simreco_kwargs["output_dataset_name"]
    assert simreco_kwargs["num_events"] == 200
    assert simreco_kwargs["num_events_per_job"] == 100
    assert "with_input_datasets" not in ana_kwargs
    assert ana_kwargs["input_datasets"]["input_file_names"].startswith("user.test.simreco.")
    assert ana_kwargs["input_datasets"]["input_file_names"].endswith(".eta_0.1_pi")
    assert "#evaluation_id" not in ana_kwargs["input_datasets"]["input_file_names"]
    assert ana_kwargs["parent_internal_id"] == "internal-1"
    assert state["result_lookup_history"] == [
        {
            "name": state["work_kwargs_history"][1]["name"],
            "key": state["work_kwargs_history"][1]["job_key"],
            "verbose": True,
            "with_details": True,
        }
    ]



def test_panda_multistep_dataset_templates_resolve_aid2e_tokens(monkeypatch, tmp_path):
    state = install_fake_idds(
        monkeypatch,
        result_sequence=[{"prepared": 2}, {"f1": 3, "f2": 4}],
    )
    context = types.SimpleNamespace(
        workflow_id="workflow:alpha",
        stage_id="stage:evaluate",
        task_id="task:001",
        job_id="ctx:job",
        execution_dir=str(tmp_path),
        output_dir=str(tmp_path),
        design_point={"x": 0.2},
        xcom={},
        artifacts={},
        logs=[],
    )
    scheduler = PanDAiDDSScheduler(
        PanDAiDDSRunnerConfig(name="user.test.panda", source_dir=str(tmp_path))
    )
    scheduler.submission_id = "submission:001"

    result = scheduler.run_stage(
        "evaluate",
        [
            {
                "job_id": "logical:dataset:tokens",
                "name": "dataset_tokens",
                "payload": {
                    "evaluator_type": "panda_multistep",
                    "trial_index": 7,
                    "steps": [
                        {
                            "name": "simreco",
                            "python_callable": panda_prepare_evaluator,
                            "return_func_results": False,
                            "output_file": "result-{step_name}-{child_key}.json",
                            "output_dataset": (
                                "{panda_scope}.aid2e.{submission_id}.{workflow_id}."
                                "{stage_id}.{job_id}.{step_name}.{child_key}.{trial_index}"
                            ),
                            "children": [{"key": "eta:0.1/pi+"}],
                        },
                        {
                            "name": "ana",
                            "python_callable": panda_evaluate_from_parent,
                            "depends_on": "simreco",
                            "dep_type": "datasets",
                            "dep_map": "one2one",
                            "input_datasets": {
                                "input_file_names": (
                                    "{panda_scope}.aid2e.{submission_id}.{workflow_id}."
                                    "{stage_id}.{job_id}.simreco.{child_key}.{trial_index}"
                                )
                            },
                            "produces_objective": True,
                        },
                    ],
                },
                "job_context": context,
            }
        ],
        parallelism_policy={"poll_interval": 0},
        working_dir=str(tmp_path),
    )

    assert result.success is True
    simreco_kwargs = state["work_kwargs_history"][0]
    ana_kwargs = state["work_kwargs_history"][1]
    expected_dataset = (
        "user.test.aid2e.submission_001.workflow_alpha.stage_evaluate."
        "logical_dataset_tokens.simreco.eta_0.1_pi.7"
    )
    assert simreco_kwargs["output_file_name"] == "result-simreco-eta_0.1_pi.json"
    assert simreco_kwargs["output_dataset_name"] == f"{expected_dataset}/"
    assert ana_kwargs["input_datasets"] == {"input_file_names": expected_dataset}
    assert ana_kwargs["parent_internal_id"] == "internal-1"


def test_panda_multistep_rejects_dataset_all2one_until_later(monkeypatch, tmp_path):
    install_fake_idds(monkeypatch)
    scheduler = PanDAiDDSScheduler(
        PanDAiDDSRunnerConfig(name="user.test.panda", source_dir=str(tmp_path))
    )

    result = scheduler.run_stage(
        "evaluate",
        [
            {
                "job_id": "logical:dataset-all2one",
                "name": "dataset_all2one",
                "payload": {
                    "evaluator_type": "panda_multistep",
                    "steps": [
                        {"name": "simreco", "python_callable": panda_prepare_evaluator},
                        {
                            "name": "ana",
                            "python_callable": panda_evaluate_from_parent,
                            "depends_on": "simreco",
                            "dep_type": "datasets",
                            "dep_map": "all2one",
                            "produces_objective": True,
                        },
                    ],
                },
            }
        ],
        parallelism_policy={"poll_interval": 0},
        working_dir=str(tmp_path),
    )

    assert result.success is False
    assert "only dep_map='one2one' is supported" in result.job_statuses[0].stderr


def test_panda_multistep_n_simreco_one_ana_then_local_final(monkeypatch, tmp_path):
    state = install_fake_idds(
        monkeypatch,
        result_sequence=[
            {"value": 10},
            {"value": 20},
            {"analyzed": 30},
        ],
    )
    scheduler = PanDAiDDSScheduler(
        PanDAiDDSRunnerConfig(name="user.test.panda", source_dir=str(tmp_path))
    )

    result = scheduler.run_stage(
        "evaluate",
        [
            {
                "job_id": "logical:three-step",
                "name": "three_step",
                "payload": {
                    "evaluator_type": "panda_multistep",
                    "steps": [
                        {
                            "name": "simreco",
                            "python_callable": panda_chunk_evaluator,
                            "children": [
                                {"key": "a", "op_kwargs": {"value": 10}},
                                {"key": "b", "op_kwargs": {"value": 20}},
                            ],
                        },
                        {
                            "name": "ana",
                            "python_callable": panda_analyze_chunks,
                            "depends_on": "simreco",
                            "dep_type": "results",
                            "dep_map": "all2one",
                            "parent_result_parameter_name": "parent_results",
                        },
                        {
                            "name": "final",
                            "python_callable": panda_local_final_from_ana,
                            "depends_on": "ana",
                            "dep_type": "results",
                            "dep_map": "one2one",
                            "runner": "local",
                            "parent_result_parameter_name": "ana_result",
                            "produces_objective": True,
                        },
                    ],
                },
            }
        ],
        parallelism_policy={"poll_interval": 0},
        working_dir=str(tmp_path),
    )

    assert result.success is True
    assert result.artifacts == {"objectives": {"objective": 31}}
    assert len(state["work_kwargs_history"]) == 3
    assert state["work_params_history"][2]["op_kwargs"]["parent_results"] == {
        "a": {"value": 10},
        "b": {"value": 20},
    }
    child_metrics = result.job_statuses[0].metrics["panda_multistep_children"]
    assert [child["step"] for child in child_metrics] == ["simreco", "simreco", "ana", "final"]
    assert [child["execution"] for child in child_metrics] == ["panda", "panda", "panda", "local"]

def test_dtlz2_dataset_simreco_writes_message_output_file(tmp_path, monkeypatch):
    from examples.evaluators.dtlz2_panda import panda_stage_simreco

    context = types.SimpleNamespace(
        design_point={
            "DTLZ2_variables.x1": 0.2,
            "DTLZ2_variables.x2": 0.3,
            "DTLZ2_variables.x3": 0.4,
            "DTLZ2_variables.x4": 0.5,
            "DTLZ2_variables.x5": 0.6,
        }
    )
    monkeypatch.chdir(tmp_path)

    result = panda_stage_simreco(
        context,
        particle="pi+",
        eta_point=0.1,
        output_file_name="my_test.txt",
        output_dataset_name="user.test.aid2e.dtlz2.simreco.eta_0p1_pi",
        num_events=200,
        num_events_per_job=100,
    )

    assert result["particle"] == "pi+"
    assert "simreco produced xyz=" in result["message"]
    output_path = tmp_path / "my_test.txt"
    assert output_path.is_file()

    import json

    data = json.loads(output_path.read_text())
    assert data["xyz"] == result["xyz"]
    assert data["message"] == result["message"]
    assert data["particle"] == "pi+"
    assert data["eta_point"] == 0.1
    assert not (tmp_path / "user.test.aid2e.dtlz2.simreco.eta_0p1_pi_000001.my_test.txt").exists()
    assert not (tmp_path / "user.test.aid2e.dtlz2.simreco.eta_0p1_pi_000002.my_test.txt").exists()


def test_dtlz2_dataset_ana_reads_and_prints_simreco_messages(tmp_path, capsys):
    from examples.evaluators.dtlz2_panda import panda_stage_ana

    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    first.write_text('{"xyz": 1.25, "message": "first simreco message"}\n')
    second.write_text('{"xyz": 2.75, "message": "second simreco message"}\n')

    result = panda_stage_ana(
        types.SimpleNamespace(design_point={}),
        input_file_names=[str(first), str(second)],
    )

    captured = capsys.readouterr()
    assert result == {"xyz": 4.0, "n_inputs": 2}
    assert f"ana read from {first}: first simreco message" in captured.out
    assert f"ana read from {second}: second simreco message" in captured.out

