# MASTERDOC — Social Media in a Box (Skill 57)

**The SACRED playbook.** Everything here is machine-enforced by the fail-closed provers in
`scripts/` and mirrored in `config/bands.json` + `SOCIAL-MANIFEST.json`. Nothing here is advisory.
A number is never "close enough": a logged **client-exact override** wins and is recorded on the
`PROCESS-CERTIFICATE`; otherwise the band is the floor and the prover exits non-zero on any miss.
**Enforcement, not description.**

> Fleet rule: NO client names anywhere. Owner "Trevor Otts" is the only permitted real name.
> ⛔ Client runtime uses the CLIENT's own providers ONLY — never Anthropic. The 19 baked prompts in
> `prompts/` are the product (v0.2.0 adds 17 podcast / 18 newsletter / 19 blog and version-bumps
> 01/15/16 with the creative-layer slots); they are hash-pinned against canon (AF-SM-PROMPT-HASH).

> **v0.2.0 one-sentence law:** *Provers freeze the FRAME (shape/size/count/safety/de-dup/provenance),
> never the PICTURE (topic/angle/voice/image aesthetic).* Every band is a RANGE or has a **logged
> client-exact override** (recorded on the certificate's `creative` block); no prover ever calls a
> model to judge content. See §7 below for the full v0.2.0 merge (folds + creative layer).

---

## 1. The product: the Universal Social Media Playbook v6.0 — 7-Part Cliffhanger Content Series

The weekly engine writes seven "episodes" (Sunday → Saturday) as one serialized TV arc, encoded
verbatim in **prompt 15** (`prompts/15-weekly-7part-content-writer.md`, 64K chars) and adapted to
each platform by **prompt 16** (`prompts/16-multi-platform-reformatter.md`, 70K chars). The SACRED
mechanics preserved from the production workflow family:

- **Three-act TV arc across the week** with dual-action endings on each day (a **cliffhanger** that
  pulls to tomorrow + a **comment driver** that pulls to the follow-up comment).
- **Three-part title system:** a main title that stays **IDENTICAL across all 7 days**, plus a daily
  subtitle in hashtag format with **NO SPACES between words**.
- **150-character hook priority** — the scroll-stopping promise lives in the first ~125–150 chars.
- **Truth standard / anti-fabrication** — no invented statistics, testimonials, or credentials;
  claims stay inside the brand's real, supplied material.
- **Deterministic style randomization seeded by the weekly theme** — 8th-word content-style pick of
  11 styles; 9th/5th-word design-style pick of 14 styles (reproducible variety, not chaos).
- **15-style artistic image library** with lifestyle-vs-typography image assignments per slide.
- **Per-client model + 2 fallbacks**, QC-feedback re-injection loop, JSON-only output with the
  em-dash ban enforced in triplicate.

The single-call and per-day engines (**prompts 01–04**) provide the multi-day multi-platform
generator, the Core-Concept (master hook) agent, the per-platform "Superpower Strategy" injection,
and the Platform-Native Reformatter. **Every** content output passes `validate_contract.py`
(shape + em-dash ban) then `prove_bands.py` (the bands below) before the pipeline may advance.

---

## 2. SACRED bands (single source of truth: `config/bands.json`; prover: `scripts/prove_bands.py`)

| Field | Band | Applies to | Prompt | AF code |
|---|---|---|---|---|
| Carousel caption | **1,500–1,800 chars** | Facebook / Instagram | 09 | AF-SM-CAPTION-BAND |
| Carousel caption | **1,500–1,900 chars** | LinkedIn | 10 | AF-SM-CAPTION-BAND |
| Image prompt | **1,000–1,700 chars** | carousel slides | 09/10/12 | AF-SM-IMGPROMPT-BAND |
| Image prompt | **1,800+ chars** | 7-part weekly series | 15 | AF-SM-IMGPROMPT-BAND |
| Post body | **300+ words** | main platform posts | 15 | AF-SM-POSTBODY-WORDS |
| followUpComment | **≤ 600 chars** | 7-part series | 15 | AF-SM-FOLLOWUP-BAND |
| followUpComment | **≤ 500 chars** | reformatter | 16 | AF-SM-FOLLOWUP-BAND |
| pdfTitle | **≤ 100 chars** | LinkedIn PDF carousel | 10 | AF-SM-PDFTITLE-BAND |
| textOnImage headline | **≤ 8 words** | carousel slides | 09/10 | AF-SM-HEADLINE-WORDS |
| Hashtags | **5–7** | Facebook / Instagram captions | 09 | AF-SM-HASHTAG-COUNT |
| Hashtags | **exactly 3** | LinkedIn | 10 | AF-SM-HASHTAG-COUNT |
| Hashtags | **5–15** | Instagram reformat | 16 | AF-SM-HASHTAG-COUNT |
| Video storyboard | **3–7 scenes, sum EXACTLY 25.0s** | Sora video | 08 | AF-SM-STORYBOARD |
| Carousel slides | **10 (FB/IG) / 9 (LinkedIn)** | carousel | 09/10 | AF-SM-CAROUSEL-SLIDES |
| Carousel assembly floor | **≥ 2 completed images** | carousel | part5/part7 | AF-SM-CAROUSEL-FLOOR |

`prove_bands.py` measures **stripped/character lengths deterministically** (clone of the
presentations floor-prover pattern), prints a per-field PASS/FAIL table, and exits non-zero on any
violation. The publisher cannot be invoked without a PASS certificate in the run manifest.

---

## 3. JSON contracts (prover: `scripts/validate_contract.py`)

- **FB/IG carousel** — `carouselCaption` + `slides[10]`, each slide `{textOnImage, prompt}`. The
  slide text uses the `HEADLINE | BODY` single-field `textOnImage` contract.
- **LinkedIn carousel** — additionally `pdfTitle` + `postAsPdf:true` + `slides[9]`; posted as a PDF
  document via GHL.
- **Reformatter** — STRICT valid JSON, no markdown, no code blocks; blocks only for the requested
  platforms; the **em-dash ban** (`AF-SM-CONTRACT-EMDASH`) is re-checked deterministically.
- **Gemini 4-grid selector** — the output is a **single digit 0–3** (`AF-SM-GRID-DIGIT`).
- **Carousel QC bot** — the output is the literal `Good` OR the exact four-field set
  `fix_type / edit_instructions / negative_prompt_additions / issue_summary`, and is **JSON-safe**
  for SeedDream re-injection (no double quotes, no backslashes, no em dashes) (`AF-SM-QC-JSON`).
- **Publish result** — the normalized `{platform, success, totalPosts, processedAccounts, errors}`
  contract per sub-mode (`AF-SM-PUBLISH-RESULT`).

---

## 4. Module contracts

### Module 0 — Preflight (`preflight_gate.py`)
Fail-closed readiness per run. Kie.ai credits ≥ **200**, OpenRouter balance ≥ **$5**, GHL Private
Integration Token valid against `GET /locations/{locationId}`, all required config fields present +
secrets confirmed SET (never printed), client `status == Paid`. FAIL → labeled failure report +
configured notification; run blocked (`sys.exit 2`); NO downstream module executes.

### Module 1 — Planner (LOCAL; replaces the `social-planner-*` n8n webhooks)
Creates the "`<brandName>` Social Media Planner" sheet from the master template; syncs
`themeOfWeek` into the local client config (replacing the `Clients_BCEO` n8n data table); appends
the normalized **20-column** weekly row: **Week Of, Theme, Research, Core Content, Images, Videos,
Facebook, Instagram, LinkedIn, YouTube, TikTok, Pinterest, Carousels, Blog, Podcast, Email, QC,
Scheduled, Overall, Notes** (`AF-SM-WRITEBACK-COLUMNS`).

### Module 2 — Content engine
Two engines: (A) single-call N-day multi-platform JSON generator (prompt 01); (B) per-day agent loop
— Core-Concept (prompt 02) → strategy injection (prompt 03) → Platform-Native Reformatter (prompt
04). Weekly 7-part series mode uses prompts 15 + 16. Every output → `validate_contract.py` +
`prove_bands.py`.

### Module 3 — Media core (driven by the local SQLite `ledger.py`)
- **Image:** Visual Prompt Architect (05) → Kie.ai Midjourney → Prompt-Doctor retry on 422 (06) →
  Gemini 4-grid vision judge picks best of 4 (07) → winner staged; SeedDream resizes 9:16 / 16:9
  when the post type demands.
- **Video:** Storyboard Architect (08; 3–7 scenes, **exactly 25.0s**) → deterministic math validator
  → Kie.ai Sora → poll → download.
- **Carousel image:** Nano-Banana Pro generate (12; 4:5, 2K) → Gemini QC bot casual-viewer test
  (11) → FAIL → SeedDream 4.5 edit from QC feedback (13) → QC 2 → final fallback strips ALL text →
  ledger update. Poll every **30s**; **≥10 complete** (9 LinkedIn) or **120-poll** timeout; assemble
  only with **≥2** images. Every fail/timeout branch alerts the configured channel.
- **Podcast cover:** 1:1 art (14), one retry, fail → notification + empty-URL return. Cover art only;
  the podcast **audio** episode stays with Skill 35 (PRD Open Decision D3).

### Module 4 — Publisher (GHL-direct)
Per-platform posting sub-modes (`modules/4-publisher/submodes/`), carousel assembly (10-slide FB/IG
via prompt 09; 9-slide LinkedIn document-PDF via prompt 10 with `postAsPdf:true` + `pdfTitle`), and
the `clean` sub-mode (delete-posts: list posts in a date range, filter by status, delete — bulk
rollback). Every sub-mode posts through **the client's OWN GHL location** with **the client's own
Private Integration Token + locationId + connected social accounts** — never operator credentials,
never direct platform APIs. Normalized result `{platform, success, totalPosts, processedAccounts,
errors}`. `done` is claimed only from the certificate **plus a live GHL post-listing verify**.

---

## 5. The gate chain (each step a separate process; each non-zero exit blocks everything downstream)

```
preflight_gate.py → [content engine] → validate_contract.py → prove_bands.py
  → [media core + ledger.py QC loop] → scrub_gate.py (output screen)
  → build_manifest.py (signed process certificate, proves ZERO Anthropic) → [publisher] → planner write-back
```

`build_manifest.py` records the config hash (secrets excluded), prompt-file hashes vs canonical,
every gate's PASS certificate, the model/provider used per call (**must show ZERO Anthropic**), and
the artifact checksums. The publisher refuses to run without a complete manifest. `scrub_gate.py`
runs at build time on every shipped file AND at runtime on generated content, and **never prints a
matched secret value** — a hit is confirmed and located, never echoed.

---

## 6. Agency vs single-brand

- **single-brand (DEFAULT, client boxes):** one brand config, one GHL location, the client's own
  providers. This is what ships fleet-wide.
- **agency (operator/master boxes only):** a roster loop over N brand configs, gated by an explicit
  `mode: agency` flag + a roster file. The run **hard-fails** (`AF-SM-AGENCY-SHARED-PIT`) if two
  roster entries share a Private Integration Token or a locationId. Never co-mingles brand resources;
  the roster loop stays sequential per brand.

---

## 7. v0.2.0 — the 35↔57 merge (folds + creative layer). SACRED, machine-enforced.

Authority: `MERGE-INTEGRATION-PLAN.md` (QC 9.2 APPROVED) + `CREATIVE-INTERJECTION-DESIGN.md`. Every
item below plugs into the SAME entry + nonce + prover spine as the v0.1.0 phases — same acceptance
bar (hash-pinned prompt, band in `config/bands.json`, phase + `AF-SM-*` in `SOCIAL-MANIFEST.json`,
prover `--self-test`, golden + broken-variant fixtures).

### 7.1 Seven folds → first-class modes (merge plan C1–C7)

| C | Capability | Mode / sub-mode | New bands / AF codes |
|---|---|---|---|
| C1 | X/Twitter parity | `twitter` publisher sub-mode + `twitter` in the `platforms` enum | inherits PIT + BYPASS-SCAN; `AF-SM-PUBLISH-RESULT` |
| C2 | Live connected-accounts discovery + Owner Q&A | P0 `check_connected_accounts` reconciles the enum vs the live GHL listing (`GET /social-media-posting/oauth/{locationId}/accounts`); deliberate skips only via the logged `platformsExcluded` | `AF-SM-DISCOVERY-DRIFT` — BOTH drift directions fail-closed; Owner Q&A answers scope from the persisted reconcile (preflight report `connected_accounts`), never a memorized list |
| C3 | Podcast audio | `podcast` (prompt 17) | `AF-SM-PODCAST-SCRIPT` (1,500–2,000 w, ≥1 `[emotion]`/para), `AF-SM-PODCAST-DURATION` (600–900 s / ≥128 kbps), `AF-SM-PODCAST-COVER` (1400×1400 JPEG); `PODCAST_DEFERRED` graceful skip |
| C4 | Newsletter | `newsletter` (prompt 18, GHL Campaigns) | `AF-SM-EMAIL-SUBJECT` (≤60), `AF-SM-EMAIL-PREVIEW` (≤120), `AF-SM-EMAIL-HTML` |
| C5 | Blog | `blog` (prompt 19, GHL blog) | `AF-SM-BLOG-TITLE` (≤80), `AF-SM-BLOG-META` (≤160), `AF-SM-BLOG-BODY` (700+ w) |
| C6 | Engagement report | `engage` (read-only) | `AF-SM-ENGAGE-REPORT`; never blocks a publish |
| C7 | Thumbnails + Stories captions | media-core thumbnail sub-step + `storiesCaption` band on reformat | `AF-SM-STORIES-CAPTION` (≤250) |

### 7.2 Creative-interjection layer (FORM vs CONTENT)

- **4 client modes:** `brief` (M1), `campaign` (M2), `client-copy` (M3 — verbatim, `AF-SM-CLIENT-COPY-MUTATED`), `reactive` (M4). Content lanes P2-BRIEF / P2-INGEST feed the identical P3→P8 chain.
- **12 injection points I1–I12** (theme, wildcard queue, brand voice, hooks/angles, campaigns, client copy, reactive, per-platform voice, art direction, persona, narrative arc, CTA/comment). The client interjects in natural language; intake normalizes into a slot, **never floors/caps a stated number**.
- **Override resolution run > config > default,** every applied override LOGGED or `AF-SM-OVERRIDE-UNLOGGED` refuses the certificate. A silent deviation is the ONLY forbidden deviation.
- **Certificate `creative` block** records `{mode, brief_sha, theme_source, overrides, client_copy_shas, persona_source, em_dash_policy, series_length, arc_template, style_pick}` — proving BOTH "nothing unsafe happened" AND "the client got EXACTLY what they asked for."
- **No-double-post de-dup** (`AF-SM-DOUBLE-POST`): content-fingerprint + slot + live-GHL reconcile; cleared only by a logged owner re-post token.
- **Freedom clause (DNA-2):** the TV-season arc is prompt-encoded guidance, "a starting framework, not a rigid template." There is **NO arc prover**; I11 (`arcTemplate`/`pitchCurve`/`seriesLength`/`nextSeasonTease`) makes the freedom addressable and certificate-logged.

### 7.3 The four TOO-RIGID fixes (R1–R4)

- **R1:** uniform `overrides` / `band_override` across ALL five evaluators (post + carousel + series + reformat + storyboard) — not just `kind=post`. Resolution run > config > default; every application logged + self-tested.
- **R2:** carousel slide-count client override accepted within **floor 2** (the real assembly limit); a below-floor override is rejected (`AF-SM-CAROUSEL-FLOOR`).
- **R3:** per-platform `hashtagPolicy` override incl. `[0,0]` (e.g. no hashtags on LinkedIn).
- **R4:** the em-dash ban splits — machine-reinjected JSON-safe fields (QC / grid) keep it FOREVER (technical); content fields keep it as the DEFAULT with a per-client logged `emDashPolicy: allow-content` opt-out.

### 7.4 Deferred (honest, fail-closed — `defer_stub.py`, `AF-SM-DEFERRED`)

Narrated Reels → v0.3.0 · `syndicate` add-on channels → v0.4.0 · persona adapter (C10) + memory-core
feed (C11) → v0.5.0. Baseline config-carried behavior is never blocked meanwhile.

### 7.5 De-dup of shared surfaces (merge plan §5)

ONE weekly-theme cron `social-media-weekly-theme` `0 8 * * 6` (`scripts/register-social-cron.sh`,
idempotent, registered in the OpenClaw GATEWAY cron store — the same store the live Skill-35 cron
uses, so the legacy `skill35-weekly-theme` is retired IN PLACE and confirmed gone before 57's cron
is armed; QC-asserts exactly one across both stores) · the per-box 35→57 flip is mechanized by
`scripts/migrate-35-to-57.sh` (atomic + idempotent + client-config-gated + receipted + rollback;
operator-triggered, never auto-run by a fleet roll) · one planner Sheet +
`themeOfWeek` · one GHL poster per location · `backend` flag defaults to `ghl-direct` fleet-wide.

### 7.6 Conscious DROPS (merge plan §2.3 — superseded, never silent)

Nothing client-facing is lost by these; each mechanism retires only because a stronger 57 mechanism
strictly supersedes it. Recorded here so no drop can ever read as silent:

| C | Skill-35 mechanism dropped | Superseded by (in THIS skill) |
|---|---|---|
| C12 | 15+6 multi-agent QC org (40-check prose QC) | Fail-closed model-free provers + signed certificate — QC coverage 1:1: Grammar→`validate_contract`, Fact-Check→provenance record, Visual→Gemini media-QC loop, Compliance→`scrub_gate`, Performance→`prove_bands`, Final→certificate |
| C12a | Producer-side per-role model tiering (rides C12) | The client-config model contract: ONE client OpenRouter model + 2 fallbacks (`route:fallback`), client Gemini vision QC, client Kie media — provers need no model at all |
| C13 | Tier 0→3 posting ladder (caf → GHL MCP → raw REST) | GHL-direct single sanctioned path + BYPASS-SCAN (`AF-SM-POST-BYPASS`); posting itself preserved (C1 + §2.1) |
| C14 | n8n runtime transport (`social-planner-*` / `podbean-publish` webhooks) | Local planner module (P1/P8) + local Podbean API call (C3); per-box retirement = flip `backend: ghl-direct` (a declared transition adapter, not plumbing surgery) |
| C15 | `weekly-batch` `0 9 * * 1` cron + `content-calendar.json` batch driver | `week` mode + the ONE ported theme cron (§7.5); the 20-column write-back keeps the planner sheet's `Images`/`Videos` preview cells; posting cadence absorbed by GHL per-post scheduling |
| C16 | Version-drift tolerance (three version numbers in one skill) | Single `skill-version.txt` + `SOCIAL-MANIFEST.json` single source of truth (a defect retired, not a capability) |
