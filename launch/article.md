# Who answers for it? The Ambassador Agent pattern

*A design pattern for agents that act on systems you do not own.*

## Key takeaways

- Tool protocols tell an agent how to call an external system. They do not say who is responsible once it does. The Ambassador Agent pattern gives every external boundary one accountable, autonomous owner.
- The definition is small: one concept, one interaction model, one reliability rule and seven duties.
- Only the core system opens a task, a task never pauses, and it always ends in one of four outcomes: succeeded, failed, rejected or unknown.
- One rule keeps the ambassador honest about what it does not know: record the intent before the action, and the outcome after. It does not promise exactly-once effects. It says which of three delivery classes each capability has.
- The pattern borrows from the outbox, the saga and the actor model, uses A2A as its reference protocol, and adopts none of them as is. It is a proposal with open questions, listed at the end.

## The problem

Your agent called a partner's API twice. The first call timed out, the model tried again, and both went through. Which agent owned that action?

In most agentic systems today the honest answer is "none of them".

We have good answers to *how* an agent reaches an external system. Tool protocols made that easy. We have a much weaker answer to *who is responsible* once it does. On an integration platform with dozens of external systems, that gap shows up in four ways:

1. Vendor field names and error codes leak into prompts, so every agent has to learn every vendor.
2. Side effects have no single owner, so duplicates and half-finished actions slip by.
3. Free text returned by an external system lands in the context of an agent that holds real authority.
4. Every agent handles outages and overload its own way.

The setting is an integration platform: a stable core system of agents and workflows that must act on, and hear from, many external systems it does not control. The number of external systems grows faster than the number of core agents.

## The pattern

Put one **ambassador agent** on each external boundary and make it the only way across. A core agent asks for a capability in its own language: `book_shipment`, not `CREATE_SHPMT` with an `ORD_NO`. The ambassador owns everything else, and it finishes every task on its own.

![A core agent opens a task with the ambassador. It passes policy and admission, the ambassador records its intent in the journal, then acts on the external system; replies pass quarantine before the core agent sees them. A task is refused when too many are waiting.](../docs/diagrams/architecture.svg)

The whole definition fits in four lines:

| Part | Statement |
|---|---|
| One concept | The ambassador: one boundary, one ambassador, one named human owner |
| One interaction model | The core opens tasks. Each task ends as succeeded, failed, rejected or unknown |
| One reliability rule | Every action is journalled before it happens |
| Seven duties | Contract, identity, policy, admission, journal, quarantine, fallback |

An ambassador is an agent in the sense that matters for architecture: it has an identity, a published contract, its own state and the authority to decide how a request is carried out. Whether it uses a model is a choice, not part of the definition.

## The interaction model: tasks

The core system talks to an ambassador through tasks. Five statements define them.

**Only the core opens a task.** An ambassador never starts an exchange with the core and never calls another ambassador. Two parties that can each start an exchange with the other can loop without end. One direction of initiation removes that whole class of failure.

**A task asks for one capability**, names the principal it is for, and carries an idempotency key when it has a side effect.

**A task never pauses.** The ambassador is fully autonomous. When it cannot decide, it does not ask a person or open a dialogue with the core. It ends the task.

**Four outcomes, always.** An outcome says only what is known about the action. `succeeded`: it was carried out. `failed`: it is known not to have been. `rejected`: refused before the boundary was crossed. `unknown`: it may or may not have been, and it must be reconciled. A timeout after a request was sent is `unknown`, never `failed`. Core agents never interpret a vendor error.

**What to do next travels beside the outcome, never in place of it.** A result can carry a fallback channel, a retry hint or the operation id to reconcile by. They are instructions, and the outcome stays a fact. A fallback channel is attached only when the action is known not to have been done. Pointing a customer to the courier's website after a timeout would risk a second booking, so it never happens while the outcome is unknown.

**News from outside arrives as a notice.** The core opens a long-lived subscription, and the ambassador sends translated, sanitised notices into it. A notice is a fact, never a command. If nobody is subscribed, the ambassador records the event and does not hold it; keeping undelivered events is the messaging layer's job.

![A core agent opens a task. The ambassador checks policy and admission, records its intent, sends the vendor request, records the outcome, sanitises the reply and answers with one of four outcomes.](../docs/diagrams/task.svg)

## The reliability rule: the journal

**Before an ambassador acts on the external system, it records its intent. After, it records the outcome.**

Between "sent" and "recorded" there is always a window in which the action may have taken effect and the ambassador cannot tell. The rule does not close that window. It makes sure the ambassador always knows it is in it, and never reports a guess as a fact.

