"""The MCP binding runs against the shipments example, through a real MCP client over memory streams."""
import pytest

pytest.importorskip("mcp")

from mcp.client import Client

from ambassador_agent import Unknown
from ambassador_agent.bindings.mcp import build_server, tool_descriptions
from examples.shipments import FakeCourier, build_ambassador

PRINCIPAL = {"subject": "core", "on_behalf_of": "customer-1", "scopes": ["shipments:read", "shipments:write"]}
ORDER = {"order_number": "O-1", "destination": "12 High Street"}


async def call(server, name, **arguments):
    async with Client(server) as client:
        return await client.call_tool(name, arguments)


def test_every_capability_is_a_tool_with_hints_from_its_contract():
    tools = {t["name"]: t for t in tool_descriptions(build_ambassador(FakeCourier()))}
    assert set(tools) == {"book_shipment", "cancel_shipment", "shipment_status"}
    assert tools["shipment_status"]["annotations"]["readOnlyHint"] is True
    assert tools["book_shipment"]["annotations"]["readOnlyHint"] is False
    assert "Never retry an unknown" in tools["book_shipment"]["description"]


async def test_a_booking_through_the_tool_succeeds_and_hides_the_vendor_dialect():
    office = FakeCourier()
    result = await call(build_server(build_ambassador(office)), "book_shipment", payload=ORDER, idempotency_key="k1", principal=PRINCIPAL)
    assert not result.is_error
    assert result.structured_content["outcome"] == "succeeded"
    assert "STAT_CD" not in str(result.structured_content["data"])
    assert office.created == 1


async def test_a_repeat_with_the_same_key_is_answered_from_the_record():
    office = FakeCourier()
    server = build_server(build_ambassador(office))
    await call(server, "book_shipment", payload=ORDER, idempotency_key="k1", principal=PRINCIPAL)
    again = await call(server, "book_shipment", payload=ORDER, idempotency_key="k1", principal=PRINCIPAL)
    assert again.structured_content["replayed"] is True
    assert office.created == 1


async def test_a_refusal_is_an_error_result_not_a_success():
    server = build_server(build_ambassador(FakeCourier()))
    result = await call(server, "book_shipment", payload=ORDER, principal={"subject": "core", "scopes": ["shipments:read"]})
    assert result.is_error
    assert result.structured_content["outcome"] == "rejected"


async def test_an_unknown_outcome_is_an_error_result_that_says_it_is_not_retryable():
    office = FakeCourier()
    office.lose_reply_next = True
    server = build_server(build_ambassador(office, on_unknown=Unknown.STOP))
    result = await call(server, "book_shipment", payload=ORDER, idempotency_key="k1", principal=PRINCIPAL)
    assert result.is_error
    assert result.structured_content["outcome"] == "unknown"
    assert result.structured_content["operation_id"]
    assert "fallback" not in result.structured_content  # no other channel while the outcome is unknown
    # a client that retries under a new key meets the held resource and does not book a second time
    retry = await call(server, "book_shipment", payload=ORDER, idempotency_key="k2", principal=PRINCIPAL)
    assert retry.structured_content["outcome"] == "rejected"
    assert retry.structured_content["error"]["code"] == "resource_held"
    assert office.created == 1


async def test_the_principal_comes_from_the_resolver_when_one_is_given():
    from ambassador_agent import Principal

    server = build_server(build_ambassador(FakeCourier()), principal_resolver=lambda _claimed: Principal("session-user", scopes=frozenset({"shipments:write"})))
    result = await call(server, "book_shipment", payload=ORDER, principal={"subject": "someone-else"})
    assert result.structured_content["outcome"] == "succeeded"
