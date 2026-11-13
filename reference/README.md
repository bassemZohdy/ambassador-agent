# Reference implementation

This folder exists to show that the [pattern](../docs/pattern.md) is buildable and to make its moving parts concrete. It is an illustration, not a framework, and the pattern does not depend on it.

- [`abstraction.md`](abstraction.md): how the agent platform and the wire protocol are kept out of the core
- [`python/`](python/): a dependency-free Python core, with Google ADK and LangGraph as example platforms and A2A as an example protocol

## Run it

```bash
cd reference/python
pip install -e ".[dev]"
python examples/shipments.py     # the worked example from docs/example.md
pytest                         # core tests; adapter tests run if the SDKs are installed
pip install -e ".[adk,langgraph,a2a]" && pytest
```

## Status

| Part | Status | What has been verified |
|---|---|---|
| Core (`ambassador.py`, `model.py`, `ports.py`, `defaults.py`) | Reference | Unit tests for every outcome, the journal rule and reconciliation, admission, notices and each intelligence level |
| Worked example (`examples/shipments.py`) | Reference | Runs end to end in CI |
| LangGraph adapter | Reference | Runs as a node in a compiled graph |
| Google ADK adapter | Experimental | Tool declaration and a direct tool call. Not run inside a live agent with a model |
| A2A binding | Experimental | Agent card and executor against the SDK types. Not run behind a server |

Experimental parts may change or be removed without notice. Do not copy them into production code without testing them against your SDK version.

## Limits

The in-memory journal, credential broker and sanitiser are stand-ins. The journal in particular does not survive a restart, which a real one must; the tests simulate a restart by handing the same journal to a new ambassador. Admission state and the record of seen events are also in memory, so this sketch runs as a single process. The adapters were last checked against `google-adk` 2.14, `langgraph` 1.2 and `a2a-sdk` 1.3. The autonomous level passes a reasoner to handlers but ships no planner. Multi-step capabilities are not journalled step by step: only the single-step form of the journal rule is implemented. The A2A binding returns the outcome as data and does not yet set task states or publish the proposed extension from [docs/protocol-mapping.md](../docs/protocol-mapping.md).

Implementations in other languages or on other platforms are welcome as sibling folders.
