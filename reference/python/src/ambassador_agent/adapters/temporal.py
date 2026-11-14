"""Temporal as the place replicas run (see docs/on-temporal.md). Experimental.

Temporal provides exclusion and routing: the workflow id is the resource key, and Temporal allows one open
workflow per id, whichever worker runs it. The ambassador's own journal stays the record of every crossing.
Nothing about the external system is decided in workflow code.

    worker side:  TemporalAmbassador(ambassador).worker(client, task_queue)
    caller side:  await submit(client, ambassador_name, resource_key, request)
                  await recover(client, ambassador_name, resource_key)
"""
from __future__ import annotations

from typing import Any, Mapping

from temporalio import activity, workflow

# Everything the workflows do not use is imported outside the workflow sandbox's re-import.
with workflow.unsafe.imports_passed_through():
    import uuid
    from dataclasses import replace
    from datetime import timedelta

    from temporalio.client import Client, WorkflowFailureError
    from temporalio.common import RetryPolicy, WorkflowIDConflictPolicy, WorkflowIDReusePolicy
    from temporalio.exceptions import WorkflowAlreadyStartedError
    from temporalio.worker import Worker

    from ambassador_agent.ambassador import Ambassador
    from ambassador_agent.model import ActionRequest, ActionResult, BoundaryError, Fallback, Outcome, Principal

PERFORM = "ambassador_perform"
RECONCILE = "ambassador_reconcile"
TASK_QUEUE = "ambassador"


# ---- what crosses Temporal: plain JSON ------------------------------------------------------------


def request_to_dict(request: "ActionRequest") -> dict[str, Any]:
    p = request.principal
    return {
        "capability": request.capability,
        "payload": dict(request.payload),
        "principal": {"subject": p.subject, "on_behalf_of": p.on_behalf_of, "scopes": sorted(p.scopes), "claims": dict(p.claims)},
        "idempotency_key": request.idempotency_key,
        "correlation_id": request.correlation_id,
        "caller": request.caller,
        "delegation": request.delegation,
    }


def request_from_dict(d: Mapping[str, Any]) -> "ActionRequest":
    p = d["principal"]
    return ActionRequest(
        d["capability"],
        d["payload"],
        Principal(p["subject"], p.get("on_behalf_of"), frozenset(p.get("scopes", ())), p.get("claims", {})),
        d.get("idempotency_key"),
        d.get("correlation_id"),
        d.get("caller"),
        d.get("delegation"),
    )


def result_from_dict(d: Mapping[str, Any]) -> "ActionResult":
    e, f = d.get("error"), d.get("fallback")
    return ActionResult(
        Outcome(d["outcome"]),
        d.get("data", {}),
        BoundaryError(e["code"], e["message"], e.get("retryable", False), e.get("retry_after_seconds")) if e else None,
        Fallback(f["channel"], f["instructions"]) if f else None,
        d.get("attempts", 0),
        d.get("replayed", False),
        d.get("operation_id"),
    )


def workflow_id(ambassador_name: str, resource: str) -> str:
    """One id per resource, shared by tasks and recovery for it, so Temporal keeps them from running together."""
    return f"{ambassador_name}/{resource}"


# ---- workflows: thin and deterministic. The decisions are the ambassador's, inside the activity ---------


@workflow.defn(name="AmbassadorTask")
class AmbassadorTask:
    @workflow.run
    async def run(self, job: dict[str, Any]) -> dict[str, Any]:
        try:
            return await workflow.execute_activity(
                PERFORM,
                job["request"],
                start_to_close_timeout=timedelta(seconds=job["timeout_seconds"]),
                # Never retried by the platform: after a timeout the action may have happened (rules C8, C9).
                # Whether to ask the external system, resend or stop is the ambassador's call, by the capability's class.
                retry_policy=RetryPolicy(maximum_attempts=1),
            )
        except Exception as exc:  # the activity timed out, its worker died, or it was cancelled
            return {
                "outcome": "unknown",
                "operation_id": job["request"]["idempotency_key"],
                "error": {
                    "code": "outcome_unknown",
                    "message": "the action may or may not have reached the external system (" + type(exc).__name__ + "). "
                    "Do not retry it or try another channel; its owner settles it.",
                    "retryable": False,
                },
            }


