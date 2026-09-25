"""Exercise offline preparation and scoring without treating scripted verdicts as model results."""

import importlib
import json
import socket
import subprocess
import sys
from pathlib import Path

import pytest
from test_report_verifier_boundary import encode, response

EVALS = Path(__file__).resolve().parents[1]


def runner():
    assert (EVALS / "report_verifier_eval.py").exists(), "offline runner missing"
    return importlib.import_module("report_verifier_eval")


def test_preparation_and_replay_never_read_labels_or_open_network(tmp_path, monkeypatch):
    module = runner()
    original = Path.open

    def guarded(path, *args, **kwargs):
        assert path.name not in {"labels.jsonl", "build_packet.py"}, "evaluator-only file read"
        return original(path, *args, **kwargs)

    def network(*args, **kwargs):
        pytest.fail("network access attempted")

    monkeypatch.setattr(Path, "open", guarded)
    monkeypatch.setattr(socket, "socket", network)
    prepared = tmp_path / "prepared"
    manifest = module.prepare(prepared)
    assert len(manifest["eligible"]) == 17 and manifest["local_invalid"] == ["v13"]
    assert not (prepared / "requests/v13.json").exists()
    request = json.loads((prepared / "requests/v01.json").read_bytes())
    source = json.loads((EVALS / "report-verifier-v2/inputs.jsonl").read_text().splitlines()[0])
    assert json.loads(request["messages"][1]["content"]) == source
    assert set(request) == {"messages", "response_schema", "max_output_tokens"}
    responses = tmp_path / "responses"
    responses.mkdir()
    result = module.replay(prepared, responses, tmp_path / "replayed")
    assert len(result["rows"]) == 18
    assert sum(r["result"]["reason_codes"] == ["verifier_error"] for r in result["rows"]) == 17


def test_score_keeps_failures_in_denominator_and_local_control_separate(tmp_path):
    module = runner()
    module.prepare(tmp_path / "prepared")
    responses = tmp_path / "responses"
    responses.mkdir()
    module.replay(tmp_path / "prepared", responses, tmp_path / "replayed")
    score = module.score(tmp_path / "replayed", tmp_path / "score")
    assert score["total"] == 18 and score["eligible"] == 17
    assert score["expected_acceptable"] == 8 and score["expected_semantic_negative"] == 9
    assert score["local_invalid_blocked"] == 1 and score["verifier_errors"] == 17
    assert score["acceptable_rejected"] == 8 and score["acceptable_substantive_rejected"] == 0
    assert score["negative_substantive_rejected"] == 0
    assert score["required_defects_rejected"] == 0
    assert score["known_bad_passed"] == 0


def test_scripted_passes_measure_missed_defects_not_accuracy(tmp_path):
    module = runner()
    module.prepare(tmp_path / "prepared")
    responses = tmp_path / "responses"
    responses.mkdir()
    inputs = [
        json.loads(line)
        for line in (EVALS / "report-verifier-v2/inputs.jsonl").read_text().splitlines()
    ]
    for data in (inputs[0], inputs[1]):
        (responses / f'{data["item_id"]}.json').write_bytes(encode(response(data)))
    module.replay(tmp_path / "prepared", responses, tmp_path / "replayed")
    score = module.score(tmp_path / "replayed", tmp_path / "score")
    assert score["acceptable_passed"] == 1 and score["known_bad_passed"] == 1
    assert score["verifier_errors"] == 15
    assert any(d["item_id"] == "v02" and d["status"] == "missed" for d in score["defects"])


def test_target_rejections_and_verdict_disagreements_are_distinct(tmp_path):
    module = runner()
    module.prepare(tmp_path / "prepared")
    responses = tmp_path / "responses"
    responses.mkdir()
    data = json.loads((EVALS / "report-verifier-v2/inputs.jsonl").read_text().splitlines()[1])
    review = response(data)
    cause = next(c for c in review["claim_checks"] if c["target"] == "/likely_cause/claim")
    cause["verdict"] = "contradicted"
    (responses / "v02.json").write_bytes(encode(review))
    module.replay(tmp_path / "prepared", responses, tmp_path / "replayed")
    score = module.score(tmp_path / "replayed", tmp_path / "score")
    assert score["negative_substantive_rejected"] == 1
    assert score["required_defects_rejected"] == 1
    assert score["exact_defect_verdict_matches"] == 0


