"""Reference adapter: LangGraph. Requires `pip install ambassador-agent[langgraph]`."""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Mapping

from ..ambassador import Ambassador
from ..model import ActionRequest, Principal

State = Mapping[str, Any]


def ambassador_node(
    ambassador: Ambassador,
    *,
    request_key: str = "boundary_request",
    result_key: str = "boundary_result",
) -> Callable[[State], Awaitable[dict[str, Any]]]:
    """Build a graph node that performs the action found at `state[request_key]`.

    The request is a dict: {"capability", "payload", "principal": {"subject", "on_behalf_of", "scopes"},
    "idempotency_key"?, "correlation_id"?}. The node writes the result dict to `state[result_key]`.
    """

    async def node(state: State) -> dict[str, Any]:
        raw = state[request_key]
        who = raw.get("principal", {})
        request = ActionRequest(
            capability=raw["capability"],
            payload=raw.get("payload", {}),
            principal=Principal(who.get("subject", "anonymous"), who.get("on_behalf_of"), frozenset(who.get("scopes", ()))),
            idempotency_key=raw.get("idempotency_key"),
            correlation_id=raw.get("correlation_id"),
        )
        result = await ambassador.perform(request)
        return {result_key: result.to_dict()}

    return node
