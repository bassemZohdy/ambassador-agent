"""Experimental binding: A2A (a2a-sdk 1.x). Requires `pip install ambassador-agent[a2a]`.

Wire contract used by this binding: the caller sends a message with one data part
    {"capability": str, "payload": {...}, "idempotency_key"?: str,
     "principal": {"subject": str, "on_behalf_of"?: str, "scopes"?: [str]}}
and receives a message with one data part holding `ActionResult.to_dict()`.

In production, derive the principal from the authenticated call context instead of
trusting the message body: pass your own `principal_resolver`.
"""
from __future__ import annotations

from typing import Any, Callable, Mapping

from a2a.helpers import get_data_parts, new_data_message
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.types import AgentCapabilities, AgentCard, AgentInterface, AgentSkill

from ..ambassador import Ambassador
from ..model import ActionRequest, Principal

PrincipalResolver = Callable[[RequestContext, Mapping[str, Any]], Principal]


def agent_card(ambassador: Ambassador, url: str, protocol_binding: str = "JSONRPC") -> AgentCard:
    """Map the ambassador's neutral description to an A2A agent card."""
    d = ambassador.describe()
    return AgentCard(
        name=d["name"],
        description=d["description"] or f"Ambassador for {d['boundary']}",
        version=d["version"],
        supported_interfaces=[AgentInterface(url=url, protocol_binding=protocol_binding)],
        capabilities=AgentCapabilities(),
        default_input_modes=["application/json"],
        default_output_modes=["application/json"],
        skills=[
            AgentSkill(
                id=c["name"],
                name=c["name"],
                description=c["description"],
                tags=["ambassador", d["boundary"], "side-effect" if c["side_effect"] else "read-only", "compensation:" + c["compensation"]],
            )
            for c in d["capabilities"]
        ],
    )


def _principal_from_body(_context: RequestContext, body: Mapping[str, Any]) -> Principal:
    who = body.get("principal") or {}
    return Principal(who.get("subject", "anonymous"), who.get("on_behalf_of"), frozenset(who.get("scopes", ())))


class AmbassadorExecutor(AgentExecutor):
    """Serves an ambassador as an A2A agent."""

    def __init__(self, ambassador: Ambassador, principal_resolver: PrincipalResolver = _principal_from_body):
        self._ambassador = ambassador
        self._principal_resolver = principal_resolver

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        parts = get_data_parts(context.message.parts) if context.message else []
        body = parts[0] if parts and isinstance(parts[0], Mapping) else None
        if body is None or "capability" not in body:
            reply: dict[str, Any] = {
                "outcome": "rejected",
                "error": {"code": "bad_request", "message": "expected one data part with a 'capability' field", "retryable": False},
            }
        else:
            request = ActionRequest(
                capability=body["capability"],
                payload=body.get("payload") or {},
                principal=self._principal_resolver(context, body),
                idempotency_key=body.get("idempotency_key"),
                correlation_id=context.task_id,
            )
            reply = (await self._ambassador.perform(request)).to_dict()
        await event_queue.enqueue_event(new_data_message(reply, context_id=context.context_id, task_id=context.task_id))

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        raise NotImplementedError("actions are short-lived; there is nothing to cancel")
