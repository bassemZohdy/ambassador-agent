# Posts

Drafts to adapt to your own voice. The article is in [article.md](article.md) and the order of publication in [publishing-plan.md](publishing-plan.md).

## Positioning

**One line:** One accountable, autonomous agent per external-system boundary.

**The claim:** Tool protocols answer "how does an agent call a system". Nobody answers "who is responsible when it does". The ambassador agent is that answer.

**Phrase to repeat:** The anti-corruption layer translates. The gateway governs. The ambassador answers for it.

**Audience:** enterprise and solution architects, integration platform teams, anyone moving from an agent demo to agents that touch systems of record.

## LinkedIn post

Your agent called a partner API twice. The first call timed out, the model retried, both went through.

Which agent owned that action?

Tool protocols solved how agents reach external systems. They did not solve who answers for what happens next.

I am proposing a design pattern for that gap: the Ambassador Agent.

One accountable, autonomous agent per external-system boundary. Core agents never touch an external system. The whole definition is four lines:

→ One concept: one boundary, one ambassador, one named owner
→ One interaction model: the core opens tasks; each ends as succeeded, failed, rejected or unknown
→ One reliability rule: every action is journalled before it happens
→ Seven duties: contract, identity, policy, admission, journal, quarantine, fallback

It borrows from the outbox, the saga and the actor model, uses A2A as its reference protocol, and adopts none of them as is.

It is a proposal, with open questions listed in the repo. Tell me where it breaks.

This is a personal project.

https://github.com/bassemZohdy/ambassador-agent

#AgenticAI #SoftwareArchitecture #IntegrationPatterns #A2A

## Short posts

1. Tool protocols tell an agent how to call a system. Nothing tells you who answers for the call. Proposal: one accountable agent per external boundary. https://github.com/bassemZohdy/ambassador-agent
2. The anti-corruption layer translates. The gateway governs. The ambassador answers for it. A design pattern for agentic integration: https://github.com/bassemZohdy/ambassador-agent
3. Before an agent acts on a system you do not own, it should write down what it is about to do. That one rule is what lets it recover alone. The journal rule, from the Ambassador Agent pattern: https://github.com/bassemZohdy/ambassador-agent
4. Agents loop. So the agent at the boundary needs admission: one task at a time per resource, a bounded wait, and a refusal when full. https://github.com/bassemZohdy/ambassador-agent

## Talk abstract

**Who answers for it? An accountability pattern for agentic integration.** As agents gain the ability to act on external systems, responsibility for those actions is spread across prompts, tools and gateways. This talk introduces the Ambassador Agent: one accountable, autonomous agent per external-system boundary. We cover the forces behind it, its interaction model and the journal rule, admission under load, how it maps onto A2A, how it differs from the anti-corruption layer, MCP servers and gateways, and the questions that are still open.

## Where to expect pushback

| Objection | Short answer |
|---|---|
| "This is just an anti-corruption layer" | It includes one. It adds an owner: identity, policy, admission, a journal and a fallback |
| "This is just an MCP server" | A tool exposes a capability. It has no lifecycle and does not answer for outcomes. Use one as the connector |
| "This is just an A2A agent" | A2A gives the task lifecycle. The journal, admission, acting for a principal and quarantine are what the ambassador adds. See the protocol mapping |
| "The name is taken" | Acknowledged in the comparison page, with the differences |
| "Why call it an agent if there is no model?" | Identity, contract, state and authority make it an agent. The model is optional by design |
| "No human in the loop is dangerous" | Autonomy is the default, and approval is an option for irreversible actions. Policy carries the weight, and the pattern says so |
| "Has anyone used it?" | Not yet in a documented way. It is a proposal, and known uses are what the repository asks for |
| "Another hop" | Yes. Skip the pattern for read-only, single-consumer lookups |
