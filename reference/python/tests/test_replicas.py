"""Two replicas of one ambassador on one shared journal: a lease with a fencing token (docs/pattern.md, "More than one replica").

Every replica opens the same SQLite file with its own connection, and the partner system lives in a file too, so a replica
can be killed in another process. The older tests in test_faults.py pin what goes wrong without leases; these show what the
lease buys.
"""
import asyncio
import os
import subprocess
import sys
import time

import pytest

from ambassador_agent import LeaseLost, Outcome, PermanentError, SqliteJournal, Unknown
from replicas_kit import Office, replica, task

HERE = os.path.dirname(os.path.abspath(__file__))


@pytest.fixture
def journal_path(tmp_path):
    return str(tmp_path / "journal.db")


@pytest.fixture
def office_path(tmp_path):
    return str(tmp_path / "office.db")


# ---- one task per resource across copies -----------------------------------------------------------------


async def test_two_replicas_never_work_on_one_resource_at_the_same_time(journal_path, office_path):
    office = Office(office_path)
    a, b = replica("a", journal_path, office), replica("b", journal_path, office)
    first, second = await asyncio.gather(a.perform(task("x", stall=0.05)), b.perform(task("y", stall=0.05)))
    assert first.outcome is Outcome.SUCCEEDED and second.outcome is Outcome.SUCCEEDED  # the second waited, then ran
    assert office.max_active == 1
    assert office.tokens("O-1") == [1, 2]  # each crossing carried the token of its own lease


async def test_the_same_task_sent_to_both_replicas_crosses_the_boundary_once(journal_path, office_path):
    office = Office(office_path)
    a, b = replica("a", journal_path, office), replica("b", journal_path, office)
    results = await asyncio.gather(a.perform(task("same", stall=0.05)), b.perform(task("same", stall=0.05)))
    assert sorted(r.replayed for r in results) == [False, True]  # the second was answered from the shared record
    assert all(r.outcome is Outcome.SUCCEEDED for r in results)
    assert office.count() == 1


async def test_different_resources_still_run_side_by_side(journal_path, office_path):
    office = Office(office_path)
    a, b = replica("a", journal_path, office), replica("b", journal_path, office)
    await asyncio.gather(a.perform(task("x", "O-1", stall=0.05)), b.perform(task("y", "O-2", stall=0.05)))
    assert office.max_active == 2 and office.count() == 2


async def test_a_replica_can_refuse_instead_of_waiting_for_another_copy(journal_path, office_path):
    office = Office(office_path)
    a = replica("a", journal_path, office)
    b = replica("b", journal_path, office, on_busy="reject")
    running = asyncio.ensure_future(a.perform(task("x", stall=0.1)))
    await asyncio.sleep(0.03)  # a holds the lease
    refused = await b.perform(task("y"))
    assert refused.outcome is Outcome.REJECTED and refused.error.code == "resource_busy" and refused.error.retryable
    assert (await running).outcome is Outcome.SUCCEEDED and office.count() == 1


async def test_a_task_longer_than_the_lease_keeps_it_by_renewing(journal_path, office_path):
    office = Office(office_path)
    a, b = replica("a", journal_path, office, ttl=0.3), replica("b", journal_path, office, ttl=0.3)
    first = asyncio.ensure_future(a.perform(task("x", stall=1.0)))  # three times the lease
    await asyncio.sleep(0.1)
    second = await b.perform(task("y"))
    assert (await first).outcome is Outcome.SUCCEEDED and second.outcome is Outcome.SUCCEEDED
    assert office.max_active == 1


# ---- a copy that dies --------------------------------------------------------------------------------------


def kill_a_replica_mid_task(journal_path, office_path, ttl):
    child = subprocess.run(
        [sys.executable, "-c", f"from replicas_kit import die_midway; die_midway({journal_path!r}, {office_path!r}, {ttl})"],
        env={**os.environ, "PYTHONPATH": os.pathsep.join([HERE, os.path.join(HERE, "..", "src")])},
        capture_output=True,
        timeout=30,
    )
    assert child.returncode == 17, child.stderr.decode()  # it died where the test said it would


async def test_the_other_replica_settles_a_dead_replicas_intent_once_the_lease_lapses_and_never_acts_twice(journal_path, office_path):
    kill_a_replica_mid_task(journal_path, office_path, ttl=1.0)
    office = Office(office_path)
    assert office.count() == 1  # the booking happened, and nobody recorded it
    b = replica("b", journal_path, office)
    assert [i["idempotency_key"] for i in await b.journal.unfinished()] == ["k1"]

    assert await b.reconcile() == []  # the dead copy's lease has not lapsed: it may only be slow, so b leaves it alone
    assert len(await b.journal.unfinished()) == 1

    deadline = time.monotonic() + 5
    settled = []
    while not settled and time.monotonic() < deadline:
        await asyncio.sleep(0.1)
        settled = await b.reconcile()
    [result] = settled
    assert result.outcome is Outcome.SUCCEEDED and result.operation_id == "k1"  # found at the partner, not sent again
    assert await b.journal.unfinished() == []
    assert office.count() == 1

    again = await b.perform(task("k1"))
    assert again.replayed and again.outcome is Outcome.SUCCEEDED and office.count() == 1


