# The Ambassador Agent pattern

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.24210615.svg)](https://doi.org/10.5281/zenodo.24210615)

**One accountable, autonomous agent per external-system boundary.**

A design pattern for agentic integration platforms. It answers a question tool protocols leave open: when an agent acts on a system you do not own, *who is responsible for that action?*

> This repository is the pattern: its definition, forces, variants, trade-offs and guidance. A small reference implementation is included to show the pattern is buildable, but the pattern does not depend on any language, agent platform or protocol.

## The pattern in one page

**Context.** A stable core system (agents, workflows, a product) must act on, and hear from, many external systems it does not control.

**Problem.** When core agents reach external systems directly through tools:

- vendor vocabulary and error codes leak into prompts
- side effects have no single owner, so duplicates and half-finished actions go unnoticed
- untrusted external content enters the context of agents that hold authority
- every agent handles outages and overload its own way

**Solution.** Put one *ambassador agent* on each boundary and make it the only path across. Core agents ask for a capability in their own language. The ambassador owns everything else, and finishes every task on its own.

![A core agent opens a task with the ambassador. It passes policy and admission, the ambassador records its intent in the journal, then acts on the external system; replies pass quarantine before the core agent sees them. A task is refused when too many are waiting.](docs/diagrams/architecture.svg)

**The definition in four parts**

| Part | Statement |
|---|---|
| One concept | The ambassador: one boundary, one ambassador, one named human owner |
| One interaction model | The core opens tasks. Each task ends as `succeeded`, `failed`, `rejected` or `unknown`. None pauses |
| One reliability rule | Every action is journalled before it happens, so the ambassador recovers on its own |
| Seven duties | Contract, identity, policy, admission, journal, quarantine, fallback |

**The seven duties**

| Duty | What it means |
|---|---|
| Contract | Capabilities named in the core system's language, each stating whether it is compensable |
| Identity | Turns "who is this for" into credentials the external system accepts |
| Policy | Refuses a task before it crosses the boundary |
| Admission | One task at a time per resource, a bounded wait, a refusal with a retry hint when full, paced to the external quota |
| Journal | Intent recorded before every crossing, outcome after; the audit record |
| Quarantine | Everything from outside is data, sanitised before core agents see it |
| Fallback | Another channel, offered only when the action is known not to have been done |

**Two choices**

- **Grouping.** One ambassador per external system, or one per logical group (for example "payments" in front of several banks).
- **Intelligence.** None, a model consulted on failures, or a model that plans inside a capability. The contract is the same in every case. If a model is needed, a fast, low-latency one is preferred.

How an ambassador is run (stateless or durable, always on or on demand) is a deployment choice and not part of the definition.

**Eight rules**

1. One boundary, one ambassador, one named human owner.
2. No connector, credential or vendor schema outside an ambassador.
3. Only the core opens a task. Ambassadors do not call the core or each other.
4. Record the intent before the action, and the outcome after.
5. Every task ends in one of four outcomes. None pauses.
6. Refuse when full. Never queue without a limit.
7. Nothing from outside reaches a core agent unsanitised, and a notice is a fact, never a command.
8. Start scripted. Add a model only when a failure mode demands it, and prefer a fast one.

## Read the pattern

| Document | What it covers |
|---|---|
| [Guide](docs/index.md) | A short introduction with four animated diagrams, the terms, and the open questions |
| [The pattern](docs/pattern.md) | Full definition: intent, context, problem, forces, solution, duties, variants, consequences |
| [Decision guide](docs/decision-guide.md) | When to use it, where a boundary ends, designing a capability, admission limits, deployment choices |
| [Worked example](docs/example.md) | The pattern applied to one boundary through six scenarios, with no code |
| [Protocol mapping](docs/protocol-mapping.md) | How the interaction model maps onto A2A as the reference protocol, the gaps, and a proposed Extension |
| [Influences](docs/influences.md) | What was taken from the outbox, saga, actor model, durable execution and others, and what was left out |
| [Comparison and prior art](docs/comparison.md) | How it differs from the cloud Ambassador pattern, anti-corruption layer, MCP servers, gateways |
| [References](docs/references.md) | Every pattern, protocol, platform and paper considered, grouped by kind |

## Reference implementation (optional)

[`reference/`](reference/) holds a dependency-free Python sketch of the pattern, with Google ADK and LangGraph as example agent platforms and A2A as an example protocol. They are illustrations, and the ADK and A2A parts are marked experimental. [`reference/abstraction.md`](reference/abstraction.md) explains how the platform and the protocol are kept out of the core.

## Status and contributing

Version 0.2: a proposed pattern, open for critique. The most useful contributions are counter-examples (a boundary the pattern does not fit), known uses, and new variants. See [CONTRIBUTING.md](CONTRIBUTING.md).

To cite it, use the DOI above (it always resolves to the latest version) or the "Cite this repository" button, which reads [CITATION.cff](CITATION.cff).

Tests: `python3 tools/test_check_docs.py && python3 tools/check_docs.py . && cd reference/python && pytest -q`

## License

The pattern documentation is licensed under [CC BY 4.0](LICENSE-DOCS.md): use and adapt it freely with attribution. The reference code is [MIT](LICENSE).
