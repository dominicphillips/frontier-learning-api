from __future__ import annotations

import json
import os
import tempfile
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .models import Status

MAX_ARTIFACT_BYTES = 16 * 1024 * 1024


def now() -> datetime:
    return datetime.now(UTC)


def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def bounded_json(path: Path) -> bytes:
    with path.open("rb") as stream:
        data = stream.read(MAX_ARTIFACT_BYTES + 1)
    if len(data) > MAX_ARTIFACT_BYTES:
        raise ValueError("Artifact exceeds size limit")
    return data


class SnapshotUnavailable(ValueError):
    pass


class BaseSnapshotStore:
    def __init__(self, path: Path, stale_after: timedelta = timedelta(days=7)):
        self.path = path
        self.state_path = path.with_suffix(".status.json")
        self.previous_path = path.with_suffix(".previous.json")
        self.stale_after = stale_after
        self._cached: object | None = None
        self._signature: tuple[int, int] | None = None
        self._read_failed = False
        self._lock = threading.RLock()

    def read(self):
        with self._lock:
            try:
                stat = self.path.stat()
                signature = (stat.st_mtime_ns, stat.st_size)
                if signature != self._signature or self._cached is None:
                    candidate = self.snapshot_model.model_validate_json(bounded_json(self.path))
                    self._cached, self._signature = candidate, signature
                self._read_failed = False
            except (OSError, ValueError):
                self._read_failed = True
                if self._cached is None:
                    try:
                        self._cached = self.snapshot_model.model_validate_json(
                            bounded_json(self.previous_path)
                        )
                    except (OSError, ValueError):
                        raise SnapshotUnavailable("No valid snapshot") from None
            assert self._cached is not None
            return self._cached

    def _state(self) -> dict:
        try:
            data = json.loads(bounded_json(self.state_path))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def record_attempt(self, *, success: bool, code: str | None = None) -> None:
        state = self._state()
        timestamp = now().isoformat()
        state.update(lastAttemptAt=timestamp, lastAttemptSucceeded=success, errorCode=code)
        if success:
            state["lastSuccessAt"] = timestamp
        atomic_json(self.state_path, state)

    def status(self) -> Status:
        state = self._state()
        try:
            snapshot = self.read()
        except SnapshotUnavailable:
            snapshot = None

        def date(key: str) -> datetime | None:
            try:
                value = datetime.fromisoformat(state[key].replace("Z", "+00:00"))
                return value if value.tzinfo is not None else None
            except (KeyError, TypeError, ValueError, AttributeError):
                return None

        freshness = "unavailable"
        if snapshot:
            stale = (
                now() - snapshot.generated_at > self.stale_after
                or self._read_failed
                or state.get("lastAttemptSucceeded") is False
                or any(x.state != "complete" for x in snapshot.coverage)
            )
            freshness = "stale" if stale else "fresh"
        return Status(
            state=freshness,
            snapshot_id=snapshot.snapshot_id if snapshot else None,
            generated_at=snapshot.generated_at if snapshot else None,
            last_attempt_at=date("lastAttemptAt"),
            last_success_at=date("lastSuccessAt"),
            resource_count=len(snapshot.resources) if snapshot else 0,
            coverage=snapshot.coverage if snapshot else [],
        )
