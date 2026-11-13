# References

Every pattern, protocol, platform and paper that was considered while defining the Ambassador Agent pattern, grouped by kind. Each entry says how it relates to the pattern.

For what was taken from each and what was left out, see [influences.md](influences.md). For how the pattern differs from its closest neighbours, see [comparison.md](comparison.md).

Links were collected in November 2026. Vendor pages describe that vendor's product and are cited for the idea, not as an endorsement.

## The name

| Source | Relation |
|---|---|
| [Ambassador pattern](https://learn.microsoft.com/azure/architecture/patterns/ambassador), Azure Architecture Center | The cloud pattern of the same name: a helper beside a client that handles connectivity. Shares the name and the outbound-connectivity idea only |
| Burns and Oppenheimer, "Design patterns for container-based distributed systems", HotCloud 2016 | The paper that named the sidecar, ambassador and adapter container patterns |
| [Ambassador, in agent pattern catalogues for mobile agents](https://people.scs.carleton.ca/~deugo/Patterns/Agent/Presentations/AgentPatterns/tsld043.htm), Deugo et al. | An agent sent to a remote place to report events. The origin of the listening-post variant |
| US patents [12,405,978](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/12405978), [12,475,151](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/12475151), [12,505,131](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/12505131) | Describe an "ambassador" component with a protocol translator between external systems and agents. Infrastructure for communication, not an accountable agent. Not legal advice |

## Boundary and integration patterns

| Source | Relation |
|---|---|
| Evans, *Domain-Driven Design*, 2003; [Anti-corruption layer](https://learn.microsoft.com/azure/architecture/patterns/anti-corruption-layer) | Translation at the border. The ambassador includes one and adds ownership |
| Hohpe and Woolf, [*Enterprise Integration Patterns*](https://www.enterpriseintegrationpatterns.com/toc.html), 2003 | Message translator, idempotent receiver, correlation identifier, messaging gateway |
| Cockburn, [Hexagonal architecture](https://alistair.cockburn.us/hexagonal-architecture/) (ports and adapters) | How an implementation keeps the platform and protocol out of its core |
| Thoughtworks, ["Your agent skill is not an anti-corruption layer"](https://www.thoughtworks.com/en-gb/insights/blog/generative-ai/your-agent-skill-not-anti-corruption-layer) | The argument that wiring tools straight into an agent couples it to upstream models |
| Araujo, ["The back-end for agents pattern"](https://medium.com/@mdbaraujo/the-back-end-for-agents-pattern-bfa-32e69baf8da3) | A mediating layer shaped per consuming agent. The ambassador is shaped per external system |
| Salesforce Architects, ["Agentic integration patterns"](https://architect.salesforce.com/docs/architect/fundamentals/guide/agentic-integration-patterns) | A vendor catalogue of how agents reach enterprise systems |
| Gravitee, ["Business process integration patterns for AI agents, APIs and event streams"](https://www.gravitee.io/corpus/gen-991/process-integration/business-process-integration-patterns-for-ai-agents-apis-and-event-streams.html) | Describes an anti-corruption layer for agent-to-legacy integration |
| Gravitee, ["AI agent gateway patterns"](https://gravitee.io/corpus/gen-541/api-gateway/ai-agent-gateway-patterns.html) | The gateway in front: identity, policy and cost limits per caller. Complements an ambassador |

## Reliability and consistency

| Source | Relation |
|---|---|
| Richardson, [Transactional outbox](https://microservices.io/patterns/data/transactional-outbox.html) | Record before sending. The source of the journal rule |
| Garcia-Molina and Salem, "Sagas", 1987; Richardson, [Saga](https://microservices.io/patterns/data/saga.html) | Compensation owned by each participant. The source of the compensation field |
| Helland, "Life beyond distributed transactions", 2007 | Why systems that do not share a transaction need idempotence and tentative operations. Background for try-confirm-cancel, which is optional here |
| Fowler, [Circuit breaker](https://martinfowler.com/bliki/CircuitBreaker.html); Nygard, *Release It!* | Stop calling a failing system and answer at once |
| Durable execution engines: [Temporal](https://temporal.io/), [Restate](https://restate.dev/) | Journal every step so a restart resumes. The journal rule extended to many steps |
| ["Durable agents: why async queues break for long-running AI workflows"](https://tianpan.co/blog/2026-04-23-durable-agents-async-queue-workflow-checkpoint) | A survey of durable execution in agent frameworks |
| Two-phase commit | Considered and excluded: external systems do not join our transactions |

## Concurrency and overload

| Source | Relation |
|---|---|
| Hewitt, Bishop and Steiger, "A universal modular Actor formalism for artificial intelligence", 1973; [Actor model](https://en.wikipedia.org/wiki/Actor_model) | Private state, identity and one piece of work at a time. The source of the admission duty |
| Virtual actors: [Orleans](https://learn.microsoft.com/dotnet/orleans/overview); [Dapr actors](https://docs.dapr.io/developing-applications/building-blocks/actors/actors-features-concepts/) | Activation on demand with state kept while idle; one turn at a time per actor |
| [Akka mailboxes](https://doc.akka.io/docs/akka/2.9/typed/mailboxes.html) | A bounded mailbox refuses when full |
| Cloudflare Durable Objects: [limits](https://developers.cloudflare.com/durable-objects/platform/limits) | Queue, then an explicit overloaded error that callers should not retry at once |
| LangChain, [Double texting](https://docs.langchain.com/langsmith/double-texting) | Four strategies for a second request on a busy thread. Only waiting and refusing are safe for external side effects |
| MuleSoft, [A2A token-based rate limit policy](https://docs.mulesoft.com/gateway/latest/policies-included-a2a-v1-token-rate-limit) | An example of cost limits for agent traffic at a gateway |
| [OWASP Top 10 for LLM applications](https://genai.owasp.org/llm-top-10/) | Lists unbounded consumption as a risk. Admission is the pattern's answer at the boundary |

## Agent protocols and platforms

| Source | Relation |
|---|---|
| [Agent2Agent (A2A) protocol](https://a2a-protocol.org/) and its [specification repository](https://github.com/a2aproject/A2A) | The reference protocol for the interaction model. See [protocol-mapping.md](protocol-mapping.md) |
| Agentic AI Foundation, ["A2A v1.0: a builder's guide"](https://aaif.io/blog/a2a-v1-0-a-builder-s-guide-part-1-discovery-tasks-and-clients) | A walk through discovery, tasks and task states in version 1.0 |
| [Model Context Protocol](https://modelcontextprotocol.io/) | A way to expose capabilities to one agent. A fit for a connector, or a binding for short tasks |
| [AutoGen Core](https://microsoft.github.io/autogen/dev/user-guide/core-user-guide/index.html) | An agent runtime built on the actor model |
| [Dapr Agents](https://dapr.io/ai/) | Agents on virtual actors and durable workflows |
| [Cloudflare Agents](https://developers.cloudflare.com/agents/) | Agents as stateful, mostly idle objects |
| Google ADK and LangGraph | The example agent platforms in the reference implementation |

## Agentic patterns

| Source | Relation |
|---|---|
| LangChain, ["Introducing ambient agents"](https://blog.langchain.com/introducing-ambient-agents) | Agents driven by event streams. Informs subscriptions and the always-on choice |
| ["Agents thinking fast and slow: a Talker-Reasoner architecture"](https://arxiv.org/abs/2410.08328), 2024; Kahneman, *Thinking, Fast and Slow*, 2011 | Fast and slow processing in agents. The basis for preferring a fast model at the boundary |
| Willison, ["The dual LLM pattern"](https://simonwillison.net/2023/Apr/25/dual-llm-pattern/) | Untrusted content kept apart from a model that holds authority. Informs quarantine |
| Arsanjani and Bustos, [*Agentic Architectural Patterns for Building Multi-Agent Systems*](https://agentic-ai.readthedocs.io/en/latest/DesignPatterns/arsanjani-patterns/), 2026 | A pattern language for multi-agent systems, including robustness and fault-tolerance patterns |
| [Awesome agentic patterns](https://github.com/jott2121/awesome-agentic-patterns) | A public catalogue of agentic patterns that accepts contributions |

## Security

| Source | Relation |
|---|---|
| Hardy, "The confused deputy", 1988; [Confused deputy problem](https://en.wikipedia.org/wiki/Confused_deputy_problem) | Why an ambassador acts for a named principal and never lends its own authority |
| Jones et al., [RFC 8693, OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693), 2020 | One way to turn a delegation into a token that identifies the principal at the external system. See [identity and trust](identity-and-trust.md) |

## How to add a reference

Open a pull request against this page with the source, a link, and one line on how it relates. Sources that describe a system already working this way belong under "Known uses" in [pattern.md](pattern.md#known-uses) instead.
