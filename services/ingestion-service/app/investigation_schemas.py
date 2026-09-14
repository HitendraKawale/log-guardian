"""Investigation inputs are separate from the unchanged per-log scoring contract."""

from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from .schemas import LogLevel

ServiceName = Annotated[str, Field(strict=True, min_length=1, max_length=128)]


class InvestigationScope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    services: tuple[ServiceName, ...] = Field(min_length=1, max_length=4)
    start: AwareDatetime
    end: AwareDatetime

    @field_validator("start", "end", mode="before")
    @classmethod
    def require_timestamp(cls, value):
        if not isinstance(value, str | datetime):
            raise ValueError("Expected an offset-aware ISO timestamp")
        return value

    @field_validator("start", "end")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def check_window(self) -> Self:
        if not timedelta(0) < self.end - self.start <= timedelta(hours=1):
            raise ValueError("Scope must span more than zero and at most one hour")
        if len(set(self.services)) != len(self.services):
            raise ValueError("Duplicate services")
        if any(name != name.strip() for name in self.services):
            raise ValueError("Service names cannot have surrounding whitespace")
        return self


class LogQuery(InvestigationScope):
    text: str | None = Field(None, strict=True, min_length=1, max_length=512)
    limit: int = Field(50, strict=True, ge=1, le=50)


class RunbookQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(strict=True, min_length=1, max_length=512)
    limit: int = Field(3, strict=True, ge=1, le=3)


class ReplayLog(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_id: str = Field(
        strict=True, min_length=1, max_length=128, pattern=r"^[A-Za-z0-9:_-]+$"
    )
    service: ServiceName
    level: LogLevel
    message: str = Field(strict=True)
    timestamp: AwareDatetime

    @field_validator("timestamp")
    @classmethod
    def utc(cls, value: datetime) -> datetime:
        return value.astimezone(UTC)


class EvidenceItem(BaseModel):
    evidence_id: str
    kind: Literal["log", "summary", "runbook"]
    content: dict[str, Any]


class EvidenceBatch(BaseModel):
    source: Literal["replay", "database", "runbooks"]
    version: str | None = None
    start: datetime | None = None
    end: datetime | None = None
    items: list[EvidenceItem] = Field(default_factory=list)
    truncated: bool = False
    error: Literal["invalid_arguments", "scope_violation", "source_unavailable"] | None = None
