"""Tests for the hypervolume utilities and pareto_front.json reporting."""

import json
from types import SimpleNamespace

import pytest

from aid2e.optimizers.base import (
    BaseOptimizer,
    SearchSpace,
    Trial,
    compute_hypervolume,
    nadir_reference_point,
)
from aid2e.utilities.configurations.base_models import RangeParameter


def _trial(index, f1, f2, status="completed"):
    return Trial(index=index, parameters={}, metrics={"f1": f1, "f2": f2}, status=status)


class _StubOptimizer(BaseOptimizer):
    def __init__(self, objective_names, objective_directions=None, thresholds=None):
        space = SearchSpace(parameters={"x": RangeParameter(name="x", value=0.5, bounds=(0.0, 1.0))})
        super().__init__(space, objective_names, objective_directions=objective_directions)
        self.config = SimpleNamespace(objective_thresholds=thresholds)

    def suggest_candidates(self, n_candidates=1):
        return []

    def update_with_results(self, trial_index, parameters, metrics):
        self.set_trial_status(trial_index, "completed", parameters=parameters, metrics=metrics)

    def serialize_state(self):
        return {}

    def load_state(self, state):
        pass


def test_hypervolume_minimize():
    trials = [_trial(0, 0.5, 0.5), _trial(1, 0.25, 0.75)]
    # Union of [0.5,1]x[0.5,1] and [0.25,1]x[0.75,1] = 0.25 + 0.0625
    assert compute_hypervolume(trials, ["f1", "f2"], {"f1": 1.0, "f2": 1.0}) == pytest.approx(0.3125)


def test_hypervolume_maximize_direction():
    trials = [_trial(0, 0.5, 0.5)]
    hv = compute_hypervolume(
        trials, ["f1", "f2"], {"f1": 0.0, "f2": 1.0}, {"f1": "maximize"}
    )
    assert hv == pytest.approx(0.25)


def test_hypervolume_ignores_points_outside_reference_and_failed_trials():
    trials = [
        _trial(0, 2.0, 0.0),
        Trial(index=1, parameters={}, metrics=None, status="failed"),
        _trial(2, 0.0, 0.0, status="running"),
    ]
    assert compute_hypervolume(trials, ["f1", "f2"], {"f1": 1.0, "f2": 1.0}) == 0.0


def test_hypervolume_requires_full_reference_point():
    with pytest.raises(ValueError, match="f2"):
        compute_hypervolume([_trial(0, 0.5, 0.5)], ["f1", "f2"], {"f1": 1.0})


def test_nadir_reference_point_respects_direction():
    trials = [_trial(0, 0.0, 1.0), _trial(1, 1.0, 3.0)]
    ref = nadir_reference_point(trials, ["f1", "f2"], {"f2": "maximize"})
    assert ref == pytest.approx({"f1": 1.1, "f2": 0.8})


def test_get_hypervolume_single_objective_is_none():
    optimizer = _StubOptimizer(["f1"])
    optimizer.update_with_results(0, {"x": 0.1}, {"f1": 1.0})
    assert optimizer.get_hypervolume() is None


def test_get_hypervolume_uses_configured_thresholds():
    optimizer = _StubOptimizer(["f1", "f2"], thresholds={"f1": 1.0, "f2": 1.0})
    optimizer.update_with_results(0, {"x": 0.1}, {"f1": 0.5, "f2": 0.5})
    hv = optimizer.get_hypervolume()
    assert hv["value"] == pytest.approx(0.25)
    assert hv["reference_point_source"] == "configured"


