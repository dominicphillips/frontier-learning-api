from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import AwareDatetime, Field, StringConstraints

from .models import Audience, Duration, Hash, Model, ShortText, Slug, Status, Title
from .providers.claude import models as claude_models
from .providers.claude.storage import SnapshotStore as ClaudeStore
from .providers.gemini import models as gemini_models
from .providers.gemini.storage import SnapshotStore as GeminiStore
from .providers.openai import models as openai_models
from .providers.openai.storage import SnapshotStore as OpenAIStore
from .storage import BaseSnapshotStore

ProviderId = Literal["openai", "claude", "gemini"]
Kind = Literal[
    "course",
    "learning-path",
    "article",
    "video",
    "event",
    "collection",
    "external",
    "tutorial",
    "use-case",
    "lab",
]
CategoryId = Annotated[
    str,
    StringConstraints(
        pattern=r"^(?:openai|claude|gemini):[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=107
    ),
]
ResourceId = Annotated[str, StringConstraints(pattern=r"^(?:oa|ca|ga)_[a-f0-9]{24}$")]


class Unit(Model):
    title: Title
    url: str
    kind: Literal["lesson", "quiz", "lab", "course", "collection", "tutorial", "use-case"]
    context: ShortText | None = None
    video_count: int | None = None


class Section(Model):
    title: Title | None = None
    context: ShortText | None = None
    units: list[Unit] = Field(default_factory=list)


class Detail(Model):
    audience: ShortText | None = None
    prerequisites: list[ShortText] = Field(default_factory=list)
    objectives: list[ShortText] = Field(default_factory=list)
    sections: list[Section] = Field(default_factory=list)


class Artwork(Model):
    url: str
    alt: ShortText | None = None
    source_url: str


class Provenance(Model):
    source_urls: list[str]
    fetched_at: AwareDatetime
    content_hash: Hash
    method: Literal["manual", "fixture", "crawler", "managed-agent"]


class Resource(Model):
    id: ResourceId
    provider: ProviderId
    title: Title
    url: str
    kind: Kind
    category_ids: list[CategoryId]
    audiences: list[Audience]
    tags: list[str]
    summary: str | None
    level: Literal["beginner", "intermediate", "advanced"] | None
    duration: Duration
    detail: Detail
    media: list[openai_models.MediaReference]
    artwork: Artwork | None
    provenance: Provenance


class ResourcePage(Model):
    items: list[Resource]
    next_cursor: str | None
    total: int
    snapshot_id: Hash


class LearningPathStep(Model):
    position: Annotated[int, Field(ge=1)]
    section_title: Title | None = None
    title: Title
    url: str
    kind: Literal["lesson", "quiz", "lab", "course", "collection", "tutorial", "use-case"]
    resource_id: ResourceId | None = None
    summary: str | None = None
    level: Literal["beginner", "intermediate", "advanced"] | None = None
    duration: Duration | None = None
    context: ShortText | None = None


class ProviderLearningPath(Model):
    id: ResourceId
    title: Title
    url: str
    kind: Literal["learning-path"] = "learning-path"
    category_ids: list[Slug]
    audiences: list[Audience]
    tags: list[str]
    summary: str | None
    level: Literal["beginner", "intermediate", "advanced"] | None
    duration: Duration
    step_count: Annotated[int, Field(ge=0)]
    steps: list[LearningPathStep]
    artwork: Artwork | None
    provenance: Provenance


class ProviderLearningPathPage(Model):
    items: list[ProviderLearningPath]
    next_cursor: str | None
    total: int
    snapshot_id: Hash


class LearningPath(Model):
    id: ResourceId
    provider: ProviderId
    title: Title
    url: str
    kind: Literal["learning-path"] = "learning-path"
    category_ids: list[CategoryId]
    audiences: list[Audience]
    tags: list[str]
    summary: str | None
    level: Literal["beginner", "intermediate", "advanced"] | None
    duration: Duration
    step_count: Annotated[int, Field(ge=0)]
    steps: list[LearningPathStep]
    artwork: Artwork | None
    provenance: Provenance


