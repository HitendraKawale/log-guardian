from datetime import UTC, datetime

from app.features import FEATURE_NAMES, featurize, keyword_count


def test_feature_vector_length_matches_names():
    vector = featurize("ERROR", "request failed", datetime.now(UTC))
    assert len(vector) == len(FEATURE_NAMES)


def test_keyword_count_is_case_insensitive():
    assert keyword_count("Connection REFUSED, request Failed") == 2


def test_level_ordinal_increases_with_severity():
    ts = datetime(2026, 1, 1, 9, tzinfo=UTC)
    debug = featurize("DEBUG", "x", ts)[0]
    critical = featurize("CRITICAL", "x", ts)[0]
    assert critical > debug


def test_unknown_level_defaults_to_info():
    ts = datetime(2026, 1, 1, 9, tzinfo=UTC)
    assert featurize("BOGUS", "x", ts)[0] == featurize("INFO", "x", ts)[0]
