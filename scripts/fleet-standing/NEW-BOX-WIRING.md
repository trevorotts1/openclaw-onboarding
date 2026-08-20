# New-box wiring spec — Rescue Rangers return leg + Fleet Standing Gate

**Status:** BINDING. **Scope:** fleet-wide, generic — this document names no client.
**Audience:** the operator agent adding a box to the fleet, and the fleet-roll stamper.

A box that passes `python3 ~/clawd/accounts/fleet-coverage-gate.py --reconcile --check-contabo`
is **monitored**. It is not yet **reachable** by Rescue Rangers and not yet **gated** for
payment standing. Those are three independent layers and each of them fails *silently*:

| Layer | Failure mode when unwired |
|---|---|
| Coverage (5 registries + gate) | heartbeat / probe / prove-floor / roll skip the box |
| Rescue return leg (roster + allowlist) | an answer is posted to Telegram and never delivered to the box |
| Standing gate (env + `fleet_standing` row) | every request ledgers as `unmatched` / `no_record_found`; ticket headers read "(unknown)"; a delinquent box is never refused |

Everything below is what turns a *monitored* box into a *wired* box.

---

## 0. The join key

One string ties all four layers together: the box's **canonical slug**.

- It lives on the box as the env var `FLEET_STANDING_BOX_SLUG`.
- It is the `box_slug` column of the `fleet_standing` data table.
- It is the `box` key of the relay `ROSTER[]` entry and of the receiver `RETURN_BOX_ALLOWLIST`.
- It is what the box's escalation snippet must send as `boxName`.

**These five values must be byte-identical.** A hostname (`*.local`, `*.lan`), a docker
container id, or a free-text company name in any of those positions breaks the join and the
system fails open — quietly.

---

## 1. Env vars on the box (four)

| Var | Same fleet-wide? | Purpose |
|---|---|---|
| `FLEET_STANDING_GATE_URL` | yes | the standing-check webhook |
| `FLEET_STANDING_GATE_HEADER` | yes | header name (default `X-Fleet-Standing-Secret`) |
| `FLEET_STANDING_GATE_SECRET` | yes | narrow shared header secret |
| `FLEET_STANDING_BOX_SLUG` | **NO — per box** | the join key |

Seed / refresh:

```
bash ~/clawd/fleet-heartbeat/scripts/propagate-fleet-standing-gate.sh --dry-run --only <slug>
bash ~/clawd/fleet-heartbeat/scripts/propagate-fleet-standing-gate.sh --only <slug>
```

Written to the box's `.../secrets/.env` **and** `openclaw.json` `env.vars` (Mac and container
paths both handled). The script backs up each file, is idempotent, skips unreachable boxes,
and never echoes the secret.

Escape hatches (operator only): `FLEET_STANDING_GATE_BYPASS=1`, `FLEET_STANDING_GATE_SHADOW=1`.

> ⛔ A client box NEVER receives an n8n API key. Scoped keys are Enterprise-only, so an API
> key would grant that box full access to every workflow and credential on the instance.
> Boxes get the header secret and nothing else.

---

## 2. (a) The escalation snippet — `boxName` must be the slug

Every **client** box's own workspace `AGENTS.md` carries a
`## Escalate to Rescue Rangers (when you are stuck)` section, wrapped in the marker pair

```
<!-- RESCUE_ESCALATION_BOXNAME_V1 -->   …section…   <!-- END RESCUE_ESCALATION_BOXNAME_V1 -->
```

> The **operator box has no such section and must never be given one** — it is not in the
> client escalation roster. The stamper below is written so it can never create one.

### Single source of truth

The section's text lives in exactly one file: the onboarding repo template
**`scripts/rescue-escalation-section.md.tpl`**. Two consumers render it and neither carries
its own copy of the prose:

- `scripts/apply-fleet-standards.sh` — the fleet-roll stamper (§ below)
- `23-ai-workforce-blueprint/templates/role-library/rescue-rangers/scripts/stamp-rescue-escalation-section.sh`
  — the standalone per-box stamper

Template tokens: `{{BOX_NAME}}` (= the canonical slug), `{{CLIENT}}`, `{{AGENT}}`,
`{{BOX_TYPE}}`, `{{RETURN_TO}}`. **Change the teaching text by editing the template, never by
editing a box.**

### The field that matters

```
_RR_BOX="${FLEET_STANDING_BOX_SLUG:-<the canonical slug>}"
...
  "boxName":         "$_RR_BOX",
```

