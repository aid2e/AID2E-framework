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


class FakeKBError(Exception):
    """Stands in for agenticwf.kb.client.KBClientError."""

    def __init__(self, status):
        super().__init__(f"HTTP {status}")
        self.status = status


def _records_kb(ref, kb_id=None, owner_subject="user-1", visibility="private", type="records"):
    owner, _, slug = ref.rpartition(":")
    return {"id": kb_id or f"id-{slug}", "ref": ref, "slug": slug, "type": type,
            "owner_subject": owner_subject, "owner_name": owner.partition(":")[2],
            "visibility": visibility}


class FakeKB:
    """Stands in for agenticwf.kb.client.KBClient; KB names are canonical.

    ``kbs`` maps refs to the KBs the caller can see; ``me`` is the caller's
    username, which refs of created personal KBs use.
    """

    def __init__(self, response=None, error=None, kbs=None, me="alice"):
        self.response = response or {"points": [], "source_jobs": [], "history": None}
        self.error = error
        self.kbs = dict(kbs) if kbs is not None else {"aid2e:aid2e": _records_kb("aid2e:aid2e")}
        self.me = me
        self.suggest_calls = []
        self.uploads = []
        self.created = []

    def request(self, method, path):
        assert method == "GET"
        if path.startswith("/knowledge-bases?"):
            return list(self.kbs.values())
        ref = path.removeprefix("/knowledge-bases/")
        for kb in self.kbs.values():
            if ref in (kb["ref"], kb["id"]):
                return kb
        raise FakeKBError(404)

    def create_knowledge_base(self, name, group=None, **body):
        owner = f"g:{group}" if group else f"u:{self.me}"
        ref = f"{owner}:{body.get('slug') or name}"
        if ref in self.kbs:
            raise FakeKBError(409)
        self.created.append({"name": name, "group": group, **body})
        kb = _records_kb(ref, kb_id=f"new-{len(self.created)}", type=body.get("type", "document"),
                         owner_subject="org:1" if group else "user-1")
        self.kbs[ref] = kb
        return kb

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
        outcomes = []
        for index, record in enumerate(records):
            nested = [k for k, v in record.get("metadata", {}).items()
                      if not isinstance(v, (str, int, float, bool))]
            outcomes.append({"index": index, "outcome": "invalid",
                             "errors": [f"metadata.{k}: not a scalar" for k in nested]}
                            if nested else {"index": index, "outcome": "created", "id": str(index)})
        return {"outcomes": outcomes,
                "created": sum(o["outcome"] == "created" for o in outcomes),
                "invalid": sum(o["outcome"] == "invalid" for o in outcomes)}


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


def _seeded_optimizer(fake_kb, points=(), seed=42):
    fake_kb.response["points"] = list(points)
    return AxOptimizer(
        search_space=_search_space(),
        config=AxOptimizerConfig(
            n_initial_samples=8, seed=seed,
            kb_warm_start=KBWarmStartConfig(knowledge_base_ids=["aid2e:aid2e"], n=2)),
        objective_names=["f1"],
    )


def test_seeded_sobol_skips_kb_points_after_rounding(fake_kb):
    cold = _seeded_optimizer(fake_kb).suggest_candidates(4)
    # The KB hands back this seed's first two Sobol points, with lost precision.
    points = [_point(round(c["group1.x"], 9), round(c["group1.y"], 9)) for c in cold[:2]]
    warm = _seeded_optimizer(fake_kb, points).suggest_candidates(4)

    assert warm[:2] == [{"group1.x": round(c["group1.x"], 9), "group1.y": round(c["group1.y"], 9)}
                        for c in cold[:2]]
    # Sobol moves on instead of repeating the KB points.
    assert warm[2:] == cold[2:]


