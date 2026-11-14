"""Ports: everything the ambassador depends on, as abstract interfaces.

Swap any of these without touching the ambassador or the core system.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol, runtime_checkable

from .model import ActionRequest, ActionResult, BoundaryError, Capability, Notice, Principal


class TransientError(Exception):
    """The external system failed in a way that may succeed on retry.

    `may_have_executed` says whether the action could have taken effect anyway. A timeout after
    the request was sent could have; a refused connection could not. When in doubt leave it True:
    the ambassador then reconciles before it retries or offers another channel.
    """

    def __init__(self, message: str = "", *, may_have_executed: bool = True):
        super().__init__(message)
        self.may_have_executed = may_have_executed


class PermanentError(Exception):
    """The external system refused or cannot do this. Retrying will not help."""

    def __init__(self, message: str, code: str = "external_refused"):
        super().__init__(message)
        self.code = code


class LeaseLost(Exception):
    """A write was refused because the replica no longer holds the lease it carries a token for.

    Raised by a journal that checks the fencing token in the same atomic step as the write. Nothing was written.
    """


@runtime_checkable
class Connector(Protocol):
    """Deterministic access to the external system (REST, SOAP, queue, MCP tool, another agent...)."""

    async def invoke(self, operation: str, payload: Mapping[str, Any], credentials: Mapping[str, Any]) -> Mapping[str, Any]: ...

    async def healthy(self) -> bool: ...


class CredentialBroker(Protocol):
    """Turns the caller's identity into credentials the external system accepts."""

    async def credentials_for(self, principal: Principal, capability: Capability) -> Mapping[str, Any]: ...


class PrincipalVerifier(Protocol):
    """Establishes who a task is for, from proof the caller cannot make up.

    Return the verified Principal (its scopes come from the proof, not from the task), or a string
    saying why the principal is not accepted. The string goes to the journal and not to the caller.
    """

    async def verify(self, request: ActionRequest) -> Principal | str: ...


class Policy(Protocol):
    """Decides whether a task may cross the boundary. Return None to allow, or a reason to refuse."""

    def refuse_reason(self, request: ActionRequest, capability: Capability) -> str | None: ...


class Journal(Protocol):
    """The durable record of every crossing. Must survive a restart.

    `begin` is called before the external system is touched and `finish` after. An intent
    that was begun and never finished is an action whose outcome is unknown.

    A finished intent whose outcome is "unknown" stays listed by `unresolved` until `resolve`
    is called with what was found out. Both are the manual-exception path.
    """

    async def begin(self, intent: Mapping[str, Any]) -> str: ...

    async def finish(self, intent_id: str, outcome: Mapping[str, Any]) -> None: ...

    async def unfinished(self) -> list[Mapping[str, Any]]: ...

    async def record(self, entry: Mapping[str, Any]) -> None: ...

    async def recall(self, idempotency_key: str) -> ActionResult | None: ...

    async def remember(self, idempotency_key: str, result: ActionResult) -> None: ...

    async def unresolved(self) -> list[Mapping[str, Any]]: ...

    async def resolve(self, operation_id: str, result: ActionResult, by: str, note: str) -> None: ...


class Leases(Protocol):
    """Mutual exclusion per resource between replicas: a time-limited lease that carries a fencing token.

    `acquire` returns a token, or None while another replica holds an unexpired lease. Tokens for one resource only
    grow, and a lease that lapsed is given to the next caller with a higher token. A journal that implements this
    (see `SqliteJournal`) can check the token in the same atomic step as its write, which is what makes a stalled
    replica harmless once another has taken over. The external system can check it too.
    """

    async def acquire(self, resource: str, holder: str, ttl_seconds: float) -> int | None: ...

    async def renew(self, resource: str, holder: str, token: int, ttl_seconds: float) -> bool: ...

    async def release(self, resource: str, holder: str, token: int) -> None: ...


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
