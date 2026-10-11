# channel_send - one channel-neutral send path (U11)

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

## What it reuses

- **Existing send:** `intake_card.openclaw_send_argv` - the same
  `openclaw message send --channel telegram ...` argv the choice card
  (`render_messages --format openclaw-json`) and the storyboard approval runner
  (`storyboard_director.approval_runner.openclaw_sender`) already build. No new
  sender was added.
- **Existing gates:** `send(..., gate=)` runs a gate FIRST and a refusal raises
  `SendRefused` **before anything is built or sent**. `song_pick_gate(run_dir)`
  is the existing `song_choices.refusal`, reused verbatim. No gate is
  re-implemented, weakened or bypassed.

```python
CS.send("app", target, text, media=[png], gate=CS.song_pick_gate, gate_input=run_dir)
# a refusal -> SendRefused -> the CLI exits 5, stdout is empty
```

## Requested-only device notice

`device_notice()` is the only notice sent to the client's device and it happens
**only when requested**.

```python
CS.device_notice(target, text, requested=False)   # -> None, NOTHING is sent
CS.device_notice(target, text, requested=True)    # -> argv, one notice sent
```

- **Never unsolicited:** `requested` is False -> no notice, no sender call.
- **One nudge, then silence:** pass `run_dir` and the nudge is recorded in
  `<run_dir>/control/device-notice.json`; every later call is a no-op, so the
  client is never spammed.

## CLI

```bash
python3 scripts/core/choice_card/intake_card/channel_send.py send \
    --channel app --target <chat-id> --message "..." [--media FILE] [--run-dir RUN]
python3 scripts/core/choice_card/intake_card/channel_send.py notice \
    --target <chat-id> --message "..." [--run-dir RUN] [--requested]
```

Exit codes: `0` sent (or nothing to send), `5` the gate refused. The sink is
injectable, so tests send nowhere.

## Proof

`python3 scripts/core/choice_card/intake_card/test_channel_send_u11.py`
(10 checks green): the shared-entrypoint identity, an existing-argv send through
each channel, the unrequested-notice silence plus its negative control, one
nudge then silence, the gate denial (nothing sent), and the real non-zero exit.
