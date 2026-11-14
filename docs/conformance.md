# Conformance

This page says what an implementation of the Ambassador Agent pattern **Must**, **Should** and **May** do. It restates the [pattern](pattern.md) as numbered rules, so a design or a piece of code can be checked against them. The pattern explains why. This page only says what.

The words follow common usage. **Must** is required: an implementation that breaks a Must rule is not an ambassador, whatever it is called. **Should** is expected, and a departure needs a stated reason. **May** is allowed and left to the owner.

The designs that break them are described in [anti-patterns](anti-patterns.md). The rules apply to one ambassador on one boundary. They do not depend on a platform, a protocol, a language or a model.

## The rules

### Boundary and ownership

| Rule | Level | Statement |
|---|---|---|
| C1 | Must | There is one ambassador for a boundary, and one named human owner for the ambassador |
| C2 | Must | No connector, credential or vendor schema is reachable from a core agent. The ambassador is the only path across |
| C3 | Must | The ambassador never calls another ambassador, and never starts an exchange with the core |
| C4 | May | The ambassador uses a model, or not. A scripted ambassador conforms equally |

### Tasks and outcomes

| Rule | Level | Statement |
|---|---|---|
| C5 | Must | Only the core opens a task. A task asks for one capability, names a principal, and carries an idempotency key when the capability has a side effect |
| C6 | Must | A task never pauses for input. It ends in a final outcome |
| C7 | Must | The final outcome is exactly one of `succeeded`, `failed`, `rejected` and `unknown`, and says only what is known about the action |
| C8 | Must | A timeout after a request was sent is `unknown`, never `failed` |
| C9 | Must | A fallback channel is attached only when the action is known not to have been done, and never beside `unknown` |
| C10 | Must | The core receives translated, sanitised results. It is never handed a vendor error to interpret |
| C11 | Should | A result carries what to do next (a retry hint, a fallback, the operation id) beside the outcome, never in place of it |

### Journal and recovery

| Rule | Level | Statement |
|---|---|---|
| C12 | Must | The intent is journalled before the action crosses the boundary, and the outcome after. A crossing with no outcome is reconciled on restart |
| C13 | Must | A timeout is settled like a crash before the ambassador retries or offers another channel. A connection that never carried the request may be retried at once |
| C14 | Must | Every task has an operation id. It is the idempotency key or one the ambassador makes, it is journalled with the intent, it is sent to the external system, and it is the same on every retry, resend and recovery |
| C15 | Must | Each capability with a side effect declares how an unknown outcome is settled: `verify`, `resend` or `stop` |
| C16 | Must | A repeat of a task with the same idempotency key is answered from the record and is not sent again |
| C17 | Must | An empty lookup is reported as `failed` only when the capability declares that absence is final and any settle window has passed. Otherwise the outcome stays `unknown` |
| C18 | Must | An open `unknown` is listed for the named owner and is never retried by the ambassador on its own. Only the owner settles it, with a name and a note, and a `failed` settlement is the first moment a fallback may be attached |
| C19 | Must | While an `unknown` is open, a new task for the same resource is refused as `rejected`, even under a new idempotency key. This applies to a capability that names a resource |
| C20 | Should | The journal is durable: it survives the restart of the ambassador |
| C21 | Should | The journal also serves as the audit record: who asked, for whom, what was sent, what came back |

### Identity and policy

| Rule | Level | Statement |
|---|---|---|
| C22 | Must | The ambassador acts for a named principal and exchanges that identity for credentials the external system accepts. It does not act as itself by default |
| C23 | Must | Policy is checked before the boundary is crossed, and a refused task ends as `rejected` |
| C24 | Should | For a capability that declares approval, the ambassador checks that the approval scope is held. It does not ask anyone |
| C38 | Must | The principal is established from a verified delegation or the caller's own verified credential, never from the task alone. A task whose principal cannot be verified ends as `rejected` before the boundary is crossed, and the refusal is journalled |
| C39 | Must | Authority is the principal's, not the ambassador's. Policy checks the principal's scopes for every task, and no credential obtained for one principal is used for another |
| C40 | Should | Credentials for the external system identify the principal or are limited to the task. When the external system allows only a shared service identity, the contract says so |
| C41 | Should | A delegation carries an expiry and names the ambassador it is meant for. Events from outside are verified before they become notices |

### Admission

| Rule | Level | Statement |
|---|---|---|
| C25 | Must | No two tasks for the same resource are in flight at once, and a waiting task never interrupts or rolls back the one running |
| C26 | Must | The wait is bounded, and when full the ambassador refuses the task with a hint of when to retry |
| C27 | Should | A fair share of the waiting room is kept per principal |
| C28 | Should | Work is released no faster than the boundary's quota allows |

