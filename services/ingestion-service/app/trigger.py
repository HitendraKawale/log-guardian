"""Label-free selection of logs worth investigating.

The anomaly scorer answers "is this line anomalous?" and answers it well on
BGL -- F1 0.973 -- but it cannot be deployed to select candidates, for a reason
no amount of accuracy fixes: it needs labels. BGL is usable because LLNL
operators tagged 348,460 lines by hand. No deployment of this system arrives
with that, and the scorer is fitted on one machine's vocabulary besides.

So candidate selection is done here instead, with no labels and no model call:

**Severity gate.** Only levels in the configured pool are considered. On BGL
this alone gives 100% recall at 41% precision, because every operator-labelled
alert sits at CRITICAL -- an ``if`` statement that no model improved on.

**Template novelty.** A line whose template this service has not emitted before
is a candidate. Novelty is per service, matching the unique index the queue
uses: "checkout has started emitting a family it never emitted before" is worth
a look even when another service emits it routinely. Held out on BGL, "the template is new" scores F1 0.75 with no labels
at all, and 79.2% of held-out rows carrying an unseen template are real alerts.
That is well short of the supervised scorer and needs nothing to train.

The trigger learns as it goes: every line it sees is recorded, so a template is
novel exactly once. That makes it self-calibrating per deployment rather than
carrying BGL's vocabulary to a service that does not share it.

Two deliberate limits:

* It **selects**, it does not spend. A candidate is a suggestion that a human
  or an explicitly-budgeted worker may act on. Wiring this straight into the
  investigation worker would create an unbounded paid-execution path driven by
  log volume, which is exactly the property that makes log ingestion cheap and
  model calls expensive.
* Nothing here may fail or slow a write. ``persist_log`` calls it best-effort,
  the same contract as the AI client: if the trigger raises, the log is stored
  and the candidate is lost.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from .templates import normalize_message

# Severity pool. ERROR and above, because that is where application logs put
# their failures -- the demo sandbox emits ERROR and never CRITICAL, and a pool
# of ("CRITICAL",) leaves the trigger inert on it. BGL's own pool is
# CRITICAL-only (every operator-labelled alert sits there), which is a property
# of that machine's logging, not a default worth shipping. Deployments set
# TRIGGER_CANDIDATE_LEVELS; an empty pool considers every severity.
DEFAULT_CANDIDATE_LEVELS: tuple[str, ...] = ("ERROR", "CRITICAL")

# Lines observed before novelty is trusted. Without this every template is new
# and a cold start would flag the entire first minute of traffic.
DEFAULT_WARMUP_LOGS = 500

# (service, template) pairs retained. Bounded so a pathological stream cannot
# grow this without limit; the oldest pair is evicted first, so a long-quiet
# family can go novel again. That is a memory bound, not a claim that re-firing
# is desirable -- the queue's unique index absorbs the repeat.
DEFAULT_MAX_TEMPLATES = 20_000

# How much context an investigation of a candidate should carry. The scope
# contract caps a window at one hour, so this must stay comfortably inside it.
DEFAULT_WINDOW = timedelta(minutes=10)


@dataclass(frozen=True)
class Candidate:
    """A log worth investigating, with the scope an investigation would need."""

    service: str
    level: str
    message: str
    timestamp: datetime
    template: str
    reason: str

    def scope(self, window: timedelta = DEFAULT_WINDOW) -> dict:
        """Return an ``InvestigationScope``-shaped dict centred on the log.

        Built as a plain dict rather than the pydantic model so this module
        stays importable by offline measurement code that has no need for the
        investigation schemas.
        """
        at = self.timestamp
        if at.tzinfo is None:
            at = at.replace(tzinfo=UTC)
        half = window / 2
        return {
            "services": (self.service,),
            "start": (at - half).astimezone(UTC),
            "end": (at + half).astimezone(UTC),
        }


class InvestigationTrigger:
    """Stateful, label-free candidate selector. Not thread-safe by design.

    One instance per process. ``consider`` is cheap: a regex pass over the
    message and a dict lookup, no I/O and no model call.
    """

    def __init__(
        self,
        candidate_levels: tuple[str, ...] = DEFAULT_CANDIDATE_LEVELS,
        warmup_logs: int = DEFAULT_WARMUP_LOGS,
        max_templates: int = DEFAULT_MAX_TEMPLATES,
    ) -> None:
        self._levels = {level.upper() for level in candidate_levels} if candidate_levels else set()
        self._warmup_logs = warmup_logs
        self._max_templates = max_templates
        # Keyed by (service, template), ordered so eviction is oldest-first.
        self._seen: OrderedDict[tuple[str, str], None] = OrderedDict()
        self.observed = 0

    @property
    def warm(self) -> bool:
        return self.observed >= self._warmup_logs

    def consider(self, service: str, level: str, message: str, timestamp: datetime):
        """Record the log, and return a ``Candidate`` if it warrants one.

        Every line is recorded whether or not it is a candidate, including
        during warmup and including levels outside the pool -- otherwise a
        template first seen at INFO would read as novel when it later appears
        at CRITICAL.
        """
        template = normalize_message(message)
        key = (service, template)
        novel = key not in self._seen
        self._remember(key)
        self.observed += 1

        if not self.warm:
            return None
        if self._levels and level.upper() not in self._levels:
            return None
        if not novel:
            return None
        return Candidate(
            service=service,
            level=level,
            message=message,
            timestamp=timestamp,
            template=template,
            reason="unseen-template",
        )

    def _remember(self, key: tuple[str, str]) -> None:
        if key in self._seen:
            self._seen.move_to_end(key)
            return
        self._seen[key] = None
        if len(self._seen) > self._max_templates:
            self._seen.popitem(last=False)