- An intent with an outcome is finished. A repeated task with the same idempotency key gets the recorded outcome back, and the external system is not called again.
- An intent with no outcome means the ambassador stopped mid-action. The outcome is unknown, and on restart it must be reconciled.
- A timeout is the same situation as a crash. Before it retries or offers another channel, the ambassador settles what may have happened. A refused connection that never carried the request is different: nothing was sent, so it can be retried freely.

![After a restart the ambassador reads the journal for intents with no outcome, then verifies with the external system, resends, or stops and reports the outcome as unknown, and records the result.](../docs/diagrams/recovery.svg)

### What the journal guarantees, and what it does not

Across a boundary the ambassador does not control, exactly-once effects are impossible in general. Each capability declares which of three delivery classes it has:

| Class | Holds when | Declared as | After an ambiguous failure |
|---|---|---|---|
| Effectively once | The external system ignores a repeated operation id, or can be asked about it | `verify` or `resend` | Ask, or send the same operation id again. At most one effect |
| At least once | The external action is naturally repeatable, or a duplicate is harmless | `resend`, chosen knowingly | Send again. A duplicate is possible and accepted |
| Unrecoverable unknown | The external system can neither deduplicate nor be asked | `stop` | Report `unknown`, hold repeats, hand it to the owner |

Every task has an **operation id**: its idempotency key, or one the ambassador makes. It is journalled with the intent and sent to the external system as its own idempotency key or client reference, the same on every retry, resend and recovery. That is what lets the other side deduplicate, or be asked. `resend` is only effectively-once if the other side deduplicates; otherwise it quietly means at-least-once.

**When "no record" can be believed.** An empty lookup does not prove the action will never happen: a request can still be in flight, or the other side can be slow to show its own writes. So a capability that verifies also declares whether **absence is final** (the external system refuses a request that arrives late) and a **settle window** (a wait before a lookup is believed). It must also be true that the lookup is by operation id and that the other side keeps the id longer than recovery takes. The ambassador acts on the declarations and cannot check them, so the owner answers for them. Without them, an empty lookup ends as `unknown`. A capability that cannot meet them should declare `stop`.

**An unknown outcome is an exception for a person.** The task ends as `unknown` with its operation id, and no other channel is offered. A repeat of the task gets `unknown` back and is not sent again, and the open exception holds its resource: a new task for the same order, even under a new idempotency key, is refused as `resource_held`. Clients follow the same rule from their side: an `unknown` is never retried under a new key. The ambassador lists its open exceptions for the named owner, who finds out from the external system's own records and records `succeeded` or `failed`, with their name and a note. A `failed` answer is the first moment another channel may be offered.

A capability with several steps extends the same journal to every step, so a restart resumes at the step that was interrupted. That is durable execution; the single-step journal is its smallest form. The journal is also the audit record: who asked, for whom, what was sent and what came back.

## The seven duties

| Duty | What the ambassador does |
|---|---|
| Contract | Publishes capabilities in the core's language, each with its declarations (below) |
| Identity | Acts for a named principal and exchanges that identity for credentials the external system accepts. It never acts as itself by default |
| Policy | Refuses a task before the boundary is crossed. With no person to ask, this check carries the full weight for irreversible actions |
| Admission | Controls how much work it takes on |
| Journal | Records intent and outcome for every crossing |
| Quarantine | Treats everything from outside as data, never as instructions, and sanitises it before a core agent sees it |
| Fallback | Offers another channel when the external system cannot finish the job and the action is known not to have been done. Never while the outcome is unknown |

### Admission

Agents loop. A runaway core workflow can open hundreds of tasks in a second, and the external system has a quota that only the ambassador knows. Admission protects the ambassador, the budget when a model is used, and that quota.

1. **One task at a time per resource.** Two callers cannot race on the same order. A second task waits or is refused. It never interrupts or rolls back the first, because an external side effect cannot be undone by cancelling the run that caused it.
2. **The wait is bounded**, with a fair share per principal.
3. **When full, refuse**, with a hint of when to retry. An unbounded wait turns overload into memory exhaustion and stale work.
4. **Pace to the external system.** Work is released no faster than its quota allows.

Limits per caller and per cost usually also sit in a gateway in front. The two complement each other: the gateway stops floods, and the ambassador protects the boundary's own quota.

### What a capability declares

| Declaration | Values | Purpose |
|---|---|---|
| Resource | A key such as an order number | Tasks for the same key run one at a time |
| Delivery class | Verify, resend, stop | How an unknown outcome is settled, after a crash or a timeout |
| Absence is final, settle window | Yes or no, and a wait | Whether an empty lookup can be believed |
| Compensation | Compensable, partly, not | Lets the core plan an action that spans several boundaries |
| Fallback | A channel and instructions | Offered beside `failed`, never beside `unknown` |
| Governance | Data classification, audit retention, approval required | Published for owners and reviewers. Approval is enforced as a scope the principal holds |

