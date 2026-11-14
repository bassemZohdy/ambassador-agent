"""Fault injection and concurrency for the reliability claims in docs/pattern.md.

What this covers: a crash at each step of a task, a request that lands after the caller gave up, tasks racing for
one resource, and seeded random runs that check the invariants after every fault has played out.

What it does NOT cover: more than one running ambassador (the locks here are in-process), a real network, a real
database under contention, or a real external system. The last two replica tests pin that limit.
"""
import asyncio
import random
from typing import Any, Mapping

import pytest

from ambassador_agent import ActionRequest, Outcome, Principal, TransientError, Unknown
from ambassador_agent.defaults import InMemoryJournal
from examples.shipments import Crash, FakeCourier, build_ambassador

WRITER = Principal("core", on_behalf_of="customer-1", scopes=frozenset({"shipments:read", "shipments:write"}))
OUTCOMES = {Outcome.SUCCEEDED, Outcome.FAILED, Outcome.REJECTED, Outcome.UNKNOWN}


def book(key=None, number="O-1"):
    return ActionRequest("book_shipment", {"order_number": number}, WRITER, idempotency_key=key)


class LateCourier(FakeCourier):
    """A courier whose request can reach it after the caller has already given up.

    `late_next` / `late_all`: the caller times out and the booking is queued; `land()` delivers the queue.
    With `rejects_late`, a request that lands after its caller gave up is refused, which is the property that
    makes "no record" final.
    """

    def __init__(self, rejects_late: bool = True) -> None:
        super().__init__()
        self.rejects_late = rejects_late
        self.late_next = 0
        self.late_all = False
        self.inflight: list[Mapping[str, Any]] = []

    async def invoke(self, operation, payload, credentials):
        if operation == "CREATE_SHPMT" and (self.late_all or self.late_next > 0):
            self.late_next = max(0, self.late_next - 1)
            self.calls.append((operation, payload))
            self.inflight.append(payload)
            raise TransientError("courier timed out")  # the caller cannot tell whether it was or will be processed
        return await super().invoke(operation, payload, credentials)

    def land(self) -> None:
        queued, self.inflight = self.inflight, []
        if self.rejects_late:
            return  # refused: the window for this request had closed
        for payload in queued:
            self._handle("CREATE_SHPMT", payload)


class CrashingJournal(InMemoryJournal):
    """Dies once, on the named journal call, to test every step between 'intent recorded' and 'outcome recorded'."""

    def __init__(self, crash_on: str | None = None) -> None:
        super().__init__()
        self.crash_on = crash_on

    def _maybe_crash(self, name: str) -> None:
        if self.crash_on == name:
            self.crash_on = None
            raise Crash()

    async def begin(self, intent):
        self._maybe_crash("begin")
        return await super().begin(intent)

    async def remember(self, key, result):
        self._maybe_crash("remember")
        await super().remember(key, result)

    async def finish(self, intent_id, outcome):
        self._maybe_crash("finish")
        await super().finish(intent_id, outcome)


# ---- a crash at each step ----------------------------------------------------


async def test_crash_before_the_intent_is_recorded_sends_nothing():
    office, journal = FakeCourier(), CrashingJournal("begin")
    with pytest.raises(Crash):
        await build_ambassador(office, journal=journal).perform(book("k"))
    assert office.calls == [] and await journal.unfinished() == []  # nothing crossed, nothing to recover
    assert (await build_ambassador(office, journal=journal).perform(book("k"))).outcome is Outcome.SUCCEEDED
    assert office.created == 1


async def test_crash_after_the_send_before_the_reply_is_found_by_recovery():
    office, journal = FakeCourier(), InMemoryJournal()
    office.crash_after_next = True
    with pytest.raises(Crash):
        await build_ambassador(office, journal=journal).perform(book("k"))
    [result] = await build_ambassador(office, journal=journal).reconcile()
    assert result.outcome is Outcome.SUCCEEDED and office.created == 1


