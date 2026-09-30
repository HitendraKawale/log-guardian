"""Render recorded facts from typed evidence, never from model-written claims."""

import json
import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .investigation_schemas import EvidenceBatch, Finding, SecurityEvidenceQuery
from .investigation_security import digest, security_page
from .investigation_tools import MAX_RESULT_BYTES
from .security_evidence import MAX_RECORDS, AuthEvent, GatewayEvent

MAX_BASELINE_FACTS = 12
MAX_BASELINE_BYTES = 64 * 1024


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


def _derive(batches):
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
    events = {}
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
        events[item.evidence_id] = row

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

    hypotheses = {}
    if summary and failures > 1:
        hypotheses["repeated_login_attempts"] = _finding(
            "More than one authentication failure was recorded. Mistakes and unauthorized guessing "
            "are possible explanations; intent and actor identity are unknown.",
            [summary.evidence_id],
        )
    if retry:
        hypotheses["retry_possible"] = _finding(
            "A same-source, same-account failure precedes a success in recorded order. "
            "A retry is possible; causal order, actor identity and legitimate ownership are not established.",
            retry,
        )

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
    checks = {code: instructions[code] for code, eligible in prerequisites.items() if eligible}

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
        "items": items,
        "events": events,
        "summary_id": summary.evidence_id if summary else None,
        "auth_counts": (auth_records, failures, successes),
        "facts": facts,
        "hypotheses": hypotheses,
        "unknowns": unknowns,
        "checks": checks,
    }


def _report(derived, ids, hypotheses, checks):
    return {
        "schema_version": 2,
        "outcome": "inconclusive",
        "facts": [derived["facts"][identity] for identity in ids],
        "hypotheses": [derived["hypotheses"][code] for code in hypotheses],
        "unknowns": derived["unknowns"],
        "checks": [derived["checks"][code] for code in checks],
    }


def _assemble(selection, batches):
    derived = _derive(batches)
    if any(code not in derived["hypotheses"] for code in selection.hypothesis_codes):
        raise ValueError("Unsupported security hypothesis")
    if any(code not in derived["checks"] for code in selection.check_codes):
        raise ValueError("Unsupported security check")
    return _report(
        derived, selection.focus_evidence_ids, selection.hypothesis_codes, selection.check_codes
    )


def assemble_security_assessment(selection: SecuritySelection, batches):
    """Only selected delivered facts and applicable codes can enter the stored report."""
    try:
        report = _assemble(selection, batches)
    except (KeyError, TypeError, IndexError, StopIteration) as exc:
        raise ValueError("Invalid security evidence or selection") from exc
    if len(json.dumps(report, ensure_ascii=False).encode()) > MAX_RESULT_BYTES:
        raise ValueError("Security report exceeds byte limit")
    return report


def _saved_evidence(saved):
    timeline = saved["report"]["timeline"]
    if not isinstance(timeline, list) or len(timeline) > MAX_RECORDS:
        raise ValueError("Invalid saved record count")
    version = digest(saved)
    expected_ids = {"security-event:" + digest([version, row["evidence"]]) for row in timeline}
    if len(expected_ids) != len(timeline):
        raise ValueError("Duplicate saved evidence")
    items, offset = {}, 0
    while True:
        batch = security_page(saved, SecurityEvidenceQuery(offset=offset, limit=48))
        if batch.error or batch.source != "security_case" or batch.version != version:
            raise ValueError("Unavailable or inconsistent saved evidence")
        summaries = [i for i in batch.items if i.content.get("count_scope") == "whole_saved_case"]
        pages = [i for i in batch.items if i.evidence_id.startswith("security-page:")]
        records = [i for i in batch.items if i.kind == "security_event"]
        if len(summaries) != 1 or len(pages) != 1 or len(batch.items) != len(records) + 2:
            raise ValueError("Invalid saved evidence page")
        summary, page = summaries[0], pages[0].content
        end = offset + len(records)
        more = end < len(timeline)
        if (
            _count(summary.content["total"]) != len(timeline)
            or _count(page["offset"]) != offset
            or _count(page["returned_records"]) != len(records)
            or len(records) > 48
            or end > len(timeline)
            or (more and not records)
            or batch.truncated != more
            or (more and _count(page["next_offset"]) != end)
            or (not more and page["next_offset"] is not None)
        ):
            raise ValueError("Incomplete saved evidence scan")
        for item in [summary, *records]:
            previous = items.get(item.evidence_id)
            if previous is not None and (item.kind != "summary" or previous != item):
                raise ValueError("Conflicting or repeated saved evidence")
            items[item.evidence_id] = item
        if not more:
            break
        offset = end
    if {i.evidence_id for i in items.values() if i.kind == "security_event"} != expected_ids:
        raise ValueError("Incomplete saved evidence membership")
    return EvidenceBatch(
        source="security_case",
        version=version,
        start=batch.start,
        end=batch.end,
        items=list(items.values()),
        truncated=False,
    )


