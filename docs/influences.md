# Influences

The Ambassador Agent pattern is defined on its own terms in [pattern.md](pattern.md). It does not adopt any earlier pattern as is. It was shaped by considering several of them, taking the part that fits an accountable boundary agent and leaving the rest.

This page records, for each influence, what was taken and what was deliberately left out. For how the pattern *differs* from its neighbours when you have to choose between them, see [comparison.md](comparison.md).

## How the candidates were weighed

The interaction and reliability ideas were compared against six criteria: accountability, autonomy, fit with systems we do not control, mapping onto A2A, simplicity and recovery. The scores are the authors' judgement, not measurements. They come from two rounds with different weights, so read them as a ranking and not as exact distances.

| Candidate | Score | Role in the pattern |
|---|---|---|
| Write-ahead intent (from the transactional outbox) | 88 | The reliability rule |
| Durable execution | 84 | The same rule extended to many steps; a deployment choice |
| Task lifecycle (from A2A) | 73 | The interaction model |
| Orchestrated saga | 71 | One contract field: compensation |
| Virtual actor | 79 | The source of the admission duty |
| Try-confirm-cancel | 65 | Optional |
| Stateless tool call | 60 | Not taken: no lifecycle and no owner of the outcome |
| Choreography between agents | 49 | Excluded |

## Software architecture

