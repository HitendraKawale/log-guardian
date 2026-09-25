"""Prescribed gateway/auth formats keep source ownership outside uploaded log content."""

import json
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictStr, model_validator

from .investigation_schemas import InvestigationScope
from .security_evidence import (
    MAX_BYTES,
    MAX_LINE_BYTES,
    MAX_RECORDS,
    SourceConfig,
    Token,
    decode_json,
    inspect_bundle,
)


class AdapterSource(SourceConfig):
    format: Literal["nginx_json", "application_auth_json"]

    @model_validator(mode="after")
    def matching_kind(self):
        if (self.format == "nginx_json") != (self.event_kind == "gateway_request"):
            raise ValueError("format_kind_mismatch")
        return self


class Registry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    sources: tuple[AdapterSource, ...] = Field(min_length=1, max_length=4)

    @model_validator(mode="after")
    def unique_sources(self):
        if len({s.source_id for s in self.sources}) != len(self.sources):
            raise ValueError("duplicate_source")
        return self


class ImportBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scope: InvestigationScope
    logs: dict[Token, StrictStr] = Field(min_length=1, max_length=4)


class NginxLog(BaseModel):
    model_config = ConfigDict(extra="forbid")
    time: Annotated[str, Field(strict=True, max_length=64)]
    request_id: Token
    remote_addr: Annotated[str, Field(strict=True, max_length=45)]
    status: Annotated[str, Field(strict=True, pattern=r"^[1-5][0-9]{2}$")]
    route: Annotated[str, Field(strict=True, max_length=256)]


class AuthLog(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_id: Token
    timestamp: Annotated[str, Field(strict=True, max_length=64)]
    request_id: Token | None = None
    account_ref: Token | None = None
    outcome: Literal["success", "failure", "unavailable"]


def analyze_import(owner: dict | Registry, body: dict) -> dict:
    """Validate all raw rows, then delegate evidence semantics to the existing engine."""
    try:
        registry = Registry.model_validate(owner)
        request = ImportBody.model_validate(body)
        raw = {name: value.encode("utf-8") for name, value in request.logs.items()}
    except (ValueError, OverflowError):
        raise ValueError("invalid_import") from None
    if set(raw) != {s.source_id for s in registry.sources}:
        raise ValueError("source_inputs_mismatch")
    if set(request.scope.services) != {s.service for s in registry.sources}:
        raise ValueError("source_scope_mismatch")
    if sum(map(len, raw.values())) > MAX_BYTES:
        raise ValueError("byte_limit")
    if sum(len(value.splitlines()) for value in raw.values()) > MAX_RECORDS:
        raise ValueError("record_limit")
    normalized = {}
    for source in registry.sources:
        rows = []
        for number, line in enumerate(raw[source.source_id].splitlines(), 1):
            if len(line) > MAX_LINE_BYTES:
                raise ValueError("line_limit")
            try:
                data = decode_json(line)
                if source.format == "nginx_json":
                    record = NginxLog.model_validate(data)
                    event = {
                        "evidence_id": record.request_id,
                        "event_time": record.time,
                        "request_id": record.request_id,
                        "client_address": record.remote_addr,
                        "http_status": int(record.status),
                        "route": record.route,
                    }
                else:
                    record = AuthLog.model_validate(data)
                    event = {
                        "evidence_id": record.event_id,
                        "event_time": record.timestamp,
                        "request_id": record.request_id,
                        "account_ref": record.account_ref,
                        "auth_outcome": record.outcome,
                    }
            except ValueError:
                raise ValueError(f"invalid_source_record:{source.source_id}:{number}") from None
            rows.append(json.dumps(event).encode())
        normalized[source.source_id] = b"\n".join(rows)
    return inspect_bundle(
        {
            "scope": request.scope.model_dump(mode="json"),
            "sources": [s.model_dump(exclude={"format"}) for s in registry.sources],
        },
        normalized,
    )
