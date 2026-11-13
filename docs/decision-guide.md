# Decision guide

## Do you need an ambassador?

Use one when at least two of these are true for an external system:

- More than one core agent or workflow uses it.
- Calls have side effects (money, records, messages to people).
- You do not control its schedule of change, its availability or its quota.
- Its responses contain free text that will be read by a model.
- Someone will ask "who did this, for whom, and when?"

Skip it for a read-only, internal, single-consumer lookup. A plain tool is enough.

## Where does one boundary end?

Give two systems separate ambassadors if any of these differ:

- **Trust**: different organisations or different data classifications.
- **Credentials**: different secrets or identity providers.
- **Ownership**: different teams answer for them.
- **Failure**: one can be down while the other is up, and callers care.

Group systems behind one ambassador when callers want an outcome and should not choose the provider (payments, notifications, identity checks). The group ambassador then owns the routing rule.

Warning signs of a god ambassador: more than about ten capabilities, more than one credential set, or two teams editing it.

## Which intelligence level?

Start scripted and move up only for a named reason.

| Symptom at the boundary | Level |
|---|---|
| Documented API, clear error codes | Scripted |
| Errors are free text, or the same code means different things | Assisted |
| Recovery depends on context ("retry, wait, or send them to a branch?") | Assisted |
| The steps vary by case and cannot be enumerated | Autonomous planning |
| The interface is a document, an email thread or a screen | Autonomous planning |
| The other side is an agent that negotiates | Autonomous planning |

If you add a model, prefer a fast, low-latency one. A model on the happy path of a high-volume call is usually a mistake: it adds latency, cost and variance to something a script does perfectly.

An ambassador does not ask a person or the core what to do. If it cannot decide, it ends the task as `failed` (known not done) or `unknown` (may have been done). If you find it needs to deliberate about goals, the decision belongs to a core agent.

## Designing a capability

For each capability with a side effect, answer four questions. The answers are part of the contract.

| Question | Options | How to choose |
|---|---|---|
| If the ambassador stops mid-action, or a request times out, how is the unknown outcome settled? | Verify, resend, stop | Verify if the external system can report on an operation id. Resend only if it ignores a repeated operation id (effectively once) or a duplicate is harmless (at least once, knowingly). Otherwise stop: outcomes will sometimes be unknown and a person settles them |
| What does the external system accept as an idempotency key or client reference? | The operation id goes there | If it accepts none, no capability on it can be better than at-least-once or stop |
| Can it be compensated? | Compensable, partly, not | Be honest: a refund is "partly", a delivered message is "not" |
| What is the resource? | A key such as an order number or an account | Tasks for the same key run one at a time. Choose the narrowest key that prevents a race |

## Setting admission limits

| Limit | Start from |
|---|---|
| Pace | The external system's published quota, with headroom |
| Waiting tasks | What can be finished within the longest wait a caller will tolerate at that pace |
| Share per principal | A fraction of the waiting limit, so one caller cannot fill it |
| Second task on a busy resource | Wait, if order matters to the caller. Refuse, if a stale request is worse than none |

Put per-caller and cost limits in a gateway in front as well. The gateway stops floods; the ambassador protects the boundary's own quota.

## Do you offer a subscription?

Offer one when the external system reports things the core needs to know: a status change, a completed payment, an expiry. Translate each event to a notice in the core's language.

Rules for notices:

- A notice states a fact. It never tells the core what to do.
- The ambassador may receive the same event twice. Handle that without sending two different notices.
- With no subscriber, the event is recorded and not held. If events must not be missed, put a durable queue between the external system and the ambassador.

## Deployment choices

These decide how an ambassador is run. They do not change what it is, and callers cannot see them.

### Stateless or durable?

Every ambassador has a durable journal. This choice is about its working state between tasks.

Choose **durable** if any of these is true:

- A capability has several steps or can outlive one request (approval waits, batch windows).
- An action completes through a later event that must be matched to it.
- A failed multi-step action must be compensated after a restart.

Otherwise stay **stateless**: one journalled step per task. It is simpler to run, scale and replace.

### Always on or on demand?

Choose **always on** if the ambassador must listen, poll, keep a session open or report health between tasks.

Choose **on demand** if it only reacts, and something reliable activates it: a task from the core, or a platform trigger when an event arrives. On demand costs nothing while idle but adds start-up time to the first task.

The two choices are independent, and all four combinations are valid.

## Checklist before production

- [ ] A named owner in the description
- [ ] Durable journal and idempotency record, with a place to list unresolved outcomes and a named owner who is told
- [ ] Reconciliation on restart tested by stopping the ambassador mid-action
- [ ] Credential broker that propagates the end user's identity
- [ ] Policy reviewed for every irreversible capability
- [ ] Admission limits set, and a refusal carries a retry hint
- [ ] Sanitiser reviewed against the content this system actually returns
- [ ] A fallback channel for every capability a person depends on
- [ ] Health exposed to your monitoring, with an alert when the circuit opens
- [ ] If durable: state store sized and recovery after restart tested
- [ ] If on demand with a subscription: the wake-up trigger tested
- [ ] A tested way to withdraw the ambassador
