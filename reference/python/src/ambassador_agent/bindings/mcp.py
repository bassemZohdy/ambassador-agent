"""Experimental binding: MCP (mcp 2.x). Requires `pip install ambassador-agent[mcp]`.

MCP is a poor fit for the pattern's task lifecycle (see docs/protocol-mapping.md#other-bindings):
a tool call is one request and one reply, so this binding suits short tasks for a single agent. It
changes no rule. Each capability becomes one tool, and the tool call opens one task.

Each tool takes
    payload          the capability's input
    idempotency_key  optional; the operation id is derived from it, as for any other binding
    principal        {"subject": str, "on_behalf_of"?: str, "scopes"?: [str]}
    delegation       optional proof that the caller may act for the principal

and returns `ActionResult.to_dict()` as structured content.

Outcomes. `succeeded` is a normal result. `failed`, `rejected` and `unknown` are returned with
`isError` set, because a client must not read them as success. That is also this binding's weakest
point, as it is for A2A: a client that treats every error as retryable may retry an `unknown`. The
reply says `retryable: false` for it, and an ambassador that holds the resource refuses a retry,
even under a new key. A client must never retry an `unknown`.

In production, do not trust the `principal` argument: pass your own `principal_resolver`, which
derives it from the authenticated session, and configure the ambassador with a PrincipalVerifier.
"""
from __future__ import annotations

import json
from typing import Any, Callable, Mapping

from mcp.server.mcpserver import MCPServer
from mcp.types import CallToolResult, TextContent, ToolAnnotations

from ..ambassador import Ambassador
from ..model import ActionRequest, Outcome, Principal

PrincipalResolver = Callable[[Mapping[str, Any] | None], Principal]


def _principal_from_argument(who: Mapping[str, Any] | None) -> Principal:
    who = who or {}
    return Principal(who.get("subject", "anonymous"), who.get("on_behalf_of"), frozenset(who.get("scopes", ())))


def tool_descriptions(ambassador: Ambassador) -> list[dict[str, Any]]:
    """The MCP tool list as plain data: one entry per capability, with hints derived from its contract."""
    d = ambassador.describe()
    return [
        {
            "name": c["name"],
            "description": _describe(c),
            "annotations": {
                "readOnlyHint": not c["side_effect"],
                "destructiveHint": bool(c["side_effect"]) and c["compensation"] == "not",
                "idempotentHint": True,  # every try carries the same operation id
                "openWorldHint": True,
            },
        }
        for c in d["capabilities"]
    ]


def _describe(c: Mapping[str, Any]) -> str:
    text = c["description"] or c["name"]
    notes = [
        "Has a side effect." if c["side_effect"] else "Read-only.",
        f"Compensation: {c['compensation']}.",
        "Ends as succeeded, failed, rejected or unknown. Never retry an unknown.",
    ]
    if c.get("input_schema"):
        notes.append("Payload schema: " + json.dumps(c["input_schema"], sort_keys=True))
    return text + " " + " ".join(notes)


def build_server(
    ambassador: Ambassador,
    *,
    principal_resolver: PrincipalResolver = _principal_from_argument,
) -> MCPServer:
    """Offer every capability of the ambassador as an MCP tool."""
    d = ambassador.describe()
    server = MCPServer(name=d["name"], instructions=d["description"] or f"Ambassador for {d['boundary']}", version=d["version"])
    for c, tool in zip(d["capabilities"], tool_descriptions(ambassador)):
        server.add_tool(
            _make_tool(ambassador, c["name"], principal_resolver),
            name=c["name"],
            description=tool["description"],
            annotations=ToolAnnotations(**tool["annotations"]),
            structured_output=False,
        )
    return server


def _make_tool(ambassador: Ambassador, capability: str, resolve: PrincipalResolver):
    async def call(
        payload: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
        principal: dict[str, Any] | None = None,
        delegation: str | None = None,
    ) -> CallToolResult:
        request = ActionRequest(
            capability=capability,
            payload=payload or {},
            principal=resolve(principal),
            idempotency_key=idempotency_key,
            delegation=delegation,
        )
        result = await ambassador.perform(request)
        reply = result.to_dict()
        return CallToolResult(
            content=[TextContent(type="text", text=json.dumps(reply, sort_keys=True))],
            structuredContent=reply,
            isError=result.outcome is not Outcome.SUCCEEDED,
        )

    call.__name__ = capability
    return call
