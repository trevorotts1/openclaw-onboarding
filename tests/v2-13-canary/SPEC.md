# V2-13 canary — lip-sync model-quality spec

Model-quality canary for the **lip-sync** leg of workflow V2-13. Owner decision
**D33** (2026-10-07). Machine-readable source of truth: `canary_spec.json`.
This file states the same content for a human reader; the spec test fails if
the two ever disagree.

## Question the canary answers

> Does the primary lip-sync model hold up on the approved ad's painful-moment
> shot in the cartoon look, and does the backup cover it when the primary does
> not?

## Provider roster (closed, ordered)

| Rank | Role | Model | Input |
|---|---|---|---|
| 1 | primary | `kling/ai-avatar-standard` | front-facing close-up keyframe image + the speaking character's own isolated line |
| 2 | backup | `infinitalk/from-audio` | front-facing close-up keyframe image + the speaking character's own isolated line |

The roster holds **exactly these two entries in this order**. A third provider,
a reversed order, or an attempt list that is not a prefix of this roster is
refused by the harness. Owner decision D33 also removed one previously-listed
provider from this canary; its token is deliberately not carried in this
directory so a roster scan stays clean.

## Shots

- **Count:** 1 or 2 shots (this window runs **2**), all cut from the **same
  keyframe**.
- **Source:** the approved H3 ad's painful-moment shot.
- **Look:** cartoon.

## Fallback rule

The backup runs only after the primary attempt fails adapter-side, returns no
saved file, or fails mouth-match QC. A successful primary attempt ends the
shot; the backup is never dispatched speculatively alongside it.

## Mode and money

- **Mode: `mock`.** Every response comes from the `fixtures` directory. No
  network client is imported by the harness, and the live entrypoint refuses
  to run.
- **Spend: 0 USD, 0 paid calls** in this window. The prices below are
  references for the later live canary, which needs its own operator budget
  approval and then routes through Skill 74 with a spend-ledger reservation.
  - primary: about 0.24 USD per close-up
  - backup: about 0.06 USD per second at 720p

## Recording

Each shot's result is recorded per model in the run output written beside this
file. The recorded result is evidence for the operator, who decides whether the
default changes; this suite never decides that on its own.

## Run

```bash
bash run_all.sh
```

Exit `0` = every check passed, `1` = at least one check failed, `2` =
tooling failure. Run log: `test-run.log` inside the run output directory.
