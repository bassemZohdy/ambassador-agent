# Identity and trust across the boundary

An ambassador holds the keys to a boundary and serves many callers. That makes it the place where someone's authority can be lent to someone who should not have it. This page says whose authority an ambassador uses, how it knows, and what it does when it cannot be sure. The rules are numbered in [conformance](conformance.md).

## Three identities

Every task involves three, and the rules below keep them apart.

| Identity | Who | How the ambassador knows |
|---|---|---|
| The caller | The core agent, or the workload it runs in | The binding authenticates it: a verified token or a mutual-TLS identity, never a name in the task |
| The principal | Who the task is for: a customer, an employee, a service | A delegation the caller presents and the binding verifies |
| The ambassador | The ambassador itself | Its own credentials, used for its own work and never as a stand-in for a principal |

The pattern says an ambassador "never acts as itself by default". This page spells out what that means for each identity.

## Delegation

Authority flows in one direction, and each step can only narrow it.

1. A person, or a system with its own authority, delegates to a core agent: *this agent may ask for these capabilities, for me, until this time*.
2. The core agent opens a task and presents that delegation with it.
3. The binding verifies the delegation and builds the principal from it: the subject, who it is on behalf of, the scopes granted, and when they end.
4. Policy checks the capability's required scopes against the principal's scopes. Nothing the task says about itself adds to them.
5. The credential broker obtains credentials for the external system. They identify the principal, or are limited to this task.

A delegation should name who it is for, who may use it, the scopes, an expiry, and the ambassador it is meant for. A token that does not name this ambassador as its audience is not accepted, so a delegation issued for one boundary cannot be replayed at another.

### Getting credentials for the external system

The external system decides what it can recognise. In order of preference:

| Option | How | When |
|---|---|---|
| Exchange for the principal's own token | The broker trades the delegation for a token that identifies the principal at the external system, as in OAuth 2.0 Token Exchange ([RFC 8693](https://www.rfc-editor.org/rfc/rfc8693)) | The external system accepts delegated tokens. The external system's own checks then apply to the principal, as a last line of defence |
| A narrow credential per task | A short-lived credential limited to one capability and one resource | The external system supports scoped keys but not delegation |
| A service identity that carries a reference | One credential for the ambassador, with the principal's identifier passed in a field | The external system has nothing better. Policy and the journal now carry the full weight, and the owner should record that choice |

The last option is a weakness, and the contract should say it is in use. The external system cannot tell callers apart, so only the ambassador's own checks stand between a caller and every other principal's data.

## The confused deputy

A deputy is a program that holds more authority than the party asking it for something. It is confused when it uses its authority for that party without asking whether the party has the right. The ambassador is that kind of program: its credentials are broader than any one caller's.

**Example.** The shop's assistant agent has the `shipments:read` scope. It opens a `cancel_shipment` task for an order. The ambassador's service credential could cancel any shipment, so the Courier would accept the request. If the ambassador only asked "may *I* do this?", the answer is yes, and a read-only caller has cancelled an order.

What prevents it:

1. **Authority comes from the principal, not from the ambassador.** Policy checks the principal's scopes for every task. The ambassador's own breadth never counts.
2. **Credentials follow the principal.** Where the external system allows it, the task is carried out under the principal's identity, so the external system refuses what the principal may not do.
3. **Ownership is checked, not only scope.** A principal that may cancel shipments may cancel its own. A capability that takes a resource declares it, and policy can compare it with what the principal owns.
4. **No credential crosses principals.** A token obtained for one principal is never reused for another task.

## A forged principal

A caller can claim to act for someone it has no delegation from. A task that says only `on_behalf_of: customer-77` proves nothing: any caller can write that.

The ambassador therefore never takes the principal from the task alone. The binding builds it from something the caller cannot make up, such as a signed delegation, or a claim the caller's own verified token carries. If that fails, the task ends as `rejected` before anything crosses the boundary, and the refusal is journalled with the caller's identity and the principal it claimed.

| Case | Result |
|---|---|
| The task names a principal and carries no delegation | `rejected`. The principal is unverified |
| The delegation is expired, or was issued to another audience | `rejected` |
| The delegation names a different caller than the one authenticated | `rejected`. A stolen delegation does not work from another workload |
| The task asks for a scope the delegation does not grant | `rejected` by policy, with the missing scopes |
| The delegation is valid and the scopes suffice | The task goes on to admission |

A rejection says that the principal was not accepted. It does not say why in detail, because the detail helps the forger.

## A compromised core agent

A core agent that reads text from outside can be steered by it. To the ambassador that looks like a legitimate caller asking for something it is entitled to, so identity checks do not catch it. What limits the harm:

- The principal's scopes bound what any one task can do, so a delegation should grant only what the agent's job needs.
- An irreversible capability can require [approval](pattern.md#what-the-contract-declares): a scope granted outside the ambassador, to a person or process that is not the agent.
- Admission limits how fast a runaway caller can act, and the journal records what it did, for whom.

An ambassador cannot tell a steered agent from a free one. It can only keep the damage within what the principal allowed.

## Trust in the other direction

The same care applies to what comes back. Replies and notices from the external system are data, never instructions, and are sanitised before any core agent sees them (see Quarantine in [the pattern](pattern.md)). A notice that arrives from outside, for instance a webhook, is accepted only after its source is verified, using the signature or the shared secret the external system provides. An unverified event is journalled as such and is not turned into a notice.

## What the journal should keep

For every task: the authenticated caller, the principal, the scopes in force, the capability, the resource, and a reference to the credential used. Never the credential itself. This answers "who did this, for whom, and under whose authority", and it is what lets an owner review a refusal.

## What the reference implementation does

It carries a `Principal` with every request, asks a credential broker for credentials for that principal, and checks the principal's scopes, including the approval scope. It does **not** verify the caller or the delegation: it takes the principal as given, and a test double stands in for the broker. That is the gap a binding must close, and the reference does not meet the rule for it ([C38](conformance.md)). A principal verifier is tracked in the backlog.

## Checklist

- [ ] The binding authenticates the caller, and builds the principal from a verified delegation
- [ ] Delegations carry an expiry and name this ambassador as the audience
- [ ] Credentials for the external system identify the principal, or are limited to the task. A shared service identity is recorded as a weakness in the contract
- [ ] Policy checks the principal's scopes for every task, and ownership where a capability takes a resource
- [ ] Irreversible capabilities require approval granted outside the ambassador
- [ ] Inbound events are verified before they become notices
- [ ] The journal records caller, principal, scopes and a credential reference, never the credential
