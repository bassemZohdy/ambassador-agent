"""Domain-side vocabulary of the pattern. No platform or protocol types appear here."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable, Mapping


class Intelligence(str, Enum):
    """How much a model is used. The contract is identical at every level."""

    SCRIPTED = "scripted"  # no model at all
    ASSISTED = "assisted"  # a model is consulted on failures only
    AUTONOMOUS = "autonomous"  # a model may plan the steps inside a capability


class Outcome(str, Enum):
    """Every task ends in exactly one of these. A task never pauses.

    An outcome says only what is known about the action. What to do next (a fallback channel,
    a retry hint, who must reconcile) travels beside it and never replaces it.
    """

    SUCCEEDED = "succeeded"  # the action was carried out
    FAILED = "failed"  # known not to have been carried out
    REJECTED = "rejected"  # refused before the boundary was crossed
    UNKNOWN = "unknown"  # may or may not have been carried out; it must be reconciled


class Unknown(str, Enum):
    """How a capability reconciles an action whose outcome was never recorded."""

    VERIFY = "verify"  # ask the external system whether it received the operation id
    RESEND = "resend"  # safe only if the external system ignores a repeated operation id
    STOP = "stop"  # the external system can do neither: report unknown, a person resolves it


class Compensation(str, Enum):
    """Whether a capability's business effect can be reversed. Compensation is not undo."""

    COMPENSABLE = "compensable"
    PARTLY = "partly"
    NOT = "not"


@dataclass(frozen=True)
class Principal:
    """Who the task is for. Travels with every request so the ambassador never acts as itself by accident."""

    subject: str
    on_behalf_of: str | None = None
    scopes: frozenset[str] = frozenset()
    claims: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Fallback:
    """Another way to finish the job when the external system cannot."""

    channel: str
    instructions: str


@dataclass(frozen=True)
class BoundaryError:
    code: str
    message: str
    retryable: bool = False
    retry_after_seconds: float | None = None  # set when a task is refused for load


@dataclass(frozen=True)
class ActionRequest:
    """A task: one capability, for one principal. Only the core system creates these."""

    capability: str
    payload: Mapping[str, Any]
    principal: Principal
    idempotency_key: str | None = None
    correlation_id: str | None = None


@dataclass(frozen=True)
class ActionResult:
    outcome: Outcome
    data: Mapping[str, Any] = field(default_factory=dict)
    error: BoundaryError | None = None
    fallback: Fallback | None = None
    attempts: int = 0
    replayed: bool = False  # True when served from the idempotency record
    operation_id: str | None = None  # the identifier the external system saw; the handle for reconciling

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"outcome": self.outcome.value, "data": dict(self.data), "attempts": self.attempts}
        if self.error:
            out["error"] = {"code": self.error.code, "message": self.error.message, "retryable": self.error.retryable}
            if self.error.retry_after_seconds is not None:
                out["error"]["retry_after_seconds"] = self.error.retry_after_seconds
        if self.fallback:
            out["fallback"] = {"channel": self.fallback.channel, "instructions": self.fallback.instructions}
        if self.replayed:
            out["replayed"] = True
        if self.operation_id:
            out["operation_id"] = self.operation_id
        return out


@dataclass(frozen=True)
class ExternalEvent:
    """Something the external system told us, still in its own shape and still untrusted."""

    type: str
    payload: Mapping[str, Any]
    event_id: str | None = None


@dataclass(frozen=True)
class Notice:
    """The same fact in the core system's language, sanitised. A notice is a fact, never a command."""

    type: str
    payload: Mapping[str, Any]
    source_boundary: str = ""
    event_id: str | None = None


# A handler is the boundary-specific procedure. It receives a BoundaryContext
# (connector, credentials, optional reasoner) and the domain payload.
Handler = Callable[[Any, Mapping[str, Any]], Awaitable[Mapping[str, Any]]]
# A verifier asks the external system about an earlier action. It returns the
# domain-shaped result if the action was received, or None if it was not.
Verifier = Callable[[Any, Mapping[str, Any]], Awaitable["Mapping[str, Any] | None"]]
EventTranslator = Callable[[ExternalEvent], "Notice | None"]
ResourceKey = Callable[[Mapping[str, Any]], str]


@dataclass(frozen=True)
class Capability:
    """One thing the core system may ask of this boundary, named in the core system's language."""

    name: str
    description: str
    handler: Handler
    input_schema: Mapping[str, Any] = field(default_factory=lambda: {"type": "object"})
    side_effect: bool = True
    required_scopes: frozenset[str] = frozenset()
    fallback: Fallback | None = None
    # Admission: tasks with the same resource key run one at a time. None means the whole boundary.
    resource: ResourceKey | None = None
    # Journal: what to do when an intent has no recorded outcome.
    on_unknown: Unknown = Unknown.STOP
    verify: Verifier | None = None
    # Contract: whether the business effect can be reversed, and by which capability.
    compensation: Compensation = Compensation.NOT
    compensated_by: str | None = None
    # Reconciliation preconditions for `verify`. A lookup that finds no record proves the action will never
    # happen only if the external system rejects late requests, or the settle window has outlived any request in flight.
    absence_is_final: bool = False
    settle_after_seconds: float = 0.0  # wait this long after sending before believing a lookup
    # Governance (optional, declarative): carried in the contract so owners and reviewers can see them.
    data_classification: str | None = None
    audit_retention_days: int | None = None
    requires_approval: bool = False  # the principal must hold the scope "approval:<capability>"

    def __post_init__(self) -> None:
        if self.on_unknown is Unknown.VERIFY and self.verify is None:
            raise ValueError(f"capability '{self.name}' declares on_unknown=verify but has no verifier")
        if self.settle_after_seconds < 0:
            raise ValueError(f"capability '{self.name}' has a negative settle window")
        if self.absence_is_final and self.on_unknown is not Unknown.VERIFY:
            raise ValueError(f"capability '{self.name}' says absence is final but does not verify")
        if self.compensation is Compensation.NOT and self.compensated_by:
            raise ValueError(f"capability '{self.name}' names a compensating capability but is not compensable")


@dataclass(frozen=True)
class AmbassadorSpec:
    """What the ambassador represents and who answers for it."""

    name: str
    boundary: str  # the external system or logical group it represents
    owner: str  # the accountable team or person
    description: str = ""
    intelligence: Intelligence = Intelligence.SCRIPTED
    version: str = "0.2.0"
