"""The Ambassador: the single accountable, autonomous owner of one external-system boundary."""
from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from .defaults import InMemoryJournal, QuarantineSanitizer, ScopePolicy, StaticCredentials
from .model import (
    ActionRequest,
    ActionResult,
    AmbassadorSpec,
    BoundaryError,
    Capability,
    EventTranslator,
    ExternalEvent,
    Intelligence,
    Notice,
    Outcome,
    Principal,
    Unknown,
)
from .ports import (
    Connector,
    CredentialBroker,
    Journal,
    PermanentError,
    Policy,
    Reasoner,
    Sanitizer,
    Subscriber,
    TransientError,
)


@dataclass(frozen=True)
class Resilience:
    max_attempts: int = 3
    backoff_seconds: float = 0.2  # doubled after each attempt
    breaker_threshold: int = 5  # consecutive failed tasks before the circuit opens
    breaker_cooldown_seconds: float = 30.0


@dataclass(frozen=True)
class Admission:
    """How much work the ambassador takes on. See the admission duty in docs/pattern.md."""

    max_waiting: int = 100  # tasks allowed to wait for a busy resource
    max_waiting_per_principal: int | None = None  # fair share; defaults to max_waiting
    on_busy: str = "wait"  # "wait" or "reject" a second task for a busy resource. Never interrupt.
    min_interval_seconds: float = 0.0  # pace: minimum gap between crossings, from the external quota
    retry_after_seconds: float = 1.0  # hint returned with a refusal


@dataclass(frozen=True)
class BoundaryContext:
    """What a capability handler is given. It is the only place the connector is reachable."""

    connector: Connector
    credentials: Mapping[str, Any]
    request: ActionRequest
    reasoner: Reasoner | None = None  # None unless intelligence is AUTONOMOUS


