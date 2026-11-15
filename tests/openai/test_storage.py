from __future__ import annotations

import copy
import json
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from frontier_learning.providers.openai.models import CollectionArtifact, Snapshot
from frontier_learning.providers.openai.storage import SnapshotStore


def test_failed_refresh_preserves_last_snapshot(tmp_path, artifact, write_artifact):
    path = tmp_path / "snapshot.json"
    store = SnapshotStore(path)
    original = store.publish(write_artifact(artifact), method="fixture")
    before = path.read_bytes()
    artifact["resources"][0]["courseBody"] = "This field must never pass through."
    with pytest.raises(ValidationError):
        store.publish(write_artifact(artifact))
    assert path.read_bytes() == before
    assert store.read().snapshot_id == original.snapshot_id
    assert store.status().state == "stale"


def test_partial_refresh_preserves_prior_resources_and_categories(
    tmp_path, artifact, write_artifact
):
    path = tmp_path / "snapshot.json"
    store = SnapshotStore(path)
    original = store.publish(write_artifact(artifact), method="fixture")
    partial = copy.deepcopy(artifact)
    partial["generatedAt"] = datetime.now(UTC).isoformat()
    partial["resources"] = partial["resources"][:1]
    partial["resources"][0]["summary"] = "Changed metadata from the bounded pass."
    partial["categories"] = partial["categories"][:1]
    partial["coverage"] = [
        {"categoryId": "work", "state": "partial", "discovered": None, "collected": 1}
    ]
    result = store.publish(write_artifact(partial))
    assert len(result.resources) == 3
    assert {c.id for c in result.categories} == {c.id for c in original.categories}
    assert all(c.state == "partial" for c in result.coverage)
    assert result.resources != original.resources
    assert store.status().state == "stale"
    assert json.loads(store.previous_path.read_text())["snapshotId"] == original.snapshot_id


def test_corrupt_disk_keeps_memory_or_persisted_last_good(tmp_path, artifact, write_artifact):
    path = tmp_path / "snapshot.json"
    store = SnapshotStore(path)
    first = store.publish(write_artifact(artifact), method="fixture")
    artifact["generatedAt"] = datetime.now(UTC).isoformat()
    second = store.publish(write_artifact(artifact))
    path.write_text("{invalid}")
    assert store.read().snapshot_id == second.snapshot_id
    assert store.status().state == "stale"
    restarted = SnapshotStore(path)
    assert restarted.read().snapshot_id == first.snapshot_id


@pytest.mark.parametrize("field", ["generated", "fetched"])
def test_future_timestamps_are_rejected(artifact, field):
    future = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    artifact["generatedAt"] = future
    if field == "fetched":
        artifact["resources"][0]["provenance"]["fetchedAt"] = future
    with pytest.raises(ValidationError):
        CollectionArtifact.model_validate_json(json.dumps(artifact))


def test_content_hashes_and_ids_are_verified(tmp_path, artifact, write_artifact):
    snapshot = SnapshotStore(tmp_path / "snapshot.json").publish(write_artifact(artifact))
    data = snapshot.model_dump(mode="json", by_alias=True)
    data["resources"][0]["title"] = "Tampered title"
    with pytest.raises(ValidationError):
        Snapshot.model_validate_json(json.dumps(data))


def test_collection_counts_reject_invented_coverage(artifact):
    artifact["coverage"][0]["collected"] = 2
    artifact["coverage"][0]["discovered"] = 2
    with pytest.raises(ValidationError):
        CollectionArtifact.model_validate_json(json.dumps(artifact))


