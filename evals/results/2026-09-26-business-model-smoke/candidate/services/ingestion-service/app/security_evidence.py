"""Correlate bounded security records without treating log content as source authority."""

import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from ipaddress import ip_address
from typing import Annotated, Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from .investigation_schemas import InvestigationScope

MAX_BYTES = 1024 * 1024
MAX_RECORDS = 1000
MAX_LINE_BYTES = 16 * 1024
Token = Annotated[
    str, Field(strict=True, min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:/-]*$")
]


class SourceConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: Token
    service: Token
    event_kind: Literal["gateway_request", "authentication_result"]
    request_namespace: Token | None = None


class BundleConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    scope: InvestigationScope
    sources: tuple[SourceConfig, ...] = Field(min_length=1, max_length=4)

    @model_validator(mode="after")
    def sources_in_scope(self):
        if len({source.source_id for source in self.sources}) != len(self.sources):
            raise ValueError("duplicate_source")
        if any(source.service not in self.scope.services for source in self.sources):
            raise ValueError("source_outside_scope")
        return self


class Event(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_id: Token
    event_time: AwareDatetime
    request_id: Token | None = None

    @field_validator("event_time", mode="before")
    @classmethod
    def timestamp(cls, value):
        if not isinstance(value, str):
            raise ValueError("timestamp_string_required")
        return datetime.fromisoformat(value)

    @field_validator("event_time")
    @classmethod
    def utc(cls, value):
        return value.astimezone(UTC)


class GatewayEvent(Event):
    route: Annotated[str, Field(strict=True, max_length=256, pattern=r"^/[A-Za-z0-9_./:{}-]*$")]
    client_address: Annotated[str, Field(strict=True, max_length=45)] | None = None
    http_status: Annotated[int, Field(strict=True, ge=100, le=599)] | None = None

    @field_validator("client_address")
    @classmethod
    def address(cls, value):
        return str(ip_address(value)) if value is not None else None


class AuthEvent(Event):
    account_ref: Token | None = None
    auth_outcome: Literal["success", "failure", "unavailable"]


@dataclass(frozen=True)
class SecurityEvent:
    source: SourceConfig
    event: GatewayEvent | AuthEvent

    @property
    def key(self):
        return self.source.source_id, self.event.evidence_id


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_json_key")
        result[key] = value
    return result


def _reject_number(value):
    raise ValueError("non_integer_json_number")


def decode_json(raw: bytes):
    """Reject ambiguous JSON before model validation; never echo its private contents."""
    try:
        return json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_number,
            parse_float=_reject_number,
        )
    except (ValueError, RecursionError):
        raise ValueError("invalid_json") from None


def parse_events(raw: bytes, source: SourceConfig, scope: InvestigationScope):
    """Parse one owner-selected source; bundle limits are enforced before this call."""
    if len(raw) > MAX_BYTES:
        raise ValueError("byte_limit")
    lines = raw.splitlines()
    if len(lines) > MAX_RECORDS:
        raise ValueError("record_limit")
    result = []
    model = GatewayEvent if source.event_kind == "gateway_request" else AuthEvent
    for number, line in enumerate(lines, 1):
        if len(line) > MAX_LINE_BYTES:
            raise ValueError("line_limit")
        try:
            event = model.model_validate(decode_json(line))
        except (ValueError, OverflowError):
            raise ValueError(f"invalid_event:{source.source_id}:{number}") from None
        if source.service not in scope.services or not scope.start <= event.event_time <= scope.end:
            raise ValueError("event_outside_scope")
        result.append(SecurityEvent(source, event))
    return result


