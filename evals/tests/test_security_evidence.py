"""Exercise the offline command on real files without a provider or label access."""

import importlib.util
import json
import socket
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "evals/security-evidence"


def runner():
    spec = importlib.util.spec_from_file_location(
        "security_evidence_cli", ROOT / "evals/security_evidence.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def config():
    return {
        "scope": {
            "services": ["edge", "auth"],
            "start": "2026-09-01T10:00:00Z",
            "end": "2026-09-01T10:10:00Z",
        },
        "sources": [
            {
                "source_id": "gateway",
                "service": "edge",
                "event_kind": "gateway_request",
                "request_namespace": "shop",
            },
            {
                "source_id": "authentication",
                "service": "auth",
                "event_kind": "authentication_result",
                "request_namespace": "shop",
            },
        ],
    }


def files(tmp_path, gateway=b"", auth=b""):
    owner = tmp_path / "owner.json"
    owner.write_text(json.dumps(config()))
    edge = tmp_path / "gateway.jsonl"
    edge.write_bytes(gateway)
    authentication = tmp_path / "auth.jsonl"
    authentication.write_bytes(auth)
    return [
        "--config",
        str(owner),
        "--source",
        f"gateway={edge}",
        "--source",
        f"authentication={authentication}",
    ]


def test_real_command_is_offline_and_emits_machine_readable_unknown_completeness(
    tmp_path, capsys, monkeypatch
):
    def no_network(*args, **kwargs):
        pytest.fail("offline command attempted network access")

    monkeypatch.setattr(socket, "socket", no_network)
    assert runner().main(files(tmp_path)) == 0
    output = capsys.readouterr()
    result = json.loads(output.out)
    assert result["collection_complete"] is None
    assert result["timeline"] == []
    assert "no_evidence" in result["gaps"]
    assert not output.err


@pytest.mark.parametrize(
    "bad", [b'{"credential":"PRIVATE-PAYLOAD"}', b"x" * 1048577], ids=["private-field", "oversized"]
)
def test_rejected_input_has_nonzero_exit_and_no_partial_output_or_private_echo(
    tmp_path, capsys, bad
):
    assert runner().main(files(tmp_path, gateway=bad)) == 2
    output = capsys.readouterr()
    assert output.out == ""
    assert "PRIVATE-PAYLOAD" not in output.err
    assert "error:" in output.err


def test_duplicate_source_arguments_and_bad_config_fail_before_analysis(tmp_path, capsys):
    cli = runner()
    arguments = files(tmp_path)
    assert cli.main(arguments + ["--source", arguments[-1]]) == 2
    assert not capsys.readouterr().out
    (tmp_path / "owner.json").write_text('{"scope": {}, "scope": {}}')
    assert cli.main(arguments) == 2
    assert not capsys.readouterr().out


def test_missing_source_file_is_an_explicit_error(tmp_path, capsys):
    args = files(tmp_path)
    (tmp_path / "auth.jsonl").unlink()
    assert runner().main(args) == 2
    assert "input_read_failed" in capsys.readouterr().err


def test_fixture_observations_match_hand_authored_expectations_without_runtime_label_reads(
    tmp_path, capsys, monkeypatch
):
    # Removing namespace checks, deduplication or ambiguity handling breaks these outcomes.
    cases = [json.loads(line) for line in (DATA / "cases.jsonl").read_text().splitlines()]
    expected = {
        row["id"]: row
        for row in map(json.loads, (DATA / "expected.jsonl").read_text().splitlines())
    }
    cli = runner()
    real_open = Path.open

    def guarded_open(path, *args, **kwargs):
        if path.name == "expected.jsonl":
            pytest.fail("runtime read evaluator-only expectations")
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guarded_open)
    monkeypatch.setattr(socket, "socket", lambda *a, **k: pytest.fail("network access"))
    assert set(expected) == {case["id"] for case in cases}
    for case in cases:
        args = files(
            tmp_path,
            **{
                key: b"\n".join(json.dumps(row).encode() for row in case[key])
                for key in ("gateway", "auth")
            },
        )
        assert cli.main(args) == 0
        result = json.loads(capsys.readouterr().out)
        want = expected[case["id"]]
        assert len(result["timeline"]) == want["records"], case["id"]
        assert len(result["links"]) == want["links"], case["id"]
        assert len(result["ambiguous_groups"]) == want["ambiguous"], case["id"]
        assert result["duplicate_records"] == want["duplicates"], case["id"]
        assert result["sources"]["authentication"]["auth_outcomes"] == want["outcomes"], case["id"]
        assert (
            result["sources"]["authentication"]["distinct_account_refs"] == want["accounts"]
        ), case["id"]
        assert result["sources"]["gateway"]["distinct_client_addresses"] == want["addresses"], case[
            "id"
        ]
        assert set(want["gaps"]) <= set(result["gaps"]), case["id"]
        assert result["collection_complete"] is None
        ids = {tuple(row["evidence"]) for row in result["timeline"]}
        assert all(
            tuple(link[k]) in ids for link in result["links"] for k in ("gateway", "authentication")
        )
