# GoHighLevel Build — Per-Phase SELF-CHECK CHECKLIST (Skill 06)

**What this is.** A scannable, top-to-bottom self-check the building agent runs
**at every phase** of a funnel/website build. It is a **VIEW of the already-shipped
gates** — it does NOT invent new ones; each line cites the SOP section it is a view
of (`v2-autonomous-build-sop.md`, with a few cues from
`references/ghl-build-spec-from-transcript.md` and `tools/gates.json`).

**How to use it.** Run each phase in order. **Do not advance a phase until its bold
`Done when:` gate passes.** The canonical `ghl_verify.render_check` (Phase 8) stays
the **un-fakeable final backstop** — nothing in this checklist replaces it; a
checkbox is a self-check, the sealed verifier is the verdict.

> **Anti-drift.** If a line here and the SOP ever disagree, the SOP wins — fix the
> checklist, never fork the gate. See the "Deliberately NOT asserted" footer for the
> inferred/suspect claims this checklist refuses to enshrine.

---

## Phase 0 — Pre-build gates + credential preflight
- [ ] **P0/P1/P2 gate receipts all `true` before the first GHL autosave** — Verify: `routing/p0-gate.json` (`offer_spec_complete:true`, `founder_name_present:true`), `routing/p1-gate.json` (`funnel_spec_valid:true`, `persona_log_verified:true`, `founder_name_present:true`), `routing/p2-persona-attach.json` (`copy_status:"APPROVED"`) (SOP P0/P1/P2).
- [ ] **Env store sourced; LOCATION PIT + location id resolve** (never the agency PIT — it 401s for media) — Verify: `set -a; source ~/.openclaw/secrets/.env; set +a` then `ghl_media.resolve_location_pit()` + `resolve_location_id()` print `CREDS OK`. An *empty env var* means "not loaded", **never** "missing" — source the store and retry before any `honest_fail` (SOP §2.0.1).
- [ ] **Sub-account matches before ANY write** — Verify: `GET /oauth/2/login/current` location == configured id via `ghl_builder.subaccount_matches`; on MISMATCH refuse, mark the task `FAILED`, write the guard verdict (SOP §2.0).
- [ ] **Method classified per page** — Verify: `routing/method-decision.json` carries a justified `method` for every page — `DIRECT` is the default; `VERCEL_EMBED` / `SKILL44_WIDGET` only when the classifier positively scores `ADVANCED` / a widget type (SOP §2.05).
- [ ] **Grocery-shopping pre-build** — needed forms / calendars / tags / workflows created in advance via Skill 44 / GHL API / MCP (**never** browser control), so they can be embedded (SOP §4; spec §4).

**Done when:** P0+P1+P2 receipts read `true`, the LOCATION PIT + location id resolve, the sub-account matches, every page has a method decision, and the funnel's dependencies are pre-built.

