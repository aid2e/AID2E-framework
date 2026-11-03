"""Tests for warm start from an AgenticWF knowledge base (a fake KB client)."""

import pytest

from aid2e.optimizers import kb_warm_start
from aid2e.optimizers.ax import optimizer as ax_optimizer_module
from aid2e.optimizers.ax.config import AxOptimizerConfig
from aid2e.optimizers.ax.optimizer import AxOptimizer
from aid2e.optimizers.base import SearchSpace
from aid2e.optimizers.kb_warm_start import KBWarmStartConfig
from aid2e.utilities.configurations.design_config import DesignConfig

pytestmark = pytest.mark.skipif(
    not ax_optimizer_module.AX_NODE_STRATEGY_AVAILABLE,
    reason="Installed Ax runtime lacks required node-based generation APIs.",
)


class FakeKB:
    """Stands in for agenticwf.kb.client.KBClient; KB names are canonical."""

    def __init__(self, response=None, error=None):
        self.response = response or {"points": [], "source_jobs": [], "history": None}
        self.error = error
        self.suggest_calls = []
        self.uploads = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        pass

    def suggest(self, **body):
        if self.error:
            raise self.error
        self.suggest_calls.append(body)
        return self.response

    def upsert_records(self, kb_id, records, record_type=None):
        self.uploads.append((kb_id, records, record_type))
        return {"inserted": len(records)}


@pytest.fixture
def fake_kb(monkeypatch):
    kb = FakeKB()
    monkeypatch.setattr(kb_warm_start, "make_client", lambda config: kb)
    return kb


def _search_space():
    return SearchSpace.from_design_config(
        DesignConfig(
            design_parameters={
                "group1": {
                    "parameters": {
                        "x": {"value": 0.5, "bounds": [0.0, 1.0]},
                        "y": {"value": 0.25, "bounds": [0.0, 1.0]},
                    }
                }
            },
            parameter_constraints=[{"name": "sum_limit", "rule": "group1.x + group1.y <= 1.5"}],
        )
    )


def _optimizer(objectives=("f1",), **kb_options):
    kb_options.setdefault("knowledge_base_ids", ["aid2e:aid2e"])
    return AxOptimizer(
        search_space=_search_space(),
        config=AxOptimizerConfig(
            n_initial_samples=4, seed=0, kb_warm_start=KBWarmStartConfig(**kb_options)
        ),
        objective_names=list(objectives),
    )


def _point(x, y, score=0.9):
    return {"params": {"group1_x": x, "group1_y": y}, "score": score,
            "source": {"job_id": "old-run", "trial_index": 3}}


def test_search_space_and_names():
    space = _search_space()
    assert kb_warm_start.kb_search_space(space.parameters) == {
        "group1.x": {"type": "float", "low": 0.0, "high": 1.0, "default": 0.5},
        "group1.y": {"type": "float", "low": 0.0, "high": 1.0, "default": 0.25},
    }
    assert kb_warm_start.name_map(space.parameters) == {"group1_x": "group1.x", "group1_y": "group1.y"}
    with pytest.raises(ValueError, match="share the KB name"):
        kb_warm_start.name_map(["a.b", "a_b"])


def test_kb_points_are_served_first(fake_kb):
    fake_kb.response["points"] = [_point(0.1, 0.2), _point(0.9, 0.9), _point(0.3, 0.4),
                                  {"params": {"group1_x": 0.5, "group1_y": 0.5},
                                   "source": {"type": "halton"}}]
    optimizer = _optimizer(n=3, description="BIC calorimeter")

    body = fake_kb.suggest_calls[0]
    assert body["objective"] == {"name": "f1", "direction": "minimize"}
    assert body["knowledge_base_ids"] == ["aid2e:aid2e"]
    assert body["n"] == body["n_total"] == 3
    assert body["description"] == "BIC calorimeter"

    candidates = optimizer.suggest_candidates(3)
    # (0.9, 0.9) violates group1.x + group1.y <= 1.5 and is dropped.
    assert candidates[:2] == [{"group1.x": 0.1, "group1.y": 0.2}, {"group1.x": 0.3, "group1.y": 0.4}]
    trials = optimizer.get_trials()
    assert [t.metadata["ax_model_key"] for t in trials[:2]] == ["kb_warm_start"] * 2
    assert trials[0].metadata["kb_source"]["job_id"] == "old-run"
    assert trials[2].metadata["ax_model_key"] != "kb_warm_start"
    assert len(optimizer.experiment.trials) == 3


def test_kb_failure_starts_cold(monkeypatch):
    kb = FakeKB(error=RuntimeError("connection refused"))
    monkeypatch.setattr(kb_warm_start, "make_client", lambda config: kb)
    optimizer = _optimizer()
    assert optimizer._kb_points == []
    assert len(optimizer.suggest_candidates(2)) == 2


def test_multi_objective_picks_objective(fake_kb):
    _optimizer(objectives=("f1", "f2"), objective="f2", include_history=True)
    body = fake_kb.suggest_calls[0]
    assert body["objective"]["name"] == "f2"
    assert body["options"]["include_history"] is False  # single objective only
    with pytest.raises(ValueError, match="not one of"):
        _optimizer(objective="f3")


def test_include_history_imports_completed_trials(fake_kb):
    fake_kb.response["history"] = [
        {"params": {"group1_x": 0.2, "group1_y": 0.3}, "value": 1.5, "job_id": "old-run"},
        {"params": {"group1_x": 0.6, "group1_y": 0.1}, "value": None, "job_id": "old-run"},
    ]
    optimizer = _optimizer(include_history=True)
    assert fake_kb.suggest_calls[0]["options"]["include_history"] is True
    (trial,) = optimizer.get_trials()
    assert trial.status == "completed"
    assert trial.metrics == {"f1": 1.5}
    assert trial.metadata["warm_started"] and trial.metadata["kb_history"]
    assert optimizer.experiment.trials[trial.index].status.is_completed


def test_upload_records_this_run(fake_kb, tmp_path):
    fake_kb.response["history"] = [{"params": {"group1_x": 0.2, "group1_y": 0.3}, "value": 1.5}]
    optimizer = _optimizer(objectives=("f1", "f2"), upload_kb_id="aid2e:aid2e",
                           job_id="bic-run-7", metadata={"detector": "bic"})
    for trial_index, _ in enumerate(optimizer.suggest_candidates(2)):
        if trial_index == 0:
            optimizer.update_with_results(trial_index, optimizer.get_trials()[0].parameters,
                                          {"f1": 1.0, "f2": 2.0})
        else:
            optimizer.mark_trial_failed(trial_index, reason="crash")

    optimizer.config.save_snapshot = False
    optimizer.save_optimization_results(tmp_path)

    kb_id, records, record_type = fake_kb.uploads[0]
    assert (kb_id, record_type) == ("aid2e:aid2e", "hpo_job")
    assert [r["job_id"] for r in records] == ["bic-run-7:f1", "bic-run-7:f2"]
    f2 = records[1]
    assert f2["objective"] == {"name": "f2", "direction": "minimize"}
    assert f2["metadata"]["detector"] == "bic"
    assert [(t["status"], t["value"]) for t in f2["trials"]] == [("complete", 2.0), ("fail", None)]


def test_serialized_state_hides_token(fake_kb):
    optimizer = _optimizer(token="secret", job_id="run-1")
    state = optimizer.serialize_state()
    assert "token" not in state["config"]["kb_warm_start"]
    assert state["kb_job_id"] == "run-1"