Compensation is not undo. A refund after a charge is "partly"; a delivered message is "not". The core orchestrates an action across boundaries, and each ambassador is a participant. A multi-step capability inside one boundary is the ambassador's own responsibility.

**What is fixed, and what is a choice.** Six rules are not negotiable: only the core opens a task; the intent is journalled before the action and the outcome after; a timeout is not a failure; no fallback is offered while the outcome is unknown; the operation id never changes; and no two tasks for one resource are in flight at once. Retries, the circuit breaker, pacing, queue size, the settle window, how much intelligence is used and whether approval is needed are the owner's policy. If changing a setting can cause a duplicate or report a guess as a fact, it is a rule.

## An agent that may not need a model

| Level | Model use | Fits when |
|---|---|---|
| Scripted | None | Stable API, clear errors, high volume |
| Assisted | Consulted on failures | Errors are ambiguous, or recovery depends on context |
| Autonomous planning | May plan the steps inside a capability | The interface is a document, a screen or another agent |

The contract is the same at every level, so you start scripted and add intelligence only where a real failure mode demands it. When you do add a model, prefer a fast, low-latency one. The boundary is on the path of every action, so speed and cost matter more there than depth of reasoning.

## A worked example

An online shop has a core assistant that helps customers. The Courier is an external system with its own codes, occasional outages, a quota of ten calls a second, and free-text remarks written by depot staff. Its ambassador offers `book_shipment`, `cancel_shipment` and `shipment_status`, plus a subscription for status changes.

| Scenario | What happens |
|---|---|
| Normal booking | Policy and admission pass, the intent is recorded, the vendor request is sent for customer 77, the outcome is recorded, and the assistant gets `succeeded` with no vendor code in sight |
| The model repeats itself | Same idempotency key: the recorded outcome is returned and the Courier is not called again |
| Outage | Connections are refused, so nothing was sent. After retries the task ends as `failed`, with instructions to book on the courier's own website |
| A lost reply | The Courier booked it and the reply timed out. The ambassador asks the Courier about the operation id, finds the booking and records `succeeded`. Retrying or using the website would have booked twice |
| A lost reply, nothing to ask | The capability declared `stop`. The task ends as `unknown`, with no other channel offered. The owner finds the booking in the Courier's portal and records it |
| A runaway caller | Ten tasks a second are released, a bounded number wait, the rest are `rejected` with a retry hint |
| A crash mid-action | On restart the open intent is verified with the Courier and recorded as `succeeded`. Nothing is sent twice |
| A hostile remark | A status event containing "ignore previous instructions" becomes a sanitised notice that states a fact |

When the Courier later starts returning vague errors, the team adds a small, fast model that classifies each failure as retry, fallback or fail. It cannot override the delivery rule: a timeout on a booking is still settled before anything is retried. Callers notice nothing.

## Binding it to a protocol

The pattern defines tasks abstractly, and a protocol carries them. A2A is the reference because it is the common standard for agents talking over a network and already has most of what is needed. It is not required.

| Pattern concept | A2A | Status |
|---|---|---|
| Ambassador description, capability | Agent card, skill | Direct |
| Task: waiting, working | `submitted`, `working` | Direct |
| Succeeded, failed, rejected | `completed`, `failed`, `rejected` | Direct |
| Subscription and notices | Streaming or push notifications on a task the core opened | Direct |
| `unknown`, fallback beside an outcome, operation id, compensation, delivery class, retry hint | None | A proposed extension |
| Admission, acting for a principal, journal, quarantine | None | The ambassador's own duties |

The right-hand column is the clearest statement of what the pattern adds. A2A's two pausing states, `input-required` and `auth-required`, are not used, because an ambassador's tasks do not pause.

## What it borrows, and what it leaves

No earlier pattern is adopted as is.

| Source | Taken | Left out |
|---|---|---|
| Transactional outbox | Record before you send | The relay and the broker |
| Saga | Each participant declares and owns its compensation | Orchestration, which stays in the core |
| Actor model | One piece of work at a time, and a bounded wait | The mailbox as a concept, supervision trees |
| Anti-corruption layer | The foreign model never leaks in | Its passive nature: no owner, no authority to refuse |
| Cloud Ambassador pattern | The name, and outbound connectivity concerns | Co-location with one client, no business meaning |
| Durable execution | Journal every step so a restart resumes | A workflow engine as a requirement |
| Ambient agents | Agents driven by events, not chat | A model in the loop for every event |
| Dual LLM pattern | Outside content is data, kept from a model with authority | A second model as the mechanism |