## Phase 1 — Media storage (folders + URLs captured FIRST)
- [ ] **One clearly-named funnel/website folder (+ per-page subfolders), created via API not browser** — Verify: `ghl_media.ensure_funnel_media_folders(...)` on the `services.*` + Bearer **LOCATION**-PIT path (or the `name-prefix` fallback when the plan has no folder endpoint) (SOP §3).
- [ ] **Every image uploaded → GHL CDN URL captured + re-verified HTTP 200; the page references THAT media-storage link** (Trevor's media-storage rule — use the returned GHL link, not an external/placeholder `src`) — Verify: `images/manifest.json` rows carry `cdn_url(https)` + `cdn_http_status:200`; no `file://`, no SVG stub (SOP §3).

**Done when:** the named media folder exists and every image has a 200-verified GHL CDN URL recorded, with the page wired to the GHL link.

## Phase 2 — Funnel / Website container (ZHC naming)
- [ ] **Funnel/website + every step/page name carries the UPPERCASE `ZHC ` prefix** — Verify: `ghl_builder.ensure_zhc_prefix` (case-insensitive match → never double-prefixed) (SOP §2 "ZHC naming"; spec steps 3/5).
- [ ] **Re-install is idempotent (no duplicate pages)** — Verify: `ghl_method.resolve_install_target(existing_pages, marker, ...)` returns `action="update"` on the page's **stable** ZHC marker; more than one match HALTs for manual cleanup (SOP §2.1–2.6, `page_read`).

**Done when:** the container and all steps/pages are ZHC-prefixed and a re-run updates in place instead of duplicating.

## Phase 3 — Build the page (FULL WIDTH on + TWO saves)
- [ ] **Section set to full width** — Verify by **toggle STATE / rendered width**, NOT a toggle colour: the rendered section spans the full viewport (full-bleed). With the toggle OFF, rows stay centred at the builder's default max-width (~1170px) — constrained, not full-bleed (SOP §2 "CANONICAL RECIPE"; spec steps 13/13b; `gates.json` gate 14 — "verify by toggle state, not label/colour").
- [ ] **Page blob is renderable** — 18-entry `general.general.colors` list + nested `section → row → column → element` + an HTML **fragment** (not a full `<!DOCTYPE>` document) — Verify: `ghl_rest_canvas.assert_renderable` passes before any save (SOP §2.06).
- [ ] **TWO saves: Save #1 = CODE, Save #2 = PAGE** — Verify: `ghl_builder.emit_two_save_plan()` order is `save_code` → `save_page`. On the browser-control path, **re-open the code element and confirm it is NOT empty** (empty = Save #2 was skipped) (SOP §2 "CANONICAL RECIPE"; spec steps 17–18).

**Done when:** full width is ON (rendered full-bleed), the blob asserts renderable, and BOTH saves (code then page) are recorded — the re-opened code element is non-empty.

## Phase 4 — SEO / AI-search "Content" panel
- [ ] **Description set (≤160) and title (≤60)** — Verify: `ghl_builder.build_seo_meta` HALTs over the caps (SOP §2.07).
- [ ] **≥3 distinct researched keywords, and EACH keyword actually appears in the page body copy [H1]** — Verify: `ghl_builder.assert_keywords_in_copy(seo_meta, page_copy)` (or `assert_seo_populated(seo_meta, page_copy=<body text>)`) — any keyword present only in the meta panel and absent from the copy is a **HARD FAIL** (mirrors the copy-fidelity gate P1-4, in the keyword→copy direction) (SOP §2.07 + §9.2a).
- [ ] **Author == the FOUNDER's personal name (never the brand, never blank)** — Verify: `ghl_builder.validate_founder_name(author, brand=...)` (SOP §2.07; P0/P1 step 1.1).
- [ ] **Canonical (when set) absolute `https` on the page's OWN domain (never a Firebase/storage host) + language explicitly `en`** — Verify: the `_validate_canonical` + language gates inside `build_seo_meta` (SOP §2.07).

**Done when:** `assert_seo_populated(seo_meta, page_copy=<body text>)` returns `ok:true` — description set, ≥3 keywords each present in the copy, author=founder, canonical/language valid.

## Phase 5 — Multi-step funnels (part-N naming)
- [ ] **Each additional step auto-numbered `ZHC part 2 … ZHC part N`** — Verify: `ghl_builder.zhc_step_name(name, order)` (SOP §2 "ZHC naming"; spec step 20).
- [ ] **The whole recipe (Phases 3–4) repeats per step** — Verify: each step's ledger reaches `previewed` (SOP §2.1–2.6).

**Done when:** every step is `ZHC part N`-named and each step independently passes Phases 3–4.

## Phase 6 — Ecosystem objects (real receipts + form→CRM proof)
- [ ] **Calendars / forms / products / workflows are REAL objects** (`status:201`, live id, re-GET 200) — `status:"PLANNED"` is a hard FAIL — Verify: receipts under `ecosystem/*.json` (SOP §4).
- [ ] **Form→CRM roundtrip proven** — submit → `contacts search` finds the new id carrying the expected tags → `after_count == before_count + 1` → re-GET → delete-after-proof, logged — Verify: `ecosystem/contact-test.json` (`tags_confirmed:true`) (SOP §4).

**Done when:** every ecosystem object has a real creation receipt and the form→CRM proof passes (no `PLANNED` stubs).

## Phase 7 — Images resolve in the RENDERED page
- [ ] **The `<img src="<GHL CDN url>">` appears in the RENDERED (hydrated) DOM** — confirmed in the rendered page, not in stored bytes — Verify: the `ghl_verify.render_check` DOM artifact contains the GHL CDN `src`; absence = page FAIL (SOP §3 "Un-fakeable gate").

**Done when:** every page's images are visible in the rendered DOM by their GHL CDN URL.

## Phase 8 — Canonical verifier (the UN-FAKEABLE final backstop)
- [ ] **`ghl_verify.render_check` per page: HTTP 200 + marker in the RENDERED DOM + zero render errors** (+ approved `copy_tokens` present, when supplied) — Verify: real DOM snapshot + desktop 1440×900 + mobile 390×844 PNG + console artifacts; the ledger advances to `previewed` only on all three (SOP §2.1–2.6).
- [ ] **The verdict comes ONLY from `ghl_verify` → `scorecard/verify-summary.json` → `ghl_gate require-pass`, run `--live`** — no ledger, `.md`, or raw-200 shell self-declares PASS; `ghl_verify.assert_consistent` blocks a summary more optimistic than the raw log — Verify: `python3 tools/ghl_builder.py verify-all <RUN> <RUN>/pages.json --run-id <id> --version client-agent --brand "<fictional brand>" --live` (SOP §7 / §7.1).
- [ ] **§9 Definition of Done incl. FAB-QC ≥ 8.5** — Verify: `qc-built-funnel.sh <slug>` ≥ 8.5 on top of the `ghl_verify` floor (SOP §9).

**Done when:** the sealed `render_check` → `require-pass` path returns `overall_pass:true` and FAB-QC ≥ 8.5. **This phase is the un-fakeable backstop and cannot be skipped or simulated.**

---

### Deliberately NOT asserted (anti-drift — do not re-add)
These inferred/suspect claims were rejected in the v3-checklist delta analysis and
are intentionally absent — do not re-introduce them as gates:
- **No "external images break for LIVE visitors" mechanism.** The media-storage rule
  (Phase 1) is grounded in Trevor's instruction to use the returned GHL link — NOT in
  an unproven preview-vs-live divergence (the live probe tested PREVIEW only).
- **No bare `/tags/` endpoint.** Tags are handled as contact attributes proven by the
  form→CRM re-read (Phase 6); GoHighLevel's tag API is nested
  (`/locations/{id}/tags`), so no bare-`/tags/` path is asserted.
- **No toggle colour ("blue=on/gray=off").** Full width is verified by toggle STATE /
  rendered full-bleed width (Phase 3), never a colour.
- **No literal "403" on sub-account mismatch.** The gate refuses on an id mismatch
  (Phase 0); the exact HTTP status is illustrative, not a contract.
- **No "GHL strips iframe/script/external-CSS" gate.** Live probe (2026-06-27)
  confirmed iframes, inline `<script>`, and external/inline CSS all SURVIVE and apply
  in custom-code blocks — so no sanitizer/strip gate is added.
