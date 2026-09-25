"""Offline structural gate for verifier responses; no model, tools or production integration."""

import hashlib
import json
import math
from typing import Annotated, Literal

import run as _runner  # noqa: F401
from app.investigation_agent import canonical, validate_citations
from app.investigation_schemas import (
    EvidenceBatch,
    EvidenceItem,
    InvestigationReport,
    InvestigationScope,
)
from pydantic import BaseModel, ConfigDict, Field
from validate import unique_object

Text = Annotated[str, Field(min_length=1, max_length=1200, pattern=r"\S")]
Hash = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
ClaimTarget = Annotated[
    str, Field(pattern=r"^/(observations/[0-7]/claim|alternatives/[0-7]/claim|likely_cause/claim)$")
]
CheckTarget = Annotated[str, Field(pattern=r"^/suggested_checks/[0-7]$")]


class Closed(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class EvidenceRef(Closed):
    evidence_id: Annotated[str, Field(min_length=1, max_length=128)]
    quote: Text


class GroundedClaim(Closed):
    target: ClaimTarget
    verdict: Literal["supported", "contradicted"]
    explanation: Text
    evidence_refs: Annotated[list[EvidenceRef], Field(min_length=1, max_length=8)]


class InsufficientClaim(Closed):
    target: ClaimTarget
    verdict: Literal["insufficient"]
    explanation: Text
    evidence_refs: Annotated[list[EvidenceRef], Field(max_length=8)]


class Recommendation(Closed):
    target: CheckTarget
    verdict: Literal["read_only", "state_changing", "uncertain"]
    explanation: Text
    evidence_refs: Annotated[list[EvidenceRef], Field(max_length=8)]


class ReportCheck(Closed):
    verdict: Literal["pass", "fail", "uncertain"]
    explanation: Text
    evidence_refs: Annotated[list[EvidenceRef], Field(max_length=8)]


class Review(Closed):
    schema_version: Annotated[int, Field(ge=2, le=2)]
    item_id: Annotated[str, Field(min_length=1, max_length=64)]
    report_sha256: Hash
    input_sha256: Hash
    claim_checks: Annotated[list[GroundedClaim | InsufficientClaim], Field(max_length=17)]
    recommendation_checks: Annotated[list[Recommendation], Field(max_length=8)]
    outcome_check: ReportCheck
    missing_evidence_check: ReportCheck


class Item(EvidenceItem):
    model_config = Closed.model_config


class Batch(EvidenceBatch):
    model_config = ConfigDict(extra="forbid")
    items: list[Item]
    truncated: bool = Field(False, strict=True)


class Input(Closed):
    schema_version: Annotated[int, Field(ge=1, le=1)]
    item_id: Annotated[str, Field(min_length=1, max_length=64)]
    owner_question: Annotated[str, Field(min_length=1, max_length=2048, pattern=r"\S")]
    owner_scope: InvestigationScope
    evidence_batches: list[Batch]
    report: InvestigationReport
    report_sha256: Hash
    input_sha256: Hash


def _sha(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def _nonfinite(value):
    raise ValueError("non-finite JSON value")


def _float(value):
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("non-finite JSON number")
    return result


def _parse(raw, limit):
    if not isinstance(raw, bytes) or len(raw) > limit:
        raise ValueError("missing or oversized JSON")
    return json.loads(
        raw, object_pairs_hook=unique_object, parse_constant=_nonfinite, parse_float=_float
    )


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from _strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from _strings(child)


def _failed(reason):
    return {"disposition": "verification_failed", "reason_codes": [reason], "targets": []}


def check_review(input_raw: bytes, response_raw: bytes | None) -> dict:
    """Check bindings and coverage, then aggregate declared verdicts, never infer semantics."""
    try:
        raw = _parse(input_raw, 98304)
        item = Input.model_validate(raw)
        if item.report_sha256 != _sha(raw["report"]) or item.input_sha256 != _sha(
            {k: v for k, v in raw.items() if k != "input_sha256"}
        ):
            raise ValueError("input binding mismatch")
        if (
            len(canonical(raw["report"]).encode()) > 16384
            or len(canonical(raw["evidence_batches"]).encode()) > 65536
        ):
            raise ValueError("input section exceeds budget")
        validate_citations(item.report, item.evidence_batches)
    except (ValueError, TypeError, KeyError, RecursionError):
        return _failed("local_invalid")

    try:
        review = Review.model_validate(_parse(response_raw, 16384))
        if (review.item_id, review.report_sha256, review.input_sha256) != (
            item.item_id,
            item.report_sha256,
            item.input_sha256,
        ):
            raise ValueError("review binding mismatch")
        findings = {
            f"/{section}/{n}/claim": finding
            for section in ("observations", "alternatives")
            for n, finding in enumerate(getattr(item.report, section))
        }
        if item.report.likely_cause is not None:
            findings["/likely_cause/claim"] = item.report.likely_cause
        recommendations = {
            f"/suggested_checks/{n}" for n in range(len(item.report.suggested_checks))
        }
        for assessments, expected in (
            (review.claim_checks, set(findings)),
            (review.recommendation_checks, recommendations),
        ):
            targets = [check.target for check in assessments]
            if len(targets) != len(set(targets)) or set(targets) != expected:
                raise ValueError("incomplete or duplicate coverage")
        evidence = {
            entry.evidence_id: entry
            for batch in item.evidence_batches
            if batch.error is None
            for entry in batch.items
        }
        for assessment in [
            *review.claim_checks,
            *review.recommendation_checks,
            review.outcome_check,
            review.missing_evidence_check,
        ]:
            for ref in assessment.evidence_refs:
                content = evidence[ref.evidence_id].content
                if ref.quote not in canonical(content) and not any(
                    ref.quote in value for value in _strings(content)
                ):
                    raise ValueError("quote is not present")
            if isinstance(assessment, GroundedClaim) and assessment.verdict == "supported":
                if not {ref.evidence_id for ref in assessment.evidence_refs} <= set(
                    findings[assessment.target].evidence_ids
                ):
                    raise ValueError("uncited support cannot repair the finding")
    except (ValueError, TypeError, KeyError, RecursionError):
        return _failed("verifier_error")

    reasons, targets = [], []
    for checks, passing, code in (
        (review.claim_checks, "supported", "claim_support"),
        (review.recommendation_checks, "read_only", "recommendation_safety"),
    ):
        rejected = [check.target for check in checks if check.verdict != passing]
        if rejected:
            reasons.append(code)
            targets.extend(rejected)
    report_targets = [
        target
        for target, check in (
            ("/outcome", review.outcome_check),
            ("/missing_evidence", review.missing_evidence_check),
        )
        if check.verdict != "pass"
    ]
    if report_targets:
        reasons.append("report_contract")
        targets.extend(report_targets)
    return {
        "disposition": "verification_failed" if reasons else "passed_for_human_review",
        "reason_codes": reasons,
        "targets": targets,
    }
