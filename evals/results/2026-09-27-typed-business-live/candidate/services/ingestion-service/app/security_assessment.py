"""Render recorded facts from typed evidence, never from model-written claims."""

import json
import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .investigation_schemas import Finding
from .investigation_tools import MAX_RESULT_BYTES
from .security_evidence import AuthEvent, GatewayEvent


class SecuritySelection(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    focus_evidence_ids: list[Annotated[str, Field(min_length=1, max_length=128)]] = Field(
        max_length=3
    )
    hypothesis_codes: list[Literal["repeated_login_attempts", "retry_possible"]] = Field(
        max_length=2
    )
    check_codes: list[
        Literal["read_auth_results", "read_rejection_reasons", "read_session_audit"]
    ] = Field(max_length=2)

    @model_validator(mode="after")
    def unique_selections(self):
        for values in (self.focus_evidence_ids, self.hypothesis_codes, self.check_codes):
            if len(values) != len(set(values)):
                raise ValueError("Duplicate security selection")
        return self


def _known_identity(value):
    return (
        isinstance(value, str)
        and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:/-]{0,127}", value) is not None
        and "redacted" not in value.lower()
    )


def _count(value):
    if type(value) is not int or not 0 <= value <= 1000:
        raise ValueError("Invalid security count")
    return value


def _finding(claim, ids):
    return Finding(claim=claim, evidence_ids=ids).model_dump(mode="json")


