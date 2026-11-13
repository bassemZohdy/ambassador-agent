# Variants

The pattern has one concept: one boundary, one ambassador, one named owner. The variants below change what sits on the far side of the boundary, or which direction information flows. They do not change the duties, the four outcomes or the reliability rule. Every variant meets the same [conformance rules](conformance.md).

| Variant | Faces | Offers the core | Choose it when |
|---|---|---|---|
| System | One external system | Capabilities | The default |
| Group | Several systems that do the same job | Capabilities | Callers want an outcome and should not pick the provider |
| Peer | Another organisation's agent | Capabilities | The partner is an agent, not an API |
| Listening post | One external system | A subscription only | You need to know what happens outside, and never act there |

## System ambassador

One ambassador for one external system. This is the default, and every other variant is a refinement of it.

![The core system opens a task with the system ambassador, which carries the one capability to the one external system.](diagrams/variant-system.svg)

Start here. Move to another variant only when this one stops fitting: callers begin choosing between providers (group), the partner turns out to be an agent (peer), or the need is to watch and not to act (listening post).

## Group ambassador

One ambassador for one logical capability, in front of several systems that can each do it, for example "payments" across several banks. The ambassador chooses the system. Callers do not, and cannot tell which one was used.

![The core system opens a task with the group ambassador. The ambassador sends it to the system it chooses and does not use the other systems for this task.](diagrams/variant-group.svg)

The group ambassador owns the routing rule and everything the rule needs: which system is healthy, which is cheapest, which is allowed for this principal. It keeps one journal for the whole group, so an action is recorded once, whichever system carried it.

What stays the same: the four outcomes, the operation id, and the rule that a fallback is offered only when the action is known not to have been done. Two cautions follow from that.

- **Failing over to another system is a fallback.** It is allowed only after the first attempt is known not to have been done. If the first attempt is `unknown`, the ambassador does not try the second system. It holds the resource and reports `unknown`, exactly as a system ambassador would.
- **The operation id must survive the choice.** The same task keeps the same id whichever system it reaches, so a recovery can ask the right system about the right action.

The [decision guide](decision-guide.md) says when to group systems behind one ambassador, and the [group example](example-group.md) works through provider choice, failover and one journal.

## Peer ambassador

The external party is another organisation's agent. The ambassador speaks an agent protocol outward, and still presents plain capabilities inward, so the core system does not change.

![The core system opens a task with the peer ambassador as a plain capability. The ambassador carries it to the partner's agent over an agent protocol.](diagrams/variant-peer.svg)

Everything the pattern asks of a boundary still applies, and some of it matters more here. The partner's agent is not under your control, may answer in free text, and may change its own behaviour without notice. Its replies pass quarantine like any other reply from outside. A task the partner leaves unanswered is `unknown`, not `failed`, and is reconciled the same way.

The [protocol mapping](protocol-mapping.md) shows how the four outcomes map onto an agent protocol, and where the mapping is weak.

## Listening post

Offers a subscription and no capabilities. It watches an external system and reports what it sees. The core opens the subscription. The listening post never starts an exchange and never acts on the external system.

![The core system opens a subscription with the listening post. When the external system sends an event, the listening post sends a notice to the core system.](diagrams/variant-listening.svg)

A notice is a fact, never a command. The listening post translates and sanitises each event, records it, and sends it into the subscription. Because it has no capabilities, it has no outcomes to reconcile, no operation ids and no fallback. It still has an owner, an identity, a journal and a quarantine.

If a notice should lead to an action, the core decides that, and opens a task with a system ambassador. The listening post never does.

## Choosing between them

- Start with a system ambassador.
- If two callers pick between providers for the same job, group them behind one ambassador.
- If the other side is an agent, use a peer ambassador. The core still sees capabilities.
- If the need is only to know, use a listening post. If the need is to act, it is not one.
