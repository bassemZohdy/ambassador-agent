"""Tests for reconciliation preconditions, the resource hold on an open unknown, and contract governance."""
import time

import pytest

from ambassador_agent import (
    ActionRequest,
    Ambassador,
    AmbassadorSpec,
    Capability,
    Outcome,
    Principal,
    Resilience,
    Unknown,
)
from ambassador_agent.defaults import InMemoryJournal
from examples.shipments import Crash, FakeCourier, build_ambassador

WRITER = Principal("core", on_behalf_of="customer-1", scopes=frozenset({"shipments:read", "shipments:write"}))


def book(key=None, number="O-1", who=WRITER):
    return ActionRequest("book_shipment", {"order_number": number}, who, idempotency_key=key)


async def crash_mid_action(office, journal, **kwargs):
    office.crash_after_next = True
    with pytest.raises(Crash):
        await build_ambassador(office, journal=journal, **kwargs).perform(book("k"))
    return build_ambassador(office, journal=journal, **kwargs)  # same journal, new process


# ---- when "no record" may be believed ---------------------------------------


async def test_no_record_is_believed_only_when_the_capability_declares_absence_final():
    office, journal = FakeCourier(), InMemoryJournal()
    restarted = await crash_mid_action(office, journal, absence_final=False)
    office.by_client_ref.clear()  # the lookup finds nothing, but nothing proves a late request will not arrive
    [result] = await restarted.reconcile()
    assert result.outcome is Outcome.UNKNOWN and result.fallback is None
    assert [e["operation_id"] for e in await restarted.unresolved()] == ["k"]


async def test_recovery_waits_out_the_settle_window_before_believing_a_lookup():
    office, journal = FakeCourier(), InMemoryJournal()
    restarted = await crash_mid_action(office, journal, settle_after=3600)
    office.by_client_ref.clear()
    calls = len(office.calls)
    assert await restarted.reconcile() == []  # too soon: a request may still be in flight
    assert len(await journal.unfinished()) == 1 and len(office.calls) == calls  # no lookup, no resend


async def test_the_live_path_sleeps_out_the_settle_window_before_the_lookup():
    office = FakeCourier()
    office.dedupes = False
    office.fail_next = 1  # a timeout the caller cannot read
    started = time.monotonic()
    result = await build_ambassador(office, settle_after=0.05).perform(book("k"))
    assert time.monotonic() - started >= 0.05
    assert result.outcome is Outcome.SUCCEEDED and office.created == 1


async def test_running_out_of_attempts_with_an_unsettled_attempt_is_unknown_not_failed():
    office = FakeCourier()
    office.fail_next = 10  # every attempt times out and none can be ruled out as late
    amb = build_ambassador(office, absence_final=False)
    result = await amb.perform(book("k"))
    assert result.outcome is Outcome.UNKNOWN and result.fallback is None
    assert [e["operation_id"] for e in await amb.unresolved()] == ["k"]


async def test_running_out_of_attempts_is_failed_with_the_fallback_when_absence_is_final():
    office = FakeCourier()
    office.fail_next = 10
    result = await build_ambassador(office, absence_final=True).perform(book("k"))
    assert result.outcome is Outcome.FAILED and result.fallback  # proven not done: another channel is safe


# ---- an open unknown holds its resource -------------------------------------


async def test_an_open_unknown_holds_its_resource_against_a_retry_under_a_new_key():
    office = FakeCourier()
    office.lose_reply_next = True
    amb = build_ambassador(office, on_unknown=Unknown.STOP)
    assert (await amb.perform(book("a"))).outcome is Outcome.UNKNOWN
    calls = len(office.calls)

    held = await amb.perform(book("b"))  # same order, new idempotency key: this is what would double-book
    assert held.outcome is Outcome.REJECTED and held.error.code == "resource_held" and held.error.retryable is False
    assert len(office.calls) == calls

    other = await amb.perform(book("c", number="O-2"))  # a different resource is not held
    assert other.outcome is Outcome.SUCCEEDED


async def test_the_hold_is_lifted_when_the_owner_settles_the_unknown():
    office = FakeCourier()
    office.lose_reply_next = True
    amb = build_ambassador(office, on_unknown=Unknown.STOP)
    await amb.perform(book("a"))
    office.by_client_ref.clear()
    office.created = 0  # the owner checked the courier's own records: it never happened
    await amb.resolve("a", Outcome.FAILED, by="ops", note="no booking on the courier side")
    assert (await amb.perform(book("b"))).outcome is Outcome.SUCCEEDED


async def test_the_same_task_is_answered_from_the_record_not_reported_as_held():
    office = FakeCourier()
    office.lose_reply_next = True
    amb = build_ambassador(office, on_unknown=Unknown.STOP)
    await amb.perform(book("a"))
    again = await amb.perform(book("a"))
    assert again.outcome is Outcome.UNKNOWN and again.replayed  # the same key is a repeat, not a new request


async def test_a_capability_without_a_declared_resource_is_never_held():
    office = FakeCourier()
    journal = InMemoryJournal()

    async def handler(ctx, payload):
        raise Crash()

    amb = Ambassador(AmbassadorSpec(name="a", boundary="b", owner="o", description="d"), office, journal=journal, resilience=Resilience(backoff_seconds=0.0))
    amb.offer(Capability("do_it", "does it", handler))  # no resource declared
    with pytest.raises(Crash):
        await amb.perform(ActionRequest("do_it", {}, WRITER, idempotency_key="x"))
    with pytest.raises(Crash):  # not refused as held: nothing says what this would collide with
        await amb.perform(ActionRequest("do_it", {}, WRITER, idempotency_key="y"))


# ---- contract governance -----------------------------------------------------


async def noop(ctx, payload):
    return {}


def test_a_negative_settle_window_is_refused():
    with pytest.raises(ValueError):
        Capability("c", "d", noop, settle_after_seconds=-1)


def test_absence_cannot_be_final_without_a_verifier():
    with pytest.raises(ValueError):
        Capability("c", "d", noop, absence_is_final=True, on_unknown=Unknown.STOP)


def test_the_contract_carries_the_reconciliation_and_governance_fields():
    contract = build_ambassador(FakeCourier(), settle_after=2.0).describe()
    book_shipment = next(c for c in contract["capabilities"] if c["name"] == "book_shipment")
    assert book_shipment["absence_is_final"] is True and book_shipment["settle_after_seconds"] == 2.0
    assert book_shipment["data_classification"] == "personal" and book_shipment["audit_retention_days"] == 365
    assert book_shipment["requires_approval"] is False


async def test_a_capability_that_requires_approval_is_refused_without_the_approval_scope():
    office = FakeCourier()
    amb = Ambassador(AmbassadorSpec(name="a", boundary="b", owner="o", description="d"), office, resilience=Resilience(backoff_seconds=0.0))
    amb.offer(Capability("wire", "moves money", noop, required_scopes=frozenset({"pay"}), requires_approval=True))
    plain = Principal("core", scopes=frozenset({"pay"}))
    approved = Principal("core", scopes=frozenset({"pay", "approval:wire"}))
    refused = await amb.perform(ActionRequest("wire", {}, plain))
    assert refused.outcome is Outcome.REJECTED and refused.error.code == "policy_refused"
    assert "approval:wire" in refused.error.message
    assert (await amb.perform(ActionRequest("wire", {}, approved))).outcome is Outcome.SUCCEEDED
