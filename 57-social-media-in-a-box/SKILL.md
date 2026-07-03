---
name: social-media-in-a-box
description: Run my social week end-to-end — the productionized weekly social-media engine. Takes a weekly theme and: validates readiness (Kie.ai credits / OpenRouter balance / GHL Private Integration Token / status), writes a week of platform-native content (7-part cliffhanger series + platform reformatter), generates media (Midjourney image with Gemini 4-grid judge, Sora 25s video, Nano-Banana carousel with a Gemini QC loop and SeedDream repair, podcast cover art), posts through the CLIENT's OWN Go High Level (Convert & Flow) location and connected social accounts, and writes the plan back to the content calendar. Modes week | day | carousel | video | podcast-cover | plan | clean across facebook / instagram / linkedin (+PDF) / youtube / tiktok / pinterest / google-business. Every SACRED character/count band and JSON contract is enforced by deterministic, fail-closed Python provers (not prose); the run mints a signed certificate proving ZERO Anthropic per run. NO n8n and NO Airtable at runtime — prompts are baked in, state is a local SQLite ledger, deliverables are local + labeled. Client runtime uses CLIENT providers ONLY, never Anthropic.
version: 0.2.0
---

# Social Media in a Box (Skill 57)

The enforcement-first, self-contained weekly-social engine. It is the productionized **v2
superset** of the mechanical core of the live Skill 35 (`social-media-planner`): same "run my
social week" job, same 7-part cliffhanger product, same GHL-direct posting to the client's own
location — rebuilt from the production n8n workflow family into a hardened, deterministic-prover,
**no-n8n-runtime** skill. Skill 57 SUPERSEDES Skill 35 as the canonical weekly-social engine (see
`BOUNDARY-35-vs-57.md`).

**v0.2.0 (the 35↔57 merge target — `MERGE-INTEGRATION-PLAN.md`, QC 9.2 APPROVED).** The seven
Skill-35 extras are now FOLDED IN as first-class modes under the same spine: X/Twitter parity (C1),
live connected-accounts discovery + Owner Q&A (C2), podcast **audio** (C3), newsletter (C4), blog
(C5), engagement report (C6), thumbnails + Stories captions (C7). Four honestly DEFER to named
versions (narrated Reels v0.3.0, `syndicate` add-on channels v0.4.0, persona + memory adapters
v0.5.0) via fail-closed defer stubs (`AF-SM-DEFERRED`). Plus the **creative-interjection layer**
(`CREATIVE-INTERJECTION-DESIGN.md`): four client-driven modes (`brief`/`campaign`/`client-copy`/
`reactive`), 12 named injection points, and a certificate `creative` block — so the client owns every
word, angle, image, and mood while the provers still freeze only the frame.

> **The one-sentence law (v0.2.0):** *Provers freeze the FRAME (shape/size/count/safety/de-dup/
> provenance), never the PICTURE (topic/angle/voice/image aesthetic).* Every band is a RANGE or has a
> logged client-exact override; no prover ever calls a model to judge content. 35 gave creativity
> WITHOUT proof; unified 57 gives creativity WITH proof — zero gates weakened, zero creative surface
> lost.

> The character/count bands, JSON contracts, and module topology captured in `MASTERDOC.md`
> (machine-mirrored in `config/bands.json` + `SOCIAL-MANIFEST.json`) are **SACRED** — never
> floored, reordered, renamed, or reinterpreted. A logged **client-exact override** wins and is
> recorded on the certificate; the client gets EXACTLY what they ask for. Every rule is
> machine-enforced by a fail-closed prover, never advisory. **Enforcement, not description.**

## The ONE sanctioned command

```
bash social-media-entry.sh --run-dir DIR --mode week
```

`social-media-entry.sh` runs three fail-closed gates (DEPS → BYPASS-SCAN for hand-rolled social
posters → engine+provers HASH-PIN), mints a run-scoped **front-door nonce**, and hands off to the
deterministic orchestrator `run_social_media.py`, which walks the mode's phases IN ORDER with **no
phase skips**. The orchestrator refuses to run unless the nonce matches (exit 4) — you cannot bypass
the gates by calling the orchestrator directly.

## Five modules (PRD §3.2)

| # | Module | What it does |
|---|--------|--------------|
| 0 | **Preflight** (`modules/0-preflight`) | Fail-closed readiness gate: Kie.ai credits ≥ 200, OpenRouter balance ≥ $5, GHL PIT valid, required config present, status == Paid. FAIL → labeled report + notification; run blocked. |
| 1 | **Planner** (`modules/1-planner`) | LOCAL replacement for the `social-planner-*` n8n webhooks: create the planner sheet, sync theme-of-week, append the normalized 20-column weekly row. |
| 2 | **Content engine** (`modules/2-content-engine`) | 7-part cliffhanger series (prompt 15) + platform reformatter (prompt 16) + single-call / per-day engines (prompts 01–04). Every output passes `validate_contract.py` + `prove_bands.py`. |
| 3 | **Media core** (`modules/3-media-core`) | Image (Midjourney → Prompt-Doctor retry → Gemini 4-grid judge → SeedDream resize), video (Sora storyboard, exactly 25.0s), carousel image (Nano-Banana → Gemini QC loop → SeedDream edit → strip-text fallback), podcast **cover** art. Driven by the local SQLite `ledger.py`. |
| 4 | **Publisher** (`modules/4-publisher`) | GHL-direct per-platform sub-modes + 10-slide FB/IG & 9-slide LinkedIn-PDF carousel assembly + `clean` rollback. Normalized result `{platform, success, totalPosts, processedAccounts, errors}`. |

