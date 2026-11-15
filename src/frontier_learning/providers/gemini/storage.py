from __future__ import annotations

from pathlib import Path

from ...storage import BaseSnapshotStore
from ...storage import SnapshotUnavailable as SnapshotUnavailable
from ...storage import atomic_json as atomic_json
from ...storage import bounded_json as bounded_json
from ...storage import now as now
from .models import CollectionArtifact, Coverage, Snapshot, assemble_snapshot, build_snapshot


class SnapshotStore(BaseSnapshotStore):
    snapshot_model = Snapshot

    def publish(
        self, artifact_path: Path, *, method: str = "manual", merge: bool = True
    ) -> Snapshot:
        try:
            artifact = CollectionArtifact.model_validate_json(bounded_json(artifact_path))
        except (OSError, ValueError):
            self.record_attempt(success=False, code="validation-or-publication-failed")
            raise
        return self.publish_artifact(artifact, method=method, merge=merge)

    def publish_artifact(
        self, artifact: CollectionArtifact, *, method: str, merge: bool = True
    ) -> Snapshot:
        """Validate and write atomically. `merge=False` is for complete sitemap passes."""
        try:
            snapshot = build_snapshot(artifact, method)  # type: ignore[arg-type]
            with self._lock:
                try:
                    old = self.read()
                except SnapshotUnavailable:
                    old = None
                if old is not None:
                    if snapshot.generated_at < old.generated_at:
                        raise ValueError("A refresh cannot move snapshot time backwards")
                    if merge:
                        snapshot = merge_snapshot(old, snapshot)
                payload = snapshot.model_dump(mode="json", by_alias=True)
                if old is not None:
                    atomic_json(self.previous_path, old.model_dump(mode="json", by_alias=True))
                atomic_json(self.path, payload)
                self._signature = None
                self._cached = snapshot
                self.record_attempt(success=True)
            return snapshot
        except (OSError, ValueError):
            self.record_attempt(success=False, code="validation-or-publication-failed")
            raise


def merge_snapshot(previous: Snapshot, incoming: Snapshot) -> Snapshot:
    """Refresh observed records without treating a bounded pass as deletion authority."""
    if incoming.generated_at < previous.generated_at:
        raise ValueError("A refresh cannot move snapshot time backwards")
    resources = {x.id: x for x in previous.resources}
    resources.update({x.id: x for x in incoming.resources})
    categories = {x.id: x for x in previous.categories}
    categories.update({x.id: x for x in incoming.categories})
    incoming_ids = {r.id for r in incoming.resources}
    incoming_coverage = {c.category_id: c for c in incoming.coverage}
    coverage = []
    for category_id in categories:
        count = sum(category_id in r.category_ids for r in resources.values())
        retained = any(
            r.id not in incoming_ids and category_id in r.category_ids for r in resources.values()
        )
        observed = incoming_coverage.get(category_id)
        state = "partial" if retained or observed is None else observed.state
        discovered = observed.discovered if observed else None
        if discovered is not None and discovered < count:
            discovered = None
        if state == "complete" and discovered != count:
            state = "partial"
        coverage.append(
            Coverage(category_id=category_id, state=state, discovered=discovered, collected=count)
        )
    return assemble_snapshot(
        incoming.generated_at, list(categories.values()), list(resources.values()), coverage
    )
