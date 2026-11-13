"""Experimental adapter: Google ADK. Requires `pip install ambassador-agent[adk]`.

Exposes each capability as an ADK tool, so a core ADK agent sees domain-named tools and
never the external system behind them.
"""
from __future__ import annotations

from typing import Any, Callable

from google.adk.tools import BaseTool
from google.adk.tools.tool_context import ToolContext
from google.genai import types

from ..ambassador import Ambassador
from ..model import ActionRequest, Capability, Principal

PrincipalResolver = Callable[[ToolContext], Principal]


def _default_principal(tool_context: ToolContext) -> Principal:
    """Reads the caller from session state. Replace with your identity propagation."""
    state = tool_context.state
    return Principal(
        subject=state.get("principal_subject", "anonymous"),
        on_behalf_of=state.get("principal_on_behalf_of"),
        scopes=frozenset(state.get("principal_scopes", ())),
    )


class CapabilityTool(BaseTool):
    def __init__(self, ambassador: Ambassador, capability: Capability, principal_resolver: PrincipalResolver):
        super().__init__(name=capability.name, description=capability.description)
        self._ambassador = ambassador
        self._capability = capability
        self._principal_resolver = principal_resolver

    def _get_declaration(self) -> types.FunctionDeclaration:
        return types.FunctionDeclaration(
            name=self.name,
            description=self.description,
            parameters_json_schema=dict(self._capability.input_schema),
        )

    async def run_async(self, *, args: dict[str, Any], tool_context: ToolContext) -> Any:
        request = ActionRequest(
            capability=self._capability.name,
            payload=args,
            principal=self._principal_resolver(tool_context),
            # One tool call is one action: a model that repeats the call does not repeat the side effect.
            idempotency_key=getattr(tool_context, "function_call_id", None),
            correlation_id=getattr(tool_context, "invocation_id", None),
        )
        return (await self._ambassador.perform(request)).to_dict()


def ambassador_tools(ambassador: Ambassador, principal_resolver: PrincipalResolver = _default_principal) -> list[BaseTool]:
    """One ADK tool per capability. Pass the list to `Agent(tools=...)`."""
    return [CapabilityTool(ambassador, c, principal_resolver) for c in ambassador.capabilities]