def test_sobol_seed_is_fixed_only_when_given(fake_kb):
    first = _seeded_optimizer(fake_kb, seed=7).suggest_candidates(3)
    assert _seeded_optimizer(fake_kb, seed=7).suggest_candidates(3) == first
    assert _seeded_optimizer(fake_kb, seed=None).suggest_candidates(3) != \
        _seeded_optimizer(fake_kb, seed=None).suggest_candidates(3)


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


def test_upload_records_this_run(fake_kb, tmp_path, caplog):
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
    with caplog.at_level("INFO", logger="aid2e.optimizers.ax.optimizer"):
        optimizer.save_optimization_results(tmp_path)
    assert "KB upload of run bic-run-7 to aid2e:aid2e succeeded: 3 record(s), 2 trial(s) " \
        "(3 created, 0 updated, 0 unchanged, 0 invalid)." in caplog.text

    kb_id, records, record_type = fake_kb.uploads[0]
    assert (kb_id, record_type) == ("id-aid2e", "hpo_job")
    assert fake_kb.created == []
    assert [r["job_id"] for r in records] == [
        "bic-run-7:f1", "bic-run-7:f2", "bic-run-7:hypervolume"]
    f2 = records[1]
    assert f2["objective"] == {"name": "f2", "direction": "minimize"}
    assert f2["metadata"]["detector"] == "bic"
    assert f2["metadata"]["objectives"] == "f1,f2"
    assert [(t["status"], t["value"]) for t in f2["trials"]] == [("complete", 2.0), ("fail", None)]

    # One completed trial: the observed-nadir reference point pads each value by 10%.
    hv = records[2]
    assert hv["objective"] == {"name": "hypervolume_f1_f2", "direction": "maximize"}
    assert hv["metadata"]["hypervolume"] == pytest.approx(0.02)
    assert hv["metadata"]["hypervolume_reference_point"] == "f1=1.1,f2=2.2"
    assert hv["metadata"]["hypervolume_reference_point_source"] == "observed_nadir"
    assert [t["status"] for t in hv["trials"]] == ["complete", "fail"]
    assert hv["trials"][0]["value"] == pytest.approx(0.02)


def test_upload_hypervolume_can_be_turned_off(fake_kb, tmp_path):
    optimizer = _optimizer(objectives=("f1", "f2"), upload_kb_id="aid2e:aid2e",
                           job_id="run-2", upload_hypervolume=False)
    (params,) = optimizer.suggest_candidates(1)
    optimizer.update_with_results(0, params, {"f1": 1.0, "f2": 2.0})
    optimizer.config.save_snapshot = False
    optimizer.save_optimization_results(tmp_path)
    assert [r["job_id"] for r in fake_kb.uploads[0][1]] == ["run-2:f1", "run-2:f2"]


def test_point_hypervolume_respects_directions_and_reference():
    ref = {"f1": 1.0, "f2": 0.0}
    directions = {"f2": "maximize"}
    assert kb_warm_start.point_hypervolume(
        {"f1": 0.5, "f2": 0.5}, ["f1", "f2"], directions, ref) == pytest.approx(0.25)
    assert kb_warm_start.point_hypervolume(
        {"f1": 1.5, "f2": 0.5}, ["f1", "f2"], directions, ref) == 0.0
    assert kb_warm_start.point_hypervolume(
        {"f1": 0.5}, ["f1", "f2"], directions, ref) is None


def test_rank_by_hypervolume_queries_the_hypervolume_record(fake_kb):
    fake_kb.response["points"] = [
        {"params": {"group1_x": 0.2, "group1_y": 0.3}, "source": {"job_id": "old:hypervolume"}},
    ]
    optimizer = _optimizer(objectives=("f1", "f2"), rank_by="hypervolume")
    (body,) = fake_kb.suggest_calls
    assert body["objective"] == {"name": "hypervolume_f1_f2", "direction": "maximize"}
    assert [p["ranked_on"] for p in optimizer._kb_points] == ["hypervolume_f1_f2"]


def test_rank_by_hypervolume_needs_several_objectives(fake_kb):
    with pytest.raises(ValueError, match="two or more objectives"):
        _optimizer(rank_by="hypervolume")


