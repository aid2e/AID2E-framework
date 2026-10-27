import json

import pytest

from aid2e.monitoring.demo import dtlz2_objective_payload
from aid2e.monitoring.events import (
    EventEntity,
    EventError,
    EventJournal,
    EventSource,
    EventType,
)


def test_event_journal_appends_and_reads_after_cursor(tmp_path):
    path = tmp_path / "run_events.jsonl"
    source = EventSource(component="test", backend="JobLibRunner")
    journal = EventJournal(path, "demo-run")

    created = journal.append(
        EventType.RUN_CREATED,
        EventEntity.RUN,
        source=source,
        canonical_state="created",
    )
    completed = journal.append(
        EventType.TRIAL_COMPLETED,
        EventEntity.TRIAL,
        source=source,
        trial_index=0,
        batch_id=1,
        canonical_state="completed",
        data={"objectives": {"f1": 0.5, "f2": 1.0}},
    )

    assert created.sequence == 1
    assert completed.sequence == 2
    assert completed.timestamp.tzinfo is not None
    assert [event.sequence for event in journal.read_after(0)] == [1, 2]
    assert [event.sequence for event in journal.read_after(1)] == [2]

    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[1])["event_type"] == "trial.completed"


def test_event_journal_continues_sequence_after_reopen(tmp_path):
    path = tmp_path / "run_events.jsonl"
    source = EventSource(component="test")
    EventJournal(path, "demo-run").append(
        EventType.RUN_CREATED,
        EventEntity.RUN,
        source=source,
    )

    reopened = EventJournal(path, "demo-run")
    event = reopened.append(
        EventType.RUN_FAILED,
        EventEntity.RUN,
        source=source,
        error=EventError(error_type="RuntimeError", message="example"),
    )

    assert event.sequence == 2
    assert reopened.latest() == event


def test_event_journal_rejects_bad_cursor_and_limit(tmp_path):
    journal = EventJournal(tmp_path / "run_events.jsonl", "demo-run")

    with pytest.raises(ValueError, match="cursor"):
        journal.read_after(-1)
    with pytest.raises(ValueError, match="limit"):
        journal.read_after(limit=0)


def test_event_journal_rejects_mixed_run_ids(tmp_path):
    path = tmp_path / "run_events.jsonl"
    source = EventSource(component="test")
    EventJournal(path, "first-run").append(
        EventType.RUN_CREATED,
        EventEntity.RUN,
        source=source,
    )

    with pytest.raises(RuntimeError, match="Unexpected run_id"):
        EventJournal(path, "second-run")


def test_dtlz2_demo_objective_payload():
    objectives = dtlz2_objective_payload(
        design_point={
            f"DTLZ2_variables.x{index}": 0.5
            for index in range(1, 6)
        }
    )

    assert objectives["f1"] == pytest.approx(2**-0.5)
    assert objectives["f2"] == pytest.approx(2**-0.5)