| Influence | What we took | What we left out |
|---|---|---|
| [Transactional outbox](https://microservices.io/patterns/data/transactional-outbox.html) | Record the intent before sending, so a crash never leaves a silent gap. This is the [journal rule](pattern.md#reliability-rule-the-journal) | The relay and the message broker. Ours is a write-ahead record with reconciliation, not a publishing mechanism |
| [Saga](https://microservices.io/patterns/data/saga.html) | Each participant owns the compensating action for its own system, and declares whether one exists | Orchestration of a transaction across systems. That belongs to the core, with ambassadors as participants |
| [Actor model](https://en.wikipedia.org/wiki/Actor_model) (Hewitt; Erlang, Akka) | Private state, addressing by identity, and one piece of work at a time. Bounded mailboxes showed that a limit and a refusal, not a queue, are what protect a system. This became [admission](pattern.md#admission) | The mailbox as a concept of the pattern, supervision trees, and actors spawning actors |
| Virtual actors ([Orleans](https://learn.microsoft.com/dotnet/orleans/overview), [Dapr Actors](https://www.diagrid.io/blog/understanding-dapr-actors-for-scalable-workflows-and-ai-agents)) | An entity that stays addressable while idle and is activated by incoming work. This is what makes *on demand* and *durable* compatible | Any dependence on a particular runtime |
| [Anti-corruption layer](https://learn.microsoft.com/azure/architecture/patterns/anti-corruption-layer) (domain-driven design) | Translation at the border so the external model never leaks into the core's language | Its passive nature. A translation layer has no identity, owner, journal or authority to refuse |
| [Ambassador](https://learn.microsoft.com/azure/architecture/patterns/ambassador) (cloud design patterns) | The name, and the idea of a representative that handles outbound connectivity concerns such as retries and circuit breaking | Co-location with a single client, and the absence of business meaning |
| [Enterprise Integration Patterns](https://www.enterpriseintegrationpatterns.com/toc.html) (Hohpe and Woolf) | Message translator, idempotent receiver and correlation identifier | The message bus as the centre of the architecture, and routing topologies |
| [Ports and adapters](https://alistair.cockburn.us/hexagonal-architecture/) (hexagonal architecture) | A core that depends only on abstract ports, so the agent platform, the protocol and the external technology can change independently | Nothing significant. It shapes an implementation, not the definition |
| [Circuit breaker](https://martinfowler.com/bliki/CircuitBreaker.html) | Stop calling a system that is failing, and answer at once | Nothing significant |
| [Confused deputy](https://en.wikipedia.org/wiki/Confused_deputy_problem) (capability security) | An ambassador acts for a named principal and never lends its own authority by default | A full capability-security model |
| Ambassador in mobile-agent catalogues ([Deugo et al.](https://people.scs.carleton.ca/~deugo/Patterns/Agent/Presentations/AgentPatterns/tsld043.htm)) | The *listening post* variant | Agent mobility: an ambassador does not migrate to the remote system |

## AI and agent systems

These are newer, and several are products as much as patterns. The pattern takes ideas from them and stays independent of every one.

| Influence | What we took | What we left out |
|---|---|---|
| Agent-to-agent protocol (A2A) | The task with a lifecycle, a waiting state, a refused state and published skills. It is the reference for the interaction model. See [protocol-mapping.md](protocol-mapping.md) | The protocol as the definition, and the task states that pause for input |
| Durable execution (for example [Temporal](https://temporal.io/), [Restate](https://restate.dev/), checkpointing in agent frameworks) | Journal each completed step so that a restart resumes instead of repeating. This defines the *durable* deployment choice | A workflow engine as a requirement |
| Concurrent-run strategies in agent servers ([LangGraph's deployment server](https://docs.langchain.com/langsmith/double-texting)) | A second request on a busy thread may wait or be refused | Interrupt and rollback. An external side effect cannot be undone by cancelling the run that caused it |
| Overload handling in actor platforms ([Akka mailboxes](https://doc.akka.io/docs/akka/2.9/typed/mailboxes.html), [Cloudflare Durable Objects](https://developers.cloudflare.com/durable-objects/platform/limits)) | A bounded wait, an explicit refusal when full, and telling callers not to retry at once | Platform-specific limits |
| Agent gateways with rate and token limits | Limits per caller and per cost belong in front of the agent | The gateway as the owner of the boundary. It cannot know the external system's own quota |
| Ambient agents ([LangChain, 2025](https://blog.langchain.com/introducing-ambient-agents)) | An agent driven by a stream of events instead of a chat. This informs subscriptions and the *always on* choice | A model in the loop for every event, and human review as a normal step |
| Agents as actors ([AutoGen Core](https://microsoft.github.io/autogen/dev/user-guide/core-user-guide/index.html), [Dapr Agents](https://dapr.io/ai/), [Cloudflare Agents](https://developers.cloudflare.com/agents/)) | Evidence that stateful, long-lived, mostly idle agents are practical | Framework coupling. Any of these can host an ambassador; none defines one |
| Fast and slow thinking in agents ([Talker-Reasoner architecture](https://arxiv.org/abs/2410.08328)) | Put fast, cheap intelligence where latency matters. The pattern prefers a fast, low-latency model at the boundary | The conversational role of the fast system, and a slow reasoner inside the ambassador by default |
| Quarantine of untrusted content ([dual LLM pattern](https://simonwillison.net/2023/Apr/25/dual-llm-pattern/)) | Content from outside is data, never instructions, and is handled apart from any model that holds authority | A second language model as the mechanism. Quarantine may be purely deterministic |

## Considered and not taken

| Idea | Why not |
|---|---|
| Human-in-the-loop as a core step | The ambassador is autonomous by definition. Approval remains an option for specific irreversible actions |
| Try-confirm-cancel as a requirement | It needs the external system to offer reservations, and most do not. It remains an option |
| Choreography: ambassadors reacting to each other's events | It breaks one direction of initiation, invites loops, and leaves nobody owning the whole flow |
| Two-phase commit | External systems do not join our transactions |
| A stateless tool call as the interaction model | It has no lifecycle and no owner of the outcome |
| The core holding a queue for messages from ambassadors | Two parties that can each start an exchange with the other can loop without end |

## What this pattern emphasises

The pattern makes five design choices. They are choices to agree or disagree with, not claims to be first:

1. **Accountability as the organising idea.** One boundary, one agent, one named human owner, one journal.
2. **Full autonomy with a fixed set of outcomes.** A task never pauses, and always ends as succeeded, failed, rejected or unknown. What to do next travels beside the outcome and never replaces it.
3. **One direction of initiation.** Only the core opens a task; news from outside arrives as notices on a subscription the core opened.
4. **Reliability from one rule.** Record the intent before the action, and reconcile what is unknown. It claims no exactly-once effect: it says which of three delivery classes a capability has.
5. **A small definition.** One concept, one interaction model, one reliability rule and seven duties. How an ambassador is run is kept out of it.

We have not found a single source that combines these five, but our search was limited. If you know one, please open an issue. It belongs on this page.
