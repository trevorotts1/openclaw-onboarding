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
| `skill-version.txt` / frontmatter `version` | `1.0.0` |
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

- **Chosen craft dir name:** `universal-sops/book-craft/`
  (parallel to the existing `universal-sops/product-bio-craft/`, `email-craft/`, `funnel-craft/`,
  `avatar-craft/`). Seed with a `README.md` + one pipeline SOP file
  `SOP-BOOK-01-TWELVE-CHAPTER-BOOK.md` documenting the gate order + certificate contract (enforcement
  lives in the Python provers; the SOP documents it — enforcement, not description).
- The SKILL.md and role files reference the shared procedure as `universal-sops/book-craft/`.

---

## 3. README catalog row (one row; insert after the `52-avatar-alchemist` row)

```
| 53-book-writer | **Book Writer — Ghostwriting Engine (Avatar Alchemist, BOOK version) (v1.0.0)** — a governed skill that turns ONE completed **book-intake interview** into a tone-matched **12-chapter nonfiction book** plus companion assets (avatar dossier, the blended **"The {First} {Last} Tone"**, locked title/subtitle + approved outline, print-ready manuscript, a **30-Day Challenge**, and an AI cover prompt) as a LOCAL-ONLY labeled `~/Downloads` bundle with a signed process certificate, on the CLIENT's own model providers — never Anthropic, never operator keys. A **Book/Brand version selector runs FIRST** (`version=book` targets this skill; `version=brand` hands off to Skill 52). Modes: **full** (flagship 12-chapter book) and **4x3x3** (offer book: 30 titles / 4 Transformational Outcomes / KP doc / `433_Deck_Data.json` → Skill 51). Fail-closed **model-free** provers MEASURE the stripped text and ignore self-reported counts — exactly 12 chapters, 2000–3500 words each, ≥3000-word blended tone, exactly 30 challenge days, byte-exact locked title/subtitle, verbatim personal-story placement, sequential chapter-batch continuity (`scripts/prove_bw_*.py`); the orchestrator (`run_book_writer.py`) runs through ONE canonical entry (`book-writer-entry.sh`, deps / bypass-scan / hash-pin) and issues a `PROCESS-CERTIFICATE` only on a full pass (no certificate = not done). The tone subsystem is a lockstep copy of the shared **`shared-utils/tone-writing-core/`** (proved by `verify_tone_core_sync.py`), shared with Skills 52 (Brand) + 54 (Anthology). Cross-linked with (never merged into) Skill 52 Avatar Alchemist; anthology is the separate sibling Skill 54. No n8n / Airtable / Google / Gmail / Slack / GHL at runtime. Standalone — no prerequisite skill. |
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
- Add a bullet to the owning department's `how-to-use-this-department.md`: *"Write my 12-chapter book /
  4x3x3 offer book — the Book version of the Avatar Alchemist."*
- Section-8 "Tools You Use" bullet in relevant role files points to `53-book-writer/SKILL.md` +
  `book-writer-entry.sh`.
