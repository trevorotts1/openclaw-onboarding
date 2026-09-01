# WIRING-SPEC — exact registration facts for Agent E (Skill 53 book-writer)

Agent A / linchpin. Every value below is FINAL and byte-exact. Agent E wires the skill into the
repo (README, root `install.sh`, `cc-compat.json`, `universal-sops/`, sibling Skill 52 cross-link)
using ONLY these strings. Fleet law: no client names; no Anthropic/`claude-*` ids; no absolute paths.
**Agent E does the GitHub/repo edits — the operator only. No git/gh here.**

---

## 1. Skill identity (FINAL)

| Field | Value |
|---|---|
| Skill number | **53** |
| Skill directory | `53-book-writer/` (repo root) |
| Frontmatter `name` | `book-writer` |
| Human name | **Book Writer — Ghostwriting Engine (Avatar Alchemist, BOOK version)** |
| `skill-version.txt` / frontmatter `version` | `1.1.6` |
| Canonical entry filename | `book-writer-entry.sh` |
| Orchestrator | `run_book_writer.py` (repo-root of the skill dir, mirrors 55's `run_product_bio.py`) |
| Manifest (single source of truth) | `BOOK-WRITER-MANIFEST.json` |
| Verify gate | `verify.sh` |
| CI battery | `qc-book-writer.sh` |
| Sibling (BRAND) | Skill **52** `avatar-alchemist` |
| Sibling (future, anthology) | Skill **54** `anthology-writer` — reference only; NOT built here |
| Shared tone core | `shared-utils/tone-writing-core` (baked lockstep into `prompts/04..08`) |

---

## 2. universal-sops craft dir (create)

- **Chosen craft dir name:** `universal-sops/book-writer-craft/`
  (parallel to the existing `universal-sops/product-bio-craft/`, `email-craft/`, `funnel-craft/`,
  `avatar-craft/`). Seed with a `README.md` + one pipeline SOP file
  `SOP-BOOK-01-TWELVE-CHAPTER-BOOK.md` documenting the gate order + certificate contract (enforcement
  lives in the Python provers; the SOP documents it — enforcement, not description).
- The SKILL.md and role files reference the shared procedure as `universal-sops/book-writer-craft/`.

---

## 3. README catalog row (one row; insert after the `52-avatar-alchemist` row)

```
| 53-book-writer | **Book Writer — Ghostwriting Engine (Avatar Alchemist, BOOK version) (v1.3.0)** — a governed skill that turns ONE completed **book-intake interview** into a tone-matched **12-chapter nonfiction book** plus companion assets (avatar dossier, the blended **"The {First} {Last} Tone"**, locked title/subtitle + approved outline, print-ready manuscript, a **30-Day Challenge**, and an AI cover prompt) as a LOCAL-ONLY labeled `~/Downloads` bundle with a signed process certificate, on the CLIENT's own model providers — never Anthropic, never operator keys. A **Book/Brand version selector runs FIRST** (`version=book` targets this skill; `version=brand` hands off to Skill 52). Modes: **full** (flagship 12-chapter book) and **4x3x3** (offer book: 30 titles / 4 Transformational Outcomes / KP doc / schema-valid `433_Deck_Data.json` prepared FOR Skill 51 — no automated import exists today; Skill 51 authors decks through its own 8-Questions intake). Fail-closed **model-free** provers MEASURE the stripped text and ignore self-reported counts — exactly 12 chapters, 2000–3500 words each, ≥3000-word blended tone, exactly 30 challenge days, byte-exact locked title/subtitle, verbatim personal-story placement, sequential chapter-batch continuity (`scripts/prove_bw_*.py`); the orchestrator (`run_book_writer.py`) runs through ONE canonical entry (`book-writer-entry.sh`, deps / bypass-scan / hash-pin) and issues a `PROCESS-CERTIFICATE` only on a full pass (no certificate = not done). The tone subsystem is a lockstep copy of the shared **`shared-utils/tone-writing-core/`** (proved by `verify_tone_core_sync.py`), shared with Skills 52 (Brand) + 54 (Anthology). Cross-linked with (never merged into) Skill 52 Avatar Alchemist; anthology is the separate sibling Skill 54. No n8n / Airtable / Google / Gmail / Slack / GHL at runtime. Standalone — no prerequisite skill. |
```

---

## 4. `cc-compat.json` registration sentence (append to `notes`; NO version bump)

The skill introduces **no new Command Center endpoint and no `mission-control.db` schema change** (a
book run is an existing `tasks` / content-publishing Kanban row, fail-soft), so `minVersion` +
`pinnedTag` are UNCHANGED. Append this sentence to the `notes` string:

```
v1.x registers Skill 53 (book-writer): the Book Writer — Ghostwriting Engine (the BOOK version of the Avatar Alchemist) turns ONE completed book-intake interview into a tone-matched 12-chapter nonfiction book plus companion assets (avatar dossier, the blended "The {First} {Last} Tone", locked title/subtitle + approved outline, manuscript, a 30-Day Challenge, an AI cover prompt) as a LOCAL-ONLY labeled ~/Downloads bundle with a signed process certificate, on the CLIENT's own model providers (never Anthropic, never operator keys). A Book/Brand version selector runs FIRST (version=book targets Skill 53; version=brand hands off to Skill 52). Modes full + 4x3x3 (the 4x3x3 offer book hands 433_Deck_Data.json + a deck outline to Skill 51). It introduces NO new Command Center endpoint and NO mission-control.db schema change (a book job is an existing tasks / content Kanban row, fail-soft), so minVersion + pinnedTag are UNCHANGED. Delivery is local + human-reviewed; nothing is sent to any external service (no n8n / Airtable / Google / Gmail / Slack / GHL) at runtime. Cross-linked with (never merged into) Skill 52 Avatar Alchemist; the tone subsystem is a lockstep copy of the shared shared-utils/tone-writing-core/ referenced by Skills 52/54. Anthology is the separate sibling Skill 54.
```

---

## 5. Root `install.sh` — `install_skill_53_book_writer` (mirror the 52/55 installer functions)

Insert between `install_skill_52_avatar_alchemist` and `install_skill_55_product_bio`. Body copies
the dir, `chmod +x` the entry/verify/scripts, and prints the two `note` lines below. Also bump the
repo skill-count / SKILLS-COUNT consistency check.

```sh
install_skill_53_book_writer() {
    local SKILL_SRC="$ONBOARDING_DIR/53-book-writer"
    local SKILL_DEST="$SKILLS_DIR/53-book-writer"
    if [ ! -d "$SKILL_SRC" ]; then
        warn "Skill 53 source dir not found at $SKILL_SRC — skipping (older onboarding bundle?)"
        return 0
    fi
    mkdir -p "$SKILL_DEST"
    cp -R "$SKILL_SRC/." "$SKILL_DEST/" 2>>"$LOG_FILE" || {
        warn "Failed to copy Skill 53 from $SKILL_SRC -> $SKILL_DEST"; return 0; }
    chmod +x "$SKILL_DEST/book-writer-entry.sh" "$SKILL_DEST/run_book_writer.py" \
             "$SKILL_DEST/verify.sh" "$SKILL_DEST/verify-deps.sh" \
             "$SKILL_DEST/preflight.sh" "$SKILL_DEST/qc-book-writer.sh" \
             "$SKILL_DEST/install.sh" 2>/dev/null || true
    chmod +x "$SKILL_DEST/scripts/"*.py 2>/dev/null || true
    success "Skill 53 (Book Writer) installed -> $SKILL_DEST"
    note "Skill 53 is the methodology + enforcement layer for the BOOK version of the Avatar Alchemist: it turns ONE completed book-intake interview into a tone-matched 12-chapter nonfiction book plus companion assets (avatar dossier, the blended 'The {First} {Last} Tone', locked title/subtitle + approved outline, manuscript, a 30-Day Challenge, an AI cover prompt). A Book/Brand version selector runs FIRST (version=book targets this skill; version=brand hands off to Skill 52). Modes: full and 4x3x3 (the offer book: 30 titles / 4 Transformational Outcomes / KP doc / 433_Deck_Data.json handed to Skill 51). Every SACRED book count/floor is MEASURED by fail-closed, model-free provers (self-reported counts are ignored): exactly 12 chapters, 2000-3500 words each, a >=3000-word blended tone, exactly 30 challenge days, a byte-exact locked title/subtitle, verbatim personal-story placement, and sequential chapter-batch continuity."
    note "It runs through the ONE sanctioned front door (book-writer-entry.sh: deps -> bypass-scan -> hash-pin) then the deterministic assembler/certifier run_book_writer.py, on the CLIENT's own model providers — never the operator's, never Anthropic model ids (AF-BK-ANTHROPIC hard-fails any RUN-LEDGER model id matching /anthropic|claude/i). Delivery is a labeled ~/Downloads bundle with a signed PROCESS-CERTIFICATE on a full pass (no certificate = not done). No n8n / Airtable / Google / Gmail / Slack / GHL at runtime. The tone subsystem is a lockstep copy of shared-utils/tone-writing-core (proved by verify_tone_core_sync.py). Cross-linked with (never merged into) Skill 52 Avatar Alchemist; anthology is the separate sibling Skill 54. Standalone — no prerequisite skill."
    return 0
}

install_skill_53_book_writer
```

---

## 6. SKILL.md cross-link wording (both directions)

**In `53-book-writer/SKILL.md`** (Agent A ships this section — see SKILL.md
"Relationship to Skill 52"): version=book is the target of Skill 52's selector; the shared tone core is
`shared-utils/tone-writing-core`; anthology is the separate sibling Skill 54; a change to either skill's
shared avatar/tone prompts MUST flag the sibling for review; NEVER merged.

**Reciprocal edit Agent E makes in `52-avatar-alchemist/SKILL.md`** (add a short paragraph near the
existing "Relationship to Product Bio (Skill 55)" section):

```
## Relationship to Book Writer (Skill 53) — cross-linked, NEVER merged
Skill 52 is the BRAND version of the Avatar Alchemist; Skill 53 (book-writer) is the BOOK version.
The shared Book/Brand selector (Q0) routes `version=book` to Skill 53 and `version=brand` to this skill —
an explicit, receipted hand-off, never a silent cross-version fallback in either direction. Both skills
bake a lockstep copy of `shared-utils/tone-writing-core/` (avatar/tone IP) and prove it with
`verify_tone_core_sync.py`; a change to those shared prompts in either skill MUST flag the sibling for
review. Anthology is the separate sibling Skill 54. Do not merge the two skills.
```

**Reciprocal manifest edit Agent E makes in `52-avatar-alchemist/AA-PIPELINE-MANIFEST.json`** — change
`branches.book` from the park stanza to a routing stanza (the PRD §4.1 un-park):

```json
"book": {
  "route": "53-book-writer",
  "handoff": "53-book-writer",
  "skill_number": 53,
  "on_absent": "park",
  "park_error": "book-skill-not-available",
  "note": "version=book performs ZERO generation here; hands off to Skill 53 (book-writer) with the already-collected shared answers, or parks fail-closed if 53 is absent. Never served by the brand pipeline."
}
```
(If policy is to keep the change minimal, at least set `"handoff": "53-book-writer"` alongside the
existing `"route"`; the reciprocal `--book-skill-present` flag on `aa_intake_gate.py` then routes
instead of parks. This edit is Agent E's; Agent A does not touch Skill 52 files.)

---

## 7. AF-BK code list (FINAL — every code, its prover, and the gate it defends)

| AF-BK code | Prover file | Concern |
|---|---|---|
| `AF-BK-INTAKE-MISSING` | `prove_bw_intake.py` | required intake field missing / boilerplate |
| `AF-BK-VERSION` | `prove_bw_intake.py` | `version` unset or not in `{book,brand}`; brand must hand off to Skill 52 |
| `AF-BK-TITLE-LOCK` | `prove_bw_titlelock.py` | locked title+subtitle not byte-exact in a required artifact |
| `AF-BK-STORIES` | `prove_bw_stories.py` | a non-N/A story key phrase missing from outline AND/OR manuscript |
| `AF-BK-CHAP-COUNT` | `prove_bw_chapters.py` | chapter count ≠ 12 |
| `AF-BK-CHAP-LEN` | `prove_bw_chapters.py` | a chapter outside 2000–3500 stripped words (catches whitespace pad) |
| `AF-BK-CONTINUITY` | `prove_bw_continuity.py` | a chapter-batch receipt missing a prior chapter's sha256 |
| `AF-BK-TONE-LEN` | `prove_bw_tone.py` | blended tone < 3000 stripped words |
| `AF-BK-CHALLENGE` | `prove_bw_challenge.py` | 30-Day Challenge ≠ exactly 30 day-sections |
| `AF-BK-433-COUNTS` | `prove_bw_433.py` | 4x3x3: not exactly 4 outcomes AND 30 titles |
| `AF-BK-433-MAP` | `prove_bw_433.py` | 4x3x3: 12 chapters not mapped 4 phases × 3, or deck-data schema-invalid |
| `AF-BK-PLACEHOLDER` | `prove_bw_placeholder.py` | unresolved `{{…}}` / `$('…')` token in any artifact/deliverable |
| `AF-BK-ANTHROPIC` | `prove_bw_noanthropic.py` | a RUN-LEDGER model id matches `/anthropic\|claude/i` (or operator cred name in env) |
| `AF-BK-ANON` | `prove_bw_anon.py` | a configured client-name token in skill files / deliverable metadata |
| `AF-BK-STAGE-SKIPPED` | `prove_bw_process.py` / `run_book_writer.py` | a phase attempted out of order / broken certificate chain |
| `AF-BK-PROCESS-INTEGRITY` | `prove_bw_process.py` / `run_book_writer.py` | certificate requested without a full pass |
| `AF-BK-HASH-PIN` | `prove_bw_process.py` / `book-writer-entry.sh` | enforcement-set hash ≠ pinned head (ENGINE-PIN.sha256) |
| `AF-BK-ENTRY-BYPASS` | `book-writer-entry.sh` | hand-rolled external uploader/notifier in the run dir (must run through the entry) |

18 codes across 12 provers + the entry + the orchestrator. The `verify.sh` `no-Anthropic` /
`no-client-name` / `no-absolute-path` scans over shipped files are additional CI belts (not AF codes).

---

## 8. Department / Kanban wiring (fail-soft; Agent E notes for the operator)

- Owning department: the Content / Publishing lineage (same owner as Skills 50/51). One Kanban `sops`
  row ("Book Writer build"); one card per book run, lane advances at gate boundaries; Review/QC → Done
  is BLOCKED without the `PROCESS-CERTIFICATE`. No new endpoint, no schema change.
  **Resolved concrete slug (FIX-BK-DEPT-01):** the real, mandatory, always-seeded department this
  lineage resolves to is `marketing` — see `23-ai-workforce-blueprint/skill-department-map.json`'s
  skill-53 entry (`"departments": ["marketing"]`, matching siblings 52/54/55/56) and
  `23-ai-workforce-blueprint/department-naming-map.json`'s `.mandatory` list. `run_book_writer.py`'s
  `mc_board.begin_run(..., department=...)` call MUST use this exact slug — a standalone `"books"`
  slug was shipped instead and was never actually seeded anywhere, so every card silently
  dropped/misrouted (`mc_board.py` fails soft on an unrecognized `department_slug`). See
  `scripts/test_department_slug.py` for the regression guard.
- **Front-door nonce — honest scope:** the `OC_BOOK_WRITER_ENTRY_NONCE` handshake
  (`book-writer-entry.sh` mints a run-scoped 0600 file; `run_book_writer.py` refuses to assemble
  without it) is **accident-prevention, not a security boundary**. The nonce lives in a
  caller-controlled file inside the run dir and is handed over via a caller-settable env var, so
  anyone able to launch the entry can also read both. It stops an accidental bare
  `run_book_writer.py --run-dir …` invocation from bypassing the deps/bypass-scan/hash-pin gates;
  it does NOT stop a determined actor. Treat the provers + certificate chain as the enforcement
  layer, never the nonce.
- Add a bullet to the owning department's `how-to-use-this-department.md`: *"Write my 12-chapter book /
  4x3x3 offer book — the Book version of the Avatar Alchemist."*
- Section-8 "Tools You Use" bullet in relevant role files points to `53-book-writer/SKILL.md` +
  `book-writer-entry.sh`.

---

## 9. Mini-app engine wiring (U01–U18, U20) — the write-back isolation train

The mini-app (`53-book-writer/mini-app/`) is the SELF-SERVE intake surface for a Book Writer
run: a client opens a universal link, answers the intake (typed / uploaded / recorded), and the
answers stage at the edge; the box that OWNS the run then polls the staged answers, transcribes
any media, and writes each answer to the client's own GHL sub-account. Every row below matches
what is ACTUALLY in the repo (paths verified on `ma/integ-base` @ d87aacde).

### Universal link + phase configs (U01/U02/U03/U05)

| Row | What it wires | Where |
|---|---|---|
| Universal link | `GET /<slug>/<phase>?tk=<token>` serves the SPA + phase config. Token validated against the KV binding row (`binding:<token>`, the SOLE authority); bad/expired/replayed/misfit token → 401 (no config, no form); order enforcement only serves a phase the run state allows. | `mini-app/worker/src/index.js` |
| SPA renderer | Warm single-page intake UI (`pages/index.html` + `pages/app.js` + per-widget modules) with the phase config injected via `SPA_INJECT_TEMPLATE`. | `mini-app/pages/`, `mini-app/worker/src/lib.js` |
| Phase configs | U01 `gen_phase_config.py` derives `mini-app/configs/P0-INTAKE-{full,4x3x3}.json` + `GATE-{1,2,3,4,433}.json` from `intake/intake-schema.json` + the manifest. Each carries `questions[]` and the `submit` block (custom_field_map / tags / raw_json_note) that drives the write-back. | `mini-app/configs/`, `mini-app/scripts/gen_phase_config.py` |
| Answer staging | `POST /api/answers?tk=` re-validates the binding, normalizes at the ONE boundary, enforces the per-step consumed counter (replay → 409), stages to per-client KV (`answer:<client>:<run>:<phase>:<qid>`), returns a receipt + done page. Injected destination fields are IGNORED. | `mini-app/worker/src/answers.js` |
| Save & resume | `POST /api/save` + `GET /api/save/resume` + reminder; reload resumes at the next-unanswered question. | `mini-app/worker/src/save.js` |

### Box ingest + GHL write-back (U12/U13/U15) — where an answer lands

| Row | What it wires | Where |
|---|---|---|
| Box ingest poller | The box that OWNS the run polls the Worker job registry (`GET /api/media/:answerId`), pulls completed media, hands it to the transcription engine, and stages the output for the write-back. Fail-closed: a done job with empty text is never trusted; a worker failure is surfaced (exit 2); a REQUIRED capability absent → `AF-BW-MA-CAPABILITY` hard-fail. | `mini-app/box/ingest_poller.py` |
| Capability probe | Per-box probe (preflight.sh mirror) writes `capability-map.json` (honest booleans only). | `mini-app/box/capability_probe.py`, `mini-app/box/capability-map.json` |
| Media transcription | Transcription engine the poller hands done media jobs to. | `mini-app/bridge/media_textractor.py` |
| GHL write-back | Turns ONE staged answer `{binding, answer}` into a GHL contact write on the CLIENT's sub-account via the Skill 44 contact rails (`services.leadconnectorhq.com/contacts/`, Bearer LOCATION-PIT, `Version: 2021-07-28`, `locationId` in body), mirrored to a durable LOCAL LEDGER MIRROR (`answers/<run>/<step>.jsonl`). GHL is a mirror, never the only copy. | `mini-app/box/ghl_writeback.py` |
| Isolation locks | POSSESSION (KV binding row present, else refused), BINDING (client_id + location_id derive ONLY from the binding row; injected destination ignored), CREDENTIAL + WHITELIST (`GOHIGHLEVEL_ALLOWED_LOCATION_IDS` must contain the bound location; empty = refuse all). Location-PIT from the canonical 11-alias env set — never the operator's key, never a literal. | `mini-app/box/ghl_writeback.py` |

### Board seam (U16) + e2e (U18) + integration artifacts (U20)

| Row | What it wires | Where |
|---|---|---|
| MC board seam | The ONE seam that wires a mini-app run's lifecycle onto the Command Center: `begin_run` opens ONE card on the marketing tasks lane (`department_slug=marketing` — the RESOLVED real seeded slug); `card_advance` per-answer heartbeat; `complete_run` → `review` NEVER `done` (review → done is the independent QC scorer's exclusive move); `block_run` → `blocked` on a gate failure. FAIL-SOFT: a board outage is logged, the run continues, and a LOCAL phase→board-receipt mapping is recorded on EVERY call. NO new CC endpoint, NO schema change (uses only `POST /api/tasks/ingest` + `GET/PATCH /api/tasks/{id}`). All write-backs ride the vendored `mc_board` shared client, which injects `Authorization: Bearer $MC_API_TOKEN` on every `PATCH /api/tasks/{id}` call (never on `/api/tasks/ingest` — that path is HMAC-signed, not Bearer; `$OPENCLAW_GATEWAY_TOKEN` would 401 this API). | `mini-app/board/mc_seam.py` |
| Playwright e2e | Headless T1–T10 suite over the REAL SPA + REAL Worker modules + a stub GHL that records every write keyed by `location_id`. T10 proves browser-level isolation (alpha answers never reach beta's location). Offline only — the stub GHL is the only transport. | `mini-app/e2e/` (harness `server.mjs`, fixtures `index.mjs`, `tests/`) |
| CC-compat note | `mini-app/integration/cc-compat.json` — the truthful statement of what the mini-app adds to the Command Center (the mc_board seam, fail-soft, NO new CC endpoint) + the grep-able proof. | `mini-app/integration/cc-compat.json` |
| Live two-fake-client smoke | `mini-app/integration/live_smoke.py` — stub-first offline battery (two fake clients, injected-destination negative, unpossessed refusal, U15 regression, lint) + a `--live` path against two disposable GHL TEST locations that requires operator-supplied `MA_LIVE_*` env and otherwise reports SKIPPED honestly. Never a client feed. | `mini-app/integration/live_smoke.py` |

**Verify gate:** `verify.sh --mini-app` runs the isolation prover (`prove_mini_app_isolation.py --self-test`), the worker node tests (`self-test.mjs`), the offline live-smoke battery, and fails closed if any is red.
