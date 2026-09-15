from app.features import keyword_count, prepare_message


def test_keyword_count_is_case_insensitive():
    assert keyword_count("Connection REFUSED, request Failed") == 2


def test_prepare_is_deterministic():
    message = "ciod: Error loading /home/yates/torus-latency.rts: No such file"
    assert prepare_message(message) == prepare_message(message)


def test_prepare_lowercases():
    assert prepare_message("DATA TLB Error Interrupt") == "data tlb error interrupt"


def test_prepare_keeps_the_path_intact():
    """The path is signal, not noise: templating it away cost held-out ROC-AUC."""
    prepared = prepare_message("ciod: Error loading /bgl/apps/SWL/mb_4_1/allreduce.rts")
    assert "/bgl/apps/swl/mb_4_1/allreduce.rts" in prepared


def test_prepare_keeps_addresses_and_numbers():
    prepared = prepare_message("CioStream socket to 172.16.96.116:33399 reason 1004")
    assert "172.16.96.116:33399" in prepared
    assert "1004" in prepared
