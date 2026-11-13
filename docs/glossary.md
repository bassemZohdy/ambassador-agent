# Glossary

The pattern's terms, in groups. Each entry is one or two sentences and points to the page that explains it. [The pattern](pattern.md) is the authority. If a definition here disagrees with it, the pattern wins.

## The parties

| Term | Meaning |
|---|---|
| **Ambassador** | The agent that owns one boundary and answers for everything that crosses it. One boundary, one ambassador, one named human owner. See [the definition](pattern.md#the-definition-in-four-parts) |
| **Boundary** | One external system, or a logical group of systems that callers treat as one. It is the line the ambassador guards |
| **Core system** | Your own agents, workflows and product, speaking your own language. It opens tasks and subscriptions, and never reaches the external system itself |
| **Owner** | The named human who answers for an ambassador: who is told about unknown outcomes, and who can patch it, limit it or switch it off |
| **External system** | Whatever sits on the far side of the boundary: a partner's API, a SOAP service, a queue, a document, a screen, or another organisation's agent |
| **Connector** | The deterministic code that talks to the external system. It is reachable only from inside the ambassador |

## The exchange

| Term | Meaning |
|---|---|
| **Capability** | One thing the core may ask of a boundary, named in the core's language, such as `book_shipment`. See [anti-patterns](anti-patterns.md#pass-through-contract) for what it is not |
| **Contract** | The capabilities an ambassador publishes, with what each one declares: side effect, scopes, resource, delivery class, compensation, fallback and the rest. Protocol-neutral; a binding maps it to a protocol |
| **Task** | One request for one capability, for one principal. Only the core opens it. A task never pauses and ends in a final outcome. See [interaction model](pattern.md#interaction-model-tasks) |
| **Outcome** | What is known about the action when the task ends: `succeeded`, `failed` (known not done), `rejected` (refused before the boundary) or `unknown` (may have been done) |
| **Unknown** | The outcome when the action may have happened and the ambassador cannot tell. Never a failure, never retried under a new key, and never offered a fallback |
| **Fallback** | Another channel that can finish the job, attached only when the action is known not to have been done |
| **Retry hint** | When, or whether, trying again may help. It travels beside the outcome and does not replace it |
| **Notice** | A fact from the external system, translated and sanitised, delivered on a subscription the core opened. Never a command |
| **Subscription** | How the core asks to hear about events. The ambassador cannot start an exchange with the core |
| **Compensation** | Whether a capability's business effect can be reversed (compensable, partly, not), declared in the contract. It is not undo |

## Identity and trust

| Term | Meaning |
|---|---|
| **Principal** | Who a task is for. The ambassador acts for the principal and never as itself. See [identity and trust](identity-and-trust.md) |
| **Caller** | The authenticated core agent, or the workload it runs in. Distinct from the principal |
| **Delegation** | Proof that a caller may act for a principal: which capabilities, until when, and for which ambassador. It narrows authority at each step |
| **Confused deputy** | A program that uses its own broader authority for a party that does not have it. An ambassador avoids it by using the principal's authority, never its own |
| **Approval** | A scope granted outside the ambassador for an irreversible capability. The ambassador checks that it is held and asks nobody |
| **Quarantine** | Everything from outside is data, never instructions, and is sanitised before any core agent sees it |

## Reliability

| Term | Meaning |
|---|---|
| **Journal** | The durable record of every crossing: intent before the action, outcome after. Also the audit record. See [the journal rule](pattern.md#reliability-rule-the-journal) |
| **Intent** | The journal entry written before an action crosses the boundary. An intent with no outcome means the ambassador stopped mid-action |
| **Operation id** | The identifier sent to the external system on every try, so it can deduplicate or be asked. The idempotency key, or one the ambassador makes. It never changes |
| **Idempotency key** | The key a caller puts on a task so a repeat is recognised as the same task and answered from the record |
| **Reconciliation** | Settling an action whose outcome was not recorded: ask the external system, send the same operation id again, or hand it to the owner |
| **Delivery class** | How an unknown outcome is settled: **effectively once** (verify or resend with a system that deduplicates or can be asked), **at least once** (resend, chosen knowingly) or **unrecoverable** (`stop`, settled by the owner) |
| **Verify, resend, stop** | The three ways a capability declares its unknown outcomes are settled |
| **Settle window** | A wait after sending, longer than any request can be in flight, before an empty lookup is believed |
| **Absence is final** | A declaration that "no record" can be believed, because the external system refuses late requests and keeps the operation id long enough |
| **Resource** | The key a capability names, such as an order number. Tasks for one resource run one at a time, and an open unknown holds it |
| **Admission** | The duty to limit work: one task at a time per resource, a bounded wait, refusal when full, and pacing to the external quota |
| **Invariant** | A rule that cannot be changed without breaking the pattern, such as journalling before acting. A change that cannot cause a duplicate or report a guess as a fact is a policy instead. See [invariants and policies](pattern.md#invariants-and-policies) |
| **Policy** | A choice the owner makes, per capability or per deployment: retry count, circuit breaker, pacing, queue size. Also the duty that refuses a task before the boundary |

## How an ambassador is run

| Term | Meaning |
|---|---|
| **Intelligence level** | How much a model is used: scripted (none), assisted (consulted on failures) or autonomous planning (may plan steps inside a capability). The contract is the same at every level. See [choices](pattern.md#choices) |
| **Durability** | A deployment choice about working state between tasks. Every ambassador has a durable journal. A **durable** ambassador also keeps state across steps, because a capability outlives one request, completes through a later event, or needs compensation after a restart. A **stateless** one journals one step per task. See [stateless or durable](decision-guide.md#stateless-or-durable) |
| **Presence** | A deployment choice about when an ambassador runs. **Always on** if it must listen, poll, keep a session open or report health between tasks. **On demand** if it only reacts and something reliable activates it. See [always on or on demand](decision-guide.md#always-on-or-on-demand) |
| **Replica** | One running copy of an ambassador. More than one needs mutual exclusion per resource across copies, a shared journal and a claim on each open intent. See [more than one replica](pattern.md#more-than-one-replica) |
| **Lease and fencing token** | One way to get mutual exclusion across replicas: a time-limited lease on the resource, with a token on every crossing that the journal or the external system checks |

## Variants

| Term | Meaning |
|---|---|
| **System ambassador** | One per external system. The default |
| **Group ambassador** | One per logical capability in front of several systems. It chooses the system; callers do not |
| **Peer ambassador** | The external party is another organisation's agent. It speaks an agent protocol outward and plain capabilities inward |
| **Listening post** | Offers a subscription and no capabilities. It watches an external system and reports |

See [variants](pattern.md#variants).

## Conformance

| Term | Meaning |
|---|---|
| **Must, Should, May** | Required, expected and allowed. A design that breaks a Must rule is non-conformant, however it is described. See [conformance](conformance.md) |
| **Binding** | The part that maps the protocol-neutral contract to a protocol such as A2A or MCP, and authenticates the caller. It never changes a rule. See [protocol mapping](protocol-mapping.md) |
