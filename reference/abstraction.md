# Abstraction layer

This page describes the reference implementation in [`python/`](python/). The pattern must outlive any one agent platform or protocol, so the code is split into a neutral core and three kinds of plug-in.

```
                 core system
                     │
        ┌────────────┴────────────┐
        │  runtime adapter        │   ADK tools, LangGraph node, ...
        │  protocol binding       │   A2A, (MCP, gRPC, queue ...)
        └────────────┬────────────┘
                     │  ActionRequest / ActionResult / Notice
        ┌────────────┴────────────┐
        │  Ambassador (core)      │   no dependencies
        └────────────┬────────────┘
                     │  ports
   Connector · CredentialBroker · Policy · Journal · Sanitizer · Reasoner · Subscriber
                     │
               external system
```

## The neutral core

`ambassador_agent.model` defines the only types that cross the layer: `ActionRequest`, `ActionResult`, `ExternalEvent`, `Notice`, `Principal`, `Capability`, `AmbassadorSpec`. None of them mentions a platform or a protocol.

An `ActionRequest` is the pattern's task and an `ActionResult` is its final outcome.

`Ambassador.describe()` returns a plain dictionary. Every discovery document (an A2A agent card, an MCP tool list, an OpenAPI file) is a mapping of that dictionary.

## Ports (what the ambassador needs)

Defined in `ambassador_agent.ports` as `typing.Protocol` classes. Implement the methods; no inheritance is required.

| Port | Methods | Default supplied |
|---|---|---|
| `Connector` | `invoke(operation, payload, credentials)`, `healthy()` | none: you write one per external system |
| `CredentialBroker` | `credentials_for(principal, capability)` | `StaticCredentials` |
| `Policy` | `refuse_reason(request, capability)` | `ScopePolicy` |
| `Journal` | `begin(intent)`, `finish(id, outcome)`, `unfinished()`, `record(entry)`, `recall(key)`, `remember(key, result)`, `unresolved()`, `resolve(operation_id, result, by, note)` | `InMemoryJournal`, and the durable `SqliteJournal` |
| `Sanitizer` | `clean(data)` | `QuarantineSanitizer` |
| `Subscriber` | `notify(notice)` | `ListSubscriber` |
| `Reasoner` | `advise(request, error, attempts)`, `think(instruction, context)` | none: required only above L0 |

A connector signals failure with `TransientError` (worth retrying) or `PermanentError` (not). A `TransientError` says whether the action `may_have_executed`: a refused connection did not, a timeout after sending may have, and that is the default. Only the first can be retried or redirected straight away. The second is settled first, by the capability's `verify`, `resend` or `stop`.

A handler sends `ctx.operation_id` to the external system as its idempotency key or client reference. It is the same on every try.

A `Capability` also declares what makes a lookup believable and what governs it. `absence_is_final` says the external system refuses late requests, so an empty `verify` can be believed. `settle_after_seconds` is the wait before a lookup is believed. Without `absence_is_final`, an empty lookup ends as `unknown`. A capability that names a `resource` is held while an `unknown` on it is open. `data_classification`, `audit_retention_days` and `requires_approval` are governance declarations that `describe()` publishes; only the last one is enforced, as the scope `approval:<capability>`.

`ambassador_agent.durable.SqliteJournal(path)` implements the `Journal` port on SQLite from the standard library. Each call commits before it returns. Opening the same file from a new process returns the intents the old one never finished.

## Runtime adapters (how a platform calls the ambassador)

An adapter converts the platform's notion of "do something" into `Ambassador.perform()`.

- **ADK**: `ambassador_tools(ambassador)` returns one tool per capability, with the capability's JSON schema as the tool declaration. The tool call id becomes the idempotency key.
- **LangGraph**: `ambassador_node(ambassador)` returns an async node that reads a request from graph state and writes the result back.

To support another platform, write one function that builds an `ActionRequest` from that platform's call and returns `result.to_dict()`.

## Protocol bindings (how the ambassador is reached over the wire)

A binding does two mappings: `describe()` to the protocol's discovery document, and a protocol message to `perform()`.

- **A2A**: `agent_card(ambassador, url)` builds the agent card with one skill per capability. `AmbassadorExecutor` serves requests sent as a single data part.

An MCP binding would map capabilities to tools; a queue binding would map messages to requests and results to replies. Neither needs a change in the core.

## Tested versions

The ADK adapter and the A2A binding are experimental; see the status table in [README.md](README.md#status). The reference adapters are smoke-tested against `google-adk` 2.14, `langgraph` 1.2 and `a2a-sdk` 1.3. These SDKs move quickly; adapter tests are skipped when an SDK is absent, and CI runs them against the latest releases.
