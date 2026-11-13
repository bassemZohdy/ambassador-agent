"""A durable journal on SQLite (standard library only).

Unlike `InMemoryJournal`, this one survives a restart: open the same file from a new process and
`unfinished()` returns the intents the old one began and never finished. It is a single-writer
journal for one ambassador process. Running replicas needs a shared store with a claim on each
open intent; see the pattern's section on more than one replica.
"""
from __future__ import annotations

import json
import sqlite3
import time
from typing import Any, Mapping

from .model import ActionResult, BoundaryError, Fallback, Outcome

_SCHEMA = """
CREATE TABLE IF NOT EXISTS intents (id INTEGER PRIMARY KEY AUTOINCREMENT, body TEXT NOT NULL, open INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS log (id INTEGER PRIMARY KEY AUTOINCREMENT, body TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS results (key TEXT PRIMARY KEY, body TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS unresolved (operation_id TEXT PRIMARY KEY, body TEXT NOT NULL);
"""


def _dump(result: ActionResult) -> str:
    return json.dumps(result.to_dict())


def _load(text: str) -> ActionResult:
    d = json.loads(text)
    e, f = d.get("error"), d.get("fallback")
    return ActionResult(
        Outcome(d["outcome"]),
        d.get("data", {}),
        BoundaryError(e["code"], e["message"], e.get("retryable", False), e.get("retry_after_seconds")) if e else None,
        Fallback(f["channel"], f["instructions"]) if f else None,
        d.get("attempts", 0),
        False,
        d.get("operation_id"),
    )


class SqliteJournal:
    """Every method commits before it returns, so a crash never loses an acknowledged write."""

    def __init__(self, path: str):
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.executescript(_SCHEMA)
        self._db.commit()

    def close(self) -> None:
        self._db.close()

    @property
    def entries(self) -> list[dict[str, Any]]:
        return [json.loads(body) for (body,) in self._db.execute("SELECT body FROM log ORDER BY id")]

    def _log(self, entry: Mapping[str, Any]) -> None:
        self._db.execute("INSERT INTO log (body) VALUES (?)", (json.dumps({**entry, "at": time.time()}, default=str),))

    async def begin(self, intent: Mapping[str, Any]) -> str:
        cur = self._db.execute("INSERT INTO intents (body) VALUES (?)", ("{}",))
        intent_id = f"intent-{cur.lastrowid}"
        entry = {**intent, "kind": "intent", "intent_id": intent_id, "at": time.time()}
        self._db.execute("UPDATE intents SET body = ? WHERE id = ?", (json.dumps(entry, default=str), cur.lastrowid))
        self._log(entry)
        self._db.commit()
        return intent_id

    async def finish(self, intent_id: str, outcome: Mapping[str, Any]) -> None:
        row_id = int(intent_id.split("-", 1)[1])
        (body,) = self._db.execute("SELECT body FROM intents WHERE id = ?", (row_id,)).fetchone()
        self._db.execute("UPDATE intents SET open = 0 WHERE id = ?", (row_id,))
        self._log({**outcome, "kind": "outcome", "intent_id": intent_id})
        if outcome.get("outcome") == "unknown":
            entry = {**json.loads(body), **outcome}
            self._db.execute("INSERT OR REPLACE INTO unresolved (operation_id, body) VALUES (?, ?)", (entry["operation_id"], json.dumps(entry, default=str)))
        self._db.commit()

    async def unfinished(self) -> list[Mapping[str, Any]]:
        return [json.loads(body) for (body,) in self._db.execute("SELECT body FROM intents WHERE open = 1 ORDER BY id")]

    async def record(self, entry: Mapping[str, Any]) -> None:
        self._log(entry)
        self._db.commit()

    async def recall(self, idempotency_key: str) -> ActionResult | None:
        row = self._db.execute("SELECT body FROM results WHERE key = ?", (idempotency_key,)).fetchone()
        return _load(row[0]) if row else None

    async def remember(self, idempotency_key: str, result: ActionResult) -> None:
        self._db.execute("INSERT OR REPLACE INTO results (key, body) VALUES (?, ?)", (idempotency_key, _dump(result)))
        self._db.commit()

    async def unresolved(self) -> list[Mapping[str, Any]]:
        return [json.loads(body) for (body,) in self._db.execute("SELECT body FROM unresolved ORDER BY rowid")]

    async def resolve(self, operation_id: str, result: ActionResult, by: str, note: str) -> None:
        (body,) = self._db.execute("SELECT body FROM unresolved WHERE operation_id = ?", (operation_id,)).fetchone()
        entry = json.loads(body)
        self._db.execute("DELETE FROM unresolved WHERE operation_id = ?", (operation_id,))
        self._log({"kind": "resolution", "operation_id": operation_id, "outcome": result.outcome.value, "by": by, "note": note})
        key = entry.get("idempotency_key")
        if key:
            if result.outcome is Outcome.SUCCEEDED:
                self._db.execute("INSERT OR REPLACE INTO results (key, body) VALUES (?, ?)", (key, _dump(result)))
            else:
                self._db.execute("DELETE FROM results WHERE key = ?", (key,))
        self._db.commit()
