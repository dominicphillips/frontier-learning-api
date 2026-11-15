from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Annotated, Literal

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
    id: Annotated[str, StringConstraints(pattern=r"^(?:oa|ca|ga)_[a-f0-9]{24}$")]
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
