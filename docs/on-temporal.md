# Running replicas on Temporal

The pattern needs [more than one replica](pattern.md#more-than-one-replica) to keep its rules, and says to use the platform's coordination and not to write one. This page maps the pattern onto one such platform, [Temporal](https://temporal.io/), as a worked example of that advice. It is not required, and the pattern does not depend on it.

The core stays a LangGraph graph, or any agent. It reaches the ambassador through the Temporal client. The ambassador's own [journal](pattern.md#reliability-rule-the-journal) remains the record of every crossing, on a store the owner chooses. Temporal provides exclusion and routing only.

## What Temporal covers

| Pattern requirement | Temporal mechanism | What stays with the ambassador |
|---|---|---|
| One task per resource across copies (C25, C35) | The workflow id is the resource key. Temporal [guarantees at most one open workflow execution with a given id](https://docs.temporal.io/workflow-execution/workflowid-runid), whichever worker runs it | Refusing the second task as `resource_busy` when its start finds the id taken |
| Every copy sees every open intent (C36) | Workers share one task queue and one journal | The journal itself. Temporal's history is not the pattern's record |
| Only one copy recovers an open intent (C36) | A recovery workflow uses the same id as a task for that resource, so a task and its recovery cannot run together | What recovery does: look up, settle or hold, as the capability declared |
| The journal rule (C12) | The activity is where the crossing happens | Writing the intent before the call and the outcome after, in the ambassador's journal |

## The mapping

- **Workflow id.** `<ambassador name>/<resource key>`. A capability without a resource uses the whole boundary as its key, as the in-process lock does.
- **One workflow, one task.** The workflow runs a single activity, which calls `Ambassador.perform` and returns the result. Nothing about the external system is decided in workflow code, which must be deterministic.
- **The activity never retries on its own.** An activity runs at least once by default, because it has a retry policy; with a maximum of one attempt it runs at most once ([the Temporal community's account](https://community.temporal.io/t/execution-guarantees-of-activities/3405)). The pattern forbids a blind retry after a timeout (C8, C9), so the retry policy allows one attempt. Retrying is the ambassador's decision, made with the capability's declared delivery class.
- **A timeout is `unknown`.** If the activity times out or its worker dies, the workflow ends without a result. The ambassador's intent is still open in its journal. The caller is told `unknown`, with the operation id, and never `failed`.
- **Recovery is a workflow too.** After a worker restart, or on a schedule, a recovery workflow with the same id family settles the open intents for that resource. It cannot start while a task for the resource is open, and the reverse.
- **A busy resource is a refusal.** A start that finds the id taken fails with Temporal's already-started error. The binding returns `rejected` with `resource_busy`, retryable, with the retry hint from admission. Waiting is the caller's retry, not a queue inside the ambassador.
- **The operation id is the idempotency key.** It is the task's own key, never Temporal's run or activity id, which differ between executions. The external system deduplicates or is asked, as for any other deployment.

## What Temporal does not do

- **It does not fence a stalled activity.** If an activity's timeout fires while its worker is only slow, the workflow ends and the id is free, and the stalled call can still reach the external system. The protection is the same as everywhere: the external system deduplicates on the operation id, and the journal refuses to settle an intent twice. A fencing token is not available from Temporal, because run ids do not only grow. If the external system can check a token that only grows, take it from the store the journal uses.
- **It does not hold an `unknown`.** The hold on a resource while an outcome is unknown (C19) lives in the ambassador's journal. A recovery or a person settles it, not a workflow ending.
- **It does not replace the settle window or the lookup rules** (C17). Whether "no record" is final is a fact about the external system.
- **It adds a second history.** Do not make the workflow's history the record. Two journals that disagree are worse than one.

## Status

This is a design mapping. The reference implementation's Temporal adapter, when it exists, is Experimental until its tests run against a real Temporal server in CI.
