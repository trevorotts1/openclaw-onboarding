# KIE official agent docs digest

Status: reference digest. Sources fetched 2026-10-09. Absorbed into this repo's
own skills; nothing from the vendor packages is installed on any box.

## Sources

The nine official agent pages under `https://docs.kie.ai/ai-agent/`:

1. `https://docs.kie.ai/ai-agent/overview.md`
2. `https://docs.kie.ai/ai-agent/install-kie-models.md`
3. `https://docs.kie.ai/ai-agent/what-can-do.md`
4. `https://docs.kie.ai/ai-agent/install-kie-chat-agents.md`
5. `https://docs.kie.ai/ai-agent/claude-code.md`
6. `https://docs.kie.ai/ai-agent/codex-cli.md`
7. `https://docs.kie.ai/ai-agent/grok-build.md`
8. `https://docs.kie.ai/ai-agent/troubleshooting.md`
9. `https://docs.kie.ai/ai-agent/changelog.md`

Fetch date for every page above: **2026-10-09**.

Vendor skills index: `https://kie.ai/.well-known/agent-skills/index.json`
(fetched 2026-10-09; lists exactly two skills, both type "archive").

## Archive fingerprints

The two vendor skill archives pulled from `https://kie.ai/.well-known/agent-skills/`
on 2026-10-09, by sha256:

| Archive | sha256 | Prefix |
|---|---|---|
| `kie-models.tar.gz` | `f6247b734033fad6ba75e0875bc105e2307c9b7e7790317a26c1b68838209f22` | `f6247b73` |
| `kie-chat-agents.tar.gz` | `f1cbf185af32ff7162dd67d9d257cd527e79846d94cae804e2bb83e08a47e8b0` | `f1cbf185` |

Both match the 2026-10-05 approval recorded in
`74-kie-live-adapter/vendor-approval.json`. The packages have not changed since
skill 74 absorbed `kie-models` on that date.

## What KIE's agent skills are

KIE publishes exactly two **agent skills**, `kie-models` and `kie-chat-agents`.
They are instruction text (a SKILL.md and a references/en.md each; no scripts),
not a running tool server. A skill is text a coding agent reads; a MCP is a
running tool server. **KIE publishes no MCP server**: `https://kie.ai/mcp`,
`https://docs.kie.ai/mcp` and `https://api.kie.ai/mcp` each returned HTTP 404
on 2026-10-09, while the control `https://docs.kie.ai/ai-agent/overview`
returned HTTP 200 from the same machine. Community MCP packages for KIE exist
on npm; KIE did not make them.

Both vendor skills install with `npx skills add https://kie.ai`. This repo
never installs them on a client box, an OpenClaw box or a 999 machine. Skill 74's
`scripts/vendor_skill_probe.sh` is the only thing that ever unpacks them, into a
throwaway HOME, on a probe box, to detect drift against the fingerprints above.

## Rules we adopt and where they live

