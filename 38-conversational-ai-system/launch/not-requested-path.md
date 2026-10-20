# Not-requested path — records nothing

Triggered when `conversation_ai.requested` is `false`. The only valid companion value
is `conversation_ai.mode: "none"`.

## What this path emits

Nothing.

- No FAQ, booking, or checkout playbook for this launch.
- No Conversation AI agent.
- No agent actions.
- No `conversation_ai` action node.
- No reply workflow, and no `conversation_ai_reply` automation unit.
- No default FAQ "just in case", no draft agent, no placeholder.

The directory you are reading is shared lane documentation. Per launch, this path
writes no file into the launch package and creates no runtime object.

## The one record

The launch package records exactly one line for this lane:

```
Conversation AI: not requested
```

That line is the complete record. It is not accompanied by a stub playbook, a
disabled agent, a commented-out workflow, or a "future" note inside a live unit.

## Validation rules

- `requested: false` + `mode: "none"` → valid, this path applies.
- `requested: false` + any other mode → invalid plan. Stop and report. Do not build,
  and do not silently coerce the mode.
- `requested: true` + `mode: "none"` → invalid plan. Stop and report.
- `requested: false` with `channels` present → invalid or ignored; no channel loads
  anything because nothing exists.

## Re-request later

A later request is an additive change to the launch plan (`requested: true`, a real
mode, and channels). Only then do the matching playbooks get built. The earlier "not
requested" line stays as the truthful record of that draft; it is not rewritten as if
the bot had always been planned.
