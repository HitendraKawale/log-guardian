"""Check verifier packet structure and provenance without performing semantic judgments."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import investigator_pilot  # noqa: F401
import pytest
from app.investigation_agent import canonical, validate_citations
from app.investigation_schemas import EvidenceBatch, InvestigationReport, InvestigationScope
from validate import unique_object

ROOT = Path(__file__).resolve().parents[2]
PACKET = ROOT / "evals/report-verifier"


def sha(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def rows(name):
    return [
        json.loads(line, object_pairs_hook=unique_object)
        for line in (PACKET / name).read_text().splitlines()
    ]


def test_packet_hashes_and_source_files():
    assert (PACKET / "manifest.json").exists(), "verifier packet not built"
    manifest = json.loads((PACKET / "manifest.json").read_bytes())
    for name, digest in manifest["files"].items():
        assert hashlib.sha256((PACKET / name).read_bytes()).hexdigest() == digest
    for name, digest in manifest["source_files"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest
    inputs, labels = rows("inputs.jsonl"), rows("labels.jsonl")
    assert len(inputs) == len(labels) == 14
    assert [row["item_id"] for row in inputs] == [f"v{n:02}" for n in range(1, 15)]
    assert {row["item_id"] for row in inputs} == {row["item_id"] for row in labels}
    assert sum(row["expected_disposition"] == "passed_for_human_review" for row in labels) == 7
    assert sum(row["gate"] == "local_invalid" for row in labels) == 1


@pytest.mark.parametrize("index", range(14))
def test_report_binding_scope_and_local_gate(index):
    assert (PACKET / "inputs.jsonl").exists(), "verifier inputs not built"
    item, label = rows("inputs.jsonl")[index], rows("labels.jsonl")[index]
    assert set(item) == {
        "schema_version",
        "item_id",
        "owner_question",
        "owner_scope",
        "evidence_batches",
        "report",
        "report_sha256",
        "input_sha256",
    }
    assert item["schema_version"] == 1
    assert item["report_sha256"] == sha(item["report"])
    assert item["input_sha256"] == sha({k: v for k, v in item.items() if k != "input_sha256"})
    assert label["input_sha256"] == item["input_sha256"]
    InvestigationScope.model_validate(item["owner_scope"])
    assert len(item["owner_question"]) <= 2048
    assert len(canonical(item["report"]).encode()) <= 16384
    assert len(canonical(item["evidence_batches"]).encode()) <= 65536
    batches = [EvidenceBatch.model_validate(batch) for batch in item["evidence_batches"]]
    report = InvestigationReport.model_validate(item["report"])
    if label["gate"] == "local_invalid":
        with pytest.raises(ValueError, match="Unknown citation"):
            validate_citations(report, batches)
    else:
        validate_citations(report, batches)
    for defect in label["required_defects"]:
        value = item["report"]
        for part in defect["target"].strip("/").split("/"):
            value = value[int(part)] if isinstance(value, list) else value[part]
        assert isinstance(value, str) and value
    if label["expected_disposition"] == "passed_for_human_review":
        assert not label["required_defects"]
    else:
        assert label["required_defects"]


def test_inputs_match_delivered_evidence_and_declared_report_sources():
    manifest = json.loads((PACKET / "manifest.json").read_bytes())
    inputs = {row["item_id"]: row for row in rows("inputs.jsonl")}
    for origin in manifest["items"]:
        item = inputs[origin["item_id"]]
        batches = []
        for name in origin["request_files"]:
            request = json.loads((ROOT / name).read_bytes())["request"]
            owner = json.loads(request["messages"][1]["content"])
            assert owner == {"question": item["owner_question"], "scope": item["owner_scope"]}
            for message in request["messages"]:
                if message["role"] == "tool":
                    batch = json.loads(message["content"])
                    if batch not in batches:
                        batches.append(batch)
        assert item["evidence_batches"] == batches
        source = json.loads((ROOT / origin["report_file"]).read_bytes())
        if origin["report_kind"] == "authored":
            report = source[origin["case_id"]]
        elif origin["report_kind"] == "raw_rejected":
            report = json.loads(source["response"]["choices"][0]["message"]["content"])
        else:
            report = source["report"]
        assert item["report"] == report


def test_packet_builder_reproduces_bytes_and_refuses_overwrite(tmp_path):
    command = [sys.executable, str(PACKET / "build_packet.py"), "--output", str(tmp_path)]
    completed = subprocess.run(command, capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr
    for name in ("inputs.jsonl", "labels.jsonl", "manifest.json"):
        assert (tmp_path / name).read_bytes() == (PACKET / name).read_bytes()
    again = subprocess.run(command, capture_output=True, text=True)
    assert again.returncode != 0 and "refusing to overwrite" in again.stderr
    assert (tmp_path / "inputs.jsonl").read_bytes() == (PACKET / "inputs.jsonl").read_bytes()


def test_response_contract_has_no_model_acceptance_switch():
    assert (PACKET / "response.schema.json").exists()
    schema = json.loads((PACKET / "response.schema.json").read_bytes())
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(schema["properties"])
    assert "accept" not in schema["properties"] and "disposition" not in schema["properties"]
    assert schema["$defs"]["claim"]["properties"]["verdict"]["enum"] == [
        "supported",
        "contradicted",
        "insufficient",
    ]
