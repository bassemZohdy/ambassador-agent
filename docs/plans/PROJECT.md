# Project plan: Ambassador Agent pattern

## Goal

Publish the Ambassador Agent as a design pattern that architects can read, judge and apply without any code. Done means: a v1.0 pattern specification, supporting guides and examples, a public docs site, and launch material that matches the specification.

## Scope

- The pattern itself: definition, glossary, conformance rules, variants, anti-patterns, identity and trust.
- Guidance around it: composition with neighbouring patterns, worked examples, FAQ.
- Repository hygiene needed to keep the docs trustworthy (link checking, contribution paths).
- Launch copy and a published docs site.

## Out of scope

- A production framework. The code under `reference/` stays a small illustration.
- Posting the launch material. That is the author's action and stays a checklist in `launch/launch-kit.md`.
- Bindings or adapters beyond what one reference task covers.

## Lanes

- repo: repository cleanup and the docs checker; independent of pattern, launch, reference
- pattern: the specification and its guides; independent of reference
- launch: docs site and launch copy; independent of reference
- reference: the reference implementation; independent of pattern, launch

## Decisions

- Name: Ambassador Agent. The pattern has one concept, the ambassador; there is no separate embassy or registry concept.
- The ambassador is an agent with or without a model: scripted, assisted or autonomous, with one contract.
- The pattern is the product; the implementation is a secondary reference with the agent platform and protocol abstracted (ADK and LangGraph as reference platforms, A2A as reference protocol).
- Interaction model: tasks through an abstraction layer, with A2A as the reference protocol but not mandated. Only the core opens a task; a task never pauses and ends in one of four outcomes. This replaces the inbox concept.
- External events reach the core as notices on a core-opened subscription. A notice is a fact, never a command. Holding undelivered events is the messaging layer's job.
- Reliability principle: every action is journalled before it happens (write-ahead intent), extending to durable execution for multi-step capabilities. Each capability declares what to do with an unknown outcome.
- Admission is a duty: one task at a time per resource (enqueue or reject, never interrupt or roll back), bounded wait, refusal with a retry hint, pacing to the external quota.
- Each capability declares whether it is compensable, partly compensable or not; orchestration across boundaries belongs to the core.
- The ambassador is fully autonomous. Human approval and TCC are optional; choreography between ambassadors and two-phase commit are excluded.
- If intelligence is needed, a fast, low-latency model is preferred. This replaces the System 1 wording.
- Durability and presence are deployment choices described in the decision guide, not part of the definition. The direction axis is removed.
- No earlier pattern is adopted as is; docs/influences.md records what was taken from each and what was left out.
- The ADK adapter and the A2A binding are kept and marked experimental.
- Licenses: CC BY 4.0 for documentation, MIT for code.
- The worked example uses an invented online shop and courier.
- Dropped: FEAT-006 (publish the docs as a GitHub Pages site) and TASK-007 (finalise the launch copy), both superseded by FEAT-012.
- Commits carry no co-author lines.

## Open questions

- Should the three already-pushed commits be rewritten to remove their co-author lines? That needs a one-time force-push.
- Where does `unknown` map in A2A terms? Current choice: failed, with the outcome and operation id carried in the extension. The weakest row of the mapping, because a client that ignores the extension may read a plain failure.
- How long may an unknown outcome be held, who is alerted, and may a task type set a time limit before escalating?
- Should the gaps be published as a formal A2A extension?
- Which generator, if any, for the docs site (FEAT-006)?

## Revisions

- 2026-11-13 · do we need Embassy and ambassador, or go with ambassador only, flattened; and the ambassador may be durable or not and always on or not · embassy concept removed; durability and presence axes added to the pattern; FEAT-002.1 and TASK-007 Done when changed, no IDs added, dropped or moved
- 2026-11-13 · agree to the inbox as a core part of the pattern; refer to other patterns as considered, not adopted as is; prefer System 1 models for intelligence, not mandated · FEAT-009 added
- 2026-11-13 · agree lets update the full repo and re evaluate the full solution · FEAT-011 added with FEAT-011.1 and FEAT-011.2; decisions rewritten around tasks, journalled actions, admission and compensation
- 2026-11-13 · collect all references, create a full documentation with animated diagrams, create the article and check how to publish and advertise it · FEAT-012 added with four children; FEAT-006 and TASK-007 dropped as superseded
- 2026-11-13 · merge all to one article and lets check where to publish · TASK-013 added
- 2026-11-13 · switch the example to the shop-and-courier domain · TASK-014 recorded as done; worked example, article, reference example and tests changed
- 2026-11-13 · review findings 3 and 4: durable journaling does not guarantee exactly-once effects, and `deferred` conflates execution outcome and fallback · `deferred` replaced by `unknown`; fallback separated from the outcome and withheld while unknown; delivery classes, operation id, ambiguous-failure rule and manual resolution added; TASK-015 recorded as done
- 2026-11-13 · second evaluation: reconciliation preconditions, HA admission, invariants versus policies, governance, fault-injection tests; no complete end-to-end implementation · empty lookups believed only when absence is final; open unknown holds its resource; replicas, invariants and governance documented; fault-injection suite and durable SQLite journal added to the reference; TASK-016 recorded as done; FEAT-002.2 and TASK-008 not closed