def test_rank_on_several_objectives_interleaves_points(fake_kb):
    responses = {
        "f1": [{"group1_x": 0.1, "group1_y": 0.1}, {"group1_x": 0.2, "group1_y": 0.2}],
        "f2": [{"group1_x": 0.1, "group1_y": 0.1}, {"group1_x": 0.9, "group1_y": 0.1}],
    }

    def suggest(**body):
        fake_kb.suggest_calls.append(body)
        name = body["objective"]["name"]
        return {"points": [{"params": p, "source": {"job_id": f"old:{name}"}}
                           for p in responses[name]],
                "source_jobs": [], "history": None}

    fake_kb.suggest = suggest
    optimizer = _optimizer(objectives=("f1", "f2"), objective=["f1", "f2"], n=3)
    assert [b["objective"]["name"] for b in fake_kb.suggest_calls] == ["f1", "f2"]
    # Round robin f1, f2, f1, ...; the repeated point from f2 is dropped.
    assert [(p["ranked_on"], p["params"]["group1.x"]) for p in optimizer._kb_points] == [
        ("f1", 0.1), ("f1", 0.2), ("f2", 0.9)]


def test_serialized_state_hides_token(fake_kb):
    optimizer = _optimizer(token="secret", job_id="run-1")
    state = optimizer.serialize_state()
    assert "token" not in state["config"]["kb_warm_start"]
    assert state["kb_job_id"] == "run-1"


def test_ensure_kb_uses_an_existing_kb():
    kb_id = "0123abcd-0000-0000-0000-00000000beef"
    kb = FakeKB(kbs={"g:aid2e:dtlz2": _records_kb("g:aid2e:dtlz2", kb_id, owner_subject="org:1")})
    assert kb_warm_start.ensure_kb(kb, "g:aid2e:dtlz2")["id"] == kb_id
    assert kb_warm_start.ensure_kb(kb, kb_id)["ref"] == "g:aid2e:dtlz2"
    assert kb.created == []


def test_ensure_kb_creates_a_missing_kb():
    kb = FakeKB(kbs={})
    created = kb_warm_start.ensure_kb(kb, "u:alice:dtlz2")
    assert created["ref"] == "u:alice:dtlz2" and created["type"] == "records"
    assert kb.created == [{"name": "dtlz2", "group": None, "slug": "dtlz2", "type": "records",
                           "description": "AID2E optimization runs (hpo_job records)"}]
    # The second call finds it.
    assert kb_warm_start.ensure_kb(kb, "u:alice:dtlz2")["id"] == created["id"]
    assert len(kb.created) == 1


def test_ensure_kb_creates_group_kbs_and_bare_slugs():
    kb = FakeKB(kbs={})
    assert kb_warm_start.ensure_kb(kb, "g:aid2e:dtlz2")["ref"] == "g:aid2e:dtlz2"
    assert kb.created[-1]["group"] == "aid2e"
    first = kb_warm_start.ensure_kb(kb, "dtlz2")
    assert first["ref"] == "u:alice:dtlz2"
    # A bare slug that exists: the create conflicts and the caller's own KB is used.
    assert kb_warm_start.ensure_kb(kb, "dtlz2")["id"] == first["id"]
    assert len(kb.created) == 2


def test_ensure_kb_rejects_other_kb_types_and_unknown_ids():
    kb = FakeKB(kbs={"u:alice:docs": _records_kb("u:alice:docs", type="document")})
    with pytest.raises(ValueError, match="records KB"):
        kb_warm_start.ensure_kb(kb, "u:alice:docs")
    with pytest.raises(ValueError, match="No knowledge base"):
        kb_warm_start.ensure_kb(kb, "0123abcd-0000-0000-0000-000000000000")