def _assemble(selection, batches):
    items = {}
    versions = set()
    failed = False
    for batch in batches:
        if batch.source != "security_case":
            raise ValueError("Non-security evidence")
        if batch.error:
            failed = True
            continue
        if not batch.version:
            raise ValueError("Missing security version")
        versions.add(batch.version)
        for item in batch.items:
            if item.evidence_id in items and items[item.evidence_id] != item:
                raise ValueError("Conflicting security evidence")
            items[item.evidence_id] = item
    if len(versions) > 1:
        raise ValueError("Mixed security cases")

    summaries = [
        i
        for i in items.values()
        if i.kind == "summary" and i.content.get("count_scope") == "whole_saved_case"
    ]
    if len(summaries) > 1:
        raise ValueError("Multiple case summaries")
    summary = summaries[0] if summaries else None
    auth_records = failures = successes = unlinked = 0
    facts = {}
    if summary:
        c = summary.content
        if summary.evidence_id != "security-summary:" + next(iter(versions)):
            raise ValueError("Unbound case summary")
        auth_sources = [
            s["source_id"] for s in c["source_config"] if s["event_kind"] == "authentication_result"
        ]
        for source in auth_sources:
            counts = c["sources"][source]
            auth_records += _count(counts["records"])
            failures += _count(counts["auth_outcomes"]["failure"])
            successes += _count(counts["auth_outcomes"]["success"])
        unlinked = _count(c["unlinked_records"])
        facts[summary.evidence_id] = _finding(
            f"Whole saved case contains {_count(c['total'])} supplied records, including "
            f"{auth_records} authentication results: {failures} failure, {successes} success. "
            f"{unlinked} records have no confirmed request counterpart.",
            [summary.evidence_id],
        )

    auth = []
    for item in items.values():
        if item.kind == "summary":
            continue
        if item.kind != "security_event":
            raise ValueError("Unsupported security evidence kind")
        c = item.content
        data = {"evidence_id": item.evidence_id, "event_time": c["event_time"]}
        if c["event_kind"] == "gateway_request":
            row = GatewayEvent.model_validate(
                {
                    **data,
                    "route": c["route"],
                    "http_status": c.get("http_status"),
                    "client_address": c.get("client_address"),
                }
            )
            status = (
                f"HTTP {row.http_status}"
                if row.http_status is not None
                else "an unavailable HTTP status"
            )
            address = (
                f" from address {json.dumps(row.client_address)}" if row.client_address else ""
            )
            claim = f"Gateway recorded {status} for route {json.dumps(row.route)} at {c['event_time']}{address}."
        elif c["event_kind"] == "authentication_result":
            account = c.get("account_ref")
            row = AuthEvent.model_validate(
                {
                    **data,
                    "auth_outcome": c["auth_outcome"],
                    "account_ref": account if _known_identity(account) else None,
                }
            )
            subject = (
                f" for account {json.dumps(row.account_ref)}"
                if row.account_ref
                else "; account reference unavailable or redacted"
            )
            claim = (
                f"Authentication service recorded {row.auth_outcome}{subject} at {c['event_time']}."
            )
            auth.append((item, row))
        else:
            raise ValueError("Unknown security event kind")
        facts[item.evidence_id] = _finding(claim, [item.evidence_id])

    # One pass over recorded order; never join redacted identities or ambiguous requests.
    earlier_failures = {}
    retry = None
    for item, row in sorted(auth, key=lambda pair: (pair[1].event_time, pair[0].evidence_id)):
        c = item.content
        source = c["evidence"][0]
        if not _known_identity(source) or not row.account_ref or c["correlation"] == "ambiguous":
            continue
        key = (source, row.account_ref)
        previous = earlier_failures.get(key)
        if row.auth_outcome == "success" and previous and previous[1].event_time < row.event_time:
            retry = [previous[0].evidence_id, item.evidence_id]
            break
        if row.auth_outcome == "failure" and previous is None:
            earlier_failures[key] = (item, row)

    hypotheses = []
    for code in selection.hypothesis_codes:
        if code == "repeated_login_attempts" and summary and failures > 1:
            hypotheses.append(
                _finding(
                    "More than one authentication failure was recorded. Mistakes and unauthorized guessing "
                    "are possible explanations; intent and actor identity are unknown.",
                    [summary.evidence_id],
                )
            )
        elif code == "retry_possible" and retry:
            hypotheses.append(
                _finding(
                    "A same-source, same-account failure precedes a success in recorded order. "
                    "A retry is possible; causal order, actor identity and legitimate ownership are not established.",
                    retry,
                )
            )
        else:
            raise ValueError("Unsupported security hypothesis")

    checks = []
    prerequisites = {
        "read_auth_results": not summary or auth_records == 0 or unlinked > 0,
        "read_rejection_reasons": failures > 0 or any(r.auth_outcome == "failure" for _, r in auth),
        "read_session_audit": successes > 0
        or unlinked > 0
        or any(r.auth_outcome == "success" for _, r in auth),
    }
    instructions = {
        "read_auth_results": "Obtain authentication-result records for the scoped requests and time window; absence from this case does not establish a service outage.",
        "read_rejection_reasons": "Inspect redacted authentication rejection reasons for the scoped attempts. Do not collect credentials, cookies, tokens or request payload dumps.",
        "read_session_audit": "Inspect session policy and redacted activity audit records for the scoped requests; do not presume compromise or business effects.",
    }
    for code in selection.check_codes:
        if not prerequisites[code]:
            raise ValueError("Unsupported security check")
        checks.append(instructions[code])

    unknowns = [
        "Collection completeness is unknown; supplied records may be incomplete.",
        "Clock alignment and causal order are unverified.",
        "Real actor identity, account ownership and authorization are unestablished.",
        "Account compromise, AI involvement and business impact are not established.",
    ]
    if summary and auth_records == 0:
        unknowns.append(
            "Authentication outcome is unknown; no authentication results were supplied."
        )
    if not summary or failed:
        unknowns.append(
            "Some security evidence is unavailable; missing reads do not establish absent records."
        )
    if any(b.truncated for b in batches):
        unknowns.append(
            "A delivered evidence page was truncated; page contents do not establish whole-case absence."
        )
    return {
        "schema_version": 2,
        "outcome": "inconclusive",
        "facts": [facts[identity] for identity in selection.focus_evidence_ids],
        "hypotheses": hypotheses,
        "unknowns": unknowns,
        "checks": checks,
    }


def assemble_security_assessment(selection: SecuritySelection, batches):
    """Only selected delivered facts and applicable codes can enter the stored report."""
    try:
        report = _assemble(selection, batches)
    except (KeyError, TypeError, IndexError, StopIteration) as exc:
        raise ValueError("Invalid security evidence or selection") from exc
    if len(json.dumps(report, ensure_ascii=False).encode()) > MAX_RESULT_BYTES:
        raise ValueError("Security report exceeds byte limit")
    return report
