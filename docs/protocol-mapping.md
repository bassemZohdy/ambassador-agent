# Protocol mapping

The pattern defines its interaction model abstractly: tasks, outcomes, notices. A protocol carries them. This page maps each concept to **A2A**, the reference protocol, and names the gaps the ambassador fills.

A2A is the reference because it is the common standard for agents talking over a network, and it already has most of what the interaction model needs. It is not required. Any protocol that can carry a task with a final outcome can bind to the pattern.

## A2A-shaped, not A2A-bound

The abstraction uses only concepts that are stable across A2A versions and that other protocols can also express: a task, its state, a message, a published capability. It does not depend on wire details.

The test for the abstraction is simple: a second binding, such as a message queue or a plain HTTP API, must be able to implement it without pretending to be A2A.

## Concept mapping

Checked against the types in the A2A Python SDK, version 1.3. It is not a full reading of the specification.

| Pattern concept | A2A equivalent | Status |
|---|---|---|
| Ambassador description | Agent card | Direct |
| Capability | Skill on the agent card | Direct |
| Task | Task | Direct |
| Waiting | `submitted` | Direct |
| Working | `working` | Direct |
| `succeeded` | `completed` | Direct |
| `failed` | `failed` | Direct |
| `rejected` | `rejected` | Direct |
| Subscription and notices | Streaming or push notifications on a task the core opened | Direct |
| Compensation | A new task on the compensating skill. `canceled` is not compensation | Direct, by convention |
| `unknown`: may have been done, must be reconciled | None | Extension |
| Fallback channel and instructions, beside an outcome | None | Extension |
| Operation id, to reconcile by | None | Extension |
| Compensable, partly, or not, per capability | None | Extension |
| Delivery class per capability: how an unknown outcome is settled | None | Extension |
| Retry hint on a refusal | None | Extension |
| Admission: one at a time per resource, bounded wait | None. The SDK starts each request concurrently and does not limit intake | Ambassador duty |
| Acting for a principal | Security schemes exist. Acting on behalf of someone is not standardised | Ambassador duty |
| Journal | None. A task store is not an audit record | Ambassador duty |
| Quarantine | None | Ambassador duty |

Two A2A task states are not used by the core pattern: `input-required` and `auth-required`. Both pause a task to ask the caller for something, and an ambassador's tasks do not pause. They remain available if you add optional human approval.

## The current mapping for `unknown`

`unknown` means the action may or may not have been carried out. A2A has no state for that. The current choice is to end the task as `failed` and carry the real outcome, `unknown`, and the operation id in extension data.

This is the weakest row in the mapping, and it is worth being plain about why. Mapping it to `completed` was rejected: a caller would read the task as done. Mapping it to `failed` has the opposite risk: a client that does not understand the extension reads a plain failure and may retry. Two things limit the harm. The ambassador answers a repeat of the same task, under the same idempotency key, with `unknown` and does not send it again. And no fallback channel is attached, so nothing invites the client to redo the action elsewhere. A client that retries under a new key, or acts on its own, defeats both.

A fallback channel and its instructions are a separate field. They travel beside `failed` when the action is known not to have been done, and are never attached to `unknown`.

## The Extension

A2A lets an agent card and a message declare extensions. The rows marked "Extension" above can be published as one ambassador extension, so that any A2A client can discover them:

| Field | Where | Values |
|---|---|---|
| Outcome | Final message of a task | `succeeded`, `failed`, `rejected`, `unknown` |
| Operation id | Final message, when unknown | The identifier to reconcile by |
| Fallback | Final message, when failed and known not done | Channel and instructions |
| Retry after | Final message, when rejected for load | Seconds |
| Compensation | Each skill | `compensable`, `partly`, `not`, and the compensating skill if any |
| Delivery class | Each skill | `verify`, `resend`, `stop` |

This extension is a proposal. It has not been published or registered anywhere.

## Other bindings

| Binding | Fits | What is lost |
|---|---|---|
| Message queue | Queued tasks, natural buffering and redelivery | Discovery; needs a separate catalogue |
| Plain HTTP API | Simple request and reply | Long-running tasks and subscriptions need polling or webhooks |
| MCP tool | Exposing capabilities to a single agent | Task lifecycle; suits short tasks only |
| Platform-native call (agent framework tool or node) | Core agents on the same platform | Nothing, within that platform |