def _baseline_order(derived):
    events = derived["events"]
    ordered = sorted(
        events,
        key=lambda identity: (
            events[identity].event_time,
            tuple(derived["items"][identity].content["evidence"]),
        ),
    )
    auth = [identity for identity in ordered if isinstance(events[identity], AuthEvent)]
    gateway = [identity for identity in ordered if isinstance(events[identity], GatewayEvent)]
    candidates = [derived["summary_id"]]
    retry = derived["hypotheses"].get("retry_possible")
    if retry:
        candidates.extend(retry["evidence_ids"])
    for outcome in ("failure", "success", "unavailable"):
        candidates.extend(
            next(([identity] for identity in auth if events[identity].auth_outcome == outcome), [])
        )
    statuses = {events[identity].http_status for identity in gateway}
    for status in sorted(statuses, key=lambda s: (6, 0) if s is None else (5 - s // 100, s)):
        candidates.append(
            next(identity for identity in gateway if events[identity].http_status == status)
        )
    return list(dict.fromkeys([*candidates, *auth, *gateway]))


def _json_size(value):
    # Match Starlette JSONResponse's UTF-8 serialization, including Unicode and separators.
    return len(
        json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode()
    )


def build_security_baseline(saved: dict) -> dict:
    """Review a complete bounded snapshot locally; never interpret an AI result as a baseline."""
    try:
        batch = _saved_evidence(saved)
        derived = _derive([batch])
        auth = [row for row in derived["events"].values() if isinstance(row, AuthEvent)]
        if derived["auth_counts"] != (
            len(auth),
            sum(row.auth_outcome == "failure" for row in auth),
            sum(row.auth_outcome == "success" for row in auth),
        ):
            raise ValueError("Inconsistent authentication counts")
        checks = [
            code
            for code in ("read_rejection_reasons", "read_session_audit", "read_auth_results")
            if code in derived["checks"] and (code != "read_auth_results" or not auth)
        ]
        ids = _baseline_order(derived)[:MAX_BASELINE_FACTS]
        total = len(derived["events"])
        while ids:
            report = _report(derived, ids, derived["hypotheses"], checks)
            cited = dict.fromkeys(
                identity
                for finding in report["facts"] + report["hypotheses"]
                for identity in finding["evidence_ids"]
            )
            shown = len(ids) - 1
            result = {
                "method": "deterministic",
                "policy_version": 1,
                "case_version": batch.version,
                "report": report,
                "coverage": {
                    "saved_records": total,
                    "reviewed_records": total,
                    "displayed_event_facts": shown,
                    "omitted_event_facts": total - shown,
                    "fact_limit": MAX_BASELINE_FACTS,
                    "display_limited": shown < total,
                },
                "evidence": [
                    derived["items"][identity].model_dump(mode="json") for identity in cited
                ],
            }
            if _json_size(report) <= MAX_RESULT_BYTES and _json_size(result) <= MAX_BASELINE_BYTES:
                return result
            ids.pop()
        raise ValueError("Mandatory baseline exceeds byte limit")
    except (KeyError, TypeError, IndexError, StopIteration, OverflowError) as exc:
        raise ValueError("Invalid saved security evidence") from exc