@workflow.defn(name="AmbassadorRecovery")
class AmbassadorRecovery:
    @workflow.run
    async def run(self, job: dict[str, Any]) -> list[dict[str, Any]]:
        return await workflow.execute_activity(
            RECONCILE,
            job["resource"],
            start_to_close_timeout=timedelta(seconds=job["timeout_seconds"]),
            retry_policy=RetryPolicy(maximum_attempts=1),
        )


# ---- worker side ------------------------------------------------------------------------------------


class TemporalAmbassador:
    """Runs one ambassador's tasks and recovery as Temporal activities. Every worker has its own copy, sharing one journal."""

    def __init__(self, ambassador: "Ambassador") -> None:
        self.ambassador = ambassador

        @activity.defn(name=PERFORM)
        async def perform(request: dict[str, Any]) -> dict[str, Any]:
            return (await ambassador.perform(request_from_dict(request))).to_dict()

        @activity.defn(name=RECONCILE)
        async def reconcile(resource: str) -> list[dict[str, Any]]:
            return [r.to_dict() for r in await ambassador.reconcile(resource)]

        self.activities = [perform, reconcile]

    def worker(self, client: Client, task_queue: str = TASK_QUEUE, **options: Any) -> Worker:
        return Worker(client, task_queue=task_queue, workflows=[AmbassadorTask, AmbassadorRecovery], activities=self.activities, **options)


# ---- caller side: the binding in front of the ambassador -----------------------------------------------


async def submit(
    client: Client,
    ambassador_name: str,
    resource: str,
    request: "ActionRequest",
    *,
    task_queue: str = TASK_QUEUE,
    timeout_seconds: float = 30.0,
    retry_after_seconds: float = 1.0,
) -> "ActionResult":
    """Open one task. A busy resource is refused, not queued: the caller retries, as with Admission(on_busy="reject")."""
    if not request.idempotency_key:
        request = replace(request, idempotency_key=f"task-{uuid.uuid4().hex}")  # the operation id must be known to the caller
    try:
        raw = await client.execute_workflow(
            AmbassadorTask.run,
            {"request": request_to_dict(request), "timeout_seconds": timeout_seconds},
            id=workflow_id(ambassador_name, resource),
            task_queue=task_queue,
            id_reuse_policy=WorkflowIDReusePolicy.ALLOW_DUPLICATE,  # a closed id is free again
            id_conflict_policy=WorkflowIDConflictPolicy.FAIL,  # an open one refuses the second task
        )
    except WorkflowAlreadyStartedError:
        return ActionResult(
            Outcome.REJECTED,
            error=BoundaryError("resource_busy", f"another task is working on '{resource}'", True, retry_after_seconds),
        )
    except WorkflowFailureError as exc:
        return ActionResult(
            Outcome.UNKNOWN,
            error=BoundaryError("outcome_unknown", f"the task ended without a result ({type(exc).__name__}). Its owner settles it.", False),
            operation_id=request.idempotency_key,
        )
    return result_from_dict(raw)


async def recover(
    client: Client,
    ambassador_name: str,
    resource: str,
    *,
    task_queue: str = TASK_QUEUE,
    timeout_seconds: float = 30.0,
) -> list["ActionResult"]:
    """Settle the open intents for one resource. Returns nothing while a task for it is running: try again later."""
    try:
        raw = await client.execute_workflow(
            AmbassadorRecovery.run,
            {"resource": resource, "timeout_seconds": timeout_seconds},
            id=workflow_id(ambassador_name, resource),
            task_queue=task_queue,
            id_reuse_policy=WorkflowIDReusePolicy.ALLOW_DUPLICATE,
            id_conflict_policy=WorkflowIDConflictPolicy.FAIL,
        )
    except WorkflowAlreadyStartedError:
        return []
    return [result_from_dict(r) for r in raw]
