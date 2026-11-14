"""The Temporal adapter (docs/on-temporal.md). Experimental.

The first test needs only the SDK. The rest need a Temporal dev server, which the SDK downloads, so they are skipped where it
cannot be fetched. CI sets AMBASSADOR_REQUIRE_TEMPORAL=1, which turns that skip into a failure so the tests cannot pass by not running.
"""
import asyncio
import os

import pytest

pytest.importorskip("temporalio")

from temporalio.client import Client  # noqa: E402
from temporalio.runtime import Runtime, TelemetryConfig  # noqa: E402
from temporalio.testing import WorkflowEnvironment  # noqa: E402

from ambassador_agent import ActionRequest, Outcome, Principal  # noqa: E402
from ambassador_agent.adapters.temporal import TemporalAmbassador, recover, request_from_dict, request_to_dict, result_from_dict, submit  # noqa: E402
from replicas_kit import CORE, Office, kill_a_replica_mid_task, replica, task  # noqa: E402

NAME = "order-ambassador"


def test_a_task_and_its_result_survive_the_trip_through_json():
    request = ActionRequest("book_order", {"order": "O-1"}, Principal("core", "customer-1", frozenset({"a"}), {"k": 1}), "key", "corr", "caller", "proof")
    assert request_from_dict(request_to_dict(request)) == request
    result = result_from_dict({"outcome": "unknown", "error": {"code": "outcome_unknown", "message": "m"}, "operation_id": "key", "replayed": True})
    assert result.outcome is Outcome.UNKNOWN and result.replayed and result.operation_id == "key" and result.fallback is None


_NO_SERVER: str | None = None


@pytest.fixture
async def env():
    global _NO_SERVER
    if _NO_SERVER:
        pytest.skip(_NO_SERVER)  # one failed start is enough: do not try the download again for every test
    try:
        environment = await WorkflowEnvironment.start_local()
    except RuntimeError as exc:  # the server could not be downloaded or started
        if os.environ.get("AMBASSADOR_REQUIRE_TEMPORAL"):
            raise
        _NO_SERVER = f"no Temporal dev server here: {exc}"
        pytest.skip(_NO_SERVER)
    yield environment
    await environment.shutdown()


@pytest.fixture
def paths(tmp_path):
    return str(tmp_path / "journal.db"), str(tmp_path / "office.db")


async def workers(env, journal_path, office, count=2):
    """`count` workers on one task queue, as separate processes would be: each has its own runtime and client, and its own
    ambassador with a connection to the same journal. (One runtime refuses two workers on one task queue.)"""
    found = []
    for i in range(count):
        client = await Client.connect(env.client.service_client.config.target_host, namespace=env.client.namespace, runtime=Runtime(telemetry=TelemetryConfig()))
        found.append(TemporalAmbassador(replica(f"w{i}", journal_path, office, leased=False)).worker(client))
    return found


async def test_two_workers_never_work_on_one_resource_at_once_and_the_second_task_is_refused(env, paths):
    journal_path, office_path = paths
    office = Office(office_path)
    ws = await workers(env, journal_path, office)
    async with ws[0], ws[1]:
        first, second = await asyncio.gather(
            submit(env.client, NAME, "O-1", task("x", stall=0.5)),
            submit(env.client, NAME, "O-1", task("y", stall=0.5)),
        )
    outcomes = sorted(r.outcome.value for r in (first, second))
    assert outcomes == ["rejected", "succeeded"]  # Temporal allows one open workflow per id
    refused = first if first.outcome is Outcome.REJECTED else second
    assert refused.error.code == "resource_busy" and refused.error.retryable
    assert office.max_active == 1 and office.count() == 1


async def test_different_resources_run_side_by_side(env, paths):
    journal_path, office_path = paths
    office = Office(office_path)
    ws = await workers(env, journal_path, office)
    async with ws[0], ws[1]:
        results = await asyncio.gather(
            submit(env.client, NAME, "O-1", task("x", "O-1", stall=0.4)),
            submit(env.client, NAME, "O-2", task("y", "O-2", stall=0.4)),
        )
    assert all(r.outcome is Outcome.SUCCEEDED for r in results)
    assert office.max_active == 2 and office.count() == 2


async def test_a_finished_resource_is_free_and_a_repeat_is_answered_from_the_journal(env, paths):
    journal_path, office_path = paths
    office = Office(office_path)
    ws = await workers(env, journal_path, office)
    async with ws[0], ws[1]:
        done = await submit(env.client, NAME, "O-1", task("same"))
        again = await submit(env.client, NAME, "O-1", task("same"))  # the workflow id is free again
    assert done.outcome is Outcome.SUCCEEDED and not done.replayed
    assert again.outcome is Outcome.SUCCEEDED and again.replayed
    assert office.count() == 1


async def test_a_timeout_is_unknown_and_a_repeat_never_books_twice(env, paths):
    journal_path, office_path = paths
    office = Office(office_path)
    ws = await workers(env, journal_path, office)
    async with ws[0], ws[1]:
        late = await submit(env.client, NAME, "O-1", task("slow", stall=1.0), timeout_seconds=0.4)
        assert late.outcome is Outcome.UNKNOWN and late.fallback is None and late.operation_id == "slow"
        await asyncio.sleep(1.5)  # the slow call is still running and finishes on its own: Temporal does not stop it
        repeat = await submit(env.client, NAME, "O-1", task("slow"))
    assert repeat.replayed and repeat.outcome in (Outcome.SUCCEEDED, Outcome.UNKNOWN)  # answered from the record, never sent again
    assert office.count() == 1


async def test_recovery_settles_a_dead_workers_intent_and_cannot_overlap_a_task(env, paths):
    journal_path, office_path = paths
    kill_a_replica_mid_task(journal_path, office_path, ttl=1.0, leased=False)  # a real process dies after the partner booked
    office = Office(office_path)
    assert office.count() == 1
    ws = await workers(env, journal_path, office)
    async with ws[0], ws[1]:
        running = asyncio.ensure_future(submit(env.client, NAME, "O-2", task("other", "O-2", stall=0.6)))
        await asyncio.sleep(0.2)
        assert await recover(env.client, NAME, "O-2") == []  # a task for O-2 is open: recovery waits
        [settled] = await recover(env.client, NAME, "O-1")  # the dead worker's resource
        await running
    assert settled.outcome is Outcome.SUCCEEDED and settled.operation_id == "k1"  # found at the partner, not sent again
    assert office.count() == 2  # the dead worker's booking, and O-2's
