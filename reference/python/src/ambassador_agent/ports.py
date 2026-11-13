"""Ports: everything the ambassador depends on, as abstract interfaces.

Swap any of these without touching the ambassador or the core system.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol, runtime_checkable

from .model import ActionRequest, ActionResult, BoundaryError, Capability, Notice, Principal


class TransientError(Exception):
    """The external system failed in a way that may succeed on retry."""


class PermanentError(Exception):
    """The external system refused or cannot do this. Retrying will not help."""

    def __init__(self, message: str, code: str = "external_refused"):
        super().__init__(message)
        self.code = code


@runtime_checkable
class Connector(Protocol):
    """Deterministic access to the external system (REST, SOAP, queue, MCP tool, another agent...)."""

    async def invoke(self, operation: str, payload: Mapping[str, Any], credentials: Mapping[str, Any]) -> Mapping[str, Any]: ...

    async def healthy(self) -> bool: ...


class CredentialBroker(Protocol):
    """Turns the caller's identity into credentials the external system accepts."""

    async def credentials_for(self, principal: Principal, capability: Capability) -> Mapping[str, Any]: ...


class Policy(Protocol):
    """Decides whether a task may cross the boundary. Return None to allow, or a reason to refuse."""

    def refuse_reason(self, request: ActionRequest, capability: Capability) -> str | None: ...


class Journal(Protocol):
    """The durable record of every crossing. Must survive a restart.

    `begin` is called before the external system is touched and `finish` after. An intent
    that was begun and never finished is an action whose outcome is unknown.
    """

    async def begin(self, intent: Mapping[str, Any]) -> str: ...

    async def finish(self, intent_id: str, outcome: Mapping[str, Any]) -> None: ...

    async def unfinished(self) -> list[Mapping[str, Any]]: ...

    async def record(self, entry: Mapping[str, Any]) -> None: ...

    async def recall(self, idempotency_key: str) -> ActionResult | None: ...

    async def remember(self, idempotency_key: str, result: ActionResult) -> None: ...


class Sanitizer(Protocol):
    """Cleans data arriving from outside before any core agent can read it."""

    def clean(self, data: Mapping[str, Any]) -> Mapping[str, Any]: ...


class Subscriber(Protocol):
    """A subscription the core system opened. Notices are delivered here."""

    async def notify(self, notice: Notice) -> None: ...


@dataclass(frozen=True)
class Advice:
    """What a reasoner recommends after a failure."""

    action: str  # "retry" | "fallback" | "fail"
    rationale: str = ""


class Reasoner(Protocol):
    """Optional intelligence. Absent when scripted; prefer a fast, low-latency model."""

    async def advise(self, request: ActionRequest, error: BoundaryError, attempts: int) -> Advice: ...

    async def think(self, instruction: str, context: Mapping[str, Any]) -> Mapping[str, Any]: ...
