# Anti-patterns and failure modes

These are designs that look like the Ambassador Agent pattern and lose its benefits, or break it. Each one says how to spot it, why it fails and what to do instead. The rules they break are numbered in [conformance](conformance.md).

The examples use the shop and courier from the [worked example](example.md).

| Anti-pattern | Looks like | Breaks |
|---|---|---|
| [God ambassador](#god-ambassador) | One ambassador for many unrelated boundaries | C1, and the point of one owner |
| [Pass-through contract](#pass-through-contract) | Capabilities that mirror the vendor's operations | C32, and the point of a contract |
| [Shared credentials](#shared-credentials) | One broad credential for every caller, or keys in core agents | C2, C39, C40 |
| [Other failure modes](#other-failure-modes) | A table of eleven more | Various |

## God ambassador

**What it looks like.** One ambassador "for integrations": the courier, the payment provider, the tax service and the email service all behind one contract, with one journal, one policy and one owner "for the whole integration layer".

**How to spot it.**

- Nobody can name one human who answers for all of it, so the owner field says "platform team".
- A change to one vendor needs a review by people who do not know that vendor.
- One flaky vendor opens the circuit breaker and every other capability starts failing with it. The breaker, the wait queue and the pacing belong to the ambassador, so they are shared by everything inside it.
- The policy file holds rules for unrelated systems, and nobody can say what a given rule is for.
- The contract has no common nouns. The capabilities share nothing but the word "integration".

**Why it fails.** The pattern gets its strength from a boundary that one owner can audit, patch, limit or switch off. A god ambassador is a second integration layer with the same shape as the one it replaced: one place where everything fails together, and nobody who can answer for any one part. The blast radius of a bad deploy, a leaked credential or a runaway loop is every boundary at once.

**Instead.** One ambassador per external system, with its own owner, journal, breaker and credentials. When several systems stand behind one logical capability, such as "payments" across several banks, use a group ambassador. That is still one capability with one owner. The test is whether one person can describe the whole contract in a sentence, and say who is called when it breaks.

## Pass-through contract

**What it looks like.** The ambassador offers `POST /consignments`, `GET /consignments/{id}` and `PATCH /consignments/{id}/labels`, with the courier's own field names. The contract is the vendor's API behind one more hop.

**How to spot it.**

- Core agent prompts contain vendor words: consignment, label state, manifest.
- A vendor version change breaks core agents, not just the ambassador.
- The core has to know which calls to make, in what order, and what a given error means.
- A capability returns the vendor's response body as it is.
- You could not replace the vendor without editing a core agent.

**Why it fails.** Everything the pattern absorbs at the boundary, such as translation, ordering, retries, recovery and the meaning of an outcome, is pushed back into the core. What remains is a proxy with a journal. It adds a hop and a duty to run without removing any of the complexity it was meant to hold.

**Instead.** Offer capabilities in the core's language: `book_shipment` for an order, not `POST /consignments`. One capability may make several calls, and the ambassador owns their order and what happens when the second fails. It returns an outcome the core can act on, never a vendor error. A good capability is one the core could describe without naming the vendor.

## Shared credentials

There are three forms of this, and they fail differently.

| Form | What it looks like | What goes wrong |
|---|---|---|
| Keys in core agents | A core agent has the courier's API key, "just for reads" | The ambassador is no longer the only path across. Nobody owns the outcome, and the key leaks into prompts and logs ([C2](conformance.md)) |
| One credential for every principal | The ambassador calls the courier as itself for every customer | A confused deputy: a caller that may only read can trigger a write, and the external system cannot tell callers apart ([C39](conformance.md)) |
| One credential for several ambassadors | The courier and the payment ambassador use the same service account | A leak or a rotation affects both, and the audit cannot say which one acted |

**How to spot it.** Search for the credential. If it appears in more than one place, or in a core agent's configuration, or the external system's own log shows one identity for every customer, this is the anti-pattern.

**Instead.** Credentials belong to the ambassador and to nobody else. Per task, they identify the principal or are limited to the task, and where the external system allows only a shared identity the contract says so ([C40](conformance.md)). Each ambassador has its own. See [identity and trust](identity-and-trust.md).

## Other failure modes

| Failure | What happens | Instead | Rule |
|---|---|---|---|
| **Timeout treated as failure** | The ambassador reports `failed` after a timeout and the core retries or redirects. The first request had landed, and the order is booked twice | Settle a timeout like a crash. Report `unknown` until it is known | C8, C13 |
| **A fallback beside `unknown`** | The result says "try the website" while the first request may still arrive | Offer a fallback only when the action is known not to have been done | C9 |
| **A new key for a retry** | A client or an orchestrator retries an `unknown` task with a fresh idempotency key | Never retry an `unknown`. The ambassador holds the resource and refuses it | C19 |
| **Journal as an afterthought** | The ambassador sends first and logs after, or logs on a best-effort basis | Record the intent before the action and the outcome after. Losing the journal means losing the truth | C12 |
| **Guessing the unknown** | A job marks every old `unknown` as `succeeded` or `failed` to keep the dashboard clean | A person settles each one from the external system's own records, with a name and a note | C18 |
| **Ambassadors in a conversation** | One ambassador reacts to another's events, or calls it to finish a job. A loop appears, and nobody owns the flow | Only the core opens a task. The core orchestrates across boundaries | C3 |
| **A workflow engine in disguise** | A capability runs for days across several boundaries, with branches and a state machine of its own | Keep a capability to one boundary. Put cross-boundary steps in the core, as a saga with compensation | C3, C5 |
| **A task that waits for a person** | The ambassador stops mid-task with "pending input" and the core polls for an answer | End the task with an outcome. A person's decision is a new task | C6 |
| **An unbounded queue** | Overload becomes memory exhaustion and hours-old work that nobody wants | Bound the wait and refuse with a hint of when to retry | C26 |
| **Text from outside in a prompt** | A vendor's error text, an email body or a notice goes to a core agent unsanitised and carries instructions | Treat everything from outside as data and sanitise it. A notice is a fact, never a command | C29, C30 |
| **A model on every path** | A language model decides policy, or sits on every call of a stable API, because it was available | Start scripted. Add a model only for a failure mode that needs it, never to decide who may do what | C23 |

## What the list has in common

Each one gives up the single, owned, recorded boundary the pattern is built on. A god ambassador gives up the single owner, a pass-through contract the meaning, shared credentials the identity, and the failure modes in the table the record or the outcome. When a design drifts from the pattern, it usually drifts in one of these directions.

If you have seen another one, open an issue so it can be added.
