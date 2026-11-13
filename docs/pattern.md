# The Ambassador Agent pattern

## Intent

Give every external-system boundary exactly one autonomous agent that represents the core system to it, and it to the core system, and that answers for everything that crosses.

## Also known as

Boundary agent, liaison agent.

## Context

You run an agentic integration platform. A stable core system (agents, workflows, a product) must act on, and hear from, many external systems you do not control: partner APIs, legacy back ends, other organisations' agents. The number of external systems grows faster than the number of core agents.

## Problem

Who is responsible for an action on a system you do not own?

Connecting core agents straight to external systems through tools spreads that responsibility until nobody holds it. Vendor vocabulary seeps into prompts. Side effects have no single owner, so duplicates and half-finished actions go unnoticed. Text from outside enters core agents' context unfiltered. Each agent invents its own handling for outages and overload.

## Forces

- **Autonomy against accountability.** Agents should act without supervision, yet every external side effect needs a traceable owner.
- **Reasoning against determinism.** Some boundaries need judgement. Most calls need speed, low cost and repeatability.
- **Reuse against isolation.** Shared integration code is efficient. Shared credentials and shared failure are dangerous.
- **Openness against trust.** External content is useful and untrusted at the same time.
- **Stability against change.** External systems change on their own schedule. The core system should not notice.
- **Demand against capacity.** Core agents can produce work faster than an external system, or a budget, can absorb it.

## Solution

Place one **ambassador agent** on each boundary and make it the only path across.

An ambassador is an agent in the sense that matters for architecture: it has an identity, a published contract, its own state and the authority to decide how a request is carried out. It is **fully autonomous**: once it accepts a task it finishes it with a final outcome, without waiting for a person or for the core. Whether it uses a model is a choice, not part of the definition.

The pattern was shaped by several earlier ones, none adopted as is. [influences.md](influences.md) records what was taken from each and what was left out.

![A core agent opens a task with the ambassador. It passes policy and admission, the ambassador records its intent in the journal, then acts on the external system; replies pass quarantine before the core agent sees them. A task is refused when too many are waiting.](diagrams/architecture.svg)

### The definition in four parts

| Part | Statement |
|---|---|
| One concept | The ambassador: one boundary, one ambassador, one named human owner |
| One interaction model | The core opens tasks. Each task ends in one of four outcomes |
| One reliability rule | Every action is journalled before it happens |
| Seven duties | Contract, identity, policy, admission, journal, quarantine, fallback |

### Interaction model: tasks

The core system talks to an ambassador through **tasks**. The pattern defines the task abstractly; a protocol carries it. A2A is the reference protocol and is not required. [protocol-mapping.md](protocol-mapping.md) shows how each concept maps.

1. **Only the core opens a task.** An ambassador never starts an exchange with the core and never calls another ambassador. This keeps one direction of initiation and rules out message loops between agents.
2. **A task asks for one capability**, names the principal it is for, and carries an idempotency key when it has a side effect.
3. **A task moves from waiting to working to a final outcome.** It never pauses for input. If the ambassador cannot decide, it ends the task with an outcome; it does not open a dialogue.
4. **Four outcomes, always.** An outcome says only what is known about the action.
   - `succeeded`: it was carried out.
   - `failed`: it is known not to have been carried out. The external system refused it, or nothing was sent.
   - `rejected`: refused before the boundary was crossed.
   - `unknown`: it may or may not have been carried out, and it must be reconciled.

   A timeout after a request was sent is `unknown`, never `failed`. Core agents never interpret a vendor error.
5. **What to do next travels beside the outcome, never in place of it.** A result may carry a fallback channel, a retry hint or the operation id to reconcile by. These are instructions. The outcome stays a fact. A fallback channel is attached only when the action is known not to have been done, and never while the outcome is `unknown`.
6. **News from outside arrives as notices on a subscription.** The core opens a long-lived subscription task; the ambassador sends translated, sanitised notices into it. A notice is a fact, never a command. If nobody is subscribed, the ambassador records the event and does not hold it: keeping undelivered events is the job of the messaging layer.

![A core agent opens a task. The ambassador checks policy and admission, records its intent, sends the vendor request, records the outcome, sanitises the reply and answers with one of four outcomes.](diagrams/task.svg)

![The core system opens a subscription. When the external system sends an event, the ambassador translates and sanitises it, records it and sends a notice to the core system.](diagrams/notice.svg)

### Reliability rule: the journal

**Before an ambassador acts on the external system, it records its intent. After, it records the outcome.**

Between "sent" and "recorded" there is always a window in which the action may have taken effect and the ambassador cannot tell. The rule does not close that window. It makes sure the ambassador always knows it is in it, and never reports a guess as a fact:

