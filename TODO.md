# Active Backlog

## 🌳 Task Tree

- [ ] **FEAT-002** · P0 · mid · Write the pattern specification v1.0
  - Done when: docs/pattern.md links every specification page and all pages pass; `python3 tools/check_docs.py docs --reachable-from docs/pattern.md`
  - Links: Ref: docs/plans/PROJECT.md#scope · Depends: TASK-001 · Lane: pattern
  - [ ] **FEAT-002.1** · low · Add a glossary of the pattern's terms
    - Done when: ambassador, boundary, capability, principal, durability and presence are defined; `python3 tools/check_docs.py docs/glossary.md --require Ambassador --require Principal --require Durability --require Presence`
  - [ ] **FEAT-002.2** · high · Add conformance rules stating what an implementation must, should and may do
    - Done when: rules are numbered and the page rejects a non-conformant case (a core agent holding a connector); `python3 tools/check_docs.py docs/conformance.md --require Must --require Non-conformant`
  - [ ] **FEAT-002.3** · mid · Give each variant its own section and diagram
    - Done when: system, group, peer and listening-post variants each have a diagram; `python3 tools/check_docs.py docs/variants.md --require Group --require Peer --require Listening`
  - [ ] **FEAT-002.4** · mid · Document anti-patterns and failure modes
    - Done when: god ambassador, pass-through contract and shared credentials are covered; `python3 tools/check_docs.py docs/anti-patterns.md --require God --require Pass-through`
  - [ ] **FEAT-002.5** · high · Document identity and trust across the boundary
    - Done when: delegation, the confused deputy and a rejected forged principal are covered; `python3 tools/check_docs.py docs/identity-and-trust.md --require Delegation --require Confused`
- [ ] **FEAT-003** · P1 · mid · Add a composition guide for gateway, MCP, saga and supervisor, one diagram each
  - Done when: four compositions each have a diagram and link to comparison.md; `python3 tools/check_docs.py docs/composition.md --require Gateway --require MCP --require Saga`
  - Links: Ref: docs/plans/PROJECT.md#scope · Depends: FEAT-002 · Lane: pattern
- [ ] **FEAT-004** · P1 · mid · Add a second worked example for a group ambassador in front of several providers
  - Done when: the example shows provider choice, failover and one ledger; `python3 tools/check_docs.py docs/example-group.md --require Failover`
  - Links: Ref: docs/plans/PROJECT.md#scope · Depends: FEAT-002 · Lane: pattern
- [ ] **FEAT-005** · P1 · mid · Add an FAQ and objections page built from the launch kit's pushback table
  - Done when: each launch-kit objection has an answer that links to the specification; `python3 tools/check_docs.py docs/faq.md --require MCP --require Anti-corruption`
  - Links: Ref: docs/plans/PROJECT.md#scope · Depends: FEAT-002 · Lane: pattern
- [ ] **TASK-008** · P2 · mid · Add an MCP binding and a durable ledger example to the reference implementation
  - Done when: both run against the shipments example; `cd reference/python && pytest tests/test_mcp_binding.py tests/test_durable_ledger.py`
  - Links: Ref: docs/plans/PROJECT.md#out-of-scope · Lane: reference
  - State: next: decompose
