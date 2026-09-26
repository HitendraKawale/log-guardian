"""Citation checks establish delivered membership, not semantic correctness."""

import pytest
from app.investigation_agent import validate_citations
from app.investigation_schemas import InvestigationReport

from tests.test_security_investigation import saved_source, tools_for


def supported(ref):
    finding = {"claim": "An observed authentication result.", "evidence_ids": [ref]}
    return InvestigationReport(
        observations=[finding],
        missing_evidence=[],
        alternatives=[],
        likely_cause=finding,
        outcome="supported",
        suggested_checks=[],
    )


async def test_security_events_are_observed_but_page_metadata_is_not(session_factory):
    batch = await tools_for(await saved_source(session_factory)).read_security_evidence()
    observed = next(i for i in batch.items if i.kind == "security_event")
    validate_citations(supported(observed.evidence_id), [batch])
    with pytest.raises(ValueError, match="Cause requires observed"):
        validate_citations(supported(batch.items[1].evidence_id), [batch])
    with pytest.raises(ValueError, match="Unknown citation"):
        validate_citations(supported("security-event:not-delivered"), [batch])


async def test_empty_case_does_not_support_a_cause(session_factory):
    from tests.security_case_helpers import SCOPE

    batch = await tools_for(
        await saved_source(session_factory, {"scope": SCOPE, "logs": {"edge": "", "auth": ""}})
    ).read_security_evidence()
    assert batch.items[0].content["total"] == 0
    assert "no_evidence" in batch.items[0].content["gaps"]
    assert batch.items[0].content["collection_complete"] is None
    with pytest.raises(ValueError, match="Cause requires observed"):
        validate_citations(supported(batch.items[0].evidence_id), [batch])
