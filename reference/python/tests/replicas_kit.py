"""Shared pieces for tests/test_replicas.py: an external system in a file, and a way to build one replica of an ambassador.

The external system lives in its own SQLite file so that a replica running in another process (and killed there) and the
test process see the same bookings, the way two copies of a service see one partner system.
"""
from __future__ import annotations

import asyncio
import os
import sqlite3
from typing import Any, Mapping

from ambassador_agent import (
    ActionRequest,
    Admission,
    Ambassador,
    AmbassadorSpec,
    BoundaryContext,
    Capability,
    Leasing,
    PermanentError,
    Principal,
    Resilience,
    SqliteJournal,
    Unknown,
)

CORE = Principal("core", on_behalf_of="customer-1")


class Office:
    """A partner system that books an order once per client reference and refuses a fencing token older than one it has seen."""

    def __init__(self, path: str, *, die_after_write: bool = False) -> None:
        self._db = sqlite3.connect(path, timeout=10.0, isolation_level=None)  # we manage transactions ourselves
        self._db.execute("CREATE TABLE IF NOT EXISTS bookings (ref TEXT PRIMARY KEY, resource TEXT, token INTEGER)")
        self._db.execute("CREATE TABLE IF NOT EXISTS fences (resource TEXT PRIMARY KEY, newest INTEGER)")
        self.die_after_write = die_after_write  # kill this process once the booking is written, before the reply
        self.active = 0
        self.max_active = 0

    def count(self, resource: str | None = None) -> int:
        sql, args = ("SELECT COUNT(*) FROM bookings", ()) if resource is None else ("SELECT COUNT(*) FROM bookings WHERE resource = ?", (resource,))
        return self._db.execute(sql, args).fetchone()[0]

    def tokens(self, resource: str) -> list[int]:
        return [t for (t,) in self._db.execute("SELECT token FROM bookings WHERE resource = ? ORDER BY rowid", (resource,))]

    def book(self, resource: str, ref: str, token: int | None) -> Mapping[str, Any]:
        self._db.execute("BEGIN IMMEDIATE")
        try:
            row = self._db.execute("SELECT newest FROM fences WHERE resource = ?", (resource,)).fetchone()
            if token is not None and row is not None and token < row[0]:
                raise PermanentError(f"token {token} is older than {row[0]}, which was already seen", code="stale_token")
            if token is not None:
                self._db.execute("INSERT INTO fences VALUES (?, ?) ON CONFLICT(resource) DO UPDATE SET newest = MAX(newest, excluded.newest)", (resource, token))
            self._db.execute("INSERT OR IGNORE INTO bookings VALUES (?, ?, ?)", (ref, resource, token))
            self._db.execute("COMMIT")
        except BaseException:
            if self._db.in_transaction:
                self._db.execute("ROLLBACK")
            raise
        if self.die_after_write:
            os._exit(17)  # the process is gone: no reply, no cleanup, no lease released
        return {"ref": ref}

    def find(self, resource: str, ref: str, token: int | None) -> Mapping[str, Any] | None:
        """A lookup carries the token too, and raises the fence like a write does. That is what lets "no record" be final:
        once the newest holder has asked, a request from an older holder that is still on its way will be refused."""
        self._db.execute("BEGIN IMMEDIATE")
        try:
            if token is not None:
                self._db.execute("INSERT INTO fences VALUES (?, ?) ON CONFLICT(resource) DO UPDATE SET newest = MAX(newest, excluded.newest)", (resource, token))
            row = self._db.execute("SELECT ref FROM bookings WHERE ref = ?", (ref,)).fetchone()
            self._db.execute("COMMIT")
        except BaseException:
            if self._db.in_transaction:
                self._db.execute("ROLLBACK")
            raise
        return {"ref": row[0]} if row else None

    async def invoke(self, operation: str, payload: Mapping[str, Any], credentials: Mapping[str, Any]) -> Mapping[str, Any]:
        if operation == "FIND":
            found = self.find(payload["resource"], payload["ref"], payload.get("token"))
            if found is None:
                raise PermanentError("no such booking", code="not_found")
            return found
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            await asyncio.sleep(payload.get("stall", 0.0))  # the work takes time, and the replica may be slow or paused
            return self.book(payload["resource"], payload["ref"], payload.get("token"))
        finally:
            self.active -= 1

    async def healthy(self) -> bool:
        return True


async def book_order(ctx: BoundaryContext, payload: Mapping[str, Any]) -> Mapping[str, Any]:
    # The fencing token goes to the partner with every crossing, next to the operation id.
    return await ctx.connector.invoke(
        "BOOK",
        {"resource": payload["order"], "ref": ctx.operation_id, "token": ctx.fencing_token, "stall": payload.get("stall", 0.0)},
        ctx.credentials,
    )


async def find_booking(ctx: BoundaryContext, payload: Mapping[str, Any]) -> Mapping[str, Any] | None:
    try:
        return await ctx.connector.invoke("FIND", {"resource": payload["order"], "ref": ctx.operation_id, "token": ctx.fencing_token}, ctx.credentials)
    except PermanentError:
        return None


def replica(
    name: str,
    journal_path: str,
    office: Office,
    *,
    ttl: float = 5.0,
    wait: float = 5.0,
    on_unknown: Unknown = Unknown.VERIFY,
    on_busy: str = "wait",
) -> Ambassador:
    """One copy of the ambassador. Every copy opens the same journal file, with a connection of its own."""
    journal = SqliteJournal(journal_path)
    ambassador = Ambassador(
        AmbassadorSpec("order-ambassador", "partner-orders", "integrations-team@example.org"),
        office,
        journal=journal,
        leases=journal,  # the same store holds the leases, so the token is checked in the same step as the write
        leasing=Leasing(holder=name, ttl_seconds=ttl, wait_seconds=wait, poll_seconds=0.01),
        admission=Admission(on_busy=on_busy, retry_after_seconds=0.1),
        resilience=Resilience(backoff_seconds=0.0),
    )
    ambassador.offer(
        Capability(
            "book_order",
            "Book an order with the partner.",
            book_order,
            resource=lambda p: str(p["order"]),
            on_unknown=on_unknown,
            verify=find_booking if on_unknown is Unknown.VERIFY else None,
            absence_is_final=on_unknown is Unknown.VERIFY,  # the partner refuses a booking request older than its own timeout
        )
    )
    return ambassador


def task(key: str, order: str = "O-1", **payload: Any) -> ActionRequest:
    return ActionRequest("book_order", {"order": order, **payload}, CORE, idempotency_key=key)


def die_midway(journal_path: str, office_path: str, ttl: float) -> None:
    """Run in a child process: take a task, write the booking at the partner, and die before the outcome is recorded."""
    ambassador = replica("doomed", journal_path, Office(office_path, die_after_write=True), ttl=ttl)
    asyncio.run(ambassador.perform(task("k1")))