`boxName` reads the live env var, falling back to the slug literal baked in at stamp time.
Historically it was pre-filled with the box's *hostname* or compose-project label — that is
the root cause of `unmatched` ledger rows and "(unknown)" ticket headers. A hostname is not
a join key.

### Seeding and self-healing

- **Now, for one box:** `bash ~/clawd/fleet-heartbeat/scripts/propagate-rescue-webhook.sh --only <slug>`
- **Every roll, automatically:** `apply-fleet-standards.sh` (invoked by `update-skills.sh`)
  re-renders the template with this box's slug and replaces the block between the markers.
  Properties, all proven on fixtures:
  - **idempotent by CONTENT** — it re-renders, compares, and writes only on a real diff, so
    a hand-edited or drifted slug is *repaired* on the next roll rather than being trusted
    because a marker happens to be present;
  - **preserves per-box identity** — `clientName` / `agentName` / `boxType` / `returnTo` are
    harvested from whatever the box already has and carried forward verbatim; only `boxName`
    is asserted. A fleet roll cannot downgrade identity a per-box propagation already wrote;
  - **upgrades in place** — an older unmarked section is replaced, not duplicated;
  - **never creates** — no section ⇒ log the wiring gap and skip;
  - **fail-open** — no slug, no template, parse or write error ⇒ log and skip *without*
    writing the marker, so a later roll retries. It can never fail a roll.

Both `propagate-rescue-webhook.sh` (guard: heading **and** `"person":` both present) and the
standalone stamper (guard: heading present) see a stamped v2 section and no-op, so there is
no double-write.

The full payload the snippet posts (nine fields; partial payloads are rejected):
`action`, `person`, `clientName`, `agentName`, `boxName`, `boxType`, `openclawVersion`,
`problem`, `alreadyTried`, `returnTo`.

---

## 3. (b) The `fleet_standing` row

n8n data table `fleet_standing` — id `aoLFsegM1aDIrcDj` on the fleet n8n host.

### Row template

| Column | Type | What to put |
|---|---|---|
| `box_slug` | string | the canonical slug — byte-identical to `FLEET_STANDING_BOX_SLUG` |
| `client_label` | string | the FULL client label as it should read in an operator alert |
| `aliases` | string | pipe-delimited FULL labels only — see the alias rule below |
| `agent_name` | string | the persona display name on that box |
| `telegram_chat_id` | string | the chat the answer must return to |
| `good_standing` | boolean | `true` on add |
| `standing_source` | string | `manual` (Stripe is advisory only, never authoritative) |
| `standing_reason` | string | why, dated — e.g. `seeded <YYYY-MM-DD> — new box` |
| `plan` | string | plan label |
| `stripe_customer_id` | string | optional; match on email or customer id, never on name |
| `updated_by` | string | who wrote the row |
| `updated_at` | date | ISO timestamp |
| `notes` | string | optional |
| `podcast_approved` | boolean | per-system entitlement |
| `anthology_approved` | boolean | per-system entitlement |
| `social_planner_approved` | boolean | per-system entitlement |
| `conversational_ai_approved` | boolean | per-system entitlement |

The schema is immutable through the public API — do not attempt to add columns.

### ⛔ ALIAS RULE — FULL LABELS ONLY

`aliases` is a single pipe-delimited (`|`) string. Both the standing gate's `rowMatches()`
and `~/clawd/fleet-standing/standing.sh` split on `|` and compare **whole tokens**.

**Permitted alias forms — all of them FULL:**
- the full client label (identical to `client_label`)
- the full legal or trading name of the business
- the full canonical slug, and full alternate slugs the box is known by
- a full email address
- a full multi-word person name

**FORBIDDEN — never add any of these:**
- any **single word** (a surname, a first name, a persona first name, a one-word brand)
- any word that a *different* client's full label could contain
- any hostname, `*.local`, `*.lan`, or docker container id
- any placeholder: `tbd`, `n/a`, `na`, `none`, `unknown`, `null`, `-`, `?`, `tba`
  (these are explicitly denylisted so a half-filled identifier fails **open** and never
  blocks a paying client)

**Why this is a hard rule, not style advice:** on 2026-08-01 a single-word alias caused a
cross-client misdelivery — a substring/token match on a generic word won the roster lookup,
and one client's rescue answer was executed as an agent turn on a *different* client's box.
Client co-mingling is a hard-rule violation. When in doubt, add nothing: an `unmatched`
verdict is safe (fail-open), a wrong match is not.