async def test_crash_while_recording_the_outcome_never_sends_twice():
    office, journal = FakeCourier(), CrashingJournal("finish")
    with pytest.raises(Crash):
        await build_ambassador(office, journal=journal).perform(book("k"))
    assert office.created == 1 and len(await journal.unfinished()) == 1
    restarted = build_ambassador(office, journal=journal)
    repeat = await restarted.perform(book("k"))  # before recovery: answered from the record, not sent again
    assert repeat.outcome is Outcome.SUCCEEDED and repeat.replayed
    [result] = await restarted.reconcile()
    assert result.outcome is Outcome.SUCCEEDED
    assert office.created == 1 and [op for op, _ in office.calls].count("CREATE_SHPMT") == 1


async def test_crash_while_remembering_the_result_leaves_an_intent_that_recovery_settles():
    office, journal = FakeCourier(), CrashingJournal("remember")
    with pytest.raises(Crash):
        await build_ambassador(office, journal=journal).perform(book("k"))
    assert len(await journal.unfinished()) == 1  # the order of writes: result first, then close the intent
    restarted = build_ambassador(office, journal=journal)
    held = await restarted.perform(book("k"))
    assert held.outcome is Outcome.UNKNOWN and held.replayed  # held, not resent, until recovery runs
    [result] = await restarted.reconcile()
    assert result.outcome is Outcome.SUCCEEDED and office.created == 1


# ---- a request that lands after the caller gave up ---------------------------


async def test_late_delivery_to_a_deduplicating_courier_is_effectively_once():
    office = LateCourier(rejects_late=False)
    office.late_next = 1  # first attempt is lost in flight; the second goes through
    result = await build_ambassador(office, absence_final=False).perform(book("k"))
    assert result.outcome is Outcome.SUCCEEDED
    office.land()  # the first one finally arrives: same client reference, so it is the same booking
    assert office.created == 1


async def test_late_delivery_without_a_proof_of_absence_ends_unknown_and_the_owner_settles_it():
    office = LateCourier(rejects_late=False)
    office.late_all = True
    amb = build_ambassador(office, absence_final=False)
    result = await amb.perform(book("k"))
    assert result.outcome is Outcome.UNKNOWN and result.fallback is None  # no other channel while it may still land
    assert office.created == 0
    office.land()  # it did land, after all
    assert office.created == 1
    settled = await amb.resolve("k", Outcome.SUCCEEDED, by="ops", note="found in the courier's own records")
    assert settled.outcome is Outcome.SUCCEEDED
    assert (await amb.perform(book("k"))).replayed and office.created == 1


async def test_late_delivery_to_a_courier_that_rejects_late_requests_is_failed_with_the_fallback():
    office = LateCourier(rejects_late=True)
    office.late_all = True
    result = await build_ambassador(office, absence_final=True).perform(book("k"))
    assert result.outcome is Outcome.FAILED and result.fallback  # absence is final: another channel is safe
    office.land()
    assert office.created == 0  # and the late ones were refused, so no second booking appears


# ---- concurrency -------------------------------------------------------------


async def test_the_same_task_sent_many_times_at_once_makes_one_booking():
    office = FakeCourier()
    office.delay = 0.01
    amb = build_ambassador(office)
    results = await asyncio.gather(*(amb.perform(book("k")) for _ in range(8)))
    assert all(r.outcome is Outcome.SUCCEEDED for r in results)
    assert sum(1 for r in results if not r.replayed) == 1 and office.created == 1
    assert [op for op, _ in office.calls].count("CREATE_SHPMT") == 1


async def test_different_keys_for_one_resource_never_overlap_at_the_boundary():
    office = FakeCourier()
    office.delay = 0.005
    amb = build_ambassador(office)
    await asyncio.gather(*(amb.perform(book(f"k{i}", number="O-7")) for i in range(6)))
    assert office.max_active == 1


class SlowJournal(InMemoryJournal):
    """A journal behind a network: each read takes time, so a check and the write that follows are not atomic."""

    async def unfinished(self):
        snapshot = await super().unfinished()  # the store answers as of now ...
        await asyncio.sleep(0.005)  # ... and the answer takes time to arrive, by when it may be stale
        return snapshot


