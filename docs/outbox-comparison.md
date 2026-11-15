# The transactional outbox and the Ambassador journal

The [journal rule](pattern.md#reliability-rule-the-journal) was taken from the transactional outbox ([influences](influences.md)). The two look alike, because both write something down before acting. They solve different problems, and the difference decides what each one can promise. All names below are invented.

## What the outbox solves

A shop service takes an order. It must save the order in its database and tell other services about it by publishing an `OrderPlaced` message. These are two systems, the database and the broker, and no transaction spans both. If the service saves and then crashes, nobody is told. If it publishes and then the save fails, others hear about an order that does not exist.

## How the outbox works

The service saves the order and writes the message to an `outbox` table in the same database transaction, so either both exist or neither does.

A separate relay process reads the unsent rows from the outbox table and publishes each one to the broker.

After the broker accepts a message, the relay marks the row as sent.

If the relay crashes between publishing and marking, it publishes the same row again on restart, so delivery is at least once.

Each consumer therefore deduplicates by message id, and the outbox does not promise more than that.

The outbox never has to decide whether a publish happened. It publishes again and relies on the consumer to ignore the repeat.

## What the Ambassador journal solves

An ambassador sends a command to a courier company's system that it does not control. The question is not how to get a message out reliably. The question is what to believe when the answer never comes back.

## How the Ambassador journal works

The ambassador writes the intent to its journal before it acts on the external system.

It then sends the command with a stable operation id.

If the courier answers, the ambassador records the outcome after the call.

A timeout after the request was sent is treated like a crash. The outcome is unknown, and the ambassador does not simply send again.

What happens next follows the delivery class the capability declares. With verify, the ambassador asks the courier whether it received the operation id. With resend, it sends the same operation id again. With stop, it reports unknown and hands it to the owner.

While an outcome is unknown, the resource stays held, so a retry under a new key is refused until someone settles it.

## Where they differ

| | Transactional outbox | Ambassador journal |
|---|---|---|
| Problem | Save to a database and publish a message without losing either | Act on a system you do not control and stay accountable for the result |
| The record | A message waiting to be sent | The intent, and later the outcome, of one action |
| After a crash or timeout | Publish the row again | Settle it by the delivery class: verify, resend or stop |
| Duplicates | Expected, and the consumer removes them | Not assumed to be harmless; the operation id lets the other side deduplicate or be asked |
| Unsure whether it happened | Never asks, because a repeat is safe | The outcome is `unknown`, and nothing is sent or offered until it is settled |
| The resource meanwhile | Not held | Held for every copy until an owner settles it |
| A stalled writer | A late publish is one more duplicate | Fenced by a token, so a late write is refused |
| Who answers for the result | The consumers | The ambassador, then its named owner |

## Why the outbox is not enough here

The outbox is correct for its problem because the other side is a broker and its consumers, and they are built to take a repeat. An ambassador faces a system that may charge twice, book twice or ship twice when it is sent the same command again. For that reason the pattern keeps the outbox's write-ahead record and adds what the outbox never needs: reconciliation, a held resource and fencing.

## Where they combine

An ambassador can use an outbox. When its journal write and its own database change must commit together, the journal row is the outbox row, and a relay can claim open intents with `SELECT … FOR UPDATE SKIP LOCKED`. That is a way to build the journal. It does not remove the unknown outcome at the external system.

## The drawings

The first drawing is the outbox, with the duplicate a crash causes. The second is the journal, with the timeout the outbox never has to answer.

![The shop saves the order and an outbox row in one transaction. The relay reads the unsent row, publishes it to the broker and marks it sent. If the relay crashes before marking, it publishes again and the consumer drops the duplicate.](diagrams/outbox-flow.svg)

![The ambassador records its intent in the journal and sends the courier a command with a stable operation id. When no answer comes, the outcome is unknown. It then verifies, resends or stops, and records the outcome, and the resource stays held while it is unknown.](diagrams/journal-flow.svg)
