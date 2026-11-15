from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Annotated, Literal, Self

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_serializer,
    model_validator,
)


def camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(x.capitalize() for x in tail)


class Model(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        alias_generator=camel,
        populate_by_name=True,
        strict=True,
    )

    @field_serializer("*", when_used="json", check_fields=False)
    def utc_dates(self, value: object) -> object:
        if isinstance(value, datetime):
            return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
        return value


Title = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=300,
        pattern=r"^[^\x00-\x1f\x7f-\x9f‪-‮⁦-⁩]+$",
    ),
]

ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]

Slug = Annotated[str, StringConstraints(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=100)]

Hash = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]

Count = Annotated[int, Field(ge=0, le=10000)]

Audience = Literal[
    "general",
    "knowledge-workers",
    "developers",
    "leaders",
    "educators",
    "students",
    "admins",
    "other",
]


class Duration(Model):
    course_minutes: Count | None = None
    path_minutes: Count | None = None
    video_seconds: Annotated[int, Field(ge=0, le=604800)] | None = None


class Category(Model):
    id: Slug
    label: Title


class CategoryCount(Category):
    count: Count


class Coverage(Model):
    category_id: Slug
    state: Literal["complete", "partial", "not-collected"]
    discovered: Count | None = None
    collected: Count

    @model_validator(mode="after")
    def consistent_counts(self) -> Self:
        if self.discovered is not None and self.discovered < self.collected:
            raise ValueError("Collected count exceeds discovery count")
        if self.state == "complete" and self.discovered != self.collected:
            raise ValueError("Complete coverage requires matching known counts")
        if self.state == "not-collected" and self.collected:
            raise ValueError("Not-collected coverage must have zero collected resources")
        return self


class FetchReport(Model):
    requests: Count
    robots_checked: Literal[True]
    completed_within_limits: Literal[True]


class CategoryPage(Model):
    items: list[CategoryCount]
    snapshot_id: Hash


class Status(Model):
    state: Literal["fresh", "stale", "unavailable"]
    snapshot_id: Hash | None
    generated_at: AwareDatetime | None
    last_attempt_at: AwareDatetime | None
    last_success_at: AwareDatetime | None
    resource_count: int
    coverage: list[Coverage]


def json_hash(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()
