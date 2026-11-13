# Comparison and prior art

The name and several of the ideas have history. This page says how the pattern differs from each neighbour, so you can choose between them. None of them is adopted as is; [influences.md](influences.md) records what was taken from each and what was left out.

## The name

| Earlier use | What it is | Difference |
|---|---|---|
| **Ambassador pattern** (cloud and microservices; [Azure Architecture Center](https://learn.microsoft.com/azure/architecture/patterns/ambassador)) | An out-of-process proxy next to a client that handles connectivity: retries, routing, TLS, telemetry | A network helper with no business meaning, owned by the client. The ambassador agent owns a business contract and is owned by the boundary |
| **Ambassador in mobile-agent pattern catalogues** ([Deugo et al.](https://people.scs.carleton.ca/~deugo/Patterns/Agent/Presentations/AgentPatterns/tsld043.htm)) | An agent sent to a remote place to watch for events and report back | Close to the inbound-only "listening post" variant here. No ownership of actions |
| **Ambassador component in US patents** [12,405,978](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/12405978), [12,475,151](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/12475151), [12,505,131](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/12505131) | An intermediary with a protocol translator between external systems and an agent cluster | Infrastructure for communication. Not an accountable agent with a contract, ledger and owner. Anyone adopting this pattern commercially should have counsel review these documents; this page is not legal advice |

This pattern keeps the word because the diplomatic meaning fits exactly: an accredited representative, with credentials, speaking the other side's language, who can be recalled.

## Neighbouring patterns

| Pattern | Shared ground | What the ambassador agent adds |
|---|---|---|
| **Anti-corruption layer** (domain-driven design) | Translate so the foreign model does not leak in | Runtime ownership: identity, policy, ledger, fallback, optional judgement |
| **MCP server / tool** | Uniform way to call an external capability | An MCP tool exposes; it does not answer for outcomes. An MCP tool is a good *connector* inside an ambassador |
| **API or agent gateway** | Central policy, auth and observability | A gateway is horizontal and semantics-free. An ambassador is vertical: one boundary, full meaning. They compose: ambassadors sit behind the gateway |
| **Back-end for agents** | A mediating layer so agents do not call APIs directly | That layer is shaped per consuming agent. An ambassador is shaped per external system and shared by all consumers |
| **Adapter / façade** | Hide an awkward interface | Stateless code. No identity, no accountability, no inbound path |
| **Supervisor / orchestrator agent** | An agent that coordinates others | A supervisor faces inward and divides work. An ambassador faces outward and guards a border |
| **Saga** | Multi-step consistency with compensation | An ambassador is a natural saga participant: it owns the compensating action for its system |

A useful summary: the anti-corruption layer says *translate*, the gateway says *govern*, the cloud ambassador says *connect*. The ambassador agent says *answer for it*.

## Further reading

- Thoughtworks, ["Your agent skill is not an anti-corruption layer"](https://www.thoughtworks.com/en-gb/insights/blog/generative-ai/your-agent-skill-not-anti-corruption-layer): why plugging MCP straight into an agent couples it to upstream models
- Gravitee, ["Business process integration patterns for AI agents, APIs and event streams"](https://www.gravitee.io/corpus/gen-991/process-integration/business-process-integration-patterns-for-ai-agents-apis-and-event-streams.html)
- Salesforce Architects, ["Agentic integration patterns"](https://architect.salesforce.com/docs/architect/fundamentals/guide/agentic-integration-patterns)
- M. Araujo, ["The back-end for agents pattern"](https://medium.com/@mdbaraujo/the-back-end-for-agents-pattern-bfa-32e69baf8da3)