def test_merge_drops_club_overview_alias_of_a_published_club(artifact):
    import copy
    import json as _json

    from frontier_learning.providers.openai.models import CollectionArtifact, build_snapshot
    from frontier_learning.providers.openai.storage import merge_snapshot

    club = "https://academy.openai.com/public/clubs/work-users-ynjqu"
    first = copy.deepcopy(artifact)
    row = copy.deepcopy(first["resources"][0])
    row.update(title="Work Users", url=club, kind="collection")
    row["provenance"]["sourceUrls"] = [club]
    first["resources"].append(row)
    first["coverage"][0].update(discovered=2, collected=2)
    previous = build_snapshot(CollectionArtifact.model_validate_json(_json.dumps(first)), "fixture")

    second = copy.deepcopy(first)
    alias = copy.deepcopy(row)
    alias.update(url=club + "/overview")
    alias["provenance"]["sourceUrls"] = [club + "/overview"]
    second["resources"].append(alias)
    second["coverage"][0].update(discovered=3, collected=3)
    incoming = build_snapshot(
        CollectionArtifact.model_validate_json(_json.dumps(second)), "fixture"
    )

    merged = merge_snapshot(previous, incoming)
    urls = [r.url for r in merged.resources]
    assert club in urls and club + "/overview" not in urls
    assert len(urls) == len(previous.resources)


def test_merge_keeps_club_overview_when_the_club_itself_is_unknown(artifact):
    import copy
    import json as _json

    from frontier_learning.providers.openai.models import CollectionArtifact, build_snapshot
    from frontier_learning.providers.openai.storage import merge_snapshot

    overview = "https://academy.openai.com/public/clubs/new-club-abc12/overview"
    second = copy.deepcopy(artifact)
    row = copy.deepcopy(second["resources"][0])
    row.update(title="New club", url=overview, kind="collection")
    row["provenance"]["sourceUrls"] = [overview]
    second["resources"].append(row)
    second["coverage"][0].update(discovered=2, collected=2)
    previous = build_snapshot(
        CollectionArtifact.model_validate_json(_json.dumps(artifact)), "fixture"
    )
    incoming = build_snapshot(
        CollectionArtifact.model_validate_json(_json.dumps(second)), "fixture"
    )
    assert overview in [r.url for r in merge_snapshot(previous, incoming).resources]


def test_merge_keeps_one_record_for_a_club_reachable_under_two_slugs(artifact):
    import copy
    import json as _json

    from frontier_learning.providers.openai.models import CollectionArtifact, build_snapshot
    from frontier_learning.providers.openai.storage import merge_snapshot

    second = copy.deepcopy(artifact)
    for slug in ("government", "government-25yzc"):
        url = f"https://academy.openai.com/public/clubs/{slug}/overview"
        row = copy.deepcopy(second["resources"][0])
        row.update(
            title="Government (United States)",
            url=url,
            kind="collection",
            summary="A space for public servants.",
        )
        row["provenance"]["sourceUrls"] = [url]
        second["resources"].append(row)
    second["coverage"][0].update(discovered=3, collected=3)
    previous = build_snapshot(
        CollectionArtifact.model_validate_json(_json.dumps(artifact)), "fixture"
    )
    incoming = build_snapshot(
        CollectionArtifact.model_validate_json(_json.dumps(second)), "fixture"
    )
    merged = merge_snapshot(previous, incoming)
    assert sum(r.title == "Government (United States)" for r in merged.resources) == 1


def test_merge_keeps_recurring_club_videos_that_share_a_title(artifact):
    import copy
    import json as _json

    from frontier_learning.providers.openai.models import CollectionArtifact, build_snapshot
    from frontier_learning.providers.openai.storage import merge_snapshot

    second = copy.deepcopy(artifact)
    for slug in ("codex-bootcamp-201-2026-09-30", "codex-bootcamp-201-2026-10-07"):
        url = f"https://academy.openai.com/public/clubs/builders-etkn1/videos/{slug}"
        row = copy.deepcopy(second["resources"][0])
        row.update(
            title="Codex bootcamp 201", url=url, kind="video", summary="Recording of the bootcamp."
        )
        row["provenance"]["sourceUrls"] = [url]
        second["resources"].append(row)
    second["coverage"][0].update(discovered=3, collected=3)
    previous = build_snapshot(
        CollectionArtifact.model_validate_json(_json.dumps(artifact)), "fixture"
    )
    incoming = build_snapshot(
        CollectionArtifact.model_validate_json(_json.dumps(second)), "fixture"
    )
    assert (
        sum(r.title == "Codex bootcamp 201" for r in merge_snapshot(previous, incoming).resources)
        == 2
    )
