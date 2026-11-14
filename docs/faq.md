# Questions and objections

The objections the pattern is most likely to meet, each with a short answer and a link to where the specification says more. The first eight are the ones expected from readers who know a neighbouring pattern. The rest come up when people try to apply it.

If you have an objection that is not here, or a counter-example, please open an issue. See [CONTRIBUTING](../CONTRIBUTING.md).

## "Isn't this just an anti-corruption layer?"

Anti-corruption layer is the closest relative, and the ambassador includes one: it translates the vendor's model into the core system's language so the foreign model does not leak in. What it adds is an owner at run time: identity, policy, admission, a journal and a fallback. An anti-corruption layer says *translate*. The ambassador says *answer for it*.

See the [neighbouring patterns](comparison.md#neighbouring-patterns) and the [seven duties](pattern.md#the-seven-duties).

## "Isn't this just an MCP server?"

No, and the two work well together. An MCP tool exposes a capability. It has no task lifecycle and does not answer for outcomes: it has no journal, no owner and no quarantine. The ambassador uses a tool like that as its *connector*, behind the ambassador, so a core agent never holds it. An ambassador can also offer its capabilities as MCP tools, as a binding, for short tasks.

See [composition: MCP](composition.md#mcp) and the [other bindings](protocol-mapping.md#other-bindings).

## "Isn't this just an A2A agent?"

A2A gives the task lifecycle and a way to discover and call an agent. It does not say who answers for the action, how a crash is recovered, or how a task is admitted under load. Those are what the ambassador adds: the journal, admission, acting for a principal, and quarantine. The pattern is A2A-shaped and not A2A-bound. The one place where A2A has no fitting state is `unknown`, and the mapping page says plainly that this is its weakest row.

See [A2A-shaped, not A2A-bound](protocol-mapping.md#a2a-shaped-not-a2a-bound) and [the current mapping for `unknown`](protocol-mapping.md#the-current-mapping-for-unknown).

## "The name is taken"

It is. The cloud and microservices "ambassador" is a network helper beside a client, and the word also appears in mobile-agent catalogues and in patents. The comparison page lists each use and what differs. The word stays because the diplomatic meaning fits: an accredited representative, with credentials, speaking the other side's language, who can be recalled. Anyone adopting the pattern commercially should have counsel read the patents listed there.

See [the name](comparison.md#the-name).

## "Why call it an agent if there is no model?"

Because of what it has, not what it runs. It has an identity, a contract, state and authority to act. The model is optional by design. An ambassador can be scripted, assisted by a small model for judgement, or autonomous in planning, and the contract is the same at every level. Callers cannot tell which level is behind a capability and should not care.

See [which intelligence level](decision-guide.md#which-intelligence-level) and the [definition](pattern.md#the-definition-in-four-parts).

## "No human in the loop is dangerous"

Autonomy is the default, and the pattern says what that costs: with nobody to catch a bad decision at run time, the whole burden falls on policy. Approval is available for specific irreversible actions. A capability can declare that it requires approval, and the ambassador then checks that the approval scope is held. It does not ask anyone. Everything an ambassador does is journalled, and an outcome nothing can settle goes to a named human owner and is not guessed.

See [optional and excluded](pattern.md#optional-and-excluded), [what the contract declares](pattern.md#what-the-contract-declares) and the [identity page](identity-and-trust.md).

## "Has anyone used it?"

Not in a documented way. This is a proposed pattern, and the repository says so. The reference implementation shows that it can be built and tests its reliability claims, but it is an illustration and not a production system. Known uses, and counter-examples where the pattern does not fit, are the most useful contributions.

See [known uses](pattern.md#known-uses) and the [open questions](index.md#status-and-open-questions).

## "Isn't it just another hop?"

Yes. It costs one more hop, a durable journal, and a model call on some paths if intelligence is used. Skip the pattern for a read-only, internal, single-consumer lookup: a plain tool is enough. Use it when an action has a side effect that someone must answer for, when several agents reach the same partner, or when text from outside must not reach an agent with authority.

See [do you need an ambassador](decision-guide.md#do-you-need-an-ambassador) and the [costs](pattern.md#consequences).

## "Doesn't a gateway already do this?"

A gateway governs: authentication, limits per caller and per cost, observability. It is horizontal and has no business meaning. It does not record intent before an action, settle an `unknown`, or know that one action is expensive and another free. Put floods and per-caller limits in the gateway and the boundary's own quota in the ambassador. The ambassador sits behind the gateway.

See [composition: gateway](composition.md#gateway).

## "Why not a saga, or a supervisor agent?"

They answer different questions and they compose. A saga keeps a multi-step action consistent, and the ambassador owns the compensating action for its own system. A supervisor divides work inside the core and faces inward, and the ambassador faces outward and guards a border. Neither can replace the ambassador, because neither answers for what crossed the boundary.

See [composition: saga](composition.md#saga) and [composition: supervisor](composition.md#supervisor).

## "Isn't the journal just the external system's idempotency key again?"

The key helps, and the ambassador uses it, but it is not enough alone. The key lets the external system deduplicate. The journal records what the ambassador meant to do and what it learned, so after a crash it knows whether to ask, resend or stop. A timeout is treated like a crash. Where the external system can neither deduplicate nor be asked, the outcome is `unknown` and goes to a person. The pattern makes that visible. It cannot remove it.

See [the reliability rule](pattern.md#reliability-rule-the-journal) and [what the journal guarantees, and what it does not](pattern.md#what-the-journal-guarantees-and-what-it-does-not).

## "Isn't the ambassador a single point of failure?"

For its boundary, yes, and the pattern says so. Run more than one copy. That needs more than a second process: mutual exclusion per resource across copies, one shared journal, a claim on each open intent, and an atomic check and write. The pattern lists options and does not choose among them. The reference implementation demonstrates one option, a lease with a fencing token on a shared SQLite file, including a copy killed mid-task. It does not run on a networked store, and the pattern has no use in production yet.

See [more than one replica](pattern.md#more-than-one-replica) and the [conformance rules for replicas](conformance.md#more-than-one-replica).

## "Is any of this new?"

Mostly not, and the pattern does not claim to be. It combines ideas that already exist: the anti-corruption layer, the actor model, durable execution, the cloud ambassador, and task lifecycles in agent protocols. What it emphasises is the single owner of the boundary and the rule that what to do next never replaces what is known.

See [influences](influences.md) and [what this pattern emphasises](influences.md#what-this-pattern-emphasises).

## "How do I know my design is an ambassador?"

Check it against the numbered rules. Each is a Must, a Should or a May, and the page lists designs that look like the pattern and fail it. The [anti-patterns](anti-patterns.md) page names the usual ways a design drifts: a god ambassador, a pass-through contract, shared credentials.

See [conformance](conformance.md) and [claiming conformance](conformance.md#claiming-conformance).
