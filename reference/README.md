# Reference implementation

This folder exists to show that the [pattern](../docs/pattern.md) is buildable and to make its moving parts concrete. It is an illustration, not a framework, and the pattern does not depend on it.

- [`abstraction.md`](abstraction.md): how the agent platform and the wire protocol are kept out of the core
- [`python/`](python/): a dependency-free Python core, with Google ADK and LangGraph as example platforms and A2A as an example protocol

## Run it

```bash
cd reference/python
pip install -e ".[dev]"
python examples/shipments.py     # the worked example from docs/example.md
pytest                         # core, fault-injection and durable-journal tests; adapter tests run if the SDKs are installed
pip install -e ".[adk,langgraph,a2a,mcp,temporal]" && pytest
```

## Status

| Part | Status | What has been verified |
|---|---|---|
| Core (`ambassador.py`, `model.py`, `ports.py`, `defaults.py`) | Reference | Unit tests for every outcome, the journal rule and reconciliation, admission, notices and each intelligence level, and for the preconditions on believing "no record", the resource hold on an open unknown and the contract's governance fields |
| Fault injection (`tests/test_faults.py`) | Reference | A crash at each step of a task, a request that lands after the caller gave up, tasks racing for one resource, and seeded random runs that check the invariants once every fault has played out |
| Principal verification (`PrincipalVerifier`, `HmacDelegations`) | Reference | A forged, tampered, expired, misdirected or stolen delegation, and a task naming a different principal, are rejected and journalled. A stand-in, off by default |
| Durable journal (`durable.py`, `SqliteJournal`) | Reference | Tested by opening the same file from a second connection as a restart: recovery, remembered results, unknown outcomes and their resolution |
| Temporal adapter (`adapters/temporal.py`, `tests/test_temporal.py`) | Experimental | The workflow id is the resource key, one activity that never retries on its own, recovery under the same id. Tests run against a real Temporal dev server in CI and are skipped where the SDK cannot download one. See [running replicas on Temporal](../docs/on-temporal.md) |
| Replicas (`leases=`, `Leasing`, `tests/test_replicas.py`) | Reference | Two copies on one shared SQLite journal: one task per resource across copies, a repeat on either copy answered once, a lease kept alive by renewing, a real process killed mid-task and its intent settled by the other copy after the lease lapses with no second action, a stalled copy refused by the journal and by the partner. One host, one file, off by default |
| Worked example (`examples/shipments.py`) | Reference | Runs end to end in CI |
| LangGraph adapter | Reference | Runs as a node in a compiled graph |
| Google ADK adapter | Experimental | Tool declaration and a direct tool call. Not run inside a live agent with a model |
| A2A binding | Experimental | Agent card and executor against the SDK types. Not run behind a server |
| MCP binding | Experimental | One tool per capability, hints from the contract. Tested through an MCP client over memory streams, against the shipments example. Not run behind a transport. `failed`, `rejected` and `unknown` come back as error results, so a client that retries every error can retry an `unknown`; the reply says it is not retryable |

Experimental parts may change or be removed without notice. Do not copy them into production code without testing them against your SDK version.

## What the replica demonstration shows

A teaching sketch, not a recommendation: a real deployment should use its platform's coordination service (see [more than one replica](../docs/pattern.md#more-than-one-replica)). This implementation runs the third option on one shared SQLite file, and its tests (`tests/test_replicas.py`) kill a real process to check these points. They are the parts that are easy to get wrong:

- **The lease covers the whole check and write.** A replica takes the lease on the resource before it reads the journal, keeps it alive while the task runs, and lets it go after the outcome is recorded. Without the lease two copies read "nothing open" before either writes.
- **The token is checked where the write happens.** The journal refuses to open an intent under a token that is no longer the newest for the resource, and refuses to settle an intent after another copy has taken the resource over. A replica that stalled past its lease finds this out on its next write, not by noticing the time.
- **The token travels to the external system, and the lookup carries it too.** A stalled replica's request may still be on its way. The external system can refuse an older token only after it has seen a newer one, and a lookup that carries the new token counts. That is what makes "no record" final for the new holder. If the external system ignores the token on a lookup, the new holder may call a booking failed and then see the old one land.
- **An open intent is claimed by taking the lease on its resource.** While the copy that opened it is alive it holds the lease, and no other copy touches the intent. When it dies it stops renewing, and the lease lapses after its time to live. That time is how long a dead copy's intent waits, and nothing shortens it safely: a copy that is only slow looks the same.
- **A repeat on another copy is still held.** An open intent holds its resource for every copy, so a retry under a new key is refused until someone settles it, and a repeat under the same key is answered as `unknown` from the record, never sent again.
- **The clock matters.** Copies on one host share a clock. Copies on several hosts need clocks that agree to well within the lease, or a store that keeps the time itself.

The reference does not show the other two options, a store other than one SQLite file, or a partner that checks the token for a real capability.

## Limits

The credential broker and sanitiser are stand-ins, and so is `HmacDelegations`: a real deployment uses its identity provider's tokens. Without a verifier the principal is taken as given. The in-memory journal does not survive a restart; `SqliteJournal` does. Several replicas can share one file when each is given the journal as its `leases` (a lease with a fencing token, checked in the same transaction as the write); without that, the locks are in-process, and `tests/test_faults.py` pins two things on purpose, that a fast shared journal makes a second replica back off by accident, and that a slow one lets both through, because the check and the write are not atomic. The lease demonstration runs on one host with a shared clock and one SQLite file; it does not show a networked store, clocks that drift, or a partner system you do not control. Admission state (waiting counts, pacing) and the record of seen events are still per process, so a second copy has its own queue and its own duplicate-event memory. The fault-injection tests are deterministic and in-process. They do not exercise a real network, a real store under contention or a real external system. The reference trusts a capability's declarations (absence is final, the settle window, the idempotency retention of the other side); it cannot check that they are true. The adapters were last checked against `google-adk` 2.14, `langgraph` 1.2 and `a2a-sdk` 1.3. The autonomous level passes a reasoner to handlers but ships no planner. Multi-step capabilities are not journalled step by step: only the single-step form of the journal rule is implemented. Open `unknown` outcomes are listed by `unresolved()` and settled by `resolve()`, but nothing alerts the owner. The A2A binding returns the outcome as data and does not yet set task states or publish the proposed extension from [docs/protocol-mapping.md](../docs/protocol-mapping.md).

Implementations in other languages or on other platforms are welcome as sibling folders.