class LearningPathPage(Model):
    items: list[LearningPath]
    next_cursor: str | None
    total: int
    snapshot_id: Hash


class Category(Model):
    id: CategoryId
    provider: ProviderId
    slug: Slug
    label: Title
    count: int


class CategoryPage(Model):
    items: list[Category]
    snapshot_id: Hash


class CatalogStatus(Model):
    state: Literal["fresh", "stale", "unavailable"]
    snapshot_id: Hash | None
    resource_count: int
    providers: dict[ProviderId, Status]


class Provider(Model):
    id: ProviderId
    label: str
    source_url: str
    resource_prefix: str
    kinds: list[str]
    status: Status


class ProviderPage(Model):
    items: list[Provider]


@dataclass(frozen=True)
class ProviderSpec:
    id: ProviderId
    label: str
    source_url: str
    prefix: str
    models: ModuleType
    store: BaseSnapshotStore


def providers(data_dir: Path) -> dict[str, ProviderSpec]:
    definitions = [
        (
            "openai",
            "OpenAI Academy",
            "https://academy.openai.com",
            "oa_",
            openai_models,
            OpenAIStore,
        ),
        (
            "claude",
            "Claude Academy",
            "https://academy.claude.com",
            "ca_",
            claude_models,
            ClaudeStore,
        ),
        ("gemini", "Google Skills", "https://www.skills.google", "ga_", gemini_models, GeminiStore),
    ]
    return {
        name: ProviderSpec(name, label, url, prefix, models, store(data_dir / f"{name}.json"))
        for name, label, url, prefix, models, store in definitions
    }


def project_resource(provider: str, resource) -> dict:
    value = resource.model_dump(mode="json", by_alias=True)
    return value | {
        "provider": provider,
        "categoryIds": [f"{provider}:{category}" for category in value["categoryIds"]],
    }


def canonical_url_key(value: str) -> str:
    parsed = urlsplit(value)
    host = parsed.hostname.lower() if parsed.hostname else ""
    return f"{host}{parsed.path.rstrip('/')}"


def project_learning_path(
    provider: ProviderId, resource, by_url: dict[str, object], *, aggregate: bool
) -> dict:
    raw = resource.model_dump(mode="json", by_alias=True)
    steps: list[dict] = []
    position = 0
    for section in resource.detail.sections:
        for unit in section.units:
            position += 1
            target = by_url.get(canonical_url_key(unit.url))
            if target is not None and target.id == resource.id:
                target = None
            steps.append(
                {
                    "position": position,
                    "sectionTitle": section.title,
                    "title": unit.title,
                    "url": unit.url,
                    "kind": unit.kind,
                    "resourceId": target.id if target is not None else None,
                    "summary": target.summary if target is not None else None,
                    "level": target.level if target is not None else None,
                    "duration": (
                        target.duration.model_dump(mode="json", by_alias=True)
                        if target is not None
                        else None
                    ),
                    "context": unit.context,
                }
            )
    payload = {
        "id": raw["id"],
        "title": raw["title"],
        "url": raw["url"],
        "kind": "learning-path",
        "categoryIds": (
            [f"{provider}:{category}" for category in raw["categoryIds"]]
            if aggregate
            else raw["categoryIds"]
        ),
        "audiences": raw["audiences"],
        "tags": raw["tags"],
        "summary": raw["summary"],
        "level": raw["level"],
        "duration": raw["duration"],
        "stepCount": len(steps),
        "steps": steps,
        "artwork": raw["artwork"],
        "provenance": raw["provenance"],
    }
    if aggregate:
        payload = {"id": payload["id"], "provider": provider} | {
            k: v for k, v in payload.items() if k != "id"
        }
    return payload


def snapshot_learning_paths(provider: ProviderId, snapshot, *, aggregate: bool) -> list[dict]:
    by_url = {canonical_url_key(item.url): item for item in snapshot.resources}
    return [
        project_learning_path(provider, item, by_url, aggregate=aggregate)
        for item in snapshot.resources
        if item.kind == "learning-path"
    ]