- An intent with an outcome is finished. A repeated task with the same idempotency key gets the recorded outcome back, and the external system is not called again.
- An intent with no outcome means the ambassador stopped mid-action. The outcome is **unknown**, and on restart the ambassador must reconcile it.
- A timeout is the same situation as a crash. When an action fails in a way that may have taken effect, the ambassador settles it by the rules below before it retries or offers another channel. A refused connection that never carried the request is different: nothing was sent, so it can be retried freely.

![After a restart the ambassador reads the journal for intents with no outcome, then verifies with the external system, resends, or stops and reports the outcome as unknown, and records the result.](diagrams/recovery.svg)

#### What the journal guarantees, and what it does not

The journal does not make an action happen exactly once. Across a boundary the ambassador does not control, exactly-once effects are impossible in general. What the pattern can give, and what each capability must declare, is one of three delivery classes:

| Class | Holds when | Declared as | After an ambiguous failure |
|---|---|---|---|
| **Effectively once** | The external system ignores a repeated operation id, or can be asked about it | `verify` or `resend` | Ask, or send the same operation id again. At most one effect |
| **At least once** | The external action is naturally repeatable, or a duplicate is harmless | `resend`, chosen knowingly | Send again. A duplicate is possible and accepted |
| **Unrecoverable unknown** | The external system can neither deduplicate nor be asked | `stop` | Report `unknown`, hold repeats, and hand it to the owner |

`resend` is only effectively-once if the other side deduplicates. If it does not, `resend` quietly means at-least-once. A capability that declares it must be able to defend that choice.

**The operation id.** Every task has one: the idempotency key it carries, or one the ambassador makes. It is journalled with the intent and sent to the external system as its idempotency key or client reference. It is the same on every retry, resend and recovery. That is what lets the other side deduplicate, or be asked. An ambassador that sends a new identifier each time cannot reconcile anything.

**Reconciliation** follows what the capability declared:

- **verify**: ask the external system whether it received the operation id. A record means `succeeded`. No record means `failed`, and a retry or another channel is now safe. If the external system cannot answer, the outcome is `unknown`.
- **resend**: send the same operation id again.
- **stop**: report `unknown`. Nothing is sent and nothing is offered.

Verification is only as strong as the external system's consistency. "No record" from a system that is slow to show its own writes is weaker than it looks. A capability that cannot rely on it should declare `stop`.

**Unknown outcomes are exceptions for a person.** An outcome that nothing here can settle is not hidden and not retried. It is held:

1. The task ends as `unknown`, with the operation id. No fallback channel is offered, because the action may already have happened.
2. A repeat of the same task gets `unknown` back. It is not sent again while the exception is open.
3. The ambassador lists its open exceptions for the named owner.
4. The owner finds out from the external system's own records and records the answer, with their name and a note. The answer is `succeeded` or `failed`, and it goes in the journal.
5. A `failed` answer is the first moment another channel may be offered, and the fallback is attached to it. A repeat of a `succeeded` task gets that answer.

A capability with several steps, or one that waits for a later event, extends the same journal to every step, so a restart resumes at the step that was interrupted. This is durable execution; the single-step journal is its smallest form.

The journal is also the audit record: who asked, for whom, what was sent, what came back.

### The seven duties

| Duty | What the ambassador does |
|---|---|
| **Contract** | Publishes capabilities in the core system's language. Each one states whether it has a side effect, its delivery class (how an unknown outcome is settled), and whether it can be compensated |
| **Identity** | Acts for a named principal and exchanges that identity for credentials the external system accepts. It never acts as itself by default |
| **Policy** | Refuses a task before the boundary is crossed when the principal may not ask for it. With no person to ask, this check carries the full weight for irreversible actions |
| **Admission** | Controls how much work it takes on. See below |
| **Journal** | Records intent and outcome for every crossing, in both directions, and keeps unknown outcomes listed until an owner settles them |
| **Quarantine** | Treats everything from outside as data, never as instructions, and sanitises it before any core agent sees it |
| **Fallback** | Offers another channel when the external system cannot finish the job and the action is known not to have been done. Never while the outcome is unknown |

#### Admission

Core agents can loop, bursts happen, and an external system has its own limits. Admission protects the ambassador, the budget when a model is used, and the external system's quota, which only the ambassador knows.

1. **One task at a time per resource.** A second task for the same resource waits or is refused. It never interrupts or rolls back the first, because an external side effect cannot be undone by cancelling it.
2. **The wait is bounded.** There is a fixed limit on waiting tasks, with a fair share per principal.
3. **When full, refuse.** The task ends as `rejected` with a hint of when to retry. An unbounded wait turns overload into memory exhaustion and stale work.
4. **Pace to the external system.** Work is released no faster than the boundary's quota allows.

