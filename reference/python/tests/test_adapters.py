"""Smoke tests for the reference adapters. Each is skipped if its SDK is not installed."""
import pytest

from examples.shipments import FakeCourier, build_ambassador

PRINCIPAL = {"subject": "core", "on_behalf_of": "customer-1", "scopes": ["shipments:read", "shipments:write"]}


async def test_langgraph_node_runs_in_a_graph():
    pytest.importorskip("langgraph")
    from typing import Any, TypedDict

    from langgraph.graph import END, START, StateGraph

    from ambassador_agent.adapters.langgraph import ambassador_node

    class State(TypedDict, total=False):
        boundary_request: dict[str, Any]
        boundary_result: dict[str, Any]

    graph = StateGraph(State)
    graph.add_node("courier", ambassador_node(build_ambassador(FakeCourier())))
    graph.add_edge(START, "courier")
    graph.add_edge("courier", END)
    out = await graph.compile().ainvoke(
        {"boundary_request": {"capability": "book_shipment", "payload": {"order_number": "O-9"}, "principal": PRINCIPAL}}
    )
    assert out["boundary_result"]["outcome"] == "succeeded"


async def test_adk_tools_expose_capabilities():
    pytest.importorskip("google.adk")
    from types import SimpleNamespace

    from ambassador_agent.adapters.adk import ambassador_tools

    tools = ambassador_tools(build_ambassador(FakeCourier()))
    assert [t.name for t in tools] == ["book_shipment", "cancel_shipment", "shipment_status"]
    declaration = tools[0]._get_declaration()
    assert declaration.parameters_json_schema["required"] == ["order_number"]

    ctx = SimpleNamespace(
        state={"principal_subject": "core", "principal_on_behalf_of": "customer-1", "principal_scopes": ["shipments:write"]},
        function_call_id="call-1",
        invocation_id="inv-1",
    )
    out = await tools[0].run_async(args={"order_number": "O-9"}, tool_context=ctx)
    assert out["outcome"] == "succeeded"


async def test_a2a_card_and_executor():
    pytest.importorskip("a2a")
    from types import SimpleNamespace

    from a2a.helpers import get_data_parts, new_data_message
    from a2a.types import Role

    from ambassador_agent.bindings.a2a import AmbassadorExecutor, agent_card

    amb = build_ambassador(FakeCourier())
    card = agent_card(amb, url="https://example.org/a2a/courier")
    assert card.name == "courier-ambassador"
    assert [s.id for s in card.skills] == ["book_shipment", "cancel_shipment", "shipment_status"]

    sent = []

    class Queue:
        async def enqueue_event(self, event):
            sent.append(event)

    message = new_data_message(
        {"capability": "book_shipment", "payload": {"order_number": "O-9"}, "principal": PRINCIPAL}, role=Role.ROLE_USER
    )
    context = SimpleNamespace(message=message, task_id="t1", context_id="c1")
    await AmbassadorExecutor(amb).execute(context, Queue())
    reply = get_data_parts(sent[0].parts)[0]
    assert reply["outcome"] == "succeeded" and reply["data"]["status"] == "booked"
