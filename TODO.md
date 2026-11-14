# Active Backlog

## 🌳 Task Tree
- [ ] **TASK-023** · P1 · high · Show that two replicas of one ambassador keep the durability and isolation guarantees
  - Done when: two replicas share one journal, claim open intents atomically, hold one task per resource across copies, and a crashed replica's intent is settled by the other with no second action; `cd reference/python && pytest tests/test_replicas.py`
  - Links: Ref: docs/pattern.md#more-than-one-replica · Lane: reference
  - State: next: decompose