def correlate(events: list[SecurityEvent], config: BundleConfig) -> dict:
    """Count observed records; confirm only unambiguous pairs in an owner namespace."""
    unique = {}
    for record in events:
        if record.key in unique and unique[record.key] != record:
            raise ValueError("conflicting_evidence")
        unique[record.key] = record
    ordered = sorted(unique.values(), key=lambda r: (r.event.event_time, r.key))
    groups = defaultdict(list)
    gaps = set()
    counts = {}
    for source in sorted(config.sources, key=lambda s: s.source_id):
        records = [r.event for r in ordered if r.source.source_id == source.source_id]
        counts[source.source_id] = {
            "records": len(records),
            "distinct_client_addresses": len(
                {
                    r.client_address
                    for r in records
                    if isinstance(r, GatewayEvent) and r.client_address is not None
                }
            ),
            "distinct_account_refs": len(
                {
                    r.account_ref
                    for r in records
                    if isinstance(r, AuthEvent) and r.account_ref is not None
                }
            ),
            "auth_outcomes": {
                outcome: sum(
                    isinstance(r, AuthEvent) and r.auth_outcome == outcome for r in records
                )
                for outcome in ("success", "failure", "unavailable")
            },
        }
        if not records:
            gaps.add("empty_source")
    for record in ordered:
        if record.event.request_id is None:
            gaps.add("missing_request_id")
        elif record.source.request_namespace is None:
            gaps.add("unconfigured_request_namespace")
        else:
            groups[record.source.request_namespace, record.event.request_id].append(record)
        if isinstance(record.event, AuthEvent):
            if record.event.account_ref is None:
                gaps.add("missing_account_ref")
            if record.event.auth_outcome == "unavailable":
                gaps.add("unavailable_authentication_outcome")
        elif record.event.client_address is None:
            gaps.add("missing_client_address")
    links, ambiguous, linked = [], [], set()
    for (namespace, request), records in sorted(groups.items()):
        gateway = [r for r in records if isinstance(r.event, GatewayEvent)]
        auth = [r for r in records if isinstance(r.event, AuthEvent)]
        group = {"request_namespace": namespace, "request_id": request}
        if len(gateway) == len(auth) == 1:
            links.append(
                {**group, "gateway": list(gateway[0].key), "authentication": list(auth[0].key)}
            )
            linked.update(r.key for r in records)
        elif len(gateway) > 1 or len(auth) > 1:
            ambiguous.append(
                {**group, "evidence": [list(r.key) for r in sorted(records, key=lambda r: r.key)]}
            )
            gaps.add("ambiguous_request_id")
        else:
            gaps.add("missing_counterpart")
    if not ordered:
        gaps.add("no_evidence")
    if not any(isinstance(r.event, AuthEvent) for r in ordered):
        gaps.add("missing_authentication_results")
    if not any(isinstance(r.event, GatewayEvent) for r in ordered):
        gaps.add("missing_gateway_requests")
    return {
        "version": 1,
        "scope": config.scope.model_dump(mode="json"),
        "source_config": [
            s.model_dump(mode="json") for s in sorted(config.sources, key=lambda s: s.source_id)
        ],
        "collection_complete": None,
        "input_records": len(events),
        "duplicate_records": len(events) - len(unique),
        "timeline": [
            {
                "evidence": list(r.key),
                "service": r.source.service,
                "event_kind": r.source.event_kind,
                **r.event.model_dump(mode="json"),
            }
            for r in ordered
        ],
        "sources": counts,
        "links": links,
        "ambiguous_groups": ambiguous,
        "unlinked": [list(r.key) for r in ordered if r.key not in linked],
        "gaps": sorted(gaps),
        "limitations": [
            "collection_completeness_unknown",
            "clock_alignment_unverified",
            "impact_not_established",
            "actor_and_ai_attribution_not_established",
        ],
    }


def inspect_bundle(config: dict, inputs: dict[str, bytes]) -> dict:
    """Public boundary: validate the whole bundle before returning any observations."""
    try:
        owner = BundleConfig.model_validate(config)
    except (ValidationError, OverflowError):
        raise ValueError("invalid_source_configuration") from None
    if set(inputs) != {source.source_id for source in owner.sources}:
        raise ValueError("source_inputs_mismatch")
    if any(not isinstance(raw, bytes) for raw in inputs.values()):
        raise ValueError("source_inputs_require_bytes")
    if sum(len(raw) for raw in inputs.values()) > MAX_BYTES:
        raise ValueError("byte_limit")
    if sum(len(raw.splitlines()) for raw in inputs.values()) > MAX_RECORDS:
        raise ValueError("record_limit")
    events = [
        event
        for source in owner.sources
        for event in parse_events(inputs[source.source_id], source, owner.scope)
    ]
    return correlate(events, owner)