class Ambassador:
    def __init__(
        self,
        spec: AmbassadorSpec,
        connector: Connector,
        *,
        credentials: CredentialBroker | None = None,
        policy: Policy | None = None,
        journal: Journal | None = None,
        sanitizer: Sanitizer | None = None,
        reasoner: Reasoner | None = None,
        resilience: Resilience | None = None,
        admission: Admission | None = None,
    ) -> None:
        if spec.intelligence is not Intelligence.SCRIPTED and reasoner is None:
            raise ValueError(f"intelligence={spec.intelligence.value} requires a reasoner")
        self.spec = spec
        self._connector = connector
        self._credentials = credentials or StaticCredentials()
        self._policy = policy or ScopePolicy()
        self.journal = journal or InMemoryJournal()
        self._sanitizer = sanitizer or QuarantineSanitizer()
        self._reasoner = reasoner
        self._resilience = resilience or Resilience()
        self._admission = admission or Admission()
        self._capabilities: dict[str, Capability] = {}
        self._translators: dict[str, EventTranslator] = {}
        self._subscribers: list[Subscriber] = []
        self._seen_events: set[str] = set()
        self._locks: dict[str, asyncio.Lock] = {}
        self._waiting = 0
        self._waiting_by: dict[str, int] = defaultdict(int)
        self._next_slot = 0.0
        self._consecutive_failures = 0
        self._open_until = 0.0

    # ---- contract -----------------------------------------------------

    def offer(self, capability: Capability) -> "Ambassador":
        """Add a capability to the contract this ambassador offers the core system."""
        self._capabilities[capability.name] = capability
        return self

    def on_event(self, external_type: str, translator: EventTranslator) -> "Ambassador":
        """Register how one kind of external event becomes a notice."""
        self._translators[external_type] = translator
        return self

    @property
    def capabilities(self) -> list[Capability]:
        return list(self._capabilities.values())

    def describe(self) -> dict[str, Any]:
        """Protocol-neutral description. Bindings map this to an A2A agent card, an MCP tool list, etc."""
        s = self.spec
        return {
            "name": s.name,
            "boundary": s.boundary,
            "owner": s.owner,
            "description": s.description,
            "version": s.version,
            "intelligence": s.intelligence.value,
            "capabilities": [
                {
                    "name": c.name,
                    "description": c.description,
                    "input_schema": dict(c.input_schema),
                    "side_effect": c.side_effect,
                    "required_scopes": sorted(c.required_scopes),
                    "fallback_channel": c.fallback.channel if c.fallback else None,
                    "on_unknown": c.on_unknown.value,
                    "compensation": c.compensation.value,
                    "compensated_by": c.compensated_by,
                }
                for c in self.capabilities
            ],
            "notices": sorted(self._translators),
        }

    # ---- tasks: only the core system opens these -----------------------

    async def perform(self, request: ActionRequest) -> ActionResult:
        """Run one task to a final outcome. It never pauses and never asks back."""
        capability = self._capabilities.get(request.capability)
        if capability is None:
            return await self._refuse(request, "unknown_capability", f"'{request.capability}' is not offered by {self.spec.name}")
        reason = self._policy.refuse_reason(request, capability)
        if reason:
            return await self._refuse(request, "policy_refused", reason)

        replay = await self._replay(request, capability)
        if replay:
            return replay

        lock, refusal = await self._admit(request, capability)
        if refusal:
            return await self._refuse(request, refusal.code, refusal.message, refusal)
        try:
            # A duplicate that waited behind the original finds the recorded outcome here.
            replay = await self._replay(request, capability)
            if replay:
                return replay
            if time.monotonic() < self._open_until:
                error = BoundaryError("circuit_open", f"{self.spec.boundary} is marked unavailable", retryable=True)
                result = _unfinished(capability, error, attempts=0)
                await self.journal.record({**self._describe(request), "kind": "not_crossed", "outcome": result.outcome.value, "error": error.code})
                return result
            await self._pace()
            # The journal rule: record the intent before touching the external system.
            intent_id = await self.journal.begin(self._describe(request))
            result = await self._attempt(request, capability)
            await self._settle(intent_id, request, capability, result)
            return result
        finally:
            if lock is not None:
                lock.release()

    async def _replay(self, request: ActionRequest, capability: Capability) -> ActionResult | None:
        if not (capability.side_effect and request.idempotency_key):
            return None
        earlier = await self.journal.recall(request.idempotency_key)
        if earlier is None:
            return None
        await self.journal.record({**self._describe(request), "kind": "replayed", "outcome": earlier.outcome.value})
        return ActionResult(earlier.outcome, earlier.data, earlier.error, earlier.fallback, earlier.attempts, replayed=True)

    async def _admit(self, request: ActionRequest, capability: Capability) -> tuple[asyncio.Lock | None, BoundaryError | None]:
        """Admission: one task at a time per resource, a bounded wait, and a refusal when full."""
        if not capability.side_effect:
            return None, None
        key = capability.resource(request.payload) if capability.resource else "*"
        lock = self._locks.setdefault(key, asyncio.Lock())
        if not lock.locked():
            await lock.acquire()
            return lock, None
        a = self._admission
        who = request.principal.on_behalf_of or request.principal.subject
        if a.on_busy == "reject":
            return None, BoundaryError("resource_busy", f"another task is working on '{key}'", True, a.retry_after_seconds)
        share = a.max_waiting_per_principal or a.max_waiting
        if self._waiting >= a.max_waiting or self._waiting_by[who] >= share:
            return None, BoundaryError("admission_full", "too many tasks are waiting", True, a.retry_after_seconds)
        self._waiting += 1
        self._waiting_by[who] += 1
        try:
            await lock.acquire()
        finally:
            self._waiting -= 1
            self._waiting_by[who] -= 1
        return lock, None

    async def _pace(self) -> None:
        gap = self._admission.min_interval_seconds
        if gap <= 0:
            return
        now = time.monotonic()
        wait = self._next_slot - now
        self._next_slot = max(now, self._next_slot) + gap
        if wait > 0:
            await asyncio.sleep(wait)

    async def _context(self, request: ActionRequest, capability: Capability) -> BoundaryContext:
        creds = await self._credentials.credentials_for(request.principal, capability)
        reasoner = self._reasoner if self.spec.intelligence is Intelligence.AUTONOMOUS else None
        return BoundaryContext(self._connector, creds, request, reasoner)

    async def _attempt(self, request: ActionRequest, capability: Capability) -> ActionResult:
        r = self._resilience
        ctx = await self._context(request, capability)
        attempts, error = 0, BoundaryError("unknown", "no attempt made")
        while attempts < r.max_attempts:
            attempts += 1
            try:
                raw = await capability.handler(ctx, request.payload)
                self._consecutive_failures = 0
                return ActionResult(Outcome.SUCCEEDED, self._sanitizer.clean(raw), attempts=attempts)
            except TransientError as exc:
                error = BoundaryError("external_unavailable", str(exc), retryable=True)
            except PermanentError as exc:
                error = BoundaryError(exc.code, str(exc), retryable=False)

            action = "retry" if error.retryable else "fail"
            if self._reasoner is not None:  # assisted and autonomous: ask for a second opinion
                action = (await self._reasoner.advise(request, error, attempts)).action
            if action != "retry":
                if action == "fail":
                    self._note_failure()
                    return ActionResult(Outcome.FAILED, error=error, attempts=attempts)
                break  # "fallback"
            if attempts < r.max_attempts:
                await asyncio.sleep(r.backoff_seconds * 2 ** (attempts - 1))
        self._note_failure()
        return _unfinished(capability, error, attempts)

    def _note_failure(self) -> None:
        self._consecutive_failures += 1
        if self._consecutive_failures >= self._resilience.breaker_threshold:
            self._open_until = time.monotonic() + self._resilience.breaker_cooldown_seconds

    async def _settle(self, intent_id: str, request: ActionRequest, capability: Capability | None, result: ActionResult, reconciled: bool = False) -> None:
        await self.journal.finish(
            intent_id,
            {
                "capability": request.capability,
                "outcome": result.outcome.value,
                "error": result.error.code if result.error else None,
                "attempts": result.attempts,
                "reconciled": reconciled,
            },
        )
        if capability and capability.side_effect and request.idempotency_key and result.outcome is Outcome.SUCCEEDED:
            await self.journal.remember(request.idempotency_key, result)

    async def _refuse(self, request: ActionRequest, code: str, message: str, error: BoundaryError | None = None) -> ActionResult:
        error = error or BoundaryError(code, message)
        await self.journal.record({**self._describe(request), "kind": "refused", "outcome": Outcome.REJECTED.value, "error": code})
        return ActionResult(Outcome.REJECTED, error=error)

    def _describe(self, request: ActionRequest) -> dict[str, Any]:
        return {
            "ambassador": self.spec.name,
            "boundary": self.spec.boundary,
            "owner": self.spec.owner,
            "capability": request.capability,
            "payload": dict(request.payload),
            "subject": request.principal.subject,
            "on_behalf_of": request.principal.on_behalf_of,
            "scopes": sorted(request.principal.scopes),
            "idempotency_key": request.idempotency_key,
            "correlation_id": request.correlation_id,
        }

    # ---- recovery: reconcile actions whose outcome was never recorded ---

    async def reconcile(self) -> list[ActionResult]:
        """Resolve every intent that has no outcome. Call this on start-up, before taking new tasks."""
        results: list[ActionResult] = []
        for intent in await self.journal.unfinished():
            request = ActionRequest(
                intent["capability"],
                intent["payload"],
                Principal(intent["subject"], intent.get("on_behalf_of"), frozenset(intent.get("scopes", ()))),
                intent.get("idempotency_key"),
                intent.get("correlation_id"),
            )
            capability = self._capabilities.get(request.capability)
            unknown = BoundaryError("outcome_unknown", "the action may or may not have reached the external system")
            if capability is None or capability.on_unknown is Unknown.STOP:
                result = ActionResult(Outcome.FAILED, error=unknown)
            elif capability.on_unknown is Unknown.RESEND:
                result = await self._attempt(request, capability)
            else:  # VERIFY
                try:
                    found = await capability.verify(await self._context(request, capability), request.payload)  # type: ignore[misc]
                except TransientError:
                    continue  # cannot tell yet; leave the intent open and try again later
                if found is None:
                    result = ActionResult(Outcome.FAILED, error=BoundaryError("not_received", "the external system has no record of the action", retryable=True))
                else:
                    result = ActionResult(Outcome.SUCCEEDED, self._sanitizer.clean(found), attempts=1)
            await self._settle(intent["intent_id"], request, capability, result, reconciled=True)
            results.append(result)
        return results

    # ---- notices: delivered only on a subscription the core opened ------

    def subscribe(self, subscriber: Subscriber) -> Callable[[], None]:
        """Open a subscription. Returns a function that closes it."""
        self._subscribers.append(subscriber)
        return lambda: self._subscribers.remove(subscriber) if subscriber in self._subscribers else None

    async def receive(self, event: ExternalEvent) -> Notice | None:
        """Translate and quarantine an external event, then notify subscribers.

        Returns the notice if it was delivered, otherwise None. With no subscriber the event is
        recorded and not held: keeping undelivered events is the messaging layer's job.
        """
        entry = {"kind": "event", "ambassador": self.spec.name, "boundary": self.spec.boundary, "type": event.type, "event_id": event.event_id}
        if event.event_id and event.event_id in self._seen_events:
            await self.journal.record({**entry, "outcome": "duplicate"})
            return None
        translator = self._translators.get(event.type)
        if translator is None:
            await self.journal.record({**entry, "outcome": "dropped", "error": "unknown_event"})
            return None
        translated = translator(event)
        if translated is None:
            await self.journal.record({**entry, "outcome": "dropped", "error": "not_relevant"})
            return None
        if event.event_id:
            self._seen_events.add(event.event_id)
        notice = Notice(translated.type, self._sanitizer.clean(translated.payload), self.spec.boundary, event.event_id)
        if not self._subscribers:
            await self.journal.record({**entry, "outcome": "recorded_no_subscriber", "notice_type": notice.type})
            return None
        for subscriber in list(self._subscribers):
            await subscriber.notify(notice)
        await self.journal.record({**entry, "outcome": "delivered", "notice_type": notice.type})
        return notice

    async def healthy(self) -> bool:
        return time.monotonic() >= self._open_until and await self._connector.healthy()


def _unfinished(capability: Capability, error: BoundaryError, attempts: int) -> ActionResult:
    if capability.fallback is not None:
        return ActionResult(Outcome.DEFERRED, error=error, fallback=capability.fallback, attempts=attempts)
    return ActionResult(Outcome.FAILED, error=error, attempts=attempts)
