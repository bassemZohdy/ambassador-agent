# Worked example: a group ambassador

The second worked example. The [first](example.md) puts an ambassador in front of one external system. This one puts a [group ambassador](variants.md#group-ambassador) in front of two. The companies and systems here are invented.

## Situation

The same online shop now ships with two couriers.

| Courier | Strength | Interface |
|---|---|---|
| **Northline** | Cheap, slow. Serves most zones | Accepts a client reference and can report on it |
| **Quickpost** | Fast, dearer. Serves cities only | Cannot report on a client reference |

Callers do not care which courier carries a parcel. They want a delivery booked. If each core agent chose, each would carry both vendors' terms in its prompt, and nobody would own the choice.

## Designing the ambassador

| Decision | Choice | Why |
|---|---|---|
| Boundary | The delivery capability, across both couriers | Callers treat it as one |
| Owner | Integrations team | One named party answers for both couriers and for the choice |
| Capabilities | `book_delivery`, `cancel_delivery`, `delivery_status` | In the shop's words. No courier is named |
| Subscription | Offered: `delivery.status_changed`, fed by both couriers | One stream, one shape |
| Intelligence | Scripted | The routing rule is a table. A model adds nothing here |
| Journal | One, for the whole group | Every attempt at either courier is recorded in the same place |

### The routing rule

The group ambassador owns the rule, and the rule is data it reads, not a prompt.

| Input | Effect |
|---|---|
| The service level asked for | Express goes to Quickpost. Standard goes to Northline |
| The destination zone | Quickpost is skipped outside cities |
| The health of each courier | A courier with an open circuit is skipped |
| The principal's allowed couriers | A courier the principal may not use is skipped |
| Cost | Of the couriers left, the cheaper first |

The first courier left is attempt 1. The next is the one failover would use.

### The contract

`book_delivery` has one resource, the order number, so two bookings for one order cannot race. It is compensable, by `cancel_delivery`.

The delivery class is a property of each courier behind the capability. The ambassador keeps this table and uses the row of the courier it used:

| | Northline | Quickpost |
|---|---|---|
| Delivery class | Effectively once, by `verify` | `stop` |
| Absence is final | Yes | Not applicable |
| What settles a lost reply | Ask Northline about the operation id | Nothing can. The owner is asked |

What the contract publishes is not this table. It states what holds on every route: the booking may end `unknown`, because Quickpost cannot be asked, a duplicate is not possible, and the capability is compensable only if both couriers can cancel. The assistant sees that line and never learns that two couriers exist. When Northline is used, the booking is settled by a lookup and the contract is met with room to spare. When Quickpost is used, `unknown` is the contract keeping its word.

The operation id belongs to the task, not to the courier. It is the same for attempt 1 and attempt 2, so the journal reads as one task with two attempts.

## Failover

![The shop assistant asks the delivery ambassador to book a delivery. The ambassador tries Northline first. Only if Northline was never sent the request does it try Quickpost.](diagrams/example-group.svg)

Failover is the one place a group ambassador could do harm, so the rule is strict and is the same one a single ambassador follows for a fallback:

> The ambassador tries the next courier only when the action at the first is **known not to have been done**.

Known not done means the request was never sent: the connection was refused, the circuit was open, or the courier answered that it does not serve this zone. A timeout is not known not done. A request that may have reached the courier may have been carried out, and booking at the second courier as well would book twice.

## Seven scenarios

**1. Normal booking.** The assistant opens `book_delivery` for customer 77, standard service, to a suburb. The rule leaves Northline. The ambassador records its intent (task, operation id, courier: Northline), sends the booking with the operation id as the client reference, records the outcome and returns `succeeded` with `{reference, status: "booked"}`. The assistant is not told which courier carries the parcel. The journal is.

**2. Express.** The same request, express service, to a city. The rule leaves Quickpost first. Same flow, other courier. The assistant's task is identical in both scenarios, and so is its prompt.

**3. The first courier is down.** Standard service. Northline refuses connections, so nothing was sent. The ambassador records attempt 1 as failed, known not done. It records a new intent for Quickpost under the same operation id, books there and returns `succeeded`. The assistant sees one success. The journal shows two attempts, so the dearer courier is not a surprise to the owner.

**4. Both couriers are down.** Both circuits are open, so nothing was sent anywhere. The task ends as `failed`, and only now is a fallback attached: the packing desk books a pickup by hand. That is safe because both bookings are known not to have been made.

**5. A lost reply at Northline.** Northline books the parcel and the reply times out. The ambassador cannot tell this from a booking that never arrived, so it does not fail over. It asks Northline about the operation id, finds the booking and ends as `succeeded`. Quickpost is never tried. This is why a timeout is not a reason to fail over.

**6. A lost reply at Quickpost, with nothing to ask.** Quickpost cannot report on a reference, so after the timeout the task ends as `unknown`, with the operation id and no other channel. The ambassador does **not** try Northline, because the parcel may already be booked at Quickpost. A repeat of the task gets `unknown`. A new task for the same order is `rejected` with `resource_held`, even under a new key. The exception is listed for the integrations team.

The owner finds the booking in Quickpost's own portal and records `succeeded`, or finds none and records `failed`. A `failed` answer lifts the hold and is the first moment another channel may be offered. The next task for that order can then be routed to Northline.

**7. A status event.** Both couriers send delivery events in their own codes. The ambassador translates each into the same `delivery.status_changed` notice and sanitises the free text. The assistant holds one subscription and cannot tell the two streams apart.

## One ledger

"Who booked this delivery, with which courier, and what else was tried?" has one place to be answered. The same is true of the cost question, the incident question and the audit question. If each courier had its own ambassador and the core did the choosing, the answer would be spread across the assistant and two journals, and nobody would own the failover decision.

## What changed for the core system

- The assistant's prompt contains three capability names and no courier terms.
- Adding a third courier changes the routing rule and adds a connector inside the group ambassador. The contract and the assistant do not change.
- Changing the order of preference between couriers is a change to one table, made by the owner.
- Outcomes are the same four. A failover is not a fifth: it is two attempts that end in one outcome.

## What this example does not settle

- **Whether the core could use more.** The contract states the worst case across routes, so a caller that would rather know a route's class cannot. A stricter, per-route contract needs the core to see the routes, which gives up the point of grouping. The pattern does not offer it.
- **Cost of a failover.** The rule lets a failover reach a dearer courier. Whether a failover may cross a price limit is a policy for the owner. The example shows the journal making it visible, not the limit.
- **The reference implementation** has one external system. It does not implement routing or failover, so there is no runnable version of this example yet.

See also: the [variants](variants.md), the [conformance rules](conformance.md) for the rule on fallback while an outcome is `unknown`, and the [first example](example.md).
