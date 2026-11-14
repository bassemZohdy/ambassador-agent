"""A durable journal on SQLite (standard library only).

Unlike `InMemoryJournal`, this one survives a restart: open the same file from a new process and
`unfinished()` returns the intents the old one began and never finished. Several
replicas may open the same file. It then also keeps the leases between them (`leases` table), and checks the
fencing token in the same transaction as the write: see the pattern's section on more than one replica.
"""
from __future__ import annotations

import json
import sqlite3
import time
from typing import Any, Callable, Mapping

from .model import ActionResult, BoundaryError, Fallback, Outcome
from .ports import LeaseLost

_SCHEMA = """
CREATE TABLE IF NOT EXISTS intents (id INTEGER PRIMARY KEY AUTOINCREMENT, body TEXT NOT NULL, open INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS log (id INTEGER PRIMARY KEY AUTOINCREMENT, body TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS results (key TEXT PRIMARY KEY, body TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS unresolved (operation_id TEXT PRIMARY KEY, body TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS leases (resource TEXT PRIMARY KEY, holder TEXT, token INTEGER NOT NULL, expires_at REAL NOT NULL);
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
    """Every method commits before it returns, so a crash never loses an acknowledged write.

    `clock` is where lease expiry reads the time. Replicas on one host share a clock; replicas on several hosts need
    clocks that agree to well within the lease, or a store that keeps the time itself.
    """

    def __init__(self, path: str, *, clock: Callable[[], float] = time.time):
        self._db = sqlite3.connect(path, check_same_thread=False, timeout=10.0)
        self._db.execute("PRAGMA journal_mode=WAL")  # a reader never blocks the replica that is writing
        self._db.executescript(_SCHEMA)
        self._db.commit()
        self._clock = clock

    def close(self) -> None:
        self._db.close()

    @property
    def entries(self) -> list[dict[str, Any]]:
        return [json.loads(body) for (body,) in self._db.execute("SELECT body FROM log ORDER BY id")]

    def _log(self, entry: Mapping[str, Any]) -> None:
        self._db.execute("INSERT INTO log (body) VALUES (?)", (json.dumps({**entry, "at": time.time()}, default=str),))

    # ---- leases: one holder per resource, a token that only grows ----------

    async def acquire(self, resource: str, holder: str, ttl_seconds: float) -> int | None:
        now = self._clock()
        self._db.execute("BEGIN IMMEDIATE")  # read and write as one step: two replicas cannot both see "free"
        try:
            row = self._db.execute("SELECT holder, token, expires_at FROM leases WHERE resource = ?", (resource,)).fetchone()
            if row is not None and row[0] is not None and row[2] > now:
                self._db.rollback()
                return None
            token = (row[1] if row else 0) + 1  # the token is kept after a release, so the next one is higher
            self._db.execute(
                "INSERT INTO leases (resource, holder, token, expires_at) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(resource) DO UPDATE SET holder = excluded.holder, token = excluded.token, expires_at = excluded.expires_at",
                (resource, holder, token, now + ttl_seconds),
            )
            self._db.commit()
            return token
        except BaseException:
            self._db.rollback()
            raise

    async def renew(self, resource: str, holder: str, token: int, ttl_seconds: float) -> bool:
        cur = self._db.execute(
            "UPDATE leases SET expires_at = ? WHERE resource = ? AND holder = ? AND token = ? AND expires_at > ?",
            (self._clock() + ttl_seconds, resource, holder, token, self._clock()),
        )
        self._db.commit()
        return cur.rowcount == 1  # False: it lapsed, and may already belong to someone else

    async def release(self, resource: str, holder: str, token: int) -> None:
        self._db.execute("UPDATE leases SET holder = NULL, expires_at = 0 WHERE resource = ? AND holder = ? AND token = ?", (resource, holder, token))
        self._db.commit()

    def _require_lease(self, resource: str, token: int, *, unexpired: bool) -> None:
        """Inside the caller's transaction: refuse the write unless this token is still the newest for the resource."""
        row = self._db.execute("SELECT holder, token, expires_at FROM leases WHERE resource = ?", (resource,)).fetchone()
        if row is None or row[1] != token or row[0] is None or (unexpired and row[2] <= self._clock()):
            self._db.rollback()
            raise LeaseLost(f"the lease on '{resource}' (token {token}) is no longer held")

    async def begin(self, intent: Mapping[str, Any]) -> str:
        self._db.execute("BEGIN IMMEDIATE")
        if intent.get("fencing_token") is not None:
            # An intent may only be opened under a live lease: a replica that stalled past its lease cannot start a crossing.
            self._require_lease(intent.get("resource") or "*", int(intent["fencing_token"]), unexpired=True)
        cur = self._db.execute("INSERT INTO intents (body) VALUES (?)", ("{}",))
        intent_id = f"intent-{cur.lastrowid}"
        entry = {**intent, "kind": "intent", "intent_id": intent_id, "at": time.time()}
        self._db.execute("UPDATE intents SET body = ? WHERE id = ?", (json.dumps(entry, default=str), cur.lastrowid))
        self._log(entry)
        self._db.commit()
        return intent_id

    async def finish(self, intent_id: str, outcome: Mapping[str, Any]) -> None:
        row_id = int(intent_id.split("-", 1)[1])
        self._db.execute("BEGIN IMMEDIATE")
        (body,) = self._db.execute("SELECT body FROM intents WHERE id = ?", (row_id,)).fetchone()
        if outcome.get("fencing_token") is not None:
            # The outcome may be recorded unless another replica has since taken the resource over and so owns recovery.
            self._require_lease(json.loads(body).get("resource") or "*", int(outcome["fencing_token"]), unexpired=False)
        closed = self._db.execute("UPDATE intents SET open = 0 WHERE id = ? AND open = 1", (row_id,))
        if closed.rowcount == 0:
            self._db.rollback()
            raise LeaseLost(f"{intent_id} was already settled by another replica")
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
