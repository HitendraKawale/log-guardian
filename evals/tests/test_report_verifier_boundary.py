"""Exercise deterministic verifier rejection paths without asking a model for judgments."""

import copy
import hashlib
import importlib
import json
from pathlib import Path

import pytest

PACKET = Path(__file__).resolve().parents[1] / "report-verifier"


def boundary():
    assert (PACKET.parent / "report_verifier_boundary.py").exists(), "offline boundary missing"
    return importlib.import_module("report_verifier_boundary")


def encode(value):
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()


def item():
    return json.loads((PACKET / "inputs.jsonl").read_text().splitlines()[0])


def response(data):
    evidence = {
        i["evidence_id"]: i
        for b in data["evidence_batches"]
        if b["error"] is None
        for i in b["items"]
    }
    findings = [
        (f"/{section}/{n}/claim", f)
        for section in ("observations", "alternatives")
        for n, f in enumerate(data["report"][section])
    ]
    if data["report"]["likely_cause"] is not None:
        findings.append(("/likely_cause/claim", data["report"]["likely_cause"]))
    result = {k: data[k] for k in ("item_id", "report_sha256", "input_sha256")}
    result.update(
        schema_version=2,
        claim_checks=[
            {
                "target": target,
                "verdict": "supported",
                "explanation": "Scripted structural check, not a semantic assessment.",
                "evidence_refs": [
                    {
                        "evidence_id": f["evidence_ids"][0],
                        "quote": evidence[f["evidence_ids"][0]]["content"]["message"],
                    }
                ],
            }
            for target, f in findings
        ],
        recommendation_checks=[
            {
                "target": f"/suggested_checks/{n}",
                "verdict": "read_only",
                "explanation": "Scripted.",
                "evidence_refs": [],
            }
            for n in range(len(data["report"]["suggested_checks"]))
        ],
        outcome_check={"verdict": "pass", "explanation": "Scripted.", "evidence_refs": []},
        missing_evidence_check={"verdict": "pass", "explanation": "Scripted.", "evidence_refs": []},
    )
    return result


def test_original_counterexample_is_rejected_for_missing_references():
    b = boundary()
    data = json.loads((PACKET / "inputs.jsonl").read_text().splitlines()[1])
    review = json.loads(
        (PACKET.parent / "report-verifier-review/empty-evidence-response.json").read_bytes()
    )
    review["schema_version"] = 2
    with pytest.raises(ValueError) as failure:
        b.Review.model_validate(review)
    assert any(error["type"] == "too_short" for error in failure.value.errors())
    assert b.check_review(encode(data), encode(review))["reason_codes"] == ["verifier_error"]


def test_empty_references_cannot_approve_claims():
    b = boundary()
    data = item()
    review = response(data)
    for claim in review["claim_checks"]:
        claim["evidence_refs"] = []
    assert b.check_review(encode(data), encode(review))["reason_codes"] == ["verifier_error"]


@pytest.mark.parametrize(
    "failure",
    [
        "missing",
        "duplicate",
        "extra",
        "hash",
        "input_hash",
        "item_id",
        "unknown_id",
        "fake_quote",
        "uncited_support",
        "unknown_field",
        "empty_explanation",
        "bad_version",
        "oversized",
        "duplicate_json",
        "nan",
        "absent",
    ],
)
def test_malformed_or_unbound_reviews_fail_closed(failure):
    b = boundary()
    data = item()
    review = response(data)
    if failure == "missing":
        review["claim_checks"].pop()
    elif failure == "duplicate":
        review["claim_checks"].append(copy.deepcopy(review["claim_checks"][0]))
    elif failure == "extra":
        review["recommendation_checks"].append(
            {
                "target": "/suggested_checks/7",
                "verdict": "read_only",
                "explanation": "Scripted.",
                "evidence_refs": [],
            }
        )
    elif failure in {"hash", "input_hash", "item_id"}:
        review[
            {"hash": "report_sha256", "input_hash": "input_sha256", "item_id": "item_id"}[failure]
        ] = "0" * 64
    elif failure == "unknown_id":
        review["claim_checks"][0]["evidence_refs"][0]["evidence_id"] = "unknown:1"
    elif failure == "fake_quote":
        review["claim_checks"][0]["evidence_refs"][0]["quote"] = "not in the original evidence"
    elif failure == "uncited_support":
        cited = set(data["report"]["observations"][0]["evidence_ids"])
        other = next(
            i
            for batch in data["evidence_batches"]
            for i in batch["items"]
            if i["evidence_id"] not in cited
        )
        review["claim_checks"][0]["evidence_refs"] = [
            {"evidence_id": other["evidence_id"], "quote": other["content"]["message"]}
        ]
    elif failure == "unknown_field":
        review["accept"] = True
    elif failure == "empty_explanation":
        review["claim_checks"][0]["explanation"] = " "
    elif failure == "bad_version":
        review["schema_version"] = True
    raw = encode(review)
    if failure == "oversized":
        raw += b" " * 16384
    elif failure == "duplicate_json":
        raw = b'{"schema_version":1,' + raw[1:]
    elif failure == "nan":
        raw = raw.replace(b'"schema_version":2', b'"schema_version":NaN')
    elif failure == "absent":
        raw = None
    assert b.check_review(encode(data), raw)["reason_codes"] == ["verifier_error"]