@pytest.mark.parametrize("mode", ["malformed", "oversized", "wrong_binding"])
def test_response_errors_are_preserved_not_dropped(tmp_path, mode):
    module = runner()
    module.prepare(tmp_path / "prepared")
    responses = tmp_path / "responses"
    responses.mkdir()
    data = json.loads((EVALS / "report-verifier-v2/inputs.jsonl").read_text().splitlines()[0])
    review = response(data)
    review["input_sha256"] = "0" * 64
    raw = {"malformed": b"not JSON", "oversized": b"x" * 20000, "wrong_binding": encode(review)}[
        mode
    ]
    (responses / "v01.json").write_bytes(raw)
    result = module.replay(tmp_path / "prepared", responses, tmp_path / "replayed")
    row = result["rows"][0]
    assert row["result"]["reason_codes"] == ["verifier_error"]
    assert row["response_capture_complete"] is (mode != "oversized")
    assert (tmp_path / "replayed/responses/v01.json").read_bytes() == raw[:16385]
    assert (responses / "v01.json").read_bytes() == raw


def test_replay_rejects_unexpected_responses_and_preparation_tampering(tmp_path):
    module = runner()
    module.prepare(tmp_path / "prepared")
    responses = tmp_path / "responses"
    responses.mkdir()
    (responses / "v13.json").write_text("{}")
    with pytest.raises(ValueError, match="unexpected"):
        module.replay(tmp_path / "prepared", responses, tmp_path / "replayed")
    (responses / "v13.json").unlink()
    (tmp_path / "prepared/requests/v01.json").write_text("{}")
    with pytest.raises(ValueError, match="preparation"):
        module.replay(tmp_path / "prepared", responses, tmp_path / "replayed")
    assert not (tmp_path / "replayed").exists()


def test_score_recomputes_verdicts_even_if_manifest_is_rehashed(tmp_path):
    module = runner()
    module.prepare(tmp_path / "prepared")
    responses = tmp_path / "responses"
    responses.mkdir()
    result = module.replay(tmp_path / "prepared", responses, tmp_path / "replayed")
    result["rows"][0]["result"] = {
        "disposition": "passed_for_human_review",
        "reason_codes": [],
        "targets": [],
    }
    path = tmp_path / "replayed/results.json"
    path.write_bytes(encode(result))
    manifest_path = tmp_path / "replayed/manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    manifest["files"]["results.json"] = module.sha(path.read_bytes())
    manifest_path.write_bytes(encode(manifest))
    with pytest.raises(ValueError, match="integrity"):
        module.score(tmp_path / "replayed", tmp_path / "score")


def test_cli_prepare_replay_score_completes(tmp_path):
    runner()
    script = str(EVALS / "report_verifier_eval.py")
    (tmp_path / "responses").mkdir()
    commands = [
        ["prepare", "--output", str(tmp_path / "prepared")],
        [
            "replay",
            "--prepared",
            str(tmp_path / "prepared"),
            "--responses",
            str(tmp_path / "responses"),
            "--output",
            str(tmp_path / "replayed"),
        ],
        ["score", "--replayed", str(tmp_path / "replayed"), "--output", str(tmp_path / "score")],
    ]
    for args, count in zip(commands, [17, 18, 18], strict=True):
        result = subprocess.run(
            [sys.executable, script, *args], capture_output=True, text=True, timeout=15
        )
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout)["items"] == count


def test_cli_has_examples_and_no_live_mode():
    runner()
    script = str(EVALS / "report_verifier_eval.py")
    for command in ([], ["prepare"], ["replay"], ["score"]):
        result = subprocess.run(
            [sys.executable, script, *command, "--help"], capture_output=True, text=True, timeout=15
        )
        assert result.returncode == 0 and "Example:" in result.stdout
    result = subprocess.run(
        [sys.executable, script, "--live"], capture_output=True, text=True, timeout=15
    )
    assert result.returncode == 2


def test_overwrite_and_score_tampering_are_rejected(tmp_path):
    module = runner()
    module.prepare(tmp_path / "prepared")
    with pytest.raises(FileExistsError):
        module.prepare(tmp_path / "prepared")
    responses = tmp_path / "responses"
    responses.mkdir()
    module.replay(tmp_path / "prepared", responses, tmp_path / "replayed")
    with pytest.raises(FileExistsError):
        module.replay(tmp_path / "prepared", responses, tmp_path / "replayed")
    module.score(tmp_path / "replayed", tmp_path / "score")
    with pytest.raises(FileExistsError):
        module.score(tmp_path / "replayed", tmp_path / "score")
    (tmp_path / "replayed/results.json").write_text("{}")
    with pytest.raises(ValueError, match="integrity"):
        module.score(tmp_path / "replayed", tmp_path / "other-score")
