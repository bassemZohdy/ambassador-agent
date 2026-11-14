"""The Ambassador: the single accountable, autonomous owner of one external-system boundary."""
from __future__ import annotations

import asyncio
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field, replace
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
    LeaseLost,
    Leases,
    PermanentError,
    Policy,
    PrincipalVerifier,
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
class Leasing:
    """How replicas share the work, when more than one copy runs. See "More than one replica" in docs/pattern.md.

    A replica takes a lease on the resource before it touches it, keeps it alive while the task runs, and lets it go
    afterwards. A replica that dies stops renewing, and the lease lapses after `ttl_seconds`: that is how long a
    crashed copy's intent waits before another copy may settle it.
    """

    holder: str = field(default_factory=lambda: f"replica-{uuid.uuid4().hex[:8]}")  # which copy this is
    ttl_seconds: float = 10.0
    wait_seconds: float = 30.0  # how long a task waits for another copy to let go before it is refused as busy
    poll_seconds: float = 0.05


@dataclass(frozen=True)
class _Held:
    resource: str
    token: int
    beat: "asyncio.Task[None]"


@dataclass(frozen=True)
class BoundaryContext:
    """What a capability handler is given. It is the only place the connector is reachable."""

    connector: Connector
    credentials: Mapping[str, Any]
    request: ActionRequest
    reasoner: Reasoner | None = None  # None unless intelligence is AUTONOMOUS
    # Send this to the external system as its idempotency key or client reference. It stays the
    # same across retries, resends and recovery, which is what lets the other side deduplicate or be asked.
    operation_id: str = ""
    # With replicas: the fencing token of the lease this task runs under. Send it to the external system, which can
    # refuse a token older than one it has already seen. None when no lease is in use.
    fencing_token: int | None = None