Considered and not taken: human-in-the-loop as a core step, try-confirm-cancel as a requirement, ambassadors reacting to each other's events, two-phase commit, and a stateless tool call as the interaction model.

It composes with what you already have. A gateway sits in front. An MCP tool makes a fine connector inside. The ambassador is the part that answers for the outcome.

## What it costs, and when to skip it

- One more hop, and a model call on some paths if intelligence is used.
- A contract you have to design. A thin pass-through contract gives none of the benefits.
- A durable journal, even for the simplest ambassador.
- A single path to each system, which must therefore be run redundantly. That needs more than a second copy: mutual exclusion per resource across copies, a shared journal, and a claim on each open intent.
- With no person in the loop, policy is the only safeguard before an irreversible action.

Use the pattern when at least two of these hold: several core agents use the system, calls have side effects, you do not control its availability or quota, its replies contain free text a model will read, or someone will ask "who did this, for whom, and when?" For a read-only, internal, single-consumer lookup, a plain tool is enough.

## Open questions

This is version 0.2 of a proposal. It has no documented use in production yet.

1. **Redundancy and admission.** The pattern lists what several replicas need and three ways to get mutual exclusion: partition by resource key, one active replica, or a lease with fencing. None of it is implemented in the reference, which is tested in one process only.
2. **The limit of autonomy.** When an outcome is unknown and the external system cannot be asked, the ambassador reports `unknown`, holds repeats and lists the exception, and a person must resolve it. How long it may be held, who is alerted, and whether a task type may set a time limit before escalating are not yet described.
3. **Policy.** The pattern does not yet say how policy is defined or reviewed.
4. **`unknown` in A2A.** A2A has no state for "may have happened". It maps to `failed` with the outcome in extension data, so a client that ignores the extension may read a plain failure and retry. The ambassador holds repeats of the same task and, for a capability that names a resource, the resource too. A client that retries under a new key against a capability with no resource still defeats it.

## Read it and break it

The repository holds the full definition, numbered conformance rules with the designs that fail them, a page on identity and trust, a decision guide, the worked example in detail, the protocol mapping and every source. It is independent of any language, agent platform or protocol. A small reference implementation is included only to show it can be built.

**https://github.com/bassemZohdy/ambassador-agent**

I would like to hear where this breaks. If you have a boundary that does not fit, or you already run something like this, please open an issue.

## References

1. Microsoft, [Ambassador pattern](https://learn.microsoft.com/azure/architecture/patterns/ambassador), Azure Architecture Center.
2. Burns and Oppenheimer, "Design patterns for container-based distributed systems", HotCloud 2016.
3. Evans, *Domain-Driven Design*, 2003; Microsoft, [Anti-corruption layer pattern](https://learn.microsoft.com/azure/architecture/patterns/anti-corruption-layer).
4. Hohpe and Woolf, [*Enterprise Integration Patterns*](https://www.enterpriseintegrationpatterns.com/toc.html), 2003.
5. Richardson, [Transactional outbox](https://microservices.io/patterns/data/transactional-outbox.html) and [Saga](https://microservices.io/patterns/data/saga.html).
6. Garcia-Molina and Salem, "Sagas", 1987.
7. Hewitt, Bishop and Steiger, "A universal modular Actor formalism for artificial intelligence", 1973.
8. [Akka mailboxes](https://doc.akka.io/docs/akka/2.9/typed/mailboxes.html); [Dapr actors](https://docs.dapr.io/developing-applications/building-blocks/actors/actors-features-concepts/); [Cloudflare Durable Objects limits](https://developers.cloudflare.com/durable-objects/platform/limits).
9. LangChain, [Double texting](https://docs.langchain.com/langsmith/double-texting) and ["Introducing ambient agents"](https://blog.langchain.com/introducing-ambient-agents).
10. [Agent2Agent (A2A) protocol](https://a2a-protocol.org/); [Model Context Protocol](https://modelcontextprotocol.io/).
11. ["Agents thinking fast and slow: a Talker-Reasoner architecture"](https://arxiv.org/abs/2410.08328), 2024.
12. Willison, ["The dual LLM pattern"](https://simonwillison.net/2023/Apr/25/dual-llm-pattern/), 2023.
13. Thoughtworks, ["Your agent skill is not an anti-corruption layer"](https://www.thoughtworks.com/en-gb/insights/blog/generative-ai/your-agent-skill-not-anti-corruption-layer).
14. Hardy, "The confused deputy", 1988.

The complete list, with how each source relates to the pattern, is in the repository's [references page](../docs/references.md).

*Bassem Zohdy is a software and solution architect. This is personal work and does not represent any employer.*