| # | Official rule or capability (source) | Owner in this repo |
|---|---|---|
| 1 | Take model names from the live list every time, never from memory (overview; kie-models rule 1) | `kie-common-rules.md` rule 10; skill 74 `discover` |
| 2 | Read the model's schema, call the path it returns (kie-models rule 2) | `kie-common-rules.md` rule 2; skill 74 `schema` / `validate` |
| 3 | Login is always `Authorization: Bearer`; a header named `apikey` gets 401 (overview; every agent page) | `kie-common-rules.md` rule 2 |
| 4 | Key lives in the variable `KIE_API_KEY`, never in chat, screenshots or committed files; reset at kie.ai/api-key if leaked (overview; install-kie-models) | `kie-common-rules.md` rule 9; skill 07 INSTALL |
| 5 | Check `code` in the reply body; HTTP 200 can still be a failure (kie-models rule 5) | `kie-common-rules.md` rule 2; skill 74 hard rule 4 |
| 6 | Generated files kept 14 days; save them locally (overview; what-can-do) | `kie-common-rules.md` rule 8 |
| 7 | Uploads deleted after 24 hours (kie-models) | `kie-common-rules.md` rule 8 |
| 8 | Task records kept 2 months; every call shows on kie.ai/logs (overview; troubleshooting) | `kie-common-rules.md` rule 8 |
| 9 | Rate limits: createTask 20 per 10 s; recordInfo 10 per s per task; discovery 1 per s shared (kie-models "Rate limits") | `kie-common-rules.md` rule 3 |
| 10 | Not enough credits = code 402; top up at kie.ai/pricing (troubleshooting; kie-models) | `kie-common-rules.md` rule 6; skill 07 INSTRUCTIONS error table |
| 11 | Troubleshooting table: 401, key missing, failed task, not enough credits, link expired (troubleshooting) | Section below; skill 74 research row 18 (closed 2026-10-09) |
| 12 | Suno results at `response.data[].audio_url`; text tasks at `response.resultObject` (kie-models) | skill 68 SKILL.md vendor note |
| 13 | Failed jobs show on kie.ai/logs (troubleshooting) | `kie-common-rules.md` rule 14 |

## Plain-English troubleshooting

Rewritten from the official table for client-facing use:

| Symptom | Plain-English cause and fix |
|---|---|
| 401 Unauthorized | The key is wrong, expired, or was sent in the wrong header. KIE only accepts `Authorization: Bearer <key>`. Check the key at kie.ai/api-key. |
| Key missing | The variable is not set in the shell that started the agent. Set it, then restart from that same window. |
| Task failed | Open kie.ai/logs to see the task and its error. Every KIE call shows up there. |
| Not enough credits (code 402) | Top up at kie.ai/pricing, then run the task again. |
| Link expired | Results are kept 14 days but links expire sooner. Skill 74 saves results locally as soon as they arrive. |

## Never on client machines

Each line is a never-rule with one line of why:

- Never run `npx skills add https://kie.ai`. It installs a second paid door that
  skips skill 74's price check, credit preflight, spend ledger and approval card,
  and it copies into every agent folder the skills CLI detects (about 55 folders
  on a typical box).
- Never write an `ANTHROPIC_*` key (`ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`) or a
  KIE base URL (`ANTHROPIC_BASE_URL=https://api.kie.ai/anthropic`) into `settings.json`.
  The one settings.json write allowed here is `env.KIE_API_KEY`, the variable name
  KIE's own docs prescribe (docs.kie.ai/ai-agent/overview, 2026-10-09). A settings-file
  value beats the shell, so an Anthropic-lane entry would silently pull claude-nine
  off 9Router and bill coding sessions to KIE credits.
- Never offer KIE as a chat provider for a coding agent. Coding sessions draw on
  the same KIE credits as media jobs, outside skill 74's preflight, and KIE
  serves only Anthropic-protocol chat ids.
- Never point Codex CLI or Grok Build provider tables at KIE.
- Never write a translation proxy for KIE. For claude-nine, 9Router already
  translates; a second translator is one more thing to break.

If any of these is found on a machine, report it. Never remove or edit it
without an operator order.

## Reference only: how coding agents connect to KIE

Recognition reference, so an agent can spot the vendor setup on a machine and
report it. This is not a how-to for client boxes.

- Model list addresses the vendor pages name: `GET /anthropic/v1/models` on
  `api.kie.ai` for the Anthropic-protocol lane; the unified catalog is
  `GET https://api.kie.ai/api/v1/models`.
- The vendor `kie-chat-agents` skill writes `ANTHROPIC_BASE_URL` and
  `ANTHROPIC_AUTH_TOKEN` into `~/.claude/settings.json`, and states that a
  value in a settings file beats the same value in the shell.
- Those writes are exactly what the "Never on client machines" section above
  forbids. Skill 74 never touches settings files (proved by
  `74-kie-live-adapter/tests/test_no_chat_agent_mutation.py`).