def test_auto_reference_point_is_fixed_across_batches():
    optimizer = _StubOptimizer(["f1", "f2"])
    optimizer.update_with_results(0, {"x": 0.1}, {"f1": 0.0, "f2": 1.0})
    optimizer.update_with_results(1, {"x": 0.2}, {"f1": 1.0, "f2": 0.0})
    first = optimizer.get_hypervolume()
    assert first["reference_point_source"] == "observed_nadir"

    optimizer.update_with_results(2, {"x": 0.3}, {"f1": 5.0, "f2": 5.0})
    optimizer.update_with_results(3, {"x": 0.4}, {"f1": 0.2, "f2": 0.2})
    second = optimizer.get_hypervolume()
    assert second["reference_point"] == first["reference_point"]
    assert second["value"] > first["value"]


def test_pareto_front_json_reports_hypervolume_history(tmp_path):
    optimizer = _StubOptimizer(["f1", "f2"], thresholds={"f1": 1.0, "f2": 1.0})
    optimizer.update_with_results(0, {"x": 0.1}, {"f1": 0.5, "f2": 0.5})
    optimizer.save_optimization_results(tmp_path)
    optimizer.save_optimization_results(tmp_path)  # no new results: no new entry
    optimizer.update_with_results(1, {"x": 0.2}, {"f1": 0.25, "f2": 0.75})
    optimizer.update_with_results(2, {"x": 0.3}, {"f1": 0.9, "f2": 0.9})
    optimizer.save_optimization_results(tmp_path)

    payload = json.loads((tmp_path / "pareto_front.json").read_text())
    assert payload["objective_names"] == ["f1", "f2"]
    assert payload["objective_directions"] == {"f1": "minimize", "f2": "minimize"}
    assert {t["trial_index"] for t in payload["trials"]} == {0, 1}
    hv = payload["hypervolume"]
    assert hv["value"] == pytest.approx(0.3125)
    assert hv["n_completed_trials"] == 3
    assert [h["n_completed_trials"] for h in hv["history"]] == [1, 3]
    assert [h["hypervolume"] for h in hv["history"]] == pytest.approx([0.25, 0.3125])


def test_pareto_front_json_single_objective_has_null_hypervolume(tmp_path):
    optimizer = _StubOptimizer(["f1"])
    optimizer.update_with_results(0, {"x": 0.1}, {"f1": 1.0})
    optimizer.save_optimization_results(tmp_path)
    payload = json.loads((tmp_path / "pareto_front.json").read_text())
    assert payload["hypervolume"] is None
    assert len(payload["trials"]) == 1


def test_optimization_loop_logs_trial_and_front_hypervolume(caplog):
    from aid2e.utilities.runtime_builders import _log_trial_hypervolumes

    optimizer = _StubOptimizer(["f1", "f2"], thresholds={"f1": 1.0, "f2": 1.0})
    batch = {
        0: ({"x": 0.1}, {"f1": 0.5, "f2": 0.5}, {}),
        1: ({"x": 0.2}, {"f1": 0.25, "f2": 0.75}, {"penalized": True}),
    }
    for index, (params, metrics, _) in batch.items():
        optimizer.update_with_results(index, params, metrics)

    with caplog.at_level("INFO", logger="aid2e.utilities.runtime_builders"):
        _log_trial_hypervolumes(optimizer, batch)
    assert "Trial 0: f1=0.5, f2=0.5 | trial hypervolume 0.25 | front hypervolume 0.3125 " \
        "(2 completed trial(s))" in caplog.text
    assert "Trial 1: f1=0.25, f2=0.75 | trial hypervolume 0.1875 | front hypervolume " \
        "0.3125 (2 completed trial(s)) [penalized]" in caplog.text


def test_single_objective_loop_logs_objectives_only(caplog):
    from aid2e.utilities.runtime_builders import _log_trial_hypervolumes

    optimizer = _StubOptimizer(["f1"])
    optimizer.update_with_results(0, {"x": 0.1}, {"f1": 1.0})
    with caplog.at_level("INFO", logger="aid2e.utilities.runtime_builders"):
        _log_trial_hypervolumes(optimizer, {0: ({"x": 0.1}, {"f1": 1.0}, {})})
    assert "Trial 0: f1=1\n" in caplog.text
