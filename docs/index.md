# The Ambassador Agent pattern

**One accountable, autonomous agent per external-system boundary.**

This is the guide to the pattern. It explains the idea in a few minutes, with four animated diagrams, and points to the page that covers each topic in depth.

## The question it answers

Tool protocols tell an agent *how* to call an external system. They do not say *who is responsible* once it does. When several core agents reach the same partner API directly, vendor terms leak into prompts, a retried call becomes a duplicate payment, text from outside lands in the context of an agent with authority, and each agent copes with outages and overload in its own way.

The Ambassador Agent pattern gives every external boundary a single owner.

## The pattern at a glance

![A core agent opens a task with the ambassador. It passes policy and admission, the ambassador records its intent in the journal, then acts on the external system; replies pass quarantine before the core agent sees them. A task is refused when too many are waiting.](diagrams/architecture.svg)

| Part | Statement |
|---|---|
| One concept | The ambassador: one boundary, one ambassador, one named human owner |
| One interaction model | The core opens tasks. Each task ends as `succeeded`, `failed`, `rejected` or `unknown`. None pauses |
| One reliability rule | Every action is journalled before it happens, so the ambassador recovers on its own |
| Seven duties | Contract, identity, policy, admission, journal, quarantine, fallback |

The full definition, with forces, variants and consequences, is in [the pattern](pattern.md).

## How it behaves

### A task

Only the core opens a task. The ambassador decides whether to admit it, records what it is about to do, acts, records what happened, and answers in the core's language.

![A core agent opens a task. The ambassador checks policy and admission, records its intent, sends the vendor request, records the outcome, sanitises the reply and answers with one of four outcomes.](diagrams/task.svg)

### Recovery

If the ambassador stops between sending and recording, the outcome is unknown. On restart it finds the open intent and follows what the capability declares: ask the external system, send the same operation id again, or stop and hand it to the owner. A timeout is treated the same way: it is not a "no".

![After a restart the ambassador reads the journal for intents with no outcome, then verifies with the external system, resends, or stops and reports the outcome as unknown, and records the result.](diagrams/recovery.svg)

### News from outside

An ambassador never starts an exchange with the core. The core opens a subscription, and the ambassador sends notices into it. A notice is a fact, never a command.

![The core system opens a subscription. When the external system sends an event, the ambassador translates and sanitises it, records it and sends a notice to the core system.](diagrams/notice.svg)

## Terms

The main terms are below. The [glossary](glossary.md) has all of them, grouped.

| Term | Meaning |
|---|---|
| Ambassador | The agent that owns one boundary and answers for everything that crosses it |
| Boundary | One external system, or a logical group of systems that callers treat as one |
| Core system | Your own agents, workflows and product, speaking your own language |
| Capability | One thing the core may ask of a boundary, named in the core's language |
| Task | One request for one capability, for one principal. Only the core opens it |
| Principal | Who the task is for. The ambassador acts for the principal, never as itself |
| Outcome | What is known about the action: succeeded, failed (known not done), rejected, or unknown (may have been done) |
| Journal | The durable record of every crossing: intent before, outcome after |
| Operation id | The identifier sent to the external system on every try, so it can deduplicate or be asked. The idempotency key, or one the ambassador makes |
| Reconciliation | Settling an action whose outcome was not recorded: ask the external system, send the same operation id again, or hand it to the owner |
| Admission | The duty to limit work: one task at a time per resource, a bounded wait, refusal when full |
| Notice | A fact from the external system, translated and sanitised, sent on a subscription |
| Compensation | Whether a capability's business effect can be reversed, declared in the contract |
| Fallback | Another channel that can finish the job when the external system cannot |

## Read on

| If you want to | Read |
|---|---|
| Understand the full definition | [The pattern](pattern.md) |
| Decide whether and how to apply it | [Decision guide](decision-guide.md) |
| Check a design or an implementation against the rules | [Conformance](conformance.md) |
| Understand delegation, the confused deputy and forged principals | [Identity and trust](identity-and-trust.md) |
| Recognise designs that look like the pattern and are not | [Anti-patterns](anti-patterns.md) |
| Choose between a system, group, peer or listening-post ambassador | [Variants](variants.md) |
| See it applied to one boundary, without code | [Worked example](example.md) |
| Bind it to a protocol | [Protocol mapping](protocol-mapping.md), with A2A as the reference |
| Know where the ideas came from | [Influences](influences.md) |
| Choose between this and a neighbouring pattern | [Comparison and prior art](comparison.md) |
| Combine it with a gateway, MCP, a saga or a supervisor | [Composition](composition.md) |
| Follow up the sources | [References](references.md) |

A small reference implementation in Python lives in the repository's `reference/` folder. It shows the pattern can be built; the pattern does not depend on it.

## Status and open questions

This is version 0.2 of a proposed pattern. It has no documented use in production yet, and the following questions are open:

1. **Redundancy and admission.** The pattern now lists what more than one replica needs (mutual exclusion per resource across copies, a shared journal, a claim on each open intent) and three ways to get mutual exclusion. None of it is implemented in the reference, which is tested in one process only, and none of it has run in production.
2. **The limit of autonomy.** When an outcome is unknown and the external system cannot be asked, the ambassador reports `unknown`, holds repeats and lists the exception. A person must resolve it. How long it may be held, who is alerted, and whether a task type may set a time limit before escalating are not yet described.
3. **Policy.** With no person in the loop, policy is the only safeguard before an irreversible action. The pattern does not yet say how policy is defined or reviewed.
4. **`unknown` in A2A.** A2A has no state for "may have happened". It maps to `failed` with the outcome in extension data, so a client that ignores the extension may read it as a plain failure. The ambassador holds repeats of the same task and, for a capability that names a resource, holds the resource too. A client that retries under a new key against a capability with no resource still defeats it.

Counter-examples and known uses are the most useful contributions. The repository's issue templates ask for both.

## The diagrams

The diagrams are drawn with [archgram](https://www.npmjs.com/package/archgram) from the specifications in `docs/diagrams/`. Each part and each arrow names the sentence of [the pattern](pattern.md) that backs it, so a diagram can be checked against the text.
