"""Behaviour of the label-free investigation trigger.

The point of these is that nothing here needs a label, a model, or a network
call -- so they are ordinary fast unit tests.
"""

from datetime import UTC, datetime, timedelta

import pytest
from app.investigation_schemas import InvestigationScope
from app.trigger import Candidate, InvestigationTrigger


def _at(minute: int = 0) -> datetime:
    return datetime(2026, 1, 1, 10, minute, tzinfo=UTC)


def _warm(trigger: InvestigationTrigger, n: int = 500) -> None:
    """Push the trigger past warmup with traffic that teaches it nothing new."""
    for i in range(n):
        trigger.consider("checkout", "INFO", "request completed", _at(0) + timedelta(seconds=i))


def test_nothing_fires_during_warmup():
    trigger = InvestigationTrigger(warmup_logs=10)
    for i in range(10):
        result = trigger.consider("checkout", "CRITICAL", f"failure mode {i}", _at())
        assert result is None, "cold start must not flag the first lines it ever sees"


def test_novel_template_is_a_candidate_once_warm():
    trigger = InvestigationTrigger(warmup_logs=5)
    _warm(trigger, 5)
    candidate = trigger.consider("checkout", "CRITICAL", "disk controller reset", _at())
    assert isinstance(candidate, Candidate)
    assert candidate.reason == "unseen-template"


def test_a_template_is_novel_exactly_once():
    trigger = InvestigationTrigger(warmup_logs=5)
    _warm(trigger, 5)
    first = trigger.consider("checkout", "CRITICAL", "disk controller reset", _at())
    second = trigger.consider("checkout", "CRITICAL", "disk controller reset", _at(1))
    assert first is not None
    assert second is None


def test_varying_identifiers_do_not_make_a_line_novel():
    """Without templating every request id would read as a new failure."""
    trigger = InvestigationTrigger(warmup_logs=5)
    _warm(trigger, 5)
    first = trigger.consider("checkout", "CRITICAL", "load failed for /srv/a/one.rts", _at())
    second = trigger.consider("checkout", "CRITICAL", "load failed for /srv/b/two.rts", _at(1))
    assert first is not None
    assert second is None, "same message family, different path"


def test_level_outside_the_pool_is_never_a_candidate():
    trigger = InvestigationTrigger(warmup_logs=5)
    _warm(trigger, 5)
    assert trigger.consider("checkout", "INFO", "a brand new INFO line", _at()) is None


def test_levels_outside_the_pool_still_teach_the_trigger():
    """A template first seen at INFO must not read as novel later at CRITICAL."""
    trigger = InvestigationTrigger(warmup_logs=5)
    _warm(trigger, 5)
    trigger.consider("checkout", "INFO", "connection pool exhausted", _at())
    later = trigger.consider("checkout", "CRITICAL", "connection pool exhausted", _at(1))
    assert later is None


def test_empty_level_pool_considers_every_severity():
    trigger = InvestigationTrigger(candidate_levels=(), warmup_logs=5)
    _warm(trigger, 5)
    assert trigger.consider("checkout", "INFO", "a brand new INFO line", _at()) is not None


def test_template_store_is_bounded_and_evicts_oldest():
    trigger = InvestigationTrigger(warmup_logs=0, max_templates=3)
    for i in range(4):
        trigger.consider("checkout", "CRITICAL", f"failure kind {chr(97 + i)}", _at())
    # "failure kind a" was evicted, so it reads as novel again.
    assert trigger.consider("checkout", "CRITICAL", "failure kind a", _at(1)) is not None


def test_candidate_scope_satisfies_the_investigation_contract():
    trigger = InvestigationTrigger(warmup_logs=5)
    _warm(trigger, 5)
    candidate = trigger.consider("checkout", "CRITICAL", "disk controller reset", _at(30))
    scope = InvestigationScope(**candidate.scope())
    assert scope.services == ("checkout",)
    assert timedelta(0) < scope.end - scope.start <= timedelta(hours=1)


def test_scope_window_is_configurable_and_still_valid():
    trigger = InvestigationTrigger(warmup_logs=5)
    _warm(trigger, 5)
    candidate = trigger.consider("checkout", "CRITICAL", "disk controller reset", _at(30))
    scope = InvestigationScope(**candidate.scope(window=timedelta(hours=1)))
    assert scope.end - scope.start == timedelta(hours=1)


def test_naive_timestamps_are_treated_as_utc():
    trigger = InvestigationTrigger(warmup_logs=5)
    _warm(trigger, 5)
    naive = datetime(2026, 1, 1, 10, 30)
    candidate = trigger.consider("checkout", "CRITICAL", "disk controller reset", naive)
    scope = InvestigationScope(**candidate.scope())
    assert scope.start.tzinfo is not None


@pytest.mark.parametrize("message", ["", "   ", "\n"])
def test_degenerate_messages_do_not_raise(message):
    trigger = InvestigationTrigger(warmup_logs=0)
    trigger.consider("checkout", "CRITICAL", message, _at())