Admission is the ambassador's own duty. Limits per caller and per cost usually also exist in a gateway in front of it, and the two complement each other.

#### Compensation

Each capability with a side effect declares one of three values:

| Value | Meaning |
|---|---|
| **Compensable** | Another capability reverses its business effect (cancel a booking) |
| **Partly compensable** | The effect can be offset but not erased (a refund after a charge) |
| **Not compensable** | Nothing reverses it (a message that has been delivered) |

Compensation is not undo. The declaration exists so the core can plan an action that spans several boundaries. The core orchestrates such an action; each ambassador is a participant. A multi-step capability inside one boundary is the ambassador's own responsibility: it journals each step and compensates its own completed steps if a later one fails.

### Discovery

The pattern adds no registry of its own. Ambassadors are published and found through whatever the platform already uses (an agent registry, agent cards, a service catalogue). The pattern only requires that each boundary resolves to exactly one ambassador, and that an ambassador can be withdrawn.

## Choices

The definition leaves two choices open.

**Grouping.** One ambassador per external system, or one per logical group in front of several systems. See variants.

**Intelligence.**

| Level | Model use | Fits when |
|---|---|---|
| Scripted | None | Stable API, clear errors, high volume |
| Assisted | Consulted on failures | Errors are ambiguous or the right recovery depends on context |
| Autonomous planning | May plan the steps inside a capability | The procedure varies, or the interface is a document, a screen or another agent |

The contract is the same at every level. Callers cannot tell, and should not care, which level is behind a capability.

If an ambassador needs intelligence, prefer a fast, low-latency model. The boundary is on the path of every action, so speed and cost matter more there than depth of reasoning. This is a preference, not a rule.

How an ambassador is run (whether it keeps state between tasks, whether it is always on) is a deployment choice, covered in the [decision guide](decision-guide.md#deployment-choices).

## Variants

- **System ambassador.** One per external system. The default.
- **Group ambassador.** One per logical capability in front of several systems (for example "payments" across banks). It chooses the system; callers do not.
- **Peer ambassador.** The external party is another organisation's agent. The ambassador speaks an agent protocol outward and still presents plain capabilities inward.
- **Listening post.** Offers a subscription and no capabilities. It watches an external system and reports.

## Optional and excluded

| | Item | Why |
|---|---|---|
| Optional | Human approval before an action | The ambassador is autonomous by definition. Add approval for specific irreversible actions if your rules need it |
| Optional | Try-confirm-cancel (reserve, then confirm) | Strong recovery, but only where the external system offers reservations |
| Excluded | Ambassadors reacting to each other's events | Breaks one direction of initiation, invites loops, and leaves nobody owning the whole flow |
| Excluded | Two-phase commit across boundaries | External systems do not join your transactions |

## Consequences

**Benefits**

- One owner per boundary: one place to audit, patch, limit or switch off.
- Core agents stay small. Their prompts contain domain words only.
- A vendor change is absorbed in one place.
- Injected instructions from outside meet a quarantine before they meet a model with authority.
- A crash or a timeout never turns into a silent duplicate, and never into a guess reported as a fact.
- Overload is refused visibly at the boundary and does not spread.

**Costs**

- One more hop, and a model call on some paths if intelligence is used.
- A durable journal is required, even for the simplest ambassador.
- Where the external system can neither deduplicate nor be asked, some outcomes will be unknown and a person must settle them. The pattern makes that visible. It cannot remove it.
- The ambassador is a single point of failure for its boundary. Run it redundantly.
- A capability contract must be designed. A thin pass-through contract gives none of the benefits.
- Full autonomy puts the whole burden on policy: there is nobody to catch a bad decision at run time.
- Too coarse a grouping produces a "god ambassador". See the decision guide.

## Rules of thumb

1. One boundary, one ambassador, one named human owner.
2. No connector, credential or vendor schema outside an ambassador.
3. Only the core opens a task. Ambassadors do not call the core or each other.
4. Record the intent before the action, and the outcome after. A timeout is not a "no".
5. Every task ends in one of four outcomes. None pauses. Another channel is offered only when the action is known not to have been done.
6. Refuse when full. Never queue without a limit.
7. Nothing from outside reaches a core agent unsanitised, and a notice is a fact, never a command.
8. Start scripted. Add a model only when a failure mode demands it, and prefer a fast one.

## Example

See the [worked example](example.md).

## Known uses

None documented yet. This is a proposed pattern. If you run something that matches it, please open an issue so it can be listed here.

## Related patterns

See [influences.md](influences.md) for what the pattern took from earlier work, and [comparison.md](comparison.md) for how it differs from its neighbours.
