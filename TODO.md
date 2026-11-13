# Active Backlog

## 🌳 Task Tree

- [ ] **FEAT-002** · P0 · mid · Write the pattern specification v1.0
  - Done when: docs/pattern.md links every specification page and all pages pass; `python3 tools/check_docs.py docs --reachable-from docs/pattern.md`
  - Links: Ref: docs/plans/PROJECT.md#scope · Depends: TASK-001 · Lane: pattern
- [ ] **TASK-008** · P2 · mid · Add an MCP binding to the reference implementation
  - Done when: it runs against the shipments example; `cd reference/python && pytest tests/test_mcp_binding.py`
  - Links: Ref: docs/plans/PROJECT.md#out-of-scope · Lane: reference
  - State: next: decompose
