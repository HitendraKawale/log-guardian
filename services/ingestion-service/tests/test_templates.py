"""Templating behaviour.

Rejected for the supervised scorer (it lowered held-out ROC-AUC) and required by
the investigation trigger (novelty detection is meaningless without it). Both
callers depend on these collapses holding, so they are pinned here.
"""

from app.templates import normalize_message


def test_normalization_is_deterministic():
    message = "ciod: Error loading /home/yates/torus-latency.rts: No such file"
    assert normalize_message(message) == normalize_message(message)


def test_paths_collapse_one_message_family():
    """The dominant source of spurious distinct lines on BGL is the path."""
    a = normalize_message("ciod: Error loading /home/spelce1/HPCC/vnm.rts: invalid image")
    b = normalize_message("ciod: Error loading /p/gb2/stella/SPPM/sppm_DD: invalid image")
    assert a == b
    assert "<path>" in a


def test_socket_addresses_collapse():
    a = normalize_message("CioStream socket to 172.16.96.116:33399, Link has been severed")
    b = normalize_message("CioStream socket to 10.0.0.1:22, Link has been severed")
    assert a == b
    assert "<addr>" in a


def test_node_coordinates_collapse():
    a = normalize_message("machine check on R02-M1-N0-C:J12-U11")
    b = normalize_message("machine check on R24-M0-N4-C:J07-U01")
    assert a == b
    assert "<node>" in a


def test_numbers_and_hex_are_abstracted():
    assert normalize_message("rts: kernel terminated for reason 1004") == normalize_message(
        "rts: kernel terminated for reason 7"
    )
    assert "<hex>" in normalize_message("instruction address: 0x1a2b3c4d")


def test_distinct_message_families_stay_distinct():
    """Abstraction must not collapse a benign family onto a failure family."""
    benign = normalize_message("ciod: Error loading /a/b.rts: invalid or missing program image")
    failure = normalize_message("ciod: Error reading message prefix on CioStream socket to 1.2.3.4")
    assert benign != failure


def test_template_is_lowercased_and_whitespace_normalised():
    assert normalize_message("  DATA   TLB	error  interrupt ") == "data tlb error interrupt"


def test_uuids_collapse_to_one_template():
    """Seen in the dashboard: two logs of one family queued as two candidates.

    Only a uuid's first group is 8+ hex characters, so the generic hex rule
    leaves the middle groups intact and every request id looks like a new
    message family.
    """
    a = normalize_message("feedback row 7ec8d7e5-32b4-4d6c-81d9-f6ac0173e2b1 accepted")
    b = normalize_message("feedback row 4391c8a9-1f15-496b-8912-b8dd7f0c1a22 accepted")
    assert a == b
    assert "<uuid>" in a


def test_uppercase_uuids_collapse_too():
    a = normalize_message("trace 7EC8D7E5-32B4-4D6C-81D9-F6AC0173E2B1 failed")
    b = normalize_message("trace 4391c8a9-1f15-496b-8912-b8dd7f0c1a22 failed")
    assert a == b
