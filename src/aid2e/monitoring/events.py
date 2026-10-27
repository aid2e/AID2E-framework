"""Append-only lifecycle events for AID2E optimization runs.

The journal is deliberately separate from DAGExecutor's detailed execution
log and checkpoint files.  Events provide a small, stable stream for external
monitors; event data can point back to detailed logs and artifacts when a
deeper investigation is required.

One :class:`EventJournal` instance is safe for concurrent threads in a single
process.  A future multi-process run registry should allocate sequences in a
database or serialize writes through a single service.
"""

from __future__ import annotations

import os
import threading
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4

from pydantic import BaseModel, Field


class EventEntity(str, Enum):
    """Object whose lifecycle changed."""

    RUN = "run"
    BATCH = "batch"
    TRIAL = "trial"
    STAGE = "stage"
    JOB = "job"


class EventType(str, Enum):
    """Stable event names consumed by monitoring clients."""

    RUN_CREATED = "run.created"
    RUN_STARTED = "run.started"
    RUN_COMPLETED = "run.completed"
    RUN_COMPLETED_WITH_FAILURES = "run.completed_with_failures"
    RUN_FAILED = "run.failed"
    RUN_CANCELLED = "run.cancelled"

    BATCH_STARTED = "batch.started"
    BATCH_COMPLETED = "batch.completed"
    BATCH_FAILED = "batch.failed"

    TRIAL_SUGGESTED = "trial.suggested"
    TRIAL_SUBMITTED = "trial.submitted"
    TRIAL_STARTED = "trial.started"
    TRIAL_COMPLETED = "trial.completed"
    TRIAL_FAILED = "trial.failed"
    TRIAL_PENALIZED = "trial.penalized"
    TRIAL_CANCELLED = "trial.cancelled"

    BACKEND_STATUS_OBSERVED = "backend.status_observed"
    BACKEND_IDS_CORRELATED = "backend.ids_correlated"
    MONITOR_WARNING = "monitor.warning"


class EventSource(BaseModel):
    """Component that observed or produced an event."""

    component: str
    backend: str | None = None
    host: str | None = None
    process_id: int | None = None


class EventError(BaseModel):
    """Sanitized error data suitable for durable monitoring records."""

    error_type: str
    message: str
    code: str | int | None = None
    retryable: bool | None = None


class BackendIdentifiers(BaseModel):
    """Optional scheduler identifiers used to correlate remote work."""

    submission_id: str | None = None
    idds_request_id: str | None = None
    idds_workflow_id: str | None = None
    idds_transform_id: str | None = None
    panda_task_id: str | None = None
    panda_job_ids: list[str] = Field(default_factory=list)
    slurm_job_id: str | None = None
    slurm_array_task_id: str | None = None


class OptimizationEvent(BaseModel):
    """One immutable optimization lifecycle event."""

    schema_version: int = 1
    event_id: str = Field(default_factory=lambda: uuid4().hex)
    sequence: int = Field(ge=1)
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    event_type: EventType
    entity_type: EventEntity
    run_id: str

    trial_index: int | None = Field(default=None, ge=0)
    batch_id: int | None = Field(default=None, ge=1)
    stage_id: str | None = None
    job_id: str | None = None

    canonical_state: str | None = None
    previous_state: str | None = None
    raw_backend_state: str | None = None

    source: EventSource
    backend_ids: BackendIdentifiers | None = None
    message: str | None = None
    error: EventError | None = None
    data: dict[str, Any] = Field(default_factory=dict)


class EventJournal:
    """Read and append a run's newline-delimited JSON event stream."""

    def __init__(self, path: str | Path, run_id: str) -> None:
        if not run_id.strip():
            raise ValueError("run_id must not be empty")

        self.path = Path(path).expanduser().resolve()
        self.run_id = run_id
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._next_sequence = self._discover_next_sequence()

    def append(
        self,
        event_type: EventType,
        entity_type: EventEntity,
        *,
        source: EventSource,
        trial_index: int | None = None,
        batch_id: int | None = None,
        stage_id: str | None = None,
        job_id: str | None = None,
        canonical_state: str | None = None,
        previous_state: str | None = None,
        raw_backend_state: str | None = None,
        backend_ids: BackendIdentifiers | None = None,
        message: str | None = None,
        error: EventError | None = None,
        data: dict[str, Any] | None = None,
    ) -> OptimizationEvent:
        """Validate, append, flush, and fsync one event."""

        with self._lock:
            event = OptimizationEvent(
                sequence=self._next_sequence,
                event_type=event_type,
                entity_type=entity_type,
                run_id=self.run_id,
                trial_index=trial_index,
                batch_id=batch_id,
                stage_id=stage_id,
                job_id=job_id,
                canonical_state=canonical_state,
                previous_state=previous_state,
                raw_backend_state=raw_backend_state,
                source=source,
                backend_ids=backend_ids,
                message=message,
                error=error,
                data=data or {},
            )

            with self.path.open("a", encoding="utf-8") as stream:
                stream.write(event.model_dump_json(exclude_none=True))
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())

            self._next_sequence += 1
            return event

    def read_after(
        self,
        cursor: int = 0,
        *,
        limit: int = 100,
    ) -> list[OptimizationEvent]:
        """Return at most ``limit`` events with a sequence after ``cursor``."""

        if cursor < 0:
            raise ValueError("cursor must be non-negative")
        if not 1 <= limit <= 1000:
            raise ValueError("limit must be between 1 and 1000")

        events: list[OptimizationEvent] = []
        for event in self._read_all():
            if event.sequence > cursor:
                events.append(event)
            if len(events) >= limit:
                break
        return events

    def latest(self) -> OptimizationEvent | None:
        """Return the last valid event, or ``None`` for an empty journal."""

        latest_event = None
        for event in self._read_all():
            latest_event = event
        return latest_event

    def _read_all(self) -> Iterator[OptimizationEvent]:
        if not self.path.exists():
            return

        with self.path.open("r", encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, start=1):
                if not line.strip():
                    continue
                try:
                    event = OptimizationEvent.model_validate_json(line)
                except Exception as exc:
                    raise RuntimeError(
                        f"Invalid event at {self.path}:{line_number}"
                    ) from exc
                if event.run_id != self.run_id:
                    raise RuntimeError(
                        f"Unexpected run_id at {self.path}:{line_number}: "
                        f"{event.run_id!r}"
                    )
                yield event

    def _discover_next_sequence(self) -> int:
        latest_event = self.latest()
        return 1 if latest_event is None else latest_event.sequence + 1
