# CONTENT <-> CONVERSATION LATTICE: Skill 6 / 44 / 35 / 38 / 3

**Master spec crosswalk:** GK-27 (master id U89) | **Repo:** openclaw-onboarding | **Phase:** P1
**Dependency:** GK-26 / U88 -- this document records the PROVEN loop, not the intended one.

**Sourced from:** `35-social-media-planner/SKILL.md` + `INSTALL.md` + `INSTRUCTIONS.md` + `CHANGELOG.md`, `38-conversational-ai-system/SKILL.md`, `06-ghl-install-pages/SKILL.md`, `44-convert-and-flow-operator/SKILL.md`, `03-agent-browser/scripts/lib-backstop-conformance.sh`, `54-anthology-writer/SKILL.md`. Every edge below cites the owning file and line. `docs/lattice-citations.json` is the machine-readable mirror of this table -- each of the five skills' QC gates re-checks its own citations from that file on every run (drift tripwire); see "How the tripwire works" below.

---

## Why this document exists

The edges described here were NOT green-field when this document was authored -- they already existed on `main` (most landed 2026-07-11/12, see the G+K.1 audit below). What was missing was (a) end-to-end PROOF that the loop works, delivered at the OFFLINE/FIXTURE tier by U88/GK-26 (`35-social-media-planner/scripts/prove_content_conversation_loop.py`, 22 tests; the genuine LIVE-PROOF tier -- real `caf social create-post` write, real GHL Conversations round-trip, real Skill 38 brain reply -- is still owed on the operator's own box, the same two-tier shape U22 and U84 already ship in this repo), (b) one canonical relationship document instead of five partial cross-references scattered across five SKILL.md files, and (c) a citation tripwire so this document cannot silently go stale the way the five partial cross-references it replaces could.

**Scope note (reconciles the prior spec's L.4 item 5):** a prior spec draft declared "Conversational AI Analytics... out of scope," which a QC pass flagged as silently dropping the operator's actual ask. Resolution, unchanged from that reconciliation: the Command Center **Analytics page** stays out of scope -- its "Connected -- no data sources active yet" state is a wired, honest empty state, not a stub. The operator's actual ask -- the **Skill 6/44 <-> Skill 35 <-> Skill 38 relationship** -- is fully in scope in this document. Nothing named in the original ask is dropped; the boundary is now explicit.

---

## The one-line summary

**Skill 38 owns every inbound conversation, full stop.** Skill 35 generates outbound content and campaign CTAs that create the conversations; Skill 6 and Skill 44 build the funnel and workflow infrastructure those conversations run on; Skill 3 is the shared browser-automation backstop both Skill 6 and Skill 44 fall through to when their primary rails are unavailable. Skill 35 never answers a conversation itself -- it only ever routes the highest-intent interaction to the skill that does.

---

## The five relationships this document canonicalizes

### 1. Inbound ownership -- Skill 38 owns ALL inbound, exclusively

Skill 35's campaign CTAs feed conversations into Skill 38 two ways: (1) the PRIMARY DM call-to-action drives FB/IG DMs into GHL Conversations, which land in Skill 38's existing inbound pipeline end to end; (2) the comment-reader surfaces each prospect comment reply as a synthetic handoff into Skill 38's `conversational-logs/` + playbook pipeline (public post comments are not a GHL Conversations event, so the comment-reader is what makes them reach the brain at all).

> **Ground truth:** `38-conversational-ai-system/SKILL.md:35` -- "Skill 38 OWNS every inbound conversation those CTAs generate; Skill 35 never answers a conversation itself."
> **Reciprocal cross-reference:** `35-social-media-planner/SKILL.md:131` -- "Cross-reference -- Skill 38 owns the conversations these CTAs generate."

### 2. Posting tier ladder -- Skill 35 -> Skill 44

The production playbook follows the 6-tier chain (Skill 36), highest applicable tier first: **Social posting** routes Tier 0 `caf social create-post` (if Skill 44 is installed) -> Tier 1 `social-media-posting_create-post` -> Tier 2 `create_social_post` -> direct API as the last resort.

> **Ground truth:** `35-social-media-planner/INSTALL.md:240`.

### 3. Build-path ladder -- Skill 38 -> Skill 44 -> Build-with-AI paste

Workflow BUILDS route through Skill 44 (caf-direct, "Option 1 -- PRIMARY") when `caf` + the Firebase refresh token are present. Skill 44 is required for Option 1 but is NOT a hard prerequisite for Skill 38 -- `scripts/00-verify-prerequisites.sh` STEP F preflights `caf` + the Firebase token and REPORTS the active build path, so a client is never silently left on the fallback. Without those, builds fall back to the manual Build-with-AI paste ("Option 2"). At RUNTIME, the conversational brain also prefers `caf` (Tier 0) for send/read/calendars/contacts, with raw REST as the documented last-resort fallback.

> **Ground truth:** `38-conversational-ai-system/SKILL.md:33` (route + Option 1/2 shape) and `38-conversational-ai-system/SKILL.md:55` (Prerequisites section -- "NOT a hard prereq").

### 4. Funnel seam -- Skill 6 -> Skill 44

When Skill 6 runs as part of a full-funnel build (SOP-07 P4 stage), after page build and verify pass Gate-3 it hands the live `page_ids` + opt-in form IDs to the CRM automation specialist to wire workflows, invoking Skill 44 for product creation, form wiring, and GoHighLevel workflow builds. Carrying `funnel_template_id` + `linked_automations` across the P4->P5 handoff is what makes Skill 44's complete-funnel automation expansion fire.

> **Ground truth:** `06-ghl-install-pages/SKILL.md:81-99` ("Full-Funnel Pipeline Integration (Skill 44 seam)").

### 5. Backstop rail -- Skill 44 -> Skill 3, and Skill 6 -> Skill 3

Skill 44's workflow writes additionally require the Firebase refresh token; when it is absent, Skill 44 falls through to **Tier 4 agent-browser as the backstop**. Skill 6 carries its own browser-driven page-build path on the same backstop (`ghl-browser-builder-full.md`, `TECHNIQUES-cross-origin-iframe-dragdrop.md`, `v2-autonomous-build-sop.md`, `tools/SELECTORS-LIVE-funnel.md`). Skill 3 itself documents this consumer contract and proves it with a five-leg conformance battery (open / ref-based snapshot / snapshot-ref stability / fill-by-ref / guaranteed close) run as part of Skill 3's own QC (GK-28/U90).

> **Ground truth:** `44-convert-and-flow-operator/SKILL.md:3` ("falls through to **Tier 4 agent-browser as the backstop**"); Skill 6 file set listed above (present, file-existence citation); `03-agent-browser/scripts/lib-backstop-conformance.sh:5-7` -- "Skill 44's Tier-4 fallback and Skill 6's browser_manager.sh assume agent-browser gives them ref-based click/fill, snapshot stability, and a guaranteed session close."

---

## Supporting edges (context, same G+K.1 audit)

These two edges are part of the same G+K.1 relationship map and are documented here for completeness, but their owning skills (45, 54, 59) are outside this unit's five-skill QC-wiring scope (Skill 6/44/35/38/3 only) -- Skill 35's own citation is still tripwired since the file lives in its tree.

| Edge | Ground truth | Tag |
|---|---|---|
| Graphics dept <-> Skill 45 <-> Skill 35 (image handoff) | `35-social-media-planner/INSTRUCTIONS.md:104-106` -- if the week's image asset comes from the Graphics department instead of the Image Generator step, it is gated by the Section 19a input-quality check: reject any graphics-department asset lacking a SOP-GIP-02 QC receipt >= 8.5. Skill 45 owns the SOPs + `diu_validator.py`. | VERIFIED |
| Skill 54 vs Skill 59 (two anthologies, different scopes) | `54-anthology-writer/SKILL.md` header -- Skill 54 is the LOCAL-ONLY methodology/gates skill: it touches no n8n, no Airtable, no Google Docs/Drive, no Slack, no Gmail, no Go High Level at runtime. Skill 59 (`59-anthology-engine/`) is the n8n/GHL/board-integrated engine. The GHL/n8n audit scopes to 59 (and 58); 54 is exempt **by design**, not by omission. | VERIFIED |

---

## The full G+K.1 edge table (verbatim source this document canonicalizes)

| Edge | Ground truth | Tag |
|---|---|---|
| **Skill 35 -> Skill 44** (posting rail) | `35-social-media-planner/INSTALL.md:240` | VERIFIED |
| **Skill 35 -> Skill 6** (weekly landing page) | Skill 35 `CHANGELOG.md:72` (Gap C) -- the weekly campaign step MAY invoke Skill 6's `funnel_matcher.py --match` when the client supplies no static link; a client-provided link ALWAYS wins (sovereignty); matcher exists at `06-ghl-install-pages/tools/funnel_matcher.py` + `funnel_matcher_cli.py` | VERIFIED |
| **Skill 35 -> Skill 38** (inbound conversations) | `38-conversational-ai-system/SKILL.md:35`; reciprocal `35-social-media-planner/SKILL.md:131` | VERIFIED |
| **Skill 38 -> Skill 44** (workflow builds + runtime) | `38-conversational-ai-system/SKILL.md:33` and `:55` | VERIFIED |
| **Skill 6 -> Skill 44** (full-funnel seam) | `06-ghl-install-pages/SKILL.md:81-99` | VERIFIED |
| **Skill 44 -> Skill 3** (browser backstop) | `44-convert-and-flow-operator/SKILL.md:3` | VERIFIED |
| **Skill 6 -> Skill 3** (build rail) | `06-ghl-install-pages` browser-rail file set (see above) | VERIFIED |
| **Graphics dept <-> Skill 45 <-> Skill 35** (image handoff) | `35-social-media-planner/INSTRUCTIONS.md:104-106` | VERIFIED |
| **Skill 54 vs Skill 59** (two anthologies, different scopes) | `54-anthology-writer/SKILL.md` header | VERIFIED |

---

## How the tripwire works

`docs/lattice-citations.json` holds a machine-readable copy of the citations above: for each edge, the owning skill, the cited file, and either an exact 1-indexed line + the substring that line must still contain, or a file-existence check. `docs/tools/check_lattice_citation.py --repo-root <repo> --skill <skill-dir>` reads that manifest and:

1. asserts the skill's `SKILL.md` still carries its one-line pointer to this document, and
2. re-checks every citation the skill owns against the CURRENT file content on disk.

If a cited line is edited so the quoted substring no longer appears there, if the file is deleted, or if the line shifts (e.g. an unrelated edit inserts lines above it and nobody updates the manifest), the check FAILS -- that is the drift tripwire. It never fabricates a PASS. Each of the five skills' own QC gate calls this checker (see below), so a citation going stale fails that skill's QC, not just this document.

| Skill | QC gate wired | Owned edges |
|---|---|---|
| `03-agent-browser` | `qc-agent-browser.sh` | E8 (Skill 3's own backstop acknowledgment) |
| `06-ghl-install-pages` | `qc-ghl-install-pages.sh` | E2-companion (funnel_matcher tooling exists), E5 (funnel seam), E7 (build-rail file set) |
| `35-social-media-planner` | `qc-skill35.sh` | E1 (posting rail), E2 (weekly landing page / Gap C), E3-reciprocal (inbound cross-ref), E9 (Graphics image handoff) |
| `38-conversational-ai-system` | `scripts/qc-lattice-pointer.sh` (run from `scripts/11-run-qc-checklist.sh`) | E3 (inbound ownership), E4 (build-path ladder) |
| `44-convert-and-flow-operator` | `qc-convert-and-flow.sh` | E6 (backstop rail) |

`docs/tools/test_check_lattice_citation.py` proves the checker itself is fail-closed: it builds an isolated fixture repo, proves a clean fixture passes, then deliberately breaks a cited line (content edit, line-number shift, and outright deletion) and a cited file (deletion) and asserts each break fails ONLY the skill that owns it -- the fail-first proof this unit's acceptance criteria require. It also runs the real manifest against this checkout end to end.

---

## No content duplication -- pointers only

Per the standing reference-links doctrine, no skill's SKILL.md duplicates the prose above. Each of the five skills carries exactly one pointer line to this document; the relationship content itself lives here, once.

---

## Revert

Revert the docs commit; the five pointer lines are one-liners per skill and can be removed independently without breaking anything else.