@pytest.mark.parametrize(
    "verdict,reason",
    [
        ("contradicted", "claim_support"),
        ("insufficient", "claim_support"),
        ("state_changing", "recommendation_safety"),
        ("uncertain", "recommendation_safety"),
        ("fail", "report_contract"),
    ],
)
def test_substantive_rejection_is_not_protocol_failure(verdict, reason):
    b = boundary()
    data = item()
    review = response(data)
    if reason == "claim_support":
        review["claim_checks"][0]["verdict"] = verdict
        if verdict == "insufficient":
            review["claim_checks"][0]["evidence_refs"] = []
    elif reason == "recommendation_safety":
        review["recommendation_checks"][0]["verdict"] = verdict
    else:
        review["outcome_check"]["verdict"] = verdict
    result = b.check_review(encode(data), encode(review))
    assert result["disposition"] == "verification_failed" and result["reason_codes"] == [reason]
    assert result["targets"]


def test_valid_structural_response_passes_without_claiming_semantic_correctness():
    b = boundary()
    data = item()
    assert b.check_review(encode(data), encode(response(data))) == {
        "disposition": "passed_for_human_review",
        "reason_codes": [],
        "targets": [],
    }


def test_existing_invalid_citation_stops_before_review():
    b = boundary()
    data = json.loads((PACKET / "inputs.jsonl").read_text().splitlines()[12])
    assert b.check_review(encode(data), None)["reason_codes"] == ["local_invalid"]


@pytest.mark.parametrize("verdict", ["supported", "contradicted"])
def test_grounded_verdicts_require_references_in_schema_and_validation(verdict):
    b = boundary()
    data = item()
    review = response(data)
    review["claim_checks"][0].update(verdict=verdict, evidence_refs=[])
    assert b.check_review(encode(data), encode(review))["reason_codes"] == ["verifier_error"]
    schema = b.Review.model_json_schema()
    assert schema["$defs"]["GroundedClaim"]["properties"]["evidence_refs"]["minItems"] == 1


@pytest.mark.parametrize(
    "failure", ["unknown_batch_field", "unknown_item_field", "overflow", "stale_hash", "oversized"]
)
def test_bad_inputs_fail_locally(failure):
    b = boundary()
    data = item()
    if failure == "unknown_batch_field":
        data["evidence_batches"][0]["accept"] = True
    elif failure == "unknown_item_field":
        data["evidence_batches"][0]["items"][0]["accept"] = True
    elif failure == "overflow":
        data["evidence_batches"][0]["items"][0]["content"]["numeric_probe"] = 1
    data["input_sha256"] = hashlib.sha256(
        encode({k: v for k, v in data.items() if k != "input_sha256"})
    ).hexdigest()
    raw = encode(data)
    if failure == "overflow":
        raw = raw.replace(b'"numeric_probe":1', b'"numeric_probe":1e999')
    elif failure == "stale_hash":
        data["owner_question"] = "Changed question"
        raw = encode(data)
    elif failure == "oversized":
        raw += b" " * 98304
    assert b.check_review(raw, None)["reason_codes"] == ["local_invalid"]


def test_v2_packet_schema_and_original_rows_are_preserved(tmp_path):
    b = boundary()
    folder = PACKET.parent / "report-verifier-v2"
    assert (
        json.loads((folder / "response.schema.json").read_bytes()) == b.Review.model_json_schema()
    )
    for name in ("inputs.jsonl", "labels.jsonl"):
        original = (PACKET / name).read_text().splitlines()
        updated = (folder / name).read_text().splitlines()
        assert updated[:14] == original and len(updated) == 18
    spec = importlib.util.spec_from_file_location("verifier_v2_builder", folder / "build_packet.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.build(tmp_path)
    for name in ("inputs.jsonl", "labels.jsonl", "manifest.json", "response.schema.json"):
        assert (tmp_path / name).read_bytes() == (folder / name).read_bytes()
    with pytest.raises(FileExistsError):
        module.build(tmp_path)


def test_verifier_attack_and_quoted_controls_remain_data():
    b = boundary()
    folder = PACKET.parent / "report-verifier-v2"
    data = [json.loads(line) for line in (folder / "inputs.jsonl").read_text().splitlines()]
    labels = [json.loads(line) for line in (folder / "labels.jsonl").read_text().splitlines()]
    assert data[14]["report"] == data[15]["report"]
    assert data[16]["evidence_batches"] == data[17]["evidence_batches"]
    for entry, label in zip(data[14:], labels[14:], strict=True):
        assert b.Input.model_validate(entry)
        assert entry["report_sha256"] == hashlib.sha256(encode(entry["report"])).hexdigest()
        assert (
            entry["input_sha256"]
            == hashlib.sha256(
                encode({k: v for k, v in entry.items() if k != "input_sha256"})
            ).hexdigest()
        )
        scripted = response(entry)
        for defect in label["required_defects"]:
            check = next(c for c in scripted["claim_checks"] if c["target"] == defect["target"])
            check.update(
                verdict="insufficient",
                evidence_refs=[],
                explanation="Scripted negative, not a model judgment.",
            )
        assert (
            b.check_review(encode(entry), encode(scripted))["disposition"]
            == label["expected_disposition"]
        )
    # The host validates structure, not entailment: an incorrect but well-formed verdict
    # with genuine quotations still passes. No prompt-injection resistance is proved.
    bad = data[14]
    assert (
        b.check_review(encode(bad), encode(response(bad)))["disposition"]
        == "passed_for_human_review"
    )


def test_rehashing_does_not_make_invalid_scope_valid():
    b = boundary()
    data = item()
    data["owner_scope"]["services"] = []
    data["input_sha256"] = hashlib.sha256(
        encode({k: v for k, v in data.items() if k != "input_sha256"})
    ).hexdigest()
    assert b.check_review(encode(data), None)["reason_codes"] == ["local_invalid"]
