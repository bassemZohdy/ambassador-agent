"""In-memory defaults so the pattern runs with zero infrastructure. Replace in production."""
from __future__ import annotations

import re
import time
from typing import Any, Mapping

from .model import ActionRequest, ActionResult, Capability, Notice, Principal


class StaticCredentials:
    def __init__(self, credentials: Mapping[str, Any] | None = None):
        self._credentials = dict(credentials or {})

    async def credentials_for(self, principal: Principal, capability: Capability) -> Mapping[str, Any]:
        return {**self._credentials, "on_behalf_of": principal.on_behalf_of or principal.subject}


class ScopePolicy:
    """Refuses a task unless the principal holds every scope the capability requires."""

    def refuse_reason(self, request: ActionRequest, capability: Capability) -> str | None:
        missing = capability.required_scopes - request.principal.scopes
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
        self._sequence = 0

    async def begin(self, intent: Mapping[str, Any]) -> str:
        self._sequence += 1
        intent_id = f"intent-{self._sequence}"
        entry = {**intent, "kind": "intent", "intent_id": intent_id, "at": time.time()}
        self._open[intent_id] = entry
        self.entries.append(entry)
        return intent_id

    async def finish(self, intent_id: str, outcome: Mapping[str, Any]) -> None:
        self._open.pop(intent_id, None)
        self.entries.append({**outcome, "kind": "outcome", "intent_id": intent_id, "at": time.time()})

    async def unfinished(self) -> list[Mapping[str, Any]]:
        return list(self._open.values())

    async def record(self, entry: Mapping[str, Any]) -> None:
        self.entries.append({**entry, "at": time.time()})

    async def recall(self, idempotency_key: str) -> ActionResult | None:
        return self._results.get(idempotency_key)

    async def remember(self, idempotency_key: str, result: ActionResult) -> None:
        self._results[idempotency_key] = result


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