async def test_a_shared_journal_makes_a_second_replica_refuse_a_busy_resource():
    """Incidental, and only as good as the store: the second replica sees the first one's open intent and backs off."""
    office = FakeCourier()
    office.delay = 0.02
    journal = InMemoryJournal()
    a, b = build_ambassador(office, journal=journal), build_ambassador(office, journal=journal)
    first, second = await asyncio.gather(a.perform(book("x", number="O-9")), b.perform(book("y", number="O-9")))
    assert first.outcome is Outcome.SUCCEEDED
    assert second.outcome is Outcome.REJECTED and second.error.code == "resource_held"
    assert office.max_active == 1


async def test_two_replicas_are_not_mutually_exclusive_when_the_check_and_the_write_are_not_atomic():
    """A known limit, pinned so it is not mistaken for a guarantee: the locks here are in-process (tests/test_replicas.py shows the lease that closes it).

    Both replicas read the journal before either has written its intent, so both proceed. A real deployment needs
    one of the options in "More than one replica" in docs/pattern.md: a partition by resource key, a single active
    replica, or a lease with fencing, plus an atomic claim on each open intent.
    """
    office = FakeCourier()
    office.delay = 0.02
    journal = SlowJournal()
    a, b = build_ambassador(office, journal=journal), build_ambassador(office, journal=journal)
    await asyncio.gather(a.perform(book("x", number="O-9")), b.perform(book("y", number="O-9")))
    assert office.max_active == 2


# ---- seeded random runs: the invariants hold after every fault has played out -------------


FAULTS = ["none", "none", "fail", "lose", "crash", "late", "down"]


async def run_seed(seed: int) -> None:
    rng = random.Random(seed)
    office, journal = LateCourier(rejects_late=True), InMemoryJournal()
    amb = build_ambassador(office, journal=journal)
    final: dict[str, Any] = {}  # operation id -> the last result the caller was given

    for i in range(rng.randint(5, 12)):
        key = f"k{rng.randint(0, 5)}"  # repeats on purpose: the same key arrives more than once
        number = f"O-{rng.randint(1, 3)}"  # several keys share a resource on purpose
        fault = rng.choice(FAULTS)
        office.down = fault == "down"
        office.fail_next = rng.randint(1, 4) if fault == "fail" else 0
        office.lose_reply_next = fault == "lose"
        office.crash_after_next = fault == "crash"
        office.late_next = rng.randint(1, 2) if fault == "late" else 0
        try:
            result = await amb.perform(book(key, number))
        except Crash:
            amb = build_ambassador(office, journal=journal)  # the process died; a new one starts on the same journal
            continue
        finally:
            office.down = False
        assert result.outcome in OUTCOMES, (seed, i)
        if result.outcome is Outcome.UNKNOWN:
            assert result.fallback is None, (seed, i, "a fallback was offered while the outcome was unknown")
        if result.operation_id:
            final[result.operation_id] = result

    # Quiescence: every fault has played out, late requests have landed (or been refused), recovery has run.
    office.down = office.late_all = False
    office.fail_next = office.late_next = 0
    office.lose_reply_next = office.crash_after_next = False
    office.land()
    amb = build_ambassador(office, journal=journal)
    for result in await amb.reconcile():
        if result.outcome is Outcome.UNKNOWN:
            assert result.fallback is None, (seed, "recovery offered a fallback while unknown")
        final[result.operation_id] = result
    assert await journal.unfinished() == [], (seed, "an intent was left open after recovery")

    for operation_id, result in final.items():
        booked = operation_id in office.by_client_ref
        if result.outcome is Outcome.SUCCEEDED:
            assert booked, (seed, operation_id, "reported succeeded but the courier has no booking")
        if result.outcome is Outcome.FAILED:
            assert not booked, (seed, operation_id, "reported failed but the courier has the booking")
    assert office.created == len(office.by_client_ref), (seed, "a booking was made twice for one operation id")


@pytest.mark.parametrize("seed", range(60))
async def test_invariants_hold_under_random_faults(seed):
    await run_seed(seed)
