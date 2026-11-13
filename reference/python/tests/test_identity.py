"""A forged, expired or misdirected principal is rejected before the boundary is crossed, and the refusal is journalled."""
import pytest

from ambassador_agent import ActionRequest, HmacDelegations, Outcome, Principal
from ambassador_agent.defaults import InMemoryJournal
from examples.shipments import FakeCourier, build_ambassador

AUDIENCE = "courier-ambassador"
SECRET = b"test-secret"


class Clock:
    def __init__(self) -> None:
        self.now = 1_000_000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def delegations(clock):
    return HmacDelegations(SECRET, AUDIENCE, clock)


def asserted(subject="assistant", on_behalf_of="customer-1", scopes=frozenset()):
    return Principal(subject, on_behalf_of=on_behalf_of, scopes=scopes)


def task(delegation, caller="assistant-workload", principal=None, number="O-1", key="k"):
    return ActionRequest(
        "book_shipment", {"order_number": number}, principal or asserted(), idempotency_key=key, caller=caller, delegation=delegation
    )


def grant(delegations, **kwargs):
    defaults = dict(caller="assistant-workload", subject="assistant", on_behalf_of="customer-1", scopes={"shipments:write"})
    return delegations.issue(**{**defaults, **kwargs})


async def refused(office, journal, result, reason_part):
    assert result.outcome is Outcome.REJECTED and result.error.code == "principal_unverified"
    assert office.calls == []  # nothing crossed the boundary
    [entry] = [e for e in journal.entries if e.get("kind") == "refused"]
    assert entry["error"] == "principal_unverified" and reason_part in entry["detail"]
    assert entry["caller"] is not None or reason_part == "caller not authenticated"
    for word in ("expired", "signature", "another", "audience", "no delegation"):
        assert word not in result.error.message  # the forger is not told why


def build(delegations, journal=None):
    office, journal = FakeCourier(), journal or InMemoryJournal()
    return office, journal, build_ambassador(office, journal=journal, verifier=delegations)


async def test_a_valid_delegation_is_accepted_and_its_scopes_are_used(delegations):
    office, journal, amb = build(delegations)
    result = await amb.perform(task(grant(delegations)))  # the task itself claims no scopes at all
    assert result.outcome is Outcome.SUCCEEDED and office.created == 1
    [intent] = [e for e in journal.entries if e.get("kind") == "intent"]
    assert intent["caller"] == "assistant-workload" and intent["scopes"] == ["shipments:write"]


async def test_a_task_that_names_a_principal_and_carries_no_delegation_is_rejected(delegations):
    office, journal, amb = build(delegations)
    result = await amb.perform(task(None, principal=asserted(scopes=frozenset({"shipments:write"}))))
    await refused(office, journal, result, "no delegation")


async def test_an_unauthenticated_caller_is_rejected(delegations):
    office, journal, amb = build(delegations)
    result = await amb.perform(task(grant(delegations), caller=None))
    await refused(office, journal, result, "caller not authenticated")


async def test_a_tampered_delegation_is_rejected(delegations):
    office, journal, amb = build(delegations)
    other = HmacDelegations(b"another-secret", AUDIENCE, delegations._clock)
    result = await amb.perform(task(grant(other)))  # signed by someone else
    await refused(office, journal, result, "signature invalid")


async def test_an_edited_delegation_is_rejected(delegations):
    office, journal, amb = build(delegations)
    body, _, signature = grant(delegations, scopes={"shipments:read"}).partition(".")
    widened = grant(delegations, scopes={"shipments:read", "shipments:write"}).partition(".")[0]
    result = await amb.perform(task(f"{widened}.{signature}"))  # new scopes, old signature
    await refused(office, journal, result, "signature invalid")


async def test_an_expired_delegation_is_rejected(delegations, clock):
    office, journal, amb = build(delegations)
    token = grant(delegations, ttl_seconds=60)
    clock.now += 61
    await refused(office, journal, await amb.perform(task(token)), "expired")


async def test_a_delegation_issued_for_another_ambassador_is_rejected(delegations):
    office, journal, amb = build(delegations)
    result = await amb.perform(task(grant(delegations, audience="payments-ambassador")))
    await refused(office, journal, result, "another ambassador")


async def test_a_stolen_delegation_does_not_work_from_another_caller(delegations):
    office, journal, amb = build(delegations)
    result = await amb.perform(task(grant(delegations), caller="some-other-workload"))
    await refused(office, journal, result, "another caller")


async def test_a_task_naming_a_different_principal_than_the_delegation_is_rejected(delegations):
    office, journal, amb = build(delegations)
    result = await amb.perform(task(grant(delegations), principal=asserted(on_behalf_of="customer-2")))
    await refused(office, journal, result, "different principal")


async def test_scopes_claimed_in_the_task_add_nothing(delegations):
    office, journal, amb = build(delegations)
    read_only = grant(delegations, scopes={"shipments:read"})
    result = await amb.perform(task(read_only, principal=asserted(scopes=frozenset({"shipments:write"}))))
    assert result.outcome is Outcome.REJECTED and result.error.code == "policy_refused"  # the delegation decides
    assert office.calls == []


async def test_without_a_verifier_the_principal_is_taken_as_given():
    """The documented gap when no verifier is configured: anyone can name a principal."""
    office = FakeCourier()
    amb = build_ambassador(office)
    forged = ActionRequest("book_shipment", {"order_number": "O-1"}, asserted(scopes=frozenset({"shipments:write"})), idempotency_key="k")
    assert (await amb.perform(forged)).outcome is Outcome.SUCCEEDED
    assert amb.describe()["verifies_principal"] is False


def test_the_contract_says_whether_the_principal_is_verified(delegations):
    assert build(delegations)[2].describe()["verifies_principal"] is True
