"""Fixed-clock detector contracts, independent of database and provider calls."""

import copy
from datetime import UTC, datetime, timedelta

import pytest
from app import trigger

START = datetime(2026, 9, 22, 10, tzinfo=UTC)


def advance(
    state=None, *, minute=0, second=0, level="ERROR", message="familiar timeout", age=0, **kwargs
):
    received = START + timedelta(minutes=minute, seconds=second)
    return trigger.advance_detector(
        state or {},
        level=level,
        message=message,
        timestamp=received - timedelta(seconds=age),
        received_at=received,
        **kwargs,
    )


def mature():
    state = {}
    for minute in range(5):
        for i in range(20):
            result = advance(state, minute=minute, second=i, level="ERROR" if i < 2 else "INFO")
            state = result.state
    return state


def test_learning_fifth_familiar_error_fires_without_novelty():
    state = {}
    for i in range(5):
        result = advance(state, second=i)
        state = result.state
        assert bool(result.signal) is (i == 4)
    assert result.signal["reasons"] == ["error-burst"]
    assert result.signal["learning"] is True
    assert result.signal["count"] == 5


def test_mature_two_per_minute_requires_six_not_five():
    state = mature()
    for i in range(6):
        result = advance(state, minute=5, second=i)
        state = result.state
        assert bool(result.signal) is (i == 5)
    assert result.signal["baseline_mean"] == 2
    assert result.signal["threshold"] == 6
    assert result.signal["learning"] is False


def test_steady_traffic_stays_below_threshold_and_services_learn_separately():
    state = mature()
    for minute in range(5, 20):
        for i in range(2):
            result = advance(state, minute=minute, second=i)
            state = result.state
            assert result.signal is None
    assert trigger.detector_readiness(state, START + timedelta(minutes=20))["baseline_ready"]
    fresh = advance()
    assert not trigger.detector_readiness(fresh.state, START)["baseline_ready"]
    assert fresh.state["observed"] == 1


def test_novelty_is_per_state_and_learns_info_templates():
    first = advance(level="INFO", warmup_logs=0)
    repeat = advance(first.state, second=1, warmup_logs=0)
    assert repeat.signal is None
    novel = advance(repeat.state, second=2, message="disk controller failed", warmup_logs=0)
    assert novel.signal["reasons"] == ["unseen-template"]
    assert advance(warmup_logs=0).signal["reasons"] == ["unseen-template"]


@pytest.mark.parametrize("age", [301, -61])
def test_late_and_future_logs_do_not_change_learning(age):
    state = mature()
    before = copy.deepcopy(state)
    result = advance(state, minute=5, age=age)
    assert result.excluded is True and result.signal is None
    assert result.state == before == state


@pytest.mark.parametrize("age", [300, -60])
def test_skew_boundaries_are_inclusive(age):
    assert advance(age=age).excluded is False


def test_bucket_boundary_does_not_merge_two_minutes():
    state = {}
    for second in range(56, 60):
        state = advance(state, second=second).state
    result = advance(state, minute=1)
    assert result.signal is None
    assert result.state["buckets"][str(int(START.timestamp()) + 60)][1] == 1


def test_quiet_boundary_and_info_do_not_keep_incident_alive():
    first = advance()
    info = advance(first.state, minute=9, level="INFO")
    assert info.state["last_eligible"] == first.state["last_eligible"]
    assert not advance(info.state, minute=9, second=59).quiet
    assert advance(info.state, minute=10).quiet


def test_long_gap_relearns_baseline_but_keeps_novelty_and_count():
    state = mature()
    result = advance(state, minute=20)
    assert result.state["observed"] == 101
    assert result.state["templates"] == state["templates"]
    assert len(result.state["buckets"]) == 1
    assert not trigger.detector_readiness(result.state, START + timedelta(minutes=20))[
        "baseline_ready"
    ]


def test_history_is_bounded_and_input_is_not_mutated():
    state = mature()
    before = copy.deepcopy(state)
    advance(state, minute=5)
    assert state == before
    for minute in range(5, 30):
        state = advance(
            state, minute=minute, level="INFO", message=f"different {'x' * minute}", max_templates=3
        ).state
    assert len(state["buckets"]) <= 16
    assert len(state["templates"]) == 3
    assert all(len(value) == 64 for value in state["templates"])


def test_empty_severity_pool_and_naive_utc_are_supported():
    result = trigger.advance_detector(
        {},
        level="INFO",
        message="hello",
        timestamp=START.replace(tzinfo=None),
        received_at=START,
        levels=(),
        warmup_logs=0,
    )
    assert result.eligible and result.signal is not None
