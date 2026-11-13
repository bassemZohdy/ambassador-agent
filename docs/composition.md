# Composing with neighbouring patterns

The ambassador agent does not replace the patterns around it. [Comparison and prior art](comparison.md) says how it differs from each neighbour. This page says how to put them together: which part does what, and what each must not take over.

| Neighbour | Where it sits | It does | The ambassador still does |
|---|---|---|---|
| Gateway | In front | Governs traffic for everyone | Answers for one boundary |
| MCP | Inside, or as a binding | Exposes a capability | Answers for the outcome |
| Saga | Above, in the core | Sequences steps across boundaries | Owns the compensation for its own system |
| Supervisor | Above, in the core | Divides work among agents | Guards the border |

In every case the rule is the same: the neighbour may add a layer, and it may not take a duty. The [conformance rules](conformance.md) still hold in full.

## Gateway

A gateway is horizontal and has no business meaning. It authenticates callers, limits traffic per caller and per cost, and gives one place to observe everything. An ambassador is vertical: one boundary, with its full meaning. They compose, with the ambassador behind the gateway.

![The core system sends a task to the gateway. The gateway passes the admitted task to the ambassador, which acts on the external system.](diagrams/composition-gateway.svg)

Put floods and per-caller limits in the gateway. Put the boundary's own quota in the ambassador: the gateway cannot know how much the external system will accept, or that one action is expensive and another is free. The two limits complement each other. Neither replaces the other.

Two things the gateway does not give you:

- **The principal.** A gateway that authenticated the caller has not established who the task is for. The ambassador still needs verified evidence of the principal (C38 in the [conformance rules](conformance.md)), and the [identity page](identity-and-trust.md) says what counts.
- **A journal.** The gateway sees a request go by. Only the ambassador records the intent before the action and the outcome after, and settles an `unknown`.

## MCP

MCP appears in two places, and they are different.

**Inside the ambassador, as a connector.** A tool exposed over MCP is a good way for the ambassador to reach the external system. It exposes the system and does not answer for outcomes: it has no journal, no owner, no policy and no quarantine. So it stays behind the ambassador. The core never holds it, and never holds a credential for it (C2).

![The core system sends a task to the ambassador. The ambassador calls an MCP tool, which makes the vendor call to the external system.](diagrams/composition-mcp.svg)

The reason is the one the Thoughtworks article gives: plugging a tool protocol straight into an agent couples the agent to the upstream model. Put the tool behind an ambassador and a vendor change is absorbed in one place.

**In front of the ambassador, as a binding.** An ambassador can also offer its capabilities as MCP tools. That is a binding, and a binding never changes a rule. It suits short tasks for a single agent, and it loses the task lifecycle, so a long task or a subscription fits another binding better. The [protocol mapping](protocol-mapping.md#other-bindings) lists the trade-offs.

## Saga

A saga keeps a multi-step action consistent by compensating completed steps when a later one fails. The core orchestrates it. Each ambassador is a participant, and owns the compensating action for its own system, because only it knows how.

![The core system opens a task with ambassador A for step 1, and with ambassador B for step 2. Each ambassador acts on its own external system. The core can later open a compensation task with ambassador A.](diagrams/composition-saga.svg)

How the four outcomes feed the saga:

| Outcome of a step | What the saga does |
|---|---|
| `succeeded` | Go on to the next step. Remember the step, in case it must be compensated |
| `failed` (known not done) | Nothing to undo for this step. Compensate the earlier steps that succeeded |
| `rejected` | The step was refused before any action. Treat as `failed`, and read the reason |
| `unknown` | Do not go on, and do not compensate this step. Wait for the owner to resolve it, then act on the answer |

The last row is the safe reading of the rules, not a separate rule. An `unknown` is not retryable, and no other channel is offered while it is open. A saga that guessed "done" or "not done" would be doing what the pattern refuses to do.

Each capability declares whether it is compensable, partly compensable or not compensable. Use the declaration to plan: put steps that cannot be reversed last. Compensation is not undo. A refund after a charge offsets the charge and does not erase it.

Do not use two-phase commit across boundaries. External systems do not join your transactions, which is why the pattern excludes it and relies on compensation.

A multi-step capability inside one boundary is different. That is the ambassador's own work. It journals each step and compensates its own completed steps if a later one fails. The core does not see it.

## Supervisor

A supervisor, or orchestrator, is an agent that coordinates other agents. It faces inward and divides work. An ambassador faces outward and guards a border. They answer different questions, and they can sit in the same system.

![A supervisor delegates to a worker agent. The worker opens a task with the ambassador, which acts on the external system.](diagrams/composition-supervisor.svg)

Every agent above the ambassador is part of the core system. A supervisor and its workers all reach the external system the same way, by opening a task, and none of them holds a connector or a credential.

Two limits keep the composition clean:

- **The supervisor does not cross the border.** If it holds a vendor client or an API key, it has become a second owner of the boundary, and nobody is accountable for the outcome. That is the case C2 forbids.
- **The ambassador does not supervise.** It does not call other ambassadors, and it does not start work in the core. It sends notices into a subscription the core opened, and a notice is a fact, never a command. Ambassadors reacting to each other's events is excluded from the pattern.

If a supervisor needs to know that something happened outside, it subscribes through a [listening post](variants.md#listening-post) and decides what to do next.

## Putting them together

The four fit in one picture, from the outside in: a gateway governs the traffic, a supervisor and its workers form the core, a saga sequences the work that spans boundaries, and each ambassador answers for its own boundary, with MCP tools or other connectors behind it. No layer takes a duty from another.