## Sixteen modes → phase subsets (`SOCIAL-MANIFEST.json` `modes`)

- **Engine (v0.1.0):** `week` (P0→P8 full), `day` (single-day regen), `carousel`, `video`,
  `podcast-cover`, `plan` (planner create/append/theme-sync), `clean` (delete-posts rollback).
- **Folds (v0.2.0, C3–C6):** `podcast` (Fish-Audio audio + bands + Podbean + cover), `newsletter`
  (GHL Campaigns digest), `blog` (GHL blog / LeadConnector), `engage` (read-only 7-day anomaly report).
- **Creative (v0.2.0, M1–M4):** `brief` (do it THIS way this week), `campaign` (off-template push),
  `client-copy` (post the client's VERBATIM copy — `AF-SM-CLIENT-COPY-MUTATED`), `reactive`
  (trend/newsjack fast lane, still full form+safety).
- **Deferred:** `syndicate` (C9, v0.4.0) fails closed with `AF-SM-DEFERRED`.

Publisher sub-mode `twitter` (C1) posts X through the client's own GHL channel. See `modes.md`.

## Live discovery + Owner Q&A (C2)

P0 preflight RECONCILES the config `platforms` enum against the **live** GHL connected-accounts
listing (`GET /social-media-posting/oauth/{locationId}/accounts`, the client's own PIT) —
`AF-SM-DISCOVERY-DRIFT`, fail-closed in BOTH directions: a configured platform with no live
account blocks (posting there would silently fail), and a live-connected platform missing from
the enum blocks (the BANNED silent-miss a fixed enum causes — a channel the client actually
connected must never be silently skipped). The client's deliberate skip is honored ONLY through
the logged `platformsExcluded` list: their choice is FINAL, and visible, never silent. In `--live`
mode an unconfirmable listing is itself a FAIL (fail-closed).

**Owner Q&A rule:** when the owner asks *"what does my planner do?" / "where do I post?"*, answer
ONLY from the latest preflight reconcile on record (`connected_accounts` in
`working/preflight/preflight_report.json` — the live result), never from a memorized platform
list, this file, or the config alone.

## The enforcement spine (`scripts/`, all fail-closed, all `--self-test`)

- `preflight_gate.py` — credits/balance/token/config/status (AF-SM-PREFLIGHT-*).
- `prove_bands.py` — the SACRED character/count bands, read from `config/bands.json` (single source of truth).
- `validate_contract.py` — per-platform JSON contracts, em-dash ban, single-digit grid, JSON-safe QC.
- `scrub_gate.py` — client-name + secret + pinData + **zero-Anthropic** screen (build AND runtime; never prints a matched value).
- `ledger.py` — local SQLite media/carousel job ledger (NO n8n data table; 30s poll, 120-poll timeout, ≥2-image assembly floor) **+ the §4.4 no-double-post de-dup** (content-fingerprint + slot + live-GHL reconcile → `AF-SM-DOUBLE-POST`; cleared only by a logged owner re-post token).
- `build_manifest.py` — config hash (secrets excluded) + prompt-hash pin (19 prompts) + gate certificates + **per-run ZERO-Anthropic proof** + agency isolation + the **creative block** (`AF-SM-OVERRIDE-UNLOGGED` — a silent band deviation is the only forbidden one; `AF-SM-CLIENT-COPY-MUTATED` — the client's words are never edited) → the signed `PROCESS-CERTIFICATE`. The publisher physically cannot run without it.
- `defer_stub.py` — fail-closed deferral stubs (`AF-SM-DEFERRED`): narrated-video v0.3.0 / syndicate v0.4.0 / persona-adapter + memory-adapter v0.5.0 — a clear "deferred to vX.Y.Z" message, never a silent no-op.
- `label_deliverables.py` — local labeled deliverables → `~/Downloads/Social-Media-in-a-Box/<brand-slug>/<YYYY-Www>/`.
- `register-social-cron.sh` — idempotent registrar for the ONE weekly-theme cron `social-media-weekly-theme` `0 8 * * 6` (dedup: exactly one per box; retires the legacy Skill-35 cron).

## Provider & credential rules (BINDING)

- ⛔ **CLIENT runtime uses CLIENT providers ONLY — NEVER Anthropic.** Text = the client's OpenRouter
  key with their chosen model + 2 fallbacks (`route:"fallback"`); vision QC = the client's Gemini;
  media = the client's Kie.ai. Zero `claude-*` / concrete-Anthropic-model ids in any client-path
  file; the manifest proves the model chain per run.
- **Posting = the client's OWN** Private Integration Token + locationId + connected social accounts,
  through `services.leadconnectorhq.com/social-media-posting/{locationId}/posts`. Never operator
  keys; never co-mingled across brands; agency mode hard-fails on a shared PIT/locationId.
- **No n8n / no Airtable at runtime.** Prompts are baked in `prompts/` (hash-pinned vs canon); state
  is the local SQLite ledger + JSON manifest; media staging is local labeled deliverables.

## Provenance & verify

`done` is claimed **only** from the signed certificate **plus a live GHL post-listing verify**
(independent end-to-end verify, not the poster's own return value). `verify.sh` is the read-only
self-verify gate (prover self-tests + golden reproduce + broken-variant rejection + full-tree scrub).