### Quarantine and notices

| Rule | Level | Statement |
|---|---|---|
| C29 | Must | Everything from outside is treated as data, never as instructions, and is sanitised before any core agent sees it |
| C30 | Must | News from outside reaches the core only as a notice on a subscription the core opened. A notice is a fact, never a command |
| C31 | May | Undelivered events are kept by the ambassador. The pattern leaves that to the messaging layer |

### Contract

| Rule | Level | Statement |
|---|---|---|
| C32 | Must | The ambassador publishes its capabilities in the core's language. Each one states whether it has a side effect, its delivery class, and whether it can be compensated |
| C33 | May | A capability declares a data classification, an audit retention and whether it requires approval |
| C34 | May | A protocol binding adds the discovery document and carries the task. It never changes a rule above |
| C42 | Must | When a capability is served through more than one external system, the contract states what holds on every route (it may end `unknown` if any route cannot be asked, a duplicate is possible if any route resends, compensable only if every route compensates). The ambassador applies the delivery class of the route it used, and the journal records the route |

### More than one replica

| Rule | Level | Statement |
|---|---|---|
| C35 | Must | When more than one copy runs, rule C25 holds across copies, not only within one |
| C36 | Must | Every copy sees every open intent and every remembered result, and only one copy recovers a given open intent |
| C37 | Should | The check of the journal and the write that follows it are atomic, or are backed by a lease with a fencing token |

## Non-conformant cases

A design that breaks a Must rule is **Non-conformant**, however it is described. These cases come up often.

| Case | Breaks | Why |
|---|---|---|
| A core agent holds a connector, an API key or a vendor client for the external system, even for reads | C2 | The ambassador is no longer the only path across, so nobody owns the outcome |
| Two services each run an "ambassador" for the same partner API | C1 | One boundary has two owners, and nothing stops them racing on a resource |
| After a timeout the ambassador reports `failed` and the core retries or redirects at once | C8, C9 | The action may have happened, so the retry can double it |
| The ambassador sends first and writes the journal afterwards | C12 | A crash between the two leaves an action nobody recorded |
| Verification finds no record, so the ambassador reports `failed` with a fallback, on a system that shows its own writes late and does not refuse late requests | C17 | A request may still be in flight. The outcome is `unknown` |
| A retry of an `unknown` task under a new idempotency key is accepted for the same order | C19 | A new key is a new request for the same thing |
| A task waits for a person's answer in the middle, in a "pending input" state | C6 | The ambassador is autonomous. It ends the task with an outcome |
| The ambassador calls the core to ask a question, or calls another ambassador to finish the job | C3 | One direction of initiation keeps message loops impossible |
| Free text from the external system is passed to a core agent unsanitised | C29 | Text from outside can carry instructions |
| An unbounded queue in front of the ambassador | C26 | Overload turns into memory exhaustion and stale work |
| A group ambassador publishes the class of its best route, and a task that fell to another route ends `unknown` | C42 | The core was promised an outcome that the route in use cannot give |
| Two replicas share a journal and each checks it, then writes, with no lease | C35, C37 | Both can read "nothing open" before either writes |
| A replica that stalled past its lease writes anyway, and nothing checks its token | C35, C37 | Two copies are then working on one resource, and the old one's record or request lands after the new one's |
| The ambassador trusts an `on_behalf_of` field in the task and acts for whoever it names | C38 | Any caller can write that field. It is a forged principal |
| One service credential with broad rights is used for every task, and policy checks only what the ambassador may do | C39 | The ambassador is a confused deputy. A read-only caller can trigger a write |

## Claiming conformance

An implementation may say it conforms to this version of the pattern when it meets every Must rule. It should say which Should rules it leaves out, and why. It should say whether it has run in production, because the pattern itself has no documented use there yet.

The [reference implementation](../reference/README.md) is built to meet the Must rules about an ambassador's own behaviour (C5 to C19, C22, C23, C25, C26, C29, C30, C32 and C39) in one process, and its tests exercise them. C1 to C4 are about architecture and ownership, which code cannot show. It meets C20 only through its SQLite journal. It meets C35 to C37 only when replicas are given a shared `SqliteJournal` as their `leases`, which is off by default: the locks are in-process otherwise, and `tests/test_faults.py` shows on purpose what goes wrong with two replicas and no lease. With leases, `tests/test_replicas.py` runs two copies on one journal, kills one in another process and checks that the other settles its intent without acting twice. That is a demonstration on one host and one file, not a deployment. It meets C38 only when a principal verifier is configured, which is off by default, and its verifier is a stand-in. [Identity and trust](identity-and-trust.md) explains the identity rules.