async def test_a_repeat_that_reaches_the_other_replica_is_held_not_sent_again(journal_path, office_path):
    kill_a_replica_mid_task(journal_path, office_path, ttl=0.5)
    office = Office(office_path)
    b = replica("b", journal_path, office)
    started = time.monotonic()
    repeat = await b.perform(task("k1"))  # waits for the dead copy's lease to lapse
    assert time.monotonic() - started >= 0.3
    assert repeat.outcome is Outcome.UNKNOWN and repeat.replayed and repeat.fallback is None  # the intent is open: never re-sent
    assert office.count() == 1


async def test_with_no_way_to_ask_the_partner_the_dead_replicas_task_stays_held_across_replicas(journal_path, office_path):
    kill_a_replica_mid_task(journal_path, office_path, ttl=0.3)
    office = Office(office_path)
    b = replica("b", journal_path, office, ttl=0.3, on_unknown=Unknown.STOP)
    await asyncio.sleep(0.4)
    [result] = await b.reconcile()
    assert result.outcome is Outcome.UNKNOWN
    assert [e["operation_id"] for e in await b.unresolved()] == ["k1"]  # waiting for a person

    c = replica("c", journal_path, office, on_unknown=Unknown.STOP)  # a third copy sees the same hold
    retry = await c.perform(task("new-key"))
    assert retry.outcome is Outcome.REJECTED and retry.error.code == "resource_held"
    assert office.count() == 1


# ---- a copy that stalls, or a late write ---------------------------------------------------------------------


class Clock:
    def __init__(self, now: float) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


async def test_a_stalled_replica_cannot_write_to_the_journal_after_another_took_over(journal_path):
    clock = Clock(100.0)
    stale, fresh = SqliteJournal(journal_path, clock=clock), SqliteJournal(journal_path, clock=clock)
    old = await stale.acquire("O-1", "a", 10)
    assert await fresh.acquire("O-1", "b", 10) is None  # a holds it
    intent = await stale.begin({"resource": "O-1", "operation_id": "x", "fencing_token": old})

    clock.now += 11  # a stalls past its lease
    new = await fresh.acquire("O-1", "b", 10)
    assert (old, new) == (1, 2)  # tokens only grow
    assert await stale.renew("O-1", "a", old, 10) is False

    with pytest.raises(LeaseLost):
        await stale.begin({"resource": "O-1", "operation_id": "y", "fencing_token": old})  # it cannot start a crossing ...
    with pytest.raises(LeaseLost):
        await stale.finish(intent, {"outcome": "succeeded", "fencing_token": old})  # ... or settle the one it began
    assert [i["operation_id"] for i in await fresh.unfinished()] == ["x"]  # the new holder recovers it


async def test_a_stalled_replicas_late_write_is_refused_once_the_new_holder_has_asked_the_partner(journal_path, office_path):
    office = Office(office_path)
    a = replica("a", journal_path, office, ttl=0.2)
    b = replica("b", journal_path, office, ttl=0.2)

    async def no_heartbeat(resource, token):  # a is paused: it stops renewing, and its request is still on its way
        await asyncio.sleep(3600)

    a._beat = no_heartbeat
    slow = asyncio.ensure_future(a.perform(task("x", stall=0.6)))
    await asyncio.sleep(0.3)  # a's lease has lapsed; its request has not arrived

    [verdict] = await b.reconcile()  # b takes the lease and asks the partner under its newer token
    assert verdict.outcome is Outcome.FAILED and verdict.error.code == "not_received"  # no record, and that is now final
    assert (await b.perform(task("y"))).outcome is Outcome.SUCCEEDED  # the resource is free again

    late = await slow  # a's request finally arrives, carrying its old token
    assert late.outcome is Outcome.FAILED and late.error.code == "stale_token"  # refused before it did anything
    assert office.count() == 1 and office.tokens("O-1")[0] > 1  # one booking, and it is the new holder's
    kinds = [e["kind"] for e in a.journal.entries if e.get("operation_id") == "x"]
    assert "settled_elsewhere" in kinds  # a is told that b owns the record now


async def test_without_the_token_on_the_lookup_a_late_write_still_gets_in(journal_path, office_path):
    """Why the lookup must carry the token: b's "no record" would be a guess, and a's late request would then be booked."""
    office = Office(office_path)
    a = replica("a", journal_path, office, ttl=0.2)
    b = replica("b", journal_path, office, ttl=0.2)

    async def no_heartbeat(resource, token):
        await asyncio.sleep(3600)

    a._beat = no_heartbeat
    original = office.find
    office.find = lambda resource, ref, token: original(resource, ref, None)  # a partner that ignores the token on a lookup
    slow = asyncio.ensure_future(a.perform(task("x", stall=0.6)))
    await asyncio.sleep(0.3)
    [verdict] = await b.reconcile()
    assert verdict.outcome is Outcome.FAILED  # b was told "no record" ...
    await slow
    assert office.count() == 1  # ... and the booking it called failed went through