> Legacy rows created before this rule may still carry single-word aliases. Treat every one
> of them as a live misdelivery risk; strip them on the next audit rather than copying the
> pattern into a new row.

---

## 4. (c) Relay ROSTER entry + receiver RETURN_BOX_ALLOWLIST entry

The return leg needs **both**. Missing either one means the answer is posted to the ops group
and never reaches the client's agent.

### 4.1 Relay `ROSTER[]` — n8n Rescue Rangers Relay, `Relay Brain` node

```js
{ aliases: ['<full-slug>', '<full client label>', '<full trading name>'],
  person: '<Full Name>',
  clientName: '<Full Client Label>',
  box: '<canonical-slug>',
  boxType: 'Mac Mini' | 'MacBook Pro' | 'Mac' | 'VPS',
  persona: '<Agent Display Name>',
  returnEnabled: true,
  shell: 'zsh' | 'bash' }
```

The full-labels-only alias rule of §3 applies to `ROSTER[].aliases` verbatim — this array is
where the 2026-08-01 misdelivery actually happened.

> ⚠️ The `Relay Brain` Code node is under a change-control hash in the operator AGENTS.md.
> Back up the live workflow JSON to
> `~/clawd/fleet-heartbeat/scripts/rescue-rangers-relay-<workflowId>-<TAG>-<UTC>.json`
> before any edit, and re-record the hash after.

### 4.2 Receiver `RETURN_BOX_ALLOWLIST` — `~/clawd/fleet-heartbeat/scripts/rescue-receiver.mjs`

Mac-tunnel box (SSH alias from `~/.ssh/config`):

```js
"<canonical-slug>": { sshAlias: "<canonical-slug>", agent: "main", shell: "zsh" },
```

VPS / docker-exec box:

```js
"<canonical-slug>": {
  type: "vps", sshHost: "root@<ip>", sshKey: null,
  container: "<container-name>", agent: "main"
},
```

`sshKey: null` means the default key. A box absent from this map returns `null` from the
lookup and the receiver deliberately refuses to SSH — that is the correct fail-safe, not a
bug to work around.

---

## 5. (d) Telegram chat id

The same chat id must appear in **three** places, or the answer lands nowhere useful:

1. `fleet_standing.telegram_chat_id`
2. the box's `returnTo` default inside its escalation snippet
3. `~/clawd/accounts/fleet-roster.json`

Seed the box side with:

```
bash ~/clawd/fleet-heartbeat/scripts/propagate-rescue-chat-id.sh --only <slug>
```

---

## 6. Acceptance test — the add is NOT done without it

Run from the **operator** box. Never run a live escalation test from a client box.

1. POST one `action:escalate` to the rescue webhook with:
   - `boxName` = the new canonical slug
   - a **suppressed test marker** so nothing reaches the live ops group: put `[synthetic]`
     (or `[smoke test]`, or `__authtest__`) anywhere in the body, **or** prefix `clientName`
     with `ROUTING-TEST`.
2. Read the newest row of the `rescue_request_ledger` data table (`ePHwQvG8xxzlcrWC`).

**PASS, all three:**
- `box_slug` on the ledger row is the canonical slug — **not** a hostname, not empty
- `verdict` is `allowed`
- nothing was posted to the Rescue Rangers ops group

**FAIL and what it means:**

| Symptom | Cause | Fix |
|---|---|---|
| `verdict: unmatched`, `reason: no_record_found` | no `fleet_standing` row, or `box_slug` mismatch | §3 |
| `verdict: unmatched`, `reason: no_identifier_supplied` | the snippet sent no `boxName` | §2 |
| `box_slug` is a hostname / container id | snippet still sends the hostname | §2 |
| `verdict: blocked` | `good_standing=false` — that is correct behaviour, not a wiring fault | — |
| a post appeared in the ops group | the test marker was missing or misspelled | re-read §6.1 |

**MANDATORY — return-leg smoke test BEFORE allowlist (added 2026-08-20, F1).**
An allowlist entry without a PASSED return-leg smoke test is NOT "wired": the
receiver's FIX-RESCUE-09 gate (`rescue-receiver.mjs`, `returnVerify.isReturnDeliveryAllowed`)
BLOCKS every SSH return for a VPS box absent from `rescue-return-verify.json`, and the
coaching answer silently falls back to the ops group instead of the client chat. This exact
failure class was observed on a Contabo box in 2026-08: allowlisted on 08-13, zero answer
deliveries for 7 days, 12+ `RETURN gate BLOCKED` events before the gap was found.

