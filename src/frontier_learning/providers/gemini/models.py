"""Strict public metadata and collection artifact contracts."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal, Self

from pydantic import (
    AfterValidator,
    AwareDatetime,
    Field,
    StringConstraints,
    model_validator,
)

from ...models import (
    Audience as Audience,
)
from ...models import (
    Category as Category,
)
from ...models import (
    CategoryCount as CategoryCount,
)
from ...models import (
    CategoryPage as CategoryPage,
)
from ...models import (
    Count as Count,
)
from ...models import (
    Coverage as Coverage,
)
from ...models import (
    Duration as Duration,
)
from ...models import (
    FetchReport as FetchReport,
)
from ...models import (
    Hash as Hash,
)
from ...models import (
    Model as Model,
)
from ...models import (
    ShortText as ShortText,
)
from ...models import (
    Slug as Slug,
)
from ...models import (
    Status as Status,
)
from ...models import (
    Title as Title,
)
from ...models import (
    camel as camel,
)
from ...models import (
    json_hash as json_hash,
)
from .security import (
    artwork_url,
    official_url,
    resource_kind,
    resource_url,
    source_url,
    stable_id,
)

ResourceUrl = Annotated[str, AfterValidator(resource_url)]
OfficialUrl = Annotated[str, AfterValidator(official_url)]
SourceUrl = Annotated[str, AfterValidator(source_url)]
Kind = Literal["course", "learning-path", "lab"]
Method = Literal["crawler", "manual", "fixture"]


class Unit(Model):
    title: Title
    url: OfficialUrl
    kind: Literal["lesson", "quiz", "lab", "course"]
    context: ShortText | None = None
    video_count: Count | None = None


class Section(Model):
    title: Title | None = None
    context: ShortText | None = None
    units: list[Unit] = Field(default_factory=list, max_length=200)


class Detail(Model):
    audience: ShortText | None = None
    prerequisites: list[ShortText] = Field(default_factory=list, max_length=20)
    objectives: list[ShortText] = Field(default_factory=list, max_length=20)
    sections: list[Section] = Field(default_factory=list, max_length=50)


class MediaReference(Model):
    kind: Literal["video", "audio", "image", "document"]
    url: OfficialUrl
    permission: Literal["permitted"]
    permission_evidence_url: SourceUrl
    title: Title | None = None


class ArtworkReference(Model):
    url: Annotated[str, AfterValidator(artwork_url)]
    alt: ShortText | None = None
    source_url: ResourceUrl


class InputProvenance(Model):
    source_urls: list[SourceUrl] = Field(min_length=1, max_length=16)
    fetched_at: AwareDatetime

    @model_validator(mode="after")
    def plausible_time(self) -> Self:
        if self.fetched_at > datetime.now(UTC) + timedelta(minutes=5):
            raise ValueError("Fetched time is implausibly in the future")
        if len(self.source_urls) != len(set(self.source_urls)):
            raise ValueError("Duplicate provenance source URL")
        return self


class Provenance(InputProvenance):
    content_hash: Hash
    method: Method


class Metadata(Model):
    title: Title
    url: ResourceUrl
    kind: Kind
    category_ids: list[Slug] = Field(default_factory=list, max_length=50)
    audiences: list[Audience] = Field(default_factory=list, max_length=8)
    tags: list[Title] = Field(default_factory=list, max_length=50)
    summary: Annotated[str, Field(min_length=1, max_length=1200)] | None = None
    level: Literal["beginner", "intermediate", "advanced"] | None = None
    duration: Duration = Field(default_factory=Duration)
    detail: Detail = Field(default_factory=Detail)
    # Course media is never copied or referenced; the list stays empty by contract.
    media: list[MediaReference] = Field(default_factory=list, max_length=0)
    # The page's own share image, hotlinked from the official host. Null when absent.
    artwork: ArtworkReference | None = None

    @model_validator(mode="after")
    def unique_values(self) -> Self:
        for values in (self.category_ids, self.audiences, self.tags):
            if len(values) != len(set(values)):
                raise ValueError("Duplicate resource category, audience or tag")
        if sum(len(x.units) for x in self.detail.sections) > 200:
            raise ValueError("Too many ordered units")
        if resource_kind(self.url) != self.kind:
            raise ValueError("Resource kind does not match its URL")
        if self.artwork is not None:
            raise ValueError(
                "Google Skills resources do not have per-page artwork; artwork must be null"
            )
        return self


class InputResource(Metadata):
    provenance: InputProvenance

    @model_validator(mode="after")
    def primary_source(self) -> Self:
        if self.url not in self.provenance.source_urls:
            raise ValueError("Provenance must include the resource URL")
        return self


class Resource(Metadata):
    id: Annotated[str, StringConstraints(pattern=r"^ga_[a-f0-9]{24}$")]
    provenance: Provenance

    @model_validator(mode="after")
    def verify_identity(self) -> Self:
        if self.id != stable_id(self.url):
            raise ValueError("Resource ID does not match its canonical URL")
        if self.provenance.content_hash != metadata_hash(self):
            raise ValueError("Resource content hash does not match its metadata")
        if self.url not in self.provenance.source_urls:
            raise ValueError("Provenance must include the resource URL")
        return self


class CollectionArtifact(Model):
    schema_version: Literal[1]
    generated_at: AwareDatetime
    categories: list[Category] = Field(max_length=200)
    resources: list[InputResource] = Field(max_length=5000)
    coverage: list[Coverage] = Field(max_length=200)
    fetch_report: FetchReport

    @model_validator(mode="after")
    def consistent_inventory(self) -> Self:
        validate_inventory(self.categories, self.resources, self.coverage)
        if self.generated_at > datetime.now(UTC) + timedelta(minutes=5):
            raise ValueError("Generation time is implausibly in the future")
        if any(r.provenance.fetched_at > self.generated_at for r in self.resources):
            raise ValueError("Fetched time is later than snapshot generation")
        return self


class Snapshot(Model):
    schema_version: Literal[1]
    snapshot_id: Hash
    generated_at: AwareDatetime
    categories: list[Category] = Field(max_length=200)
    resources: list[Resource] = Field(max_length=5000)
    coverage: list[Coverage] = Field(max_length=200)

    @model_validator(mode="after")
    def consistent_snapshot(self) -> Self:
        validate_inventory(self.categories, self.resources, self.coverage)
        if self.generated_at > datetime.now(UTC) + timedelta(minutes=5):
            raise ValueError("Generation time is implausibly in the future")
        if any(r.provenance.fetched_at > self.generated_at for r in self.resources):
            raise ValueError("Fetched time is later than snapshot generation")
        if self.snapshot_id != snapshot_hash(self):
            raise ValueError("Snapshot hash does not match its contents")
        return self


class ResourcePage(Model):
    items: list[Resource]
    next_cursor: str | None
    total: int
    snapshot_id: Hash


def metadata_hash(resource: Metadata) -> str:
    return json_hash(resource.model_dump(mode="json", by_alias=True, exclude={"id", "provenance"}))


def snapshot_hash(snapshot: Snapshot) -> str:
    return json_hash(snapshot.model_dump(mode="json", by_alias=True, exclude={"snapshot_id"}))


def validate_inventory(categories: list, resources: list, coverage: list[Coverage]) -> None:
    ids = [x.id for x in categories]
    urls = [x.url for x in resources]
    if len(ids) != len(set(ids)) or len(urls) != len(set(urls)):
        raise ValueError("Duplicate category ID or resource URL")
    if {x.category_id for x in coverage} != set(ids) or len(coverage) != len(ids):
        raise ValueError("Coverage must contain exactly one row per category")
    for resource in resources:
        if set(resource.category_ids) - set(ids):
            raise ValueError("Resource refers to an unknown category")
    for item in coverage:
        count = sum(item.category_id in r.category_ids for r in resources)
        if count != item.collected:
            raise ValueError("Coverage count does not match category membership")


def build_snapshot(artifact: CollectionArtifact, method: Method) -> Snapshot:
    resources = []
    for source in artifact.resources:
        data = source.model_dump()
        data["id"] = stable_id(source.url)
        data["provenance"].update(content_hash=metadata_hash(source), method=method)
        resources.append(Resource.model_validate(data))
    return assemble_snapshot(
        artifact.generated_at, artifact.categories, resources, artifact.coverage
    )


def assemble_snapshot(
    generated_at: datetime,
    categories: list[Category],
    resources: list[Resource],
    coverage: list[Coverage],
) -> Snapshot:
    data = {
        "schema_version": 1,
        "generated_at": generated_at,
        "categories": sorted(categories, key=lambda x: x.id),
        "resources": sorted(resources, key=lambda x: x.id),
        "coverage": sorted(coverage, key=lambda x: x.category_id),
    }
    normalized = {
        camel(k): [x.model_dump(mode="json", by_alias=True) for x in v]
        if isinstance(v, list)
        else v.astimezone(UTC).isoformat().replace("+00:00", "Z")
        if isinstance(v, datetime)
        else v
        for k, v in data.items()
    }
    return Snapshot.model_validate(dict(data, snapshot_id=json_hash(normalized)))
