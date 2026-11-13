"""The SQLite journal survives a restart: a second connection on the same file stands in for a new process."""
import pytest

from ambassador_agent import ActionRequest, Outcome, Principal, SqliteJournal, Unknown
from examples.shipments import Crash, FakeCourier, build_ambassador

WRITER = Principal("core", on_behalf_of="customer-1", scopes=frozenset({"shipments:read", "shipments:write"}))


def book(key="k", number="O-1"):
    return ActionRequest("book_shipment", {"order_number": number}, WRITER, idempotency_key=key)


@pytest.fixture
def path(tmp_path):
    return str(tmp_path / "journal.db")


async def test_a_crash_mid_action_is_found_and_settled_after_a_real_restart(path):
    office = FakeCourier()
    first = SqliteJournal(path)
    office.crash_after_next = True
    with pytest.raises(Crash):
        await build_ambassador(office, journal=first).perform(book())
    first.close()  # the process is gone

    second = SqliteJournal(path)  # a new process opens the same file
    assert [i["operation_id"] for i in await second.unfinished()] == ["k"]
    [result] = await build_ambassador(office, journal=second).reconcile()
    assert result.outcome is Outcome.SUCCEEDED and office.created == 1
    assert await second.unfinished() == []


async def test_a_remembered_result_answers_a_repeat_after_a_restart(path):
    office = FakeCourier()
    first = SqliteJournal(path)
    done = await build_ambassador(office, journal=first).perform(book())
    first.close()

    second = SqliteJournal(path)
    repeat = await build_ambassador(office, journal=second).perform(book())
    assert repeat.replayed and repeat.outcome is Outcome.SUCCEEDED and repeat.data == done.data
    assert office.created == 1 and [op for op, _ in office.calls].count("CREATE_SHPMT") == 1


async def test_an_unknown_outcome_and_its_resolution_survive_a_restart(path):
    office = FakeCourier()
    office.lose_reply_next = True
    first = SqliteJournal(path)
    unknown = await build_ambassador(office, journal=first, on_unknown=Unknown.STOP).perform(book())
    assert unknown.outcome is Outcome.UNKNOWN
    first.close()

    second = SqliteJournal(path)
    amb = build_ambassador(office, journal=second, on_unknown=Unknown.STOP)
    assert [e["operation_id"] for e in await amb.unresolved()] == ["k"]
    held = await amb.perform(book("other"))  # the hold on the resource was restored with the record
    assert held.outcome is Outcome.REJECTED and held.error.code == "resource_held"

    await amb.resolve("k", Outcome.SUCCEEDED, by="ops", note="found in the courier's records")
    second.close()

    third = SqliteJournal(path)
    amb = build_ambassador(office, journal=third, on_unknown=Unknown.STOP)
    assert await amb.unresolved() == []
    assert (await amb.perform(book())).replayed  # the settled answer is what a repeat now gets


async def test_a_failed_resolution_frees_the_key_across_a_restart(path):
    office = FakeCourier()
    office.lose_reply_next = True
    first = SqliteJournal(path)
    amb = build_ambassador(office, journal=first, on_unknown=Unknown.STOP)
    await amb.perform(book())
    office.by_client_ref.clear()
    office.created = 0
    result = await amb.resolve("k", Outcome.FAILED, by="ops", note="nothing on the courier side")
    assert result.fallback  # only now may another channel be offered
    first.close()

    again = await build_ambassador(office, journal=SqliteJournal(path), on_unknown=Unknown.STOP).perform(book())
    assert again.outcome is Outcome.SUCCEEDED and not again.replayed


async def test_the_log_keeps_the_order_of_what_happened(path):
    office = FakeCourier()
    journal = SqliteJournal(path)
    await build_ambassador(office, journal=journal).perform(book())
    kinds = [e["kind"] for e in journal.entries]
    assert kinds.index("intent") < kinds.index("outcome")