def test_missing_upload_kb_is_created_and_read(monkeypatch, tmp_path):
    kb = FakeKB(kbs={})
    monkeypatch.setattr(kb_warm_start, "make_client", lambda config: kb)
    optimizer = _optimizer(knowledge_base_ids=["dtlz2"], upload_kb_id="dtlz2", job_id="run-1")
    assert [c["slug"] for c in kb.created] == ["dtlz2"]
    assert kb.suggest_calls[0]["knowledge_base_ids"] == ["new-1"]

    optimizer.config.save_snapshot = False
    optimizer.save_optimization_results(tmp_path)
    optimizer.save_optimization_results(tmp_path)
    assert [kb_id for kb_id, _, _ in kb.uploads] == ["new-1", "new-1"]
    assert len(kb.created) == 1


def test_create_upload_kb_off_uses_the_ref_as_given(monkeypatch, tmp_path):
    kb = FakeKB(kbs={})
    monkeypatch.setattr(kb_warm_start, "make_client", lambda config: kb)
    optimizer = _optimizer(knowledge_base_ids=None, upload_kb_id="u:alice:dtlz2",
                           create_upload_kb=False)
    optimizer.config.save_snapshot = False
    optimizer.save_optimization_results(tmp_path)
    assert kb.created == [] and kb.uploads[0][0] == "u:alice:dtlz2"


def test_rejected_records_fail_the_upload():
    kb = FakeKB()
    records = [{"job_id": "run-1", "metadata": {"objectives": ["f1", "f2"]}}]
    with pytest.raises(ValueError, match="rejected 1 of 1 record.*run-1.*metadata.objectives"):
        kb_warm_start.upload(kb, "id-1", records)


def test_nested_metadata_is_refused_in_the_config():
    with pytest.raises(ValueError, match="strings, numbers or booleans"):
        kb_warm_start.KBWarmStartConfig(metadata={"tags": ["a", "b"]})


def test_rejected_upload_is_logged_as_a_failure(fake_kb, tmp_path, caplog):
    optimizer = _optimizer(upload_kb_id="aid2e:aid2e", job_id="run-9")
    optimizer.config.save_snapshot = False
    fake_kb.upsert_records = lambda kb_id, records, record_type=None: {
        "outcomes": [{"index": 0, "outcome": "invalid", "errors": ["metadata.x: bad"]}], "invalid": 1}
    optimizer.save_optimization_results(tmp_path)
    assert "KB upload of run run-9 to aid2e:aid2e FAILED: KB rejected 1 of 1 record(s): " \
        "run-9: metadata.x: bad" in caplog.text


def test_hypervolume_scores_rank_trials_outside_a_tight_reference_point():
    """With objective_thresholds (1, 1), random DTLZ2 trials all lie outside the box."""
    from aid2e.optimizers.base import Trial

    trials = [
        Trial(index=0, parameters={"x": 0.1}, metrics={"f1": 1.6, "f2": 0.01}, status="completed"),
        Trial(index=1, parameters={"x": 0.2}, metrics={"f1": 1.2, "f2": 1.2}, status="completed"),
        Trial(index=2, parameters={"x": 0.3}, metrics={"f1": 1.8, "f2": 1.8}, status="completed"),
    ]
    front = {"value": 0.0, "reference_point": {"f1": 1.0, "f2": 1.0},
             "reference_point_source": "configured", "n_completed_trials": 3}
    records = kb_warm_start.job_records(
        trials, KBWarmStartConfig(), "run-3", _search_space().parameters,
        ["f1", "f2"], {}, framework="aid2e-ax", hypervolume=front)
    hv = records[-1]
    assert hv["metadata"]["hypervolume_reference_point"] == "f1=1,f2=1"
    assert hv["metadata"]["trial_score_reference_point"] == "f1=1.86,f2=1.979"
    scores = [t["value"] for t in hv["trials"]]
    assert all(score > 0 for score in scores)
    # The dominated trial scores lowest; the two front trials rank above it.
    assert scores[2] < min(scores[0], scores[1])
