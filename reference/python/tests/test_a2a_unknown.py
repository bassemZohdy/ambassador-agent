"""An A2A client that does not understand `unknown` cannot make the ambassador act twice.

A2A has no state for `unknown` (docs/protocol-mapping.md), so the ambassador cannot rely on a client
reading it correctly. These tests play the client that gets it wrong: it retries every reply it does
not recognise, with the same key and with a new one. The guarantee is on the server side.
"""
from types import SimpleNamespace

import pytest

pytest.importorskip("a2a")

from a2a.helpers import get_data_parts, new_data_message
from a2a.types import Role

from ambassador_agent import Unknown
from ambassador_agent.bindings.a2a import AmbassadorExecutor
from examples.shipments import FakeCourier, build_ambassador

PRINCIPAL = {"subject": "core", "on_behalf_of": "customer-1", "scopes": ["shipments:read", "shipments:write"]}


class Client:
    """A naive client: sends one booking per call and returns the reply data."""

    def __init__(self, ambassador):
        self.executor = AmbassadorExecutor(ambassador)
        self.calls = 0

    async def book(self, key):
        sent = []

        class Queue:
            async def enqueue_event(self, event):
                sent.append(event)

        body = {"capability": "book_shipment", "payload": {"order_number": "O-1", "destination": "12 High Street"}, "principal": PRINCIPAL, "idempotency_key": key}
        self.calls += 1
        context = SimpleNamespace(message=new_data_message(body, role=Role.ROLE_USER), task_id=f"t{self.calls}", context_id="c1")
        await self.executor.execute(context, Queue())
        return get_data_parts(sent[0].parts)[0]


def lossy_ambassador():
    office = FakeCourier()
    office.lose_reply_next = True
    return office, build_ambassador(office, on_unknown=Unknown.STOP)


async def test_the_reply_carries_the_real_outcome_and_no_fallback():
    office, amb = lossy_ambassador()
    reply = await Client(amb).book("k1")
    assert reply["outcome"] == "unknown"
    assert reply["operation_id"]
    assert "fallback" not in reply  # a fallback is offered only when the action is known not to have been done
    assert office.created == 1


async def test_a_client_that_retries_with_the_same_key_never_books_a_second_time():
    office, amb = lossy_ambassador()
    client = Client(amb)
    first = await client.book("k1")
    replies = [await client.book("k1") for _ in range(5)]
    assert all(r["outcome"] == "unknown" and r["operation_id"] == first["operation_id"] for r in replies)
    assert office.created == 1


async def test_a_client_that_retries_with_new_keys_is_refused_and_never_books_a_second_time():
    office, amb = lossy_ambassador()
    client = Client(amb)
    await client.book("k1")
    replies = [await client.book(f"new-{n}") for n in range(5)]
    assert all(r["outcome"] == "rejected" and r["error"]["code"] == "resource_held" for r in replies)
    assert all(r["error"]["retryable"] is False for r in replies)
    assert office.created == 1