The order is load-bearing: add the box to the receiver allowlist, THEN run the
loopback smoke test, THEN consider the wiring done:

```
ssh <sshHost> docker exec <container> sh -lc 'echo RETURN-LEG-SMOKE-OK'
```

PASS = command exits 0 with that exact marker. Record it with:

```
bash ~/clawd/fleet-heartbeat/scripts/rr-reconcile.sh --smoke-test <slug>
```

which writes the `verified:true` entry into
`~/clawd/fleet-heartbeat/state/rescue-return-verify.json`. A box that cannot pass the smoke
test stays ALLOWLISTED BUT UNVERIFIED: the gate keeps it safe (no SSH, answers fall back to
the ops group) but the wiring is INCOMPLETE and must be tracked, not forgotten. A run of
`rr-reconcile.sh --check` (nightly + after every wiring) reports
`RETURN-ALLOWLISTED-UNVERIFIED` for exactly that state, so it can never sit silent for days
again.

Then re-run `fleet-coverage-gate.py --reconcile --check-contabo` and report its `PASS` line
as the evidence. Never report a box "wired" on the strength of a successful SSH or a green
coverage gate alone.

---

## 7. Where the machinery lives

| Thing | Path |
|---|---|
| Standing-gate env seeder | `~/clawd/fleet-heartbeat/scripts/propagate-fleet-standing-gate.sh` |
| Escalation-snippet propagator | `~/clawd/fleet-heartbeat/scripts/propagate-rescue-webhook.sh` |
| Telegram chat-id propagator | `~/clawd/fleet-heartbeat/scripts/propagate-rescue-chat-id.sh` |
| Receiver + `RETURN_BOX_ALLOWLIST` | `~/clawd/fleet-heartbeat/scripts/rescue-receiver.mjs` |
| Canonical escalation template (SINGLE SOURCE OF TRUTH) | onboarding repo `scripts/rescue-escalation-section.md.tpl` |
| Per-box template stamper (standalone) | onboarding repo `23-ai-workforce-blueprint/templates/role-library/rescue-rangers/scripts/stamp-rescue-escalation-section.sh` |
| Fleet-roll AGENTS.md stamper (self-healing) | onboarding repo `scripts/apply-fleet-standards.sh` §5j, marker pair `RESCUE_ESCALATION_BOXNAME_V1` |
| Standing flip / check CLI | `~/clawd/fleet-standing/standing.sh` |
| Coverage gate | `~/clawd/accounts/fleet-coverage-gate.py` |
| Step-by-step add process | `~/clawd/accounts/ADD-A-FLEET-CLIENT.md` |
| Rescue Rangers install walkthrough | `~/clawd/fleet-heartbeat/rescue-rangers-setup.md` |

---

## 8. Notes for whoever maintains this

- The standing gate is **fail-open by design**. Only an explicit `blocked` refuses service;
  `unmatched`, `held`, and an unreachable gate all proceed. Never "harden" it into
  fail-closed — that would freeze the whole fleet on an n8n hiccup. The consequence is that
  bad identity **neutralises** the gate rather than breaking it, which is exactly why §0–§3
  are strict.
- The roll stamp is `~/.openclaw/skills/.onboarding-version`. There is no `workspace/VERSION.txt`.
- `update-skills.sh` is idempotent; re-running it after an interrupted roll is the correct
  recovery, and the escalation stamp described in §2 inherits that property.
- **Which AGENTS.md.** The file a box's agent actually loads is
  `<its configured workspace>/AGENTS.md` — the loader reads that ONE directory and never
  walks a hierarchy. On most client boxes that is `…/.openclaw/workspace/AGENTS.md` and
  `…/.openclaw/AGENTS.md` is a decoy; on a box whose `agents.defaults.workspace` points
  somewhere else, the decoy is a different filename. **Never assume — confirm from the
  runtime** (`openclaw agent --agent <id> --json` → `systemPromptReport.injectedWorkspaceFiles[].path`).
- **Two silent traps to check after any AGENTS.md edit**, both invisible to a `grep` on disk:
  `truncated: true` (oversized bootstrap, content dropped from every turn with no error) and
  `missing: true` with `injectedChars ≈ 107` (workspace boundary guard rejected a symlink;
  the file is perfectly intact on disk). Distinguish by the numbers, never by file contents.