class Ambassador:
    def __init__(
        self,
        spec: AmbassadorSpec,
        connector: Connector,
        *,
        credentials: CredentialBroker | None = None,
        policy: Policy | None = None,
        verifier: PrincipalVerifier | None = None,
        journal: Journal | None = None,
        sanitizer: Sanitizer | None = None,
        reasoner: Reasoner | None = None,
        resilience: Resilience | None = None,
        admission: Admission | None = None,
        leases: Leases | None = None,
        leasing: Leasing | None = None,
    ) -> None:
        if spec.intelligence is not Intelligence.SCRIPTED and reasoner is None:
            raise ValueError(f"intelligence={spec.intelligence.value} requires a reasoner")
        self.spec = spec
        self._connector = connector
        self._credentials = credentials or StaticCredentials()
        self._policy = policy or ScopePolicy()
        self._verifier = verifier  # None: the principal is taken as given (see docs/identity-and-trust.md)
        self.journal = journal or InMemoryJournal()
        self._sanitizer = sanitizer or QuarantineSanitizer()
        self._reasoner = reasoner
        self._resilience = resilience or Resilience()
        self._admission = admission or Admission()
        self._leases = leases  # None: this is the only copy, and the in-process locks are enough
        self._leasing = leasing or Leasing()
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
            "verifies_principal": self._verifier is not None,
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
                    "absence_is_final": c.absence_is_final,
                    "settle_after_seconds": c.settle_after_seconds,
                    "data_classification": c.data_classification,
                    "audit_retention_days": c.audit_retention_days,
                    "requires_approval": c.requires_approval,
                }
                for c in self.capabilities
            ],
            "notices": sorted(self._translators),
        }

    # ---- tasks: only the core system opens these -----------------------

    async def perform(self, request: ActionRequest) -> ActionResult:
        """Run one task to a final outcome. It never pauses and never asks back."""
        if self._verifier is not None:
            # Before anything else, so a caller that cannot prove who it acts for learns nothing about the contract.
            verified = await self._verifier.verify(request)
            if isinstance(verified, str):
                return await self._refuse(request, "principal_unverified", "the principal was not accepted", detail=verified)
            request = replace(request, principal=verified)  # scopes now come from the proof, not from the task
        capability = self._capabilities.get(request.capability)
        if capability is None:
            return await self._refuse(request, "unknown_capability", f"'{request.capability}' is not offered by {self.spec.name}")
        reason = self._policy.refuse_reason(request, capability)
        if reason:
            return await self._refuse(request, "policy_refused", reason)

        replay = await self._replay(request, capability)
        if replay:
            return replay
        operation_id = request.idempotency_key or f"op-{uuid.uuid4().hex}"

        lock, refusal = await self._admit(request, capability)
        if refusal:
            return await self._refuse(request, refusal.code, refusal.message, refusal)
        lease: _Held | None = None
        try:
            if self._leases is not None and lock is not None:
                # Between copies the in-process lock means nothing, so the resource is leased too. Everything below,
                # the check of the journal and the write that follows it, happens under the lease.
                lease = await self._hold((capability.resource(request.payload) if capability.resource else "") or "*", wait=self._admission.on_busy != "reject")
                if lease is None:
                    busy = BoundaryError("resource_busy", "another copy of this ambassador is working on the resource", True, self._admission.retry_after_seconds)
                    return await self._refuse(request, busy.code, busy.message, busy)
            # A duplicate that waited behind the original finds the recorded outcome here.
            replay = await self._replay(request, capability, pending=True)
            if replay:
                return replay
            held = await self._held_by(request, capability)
            if held:
                return await self._refuse(
                    request,
                    "resource_held",
                    f"an earlier action on this resource has an unknown outcome (operation {held}); its owner must settle it first",
                )
            if time.monotonic() < self._open_until:
                error = BoundaryError("circuit_open", f"{self.spec.boundary} is marked unavailable", retryable=True)
                result = _failed(capability, error, attempts=0, operation_id=operation_id)  # nothing was sent
                await self.journal.record({**self._describe(request, operation_id), "kind": "not_crossed", "outcome": result.outcome.value, "error": error.code})
                return result
            await self._pace()
            # The journal rule: record the intent before touching the external system.
            token = lease.token if lease else None
            try:
                intent_id = await self.journal.begin({**self._describe(request, operation_id), **({"fencing_token": token} if token is not None else {})})
            except LeaseLost:
                # The lease lapsed before the intent was written, so nothing was sent and another copy may have the resource.
                lost = BoundaryError("lease_lost", "this copy lost its lease on the resource before it began", True, self._admission.retry_after_seconds)
                return await self._refuse(request, lost.code, lost.message, lost)
            result = await self._attempt(request, capability, operation_id, token)
            try:
                await self._settle(intent_id, request, capability, result, fencing_token=token)
            except LeaseLost:
                # The lease lapsed while the task ran and another copy took the resource over, so recovery is its job now.
                # The result is real and is returned; the record of it is the other copy's to write.
                await self.journal.record({**self._describe(request, operation_id), "kind": "settled_elsewhere", "outcome": result.outcome.value})
            return result
        finally:
            if lease is not None:
                await self._drop(lease)
            if lock is not None:
                lock.release()

    async def _replay(self, request: ActionRequest, capability: Capability, pending: bool = False) -> ActionResult | None:
        """Answer a repeated task from the record, so the external system is not called again.

        Both a success and an unresolved unknown are remembered. `pending` also covers an intent that
        a crash left open and `reconcile` has not settled yet: it is held, never sent a second time.
        """
        if not (capability.side_effect and request.idempotency_key):
            return None
        earlier = await self.journal.recall(request.idempotency_key)
        if earlier is None and pending:
            for intent in await self.journal.unfinished():
                if intent.get("idempotency_key") == request.idempotency_key:
                    earlier = ActionResult(Outcome.UNKNOWN, error=_unknown_error(), operation_id=intent.get("operation_id"))
        if earlier is None:
            return None
        await self.journal.record({**self._describe(request, earlier.operation_id), "kind": "replayed", "outcome": earlier.outcome.value})
        return ActionResult(earlier.outcome, earlier.data, earlier.error, earlier.fallback, earlier.attempts, replayed=True, operation_id=earlier.operation_id)

    async def _held_by(self, request: ActionRequest, capability: Capability) -> str | None:
        """An open unknown outcome holds its resource, so a retry under a new key cannot cross the boundary.

        Only capabilities that declare a resource are held. Returns the operation id doing the holding.
        """
        if not (capability.side_effect and capability.resource):
            return None
        key = capability.resource(request.payload)
        for entry in [*await self.journal.unfinished(), *await self.journal.unresolved()]:
            if entry.get("ambassador") != self.spec.name or entry.get("resource") != key:
                continue
            if request.idempotency_key and entry.get("idempotency_key") == request.idempotency_key:
                continue  # the same task: answered from the record, not held
            return entry.get("operation_id")
        return None

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

    async def _hold(self, resource: str, *, wait: bool) -> _Held | None:
        """Take the lease on a resource, waiting for another copy to let go if allowed. None: it did not come free."""
        assert self._leases is not None
        lg = self._leasing
        deadline = time.monotonic() + (lg.wait_seconds if wait else 0.0)
        while True:
            token = await self._leases.acquire(resource, lg.holder, lg.ttl_seconds)
            if token is not None:
                return _Held(resource, token, asyncio.ensure_future(self._beat(resource, token)))
            if time.monotonic() >= deadline:
                return None
            await asyncio.sleep(lg.poll_seconds)

    async def _beat(self, resource: str, token: int) -> None:
        """Keep the lease alive while the task runs. A copy that dies stops here, and the lease lapses."""
        assert self._leases is not None
        lg = self._leasing
        while True:
            await asyncio.sleep(lg.ttl_seconds / 3)
            if not await self._leases.renew(resource, lg.holder, token, lg.ttl_seconds):
                return  # lost: the next write under this token is refused by the journal

    async def _drop(self, held: _Held) -> None:
        assert self._leases is not None
        held.beat.cancel()
        await self._leases.release(held.resource, self._leasing.holder, held.token)

    async def _context(self, request: ActionRequest, capability: Capability, operation_id: str, fencing_token: int | None = None) -> BoundaryContext:
        creds = await self._credentials.credentials_for(request.principal, capability)
        reasoner = self._reasoner if self.spec.intelligence is Intelligence.AUTONOMOUS else None
        return BoundaryContext(self._connector, creds, request, reasoner, operation_id, fencing_token)

    async def _attempt(self, request: ActionRequest, capability: Capability, operation_id: str, fencing_token: int | None = None) -> ActionResult:
        r = self._resilience
        ctx = await self._context(request, capability, operation_id, fencing_token)
        attempts, error = 0, BoundaryError("unknown", "no attempt made")
        unsettled = False  # an earlier attempt may have taken effect and that has not been ruled out
        while attempts < r.max_attempts:
            attempts += 1
            sent_at = time.monotonic()
            try:
                raw = await capability.handler(ctx, request.payload)
                self._consecutive_failures = 0
                return ActionResult(Outcome.SUCCEEDED, self._sanitizer.clean(raw), attempts=attempts, operation_id=operation_id)
            except TransientError as exc:
                error = BoundaryError("external_unavailable", str(exc), retryable=True)
                if capability.side_effect and exc.may_have_executed:
                    # A timeout is not a "no". Settle what happened before anything is retried or redirected.
                    settled, absent_proven = await self._settle_ambiguous(ctx, capability, request, error, attempts, sent_at)
                    if settled is not None:
                        return settled
                    unsettled = not absent_proven  # otherwise it is now safe to send again
            except PermanentError as exc:
                error = BoundaryError(exc.code, str(exc), retryable=False)

            action = "retry" if error.retryable else "fail"
            if self._reasoner is not None:  # assisted and autonomous: ask for a second opinion
                action = (await self._reasoner.advise(request, error, attempts)).action
            if action != "retry":
                if action == "fail":
                    self._note_failure()
                    return ActionResult(Outcome.FAILED, error=error, attempts=attempts, operation_id=operation_id)
                break  # "fallback"
            if attempts < r.max_attempts:
                await asyncio.sleep(r.backoff_seconds * 2 ** (attempts - 1))
        self._note_failure()
        if unsettled:
            # Out of attempts while an earlier one may still land. "Failed" would be a guess and a fallback a second booking.
            return ActionResult(Outcome.UNKNOWN, error=_unknown_error(error), attempts=attempts, operation_id=operation_id)
        return _failed(capability, error, attempts, operation_id)

    async def _settle_ambiguous(
        self, ctx: BoundaryContext, capability: Capability, request: ActionRequest, error: BoundaryError, attempts: int, sent_at: float
    ) -> tuple[ActionResult | None, bool]:
        """The action may have taken effect. Decide what is known, using only what the capability declared.

        Returns (result, absent_proven). A result is final. With none, it is safe to send the same operation
        id again, and absent_proven says whether the action is also proven never to have happened.
        """
        unknown = ActionResult(Outcome.UNKNOWN, error=_unknown_error(error), attempts=attempts, operation_id=ctx.operation_id)
        if capability.on_unknown is Unknown.RESEND:
            return None, False  # the external system ignores a repeated operation id, so sending again is safe
        if capability.on_unknown is Unknown.STOP or capability.verify is None:
            return unknown, False  # cannot be settled from here: no resend, no other channel
        wait = capability.settle_after_seconds - (time.monotonic() - sent_at)
        if wait > 0:
            await asyncio.sleep(wait)  # let a request still in flight land before believing "no record"
        try:
            found = await capability.verify(ctx, request.payload)
        except (TransientError, PermanentError):
            return unknown, False  # asked, and could not be told
        if found is None:
            return None, capability.absence_is_final
        return ActionResult(Outcome.SUCCEEDED, self._sanitizer.clean(found), attempts=attempts, operation_id=ctx.operation_id), True

    def _note_failure(self) -> None:
        self._consecutive_failures += 1
        if self._consecutive_failures >= self._resilience.breaker_threshold:
            self._open_until = time.monotonic() + self._resilience.breaker_cooldown_seconds

    async def _settle(
        self, intent_id: str, request: ActionRequest, capability: Capability | None, result: ActionResult, reconciled: bool = False, fencing_token: int | None = None
    ) -> None:
        # A success is remembered so a repeat is answered, not re-sent. So is an unknown, so a repeat is held
        # rather than sent a second time while the owner finds out what happened. The result is remembered
        # BEFORE the intent is closed: a crash between the two leaves an open intent that recovery settles,
        # never a closed intent whose result a repeat cannot find.
        if capability and capability.side_effect and request.idempotency_key and result.outcome in (Outcome.SUCCEEDED, Outcome.UNKNOWN):
            await self.journal.remember(request.idempotency_key, result)
        await self.journal.finish(
            intent_id,
            {
                "capability": request.capability,
                "outcome": result.outcome.value,
                "error": result.error.code if result.error else None,
                "attempts": result.attempts,
                "reconciled": reconciled,
                "operation_id": result.operation_id,
                **({"fencing_token": fencing_token} if fencing_token is not None else {}),
            },
        )

    async def _refuse(self, request: ActionRequest, code: str, message: str, error: BoundaryError | None = None, detail: str | None = None) -> ActionResult:
        error = error or BoundaryError(code, message)
        record = {**self._describe(request), "kind": "refused", "outcome": Outcome.REJECTED.value, "error": code}
        if detail:
            record["detail"] = detail  # why, for the owner. The caller is told only that it was not accepted
        await self.journal.record(record)
        return ActionResult(Outcome.REJECTED, error=error)

    def _describe(self, request: ActionRequest, operation_id: str | None = None) -> dict[str, Any]:
        capability = self._capabilities.get(request.capability)
        return {
            "operation_id": operation_id,
            "resource": capability.resource(request.payload) if capability and capability.resource else None,
            "ambassador": self.spec.name,
            "boundary": self.spec.boundary,
            "owner": self.spec.owner,
            "capability": request.capability,
            "payload": dict(request.payload),
            "caller": request.caller,
            "subject": request.principal.subject,
            "on_behalf_of": request.principal.on_behalf_of,
            "scopes": sorted(request.principal.scopes),
            "idempotency_key": request.idempotency_key,
            "correlation_id": request.correlation_id,
        }

    # ---- recovery: reconcile actions whose outcome was never recorded ---

    async def reconcile(self) -> list[ActionResult]:
        """Settle every intent that has no outcome. Call this on start-up, before taking new tasks.

        Each result is one of: succeeded (found, or resent safely), failed (confirmed not done, with the
        fallback if the capability has one), or unknown (it cannot be told from here; see `unresolved`).
        """
        results: list[ActionResult] = []
        for intent in await self.journal.unfinished():
            capability = self._capabilities.get(intent["capability"])
            held: _Held | None = None
            if self._leases is not None and (capability is None or capability.side_effect):
                # The claim on an open intent is the lease on its resource. While the copy that opened it is alive, it
                # holds the lease and this copy leaves the intent alone; once that copy has died the lease lapses.
                held = await self._hold(intent.get("resource") or "*", wait=False)
                if held is None:
                    continue
            try:
                result = await self._reconcile_one(intent, held.token if held else None)
            except LeaseLost:
                continue  # another copy settled it first
            finally:
                if held is not None:
                    await self._drop(held)
            if result is not None:
                results.append(result)
        return results

    async def _reconcile_one(self, intent: Mapping[str, Any], fencing_token: int | None) -> ActionResult | None:
        request = ActionRequest(
            intent["capability"],
            intent["payload"],
            Principal(intent["subject"], intent.get("on_behalf_of"), frozenset(intent.get("scopes", ()))),
            intent.get("idempotency_key"),
            intent.get("correlation_id"),
        )
        operation_id = intent["operation_id"]
        capability = self._capabilities.get(request.capability)
        if capability is None or capability.on_unknown is Unknown.STOP:
            # Nothing here can settle it: no lookup, no safe resend. It becomes an exception for the owner.
            result = ActionResult(Outcome.UNKNOWN, error=_unknown_error(), operation_id=operation_id)
        elif capability.on_unknown is Unknown.RESEND:
            result = await self._attempt(request, capability, operation_id, fencing_token)  # the external system ignores a repeated operation id
        else:  # VERIFY
            if time.time() - float(intent.get("at", 0)) < capability.settle_after_seconds:
                return None  # too soon to believe "no record": a request may still be in flight. Try again later
            try:
                found = await capability.verify(await self._context(request, capability, operation_id, fencing_token), request.payload)  # type: ignore[misc]
            except TransientError:
                return None  # cannot tell yet; leave the intent open and try again later
            if found is None and capability.absence_is_final:
                error = BoundaryError("not_received", "the external system has no record of the action and rejects late requests", retryable=True)
                result = _failed(capability, error, 0, operation_id)
            elif found is None:
                # No record is not proof: a late request could still land. Hold it for the owner, offer nothing.
                error = BoundaryError("not_received_unproven", "the external system has no record yet, and may still receive it")
                result = ActionResult(Outcome.UNKNOWN, error=_unknown_error(error), operation_id=operation_id)
            else:
                result = ActionResult(Outcome.SUCCEEDED, self._sanitizer.clean(found), attempts=1, operation_id=operation_id)
        await self._settle(intent["intent_id"], request, capability, result, reconciled=True, fencing_token=fencing_token)
        return result

    # ---- manual exceptions: an unknown outcome nothing here could settle ---

    async def unresolved(self) -> list[Mapping[str, Any]]:
        """Actions whose outcome is unknown and still waiting for the named owner."""
        return [e for e in await self.journal.unresolved() if e.get("ambassador") == self.spec.name]

    async def resolve(self, operation_id: str, outcome: Outcome, *, by: str, note: str = "") -> ActionResult:
        """Record what a person found out about an unknown outcome (for example, from the external system's own records).

        Only `succeeded` or `failed` can be recorded. A `failed` answer is the first moment another
        channel may safely be offered, so the capability's fallback is attached to it here.
        """
        if outcome not in (Outcome.SUCCEEDED, Outcome.FAILED):
            raise ValueError("an unknown outcome is resolved to succeeded or failed")
        entry = next((e for e in await self.journal.unresolved() if e["operation_id"] == operation_id), None)
        if entry is None:
            raise KeyError(f"no unresolved action with operation id '{operation_id}'")
        capability = self._capabilities.get(entry["capability"])
        if outcome is Outcome.SUCCEEDED:
            result = ActionResult(outcome, operation_id=operation_id)
        else:
            error = BoundaryError("confirmed_not_done", f"confirmed by {by}: {note}".strip(": "), retryable=True)
            result = ActionResult(outcome, error=error, fallback=capability.fallback if capability else None, operation_id=operation_id)
        await self.journal.resolve(operation_id, result, by, note)
        return result

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


def _unknown_error(cause: BoundaryError | None = None) -> BoundaryError:
    detail = f" ({cause.message})" if cause and cause.message else ""
    return BoundaryError(
        "outcome_unknown",
        "the action may or may not have reached the external system" + detail + ". Do not retry it or try another channel; its owner settles it.",
    )


def _failed(capability: Capability, error: BoundaryError, attempts: int, operation_id: str | None) -> ActionResult:
    """Known not to have been done. Only here may another channel be offered."""
    return ActionResult(Outcome.FAILED, error=error, fallback=capability.fallback, attempts=attempts, operation_id=operation_id)
