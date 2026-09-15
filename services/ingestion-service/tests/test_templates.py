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
