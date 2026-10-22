# channel_send - one channel-neutral send path over the real channel adapter

`channel_send.py` is the **one** send path for the three delivery channels:
`app`, `terminal` and `storyboard`. Each channel is `send()` bound to its name,
so all three reach the same function object and the send rules can never drift
between them.

```python
from choice_card.intake_card import channel_send as CS
CS.CHANNEL_SEND["app"].func is CS.send          # True
CS.CHANNEL_SEND["terminal"].func is CS.send     # True
CS.CHANNEL_SEND["storyboard"].func is CS.send   # True
```

## W03-U1: the actual channel adapter, never a hardcoded Telegram

Nothing here hardcodes Telegram (findings D06/D07). Every send resolves the
run's **canonical origin record** and routes its typed artifacts through the
channel the run actually came from:

| origin channel | adapter | addressing |
| --- | --- | --- |
| `telegram` | `openclaw message send` | correct authenticated bot/account (`--account`), chat (`--target`), thread (`--thread-id`) |
| `app` | `openclaw message send` | returns to the OpenClaw-app conversation id |
| `terminal` | the host's artifact display | text inline; artifacts as host paths, every playback limit recorded WITH its evidence |
| `studio` | `approvals_bridge.publish` | the run's studio order (unchanged) |

## The one origin record

`delivery_outbox.load_origin(run_dir)` reads `control/origin.json` - written
**once** at run creation with `save_origin` (a conflicting record raises
`OriginConflict`, resolved through the authenticated session, never a guess).
The approval sender, progress reporter, Studio bridge, watchdog, Command Center
projection and final deliverer all consume this record.

`migrate_legacy_destinations(run_dir)` folds recognized legacy destination
schemas in idempotently. A bare chat id with no channel marker is recorded as
`unresolved` - **no global Telegram target is ever guessed**.

## Durable delivery outbox (`delivery_outbox.py`)

Every send is a typed artifact envelope split into pieces (text chunks at
semantic boundaries with ordered part numbers, attachments individually):

| state | meaning |
| --- | --- |
| `prepared` | staged - returning JSON or writing a local file is NEVER sent |
| `queued` | durably in `<run_dir>/outbox/` |
| `sending` | dispatched, awaiting the channel receipt |
| `sent` | the channel acknowledged it - only with a recorded receipt |
| `retryable_failure` | transient dispatch failure; resending the same bytes is safe |
| `action_required` | no destination / permanent problem |
| `uncertain` | dispatched but unproven; resolved via the channel's own idempotency/readback |

A crash resends only pieces without receipts. `Outbox.redestinate(origin)`
repairs the destination after a no-target run and `resume` then delivers - the
payload bytes never change, so no paid media is spent repairing a failed send.
Large sets use numbered contact sheets (`contact_sheets`) and paginated cards
(`paginate`) within the channel's real size limits (`CHANNEL_LIMITS`).

## Requested-only device notice

`device_notice()` is the only notice sent to the client's device and it happens
**only when requested**.

```python
CS.device_notice(target, text, requested=False)   # -> None, NOTHING is sent
CS.device_notice(target, text, requested=True)    # -> payload, one notice sent
```

- **Never unsolicited:** `requested` is False -> no notice, no sender call.
- **One nudge, then silence:** pass `run_dir` and the nudge is recorded in
  `<run_dir>/control/device-notice.json`; every later call is a no-op.
- The record claims `sent: true` **only with the channel receipt**; a dispatch
  without one is recorded honestly as `uncertain`.

## What it reuses

- **Existing command builder:** `intake_card.channel_send_argv` - the same
  `openclaw message send` argv shape the choice card and the storyboard
  approval runner build, now parameterized by the RESOLVED channel. The bare
  `openclaw_send_argv(target, ...)` entry remains only for legacy callers that
  explicitly address a Telegram chat id.
- **Existing gates:** `send(..., gate=)` runs a gate FIRST and a refusal raises
  `SendRefused` **before anything is built or sent**. `song_pick_gate(run_dir)`
  is the existing `song_choices.refusal`, reused verbatim.

## CLI

```bash
python3 scripts/core/choice_card/intake_card/channel_send.py send \
    --channel app --message "..." [--target <chat-id>] [--media FILE] \
    [--run-dir RUN] [--origin '<json>']
python3 scripts/core/choice_card/intake_card/channel_send.py notice \
    --target <chat-id> --message "..." [--run-dir RUN] [--requested]
```

Exit codes: `0` sent-or-staged (or nothing to send), `5` the gate refused. The
sink is injectable and MAY return the channel receipt, so tests send nowhere.

## Proof

- `test_channel_send_u11.py` - the transport-spy counterexample (no hardcoded
  telegram on any surface), no-sent-without-receipt, no-target stays
  action-required and repair resumes delivery, plus the standing contract.
- `test_delivery_outbox_w03.py` - envelope states, deterministic piece
  identity, semantic part numbers, contact sheets, crash resend of only
  missing pieces, readback resolution, no-paid-media repair, origin migration
  without guessing.
