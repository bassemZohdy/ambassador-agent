"""In-memory defaults so the pattern runs with zero infrastructure. Replace in production."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import time
from typing import Any, Callable, Mapping

from .model import ActionRequest, ActionResult, Capability, Notice, Outcome, Principal


class StaticCredentials:
    def __init__(self, credentials: Mapping[str, Any] | None = None):
        self._credentials = dict(credentials or {})

    async def credentials_for(self, principal: Principal, capability: Capability) -> Mapping[str, Any]:
        return {**self._credentials, "on_behalf_of": principal.on_behalf_of or principal.subject}


class HmacDelegations:
    """Signed delegations, using the standard library only. A stand-in for a real token service.

    A delegation says: this caller may act for this principal, with these scopes, for this ambassador,
    until this time. In production use the tokens your identity provider issues (a signed JWT, an
    OAuth token exchange) and the same checks. The point here is the checks, not the encoding.
    """

    def __init__(self, secret: bytes, audience: str, clock: Callable[[], float] = time.time) -> None:
        self._secret = secret
        self.audience = audience
        self._clock = clock

    def issue(
        self,
        *,
        caller: str,
        subject: str,
        on_behalf_of: str | None = None,
        scopes: frozenset[str] | set[str] = frozenset(),
        ttl_seconds: float = 300.0,
        audience: str | None = None,
    ) -> str:
        claims = {
            "caller": caller,
            "subject": subject,
            "on_behalf_of": on_behalf_of,
            "scopes": sorted(scopes),
            "aud": audience or self.audience,
            "exp": self._clock() + ttl_seconds,
        }
        body = base64.urlsafe_b64encode(json.dumps(claims, sort_keys=True).encode())
        return f"{body.decode()}.{self._sign(body)}"

    async def verify(self, request: ActionRequest) -> Principal | str:
        if not request.delegation:
            return "no delegation presented"
        if not request.caller:
            return "caller not authenticated"
        body, _, signature = request.delegation.partition(".")
        if not body or not hmac.compare_digest(signature, self._sign(body.encode())):
            return "delegation signature invalid"
        try:
            claims = json.loads(base64.urlsafe_b64decode(body.encode()))
            expires, audience, caller = float(claims["exp"]), claims["aud"], claims["caller"]
            subject, on_behalf_of, scopes = claims["subject"], claims.get("on_behalf_of"), frozenset(claims["scopes"])
        except (ValueError, KeyError, TypeError):
            return "delegation unreadable"
        if expires <= self._clock():
            return "delegation expired"
        if audience != self.audience:
            return f"delegation issued for another ambassador ({audience})"
        if caller != request.caller:
            return "delegation issued to another caller"
        asserted = request.principal
        if (asserted.subject, asserted.on_behalf_of) != (subject, on_behalf_of):
            return "task names a different principal than the delegation"
        return Principal(subject=subject, on_behalf_of=on_behalf_of, scopes=scopes, claims={"caller": caller})

    def _sign(self, body: bytes) -> str:
        return base64.urlsafe_b64encode(hmac.new(self._secret, body, hashlib.sha256).digest()).decode()


class ScopePolicy:
    """Refuses a task unless the principal holds every scope the capability requires."""

    def refuse_reason(self, request: ActionRequest, capability: Capability) -> str | None:
        required = capability.required_scopes
        if capability.requires_approval:
            required = required | {f"approval:{capability.name}"}  # the approval itself is granted outside the ambassador
        missing = required - request.principal.scopes
        return f"missing scopes: {sorted(missing)}" if missing else None


class InMemoryJournal:
    """A journal that lives in memory. It shows the contract; it does NOT survive a restart.

    A real journal must be durable: the whole point of recording an intent is to find it again
    after the process has died. Pass the same instance to a new Ambassador to simulate a restart.
    """

    def __init__(self) -> None:
        self.entries: list[dict[str, Any]] = []
        self._open: dict[str, dict[str, Any]] = {}
        self._results: dict[str, ActionResult] = {}
        self._unresolved: dict[str, dict[str, Any]] = {}
        self._sequence = 0

    async def begin(self, intent: Mapping[str, Any]) -> str:
        self._sequence += 1
        intent_id = f"intent-{self._sequence}"
        entry = {**intent, "kind": "intent", "intent_id": intent_id, "at": time.time()}
        self._open[intent_id] = entry
        self.entries.append(entry)
        return intent_id

    async def finish(self, intent_id: str, outcome: Mapping[str, Any]) -> None:
        intent = self._open.pop(intent_id, None)
        self.entries.append({**outcome, "kind": "outcome", "intent_id": intent_id, "at": time.time()})
        if outcome.get("outcome") == "unknown" and intent is not None:
            self._unresolved[intent["operation_id"]] = {**intent, **outcome}

    async def unfinished(self) -> list[Mapping[str, Any]]:
        return list(self._open.values())

    async def record(self, entry: Mapping[str, Any]) -> None:
        self.entries.append({**entry, "at": time.time()})

    async def recall(self, idempotency_key: str) -> ActionResult | None:
        return self._results.get(idempotency_key)

    async def remember(self, idempotency_key: str, result: ActionResult) -> None:
        self._results[idempotency_key] = result

    async def unresolved(self) -> list[Mapping[str, Any]]:
        return list(self._unresolved.values())

    async def resolve(self, operation_id: str, result: ActionResult, by: str, note: str) -> None:
        entry = self._unresolved.pop(operation_id)
        self.entries.append(
            {"kind": "resolution", "operation_id": operation_id, "outcome": result.outcome.value, "by": by, "note": note, "at": time.time()}
        )
        key = entry.get("idempotency_key")
        if key:
            if result.outcome is Outcome.SUCCEEDED:
                self._results[key] = result  # a repeat of the task now gets the settled answer
            else:
                self._results.pop(key, None)  # confirmed not done: the same key may be tried again


_SUSPECT = re.compile(
    r"(ignore (all |any )?(previous|prior|above) instructions|disregard (the )?(system|previous) prompt|you are now|</?system>)",
    re.IGNORECASE,
)


class QuarantineSanitizer:
    """Baseline quarantine: caps string length and neutralises instruction-like text.

    This is a floor, not a defence in depth. Treat everything from outside as data, never as instructions.
    """

    def __init__(self, max_len: int = 4000):
        self.max_len = max_len

    def clean(self, data: Mapping[str, Any]) -> Mapping[str, Any]:
        return {k: self._clean(v) for k, v in data.items()}

    def _clean(self, value: Any) -> Any:
        if isinstance(value, str):
            return _SUSPECT.sub("[removed]", value[: self.max_len])
        if isinstance(value, Mapping):
            return {k: self._clean(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [self._clean(v) for v in value]
        return value


class ListSubscriber:
    """Collects notices in a list. Stands in for a subscription the core system opened."""

    def __init__(self) -> None:
        self.notices: list[Notice] = []

    async def notify(self, notice: Notice) -> None:
        self.notices.append(notice)
