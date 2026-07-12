# SOP-SOCIAL-03: CREATIVE INTERJECTION — FORM IS PROVEN, CONTENT IS SOVEREIGN

**Cluster:** Social-Media-Craft Rules (`universal-sops/social-media-craft/`)
**Master authority:** `SOCIAL-PIPELINE-MANIFEST.json` + `57-social-media-in-a-box/MASTERDOC.md` (§4) + `57-social-media-in-a-box/scripts/build_manifest.py`
**Owning roles:** Content Marketing Strategist (brief direction) + Chief Marketing Officer (campaign approval) + Conversion Copywriter (client-copy)
**Stage:** P2-BRIEF / P2-INGEST (content-lane variants of P2; identical P3->P8 gate chain)
**Produces:** `working/creative/brief.json`, `working/creative/overrides.json`, `working/creative/applied.json`, `working/creative/client-copy/*.json`; the certificate's `creative` block
**Gates this stage satisfies:** AF-SM-OVERRIDE-UNLOGGED, AF-SM-CLIENT-COPY-MUTATED, AF-SM-DOUBLE-POST, plus every P3 band code

---

## 0. THE ONE-SENTENCE LAW (§4.0)

> **Provers freeze the FRAME, never the PICTURE.** The client owns every word, angle, image, and mood; the engine proves only that the frame (shape, size, count, safety, de-dup, provenance) held.

Three facts make this true and v0.2.0 keeps all three: the prompt hash pins the SYSTEM message only (creativity flows through never-hashed USER slots); every band is a RANGE or has a client-exact override; no prover calls a model to judge content.

## 1. THE FOUR CREATIVE MODES (M1-M4)

| Mode | Owner | What the client controls / what stays enforced |
|---|---|---|
| `brief` (M1) | content-marketing-strategist | "Do it THIS way this week." The brief steers theme/angle/hooks/format/voice/arc/visuals through the un-hashed slots and overrides every default. Bands (logged overrides), scrub, certificate, de-dup, GHL-only posting all stay enforced. |
| `campaign` (M2) | chief-marketing-officer | One-off / off-template push (flash sale, launch takeover) with its own asset list + schedule + planner row. Off-**template**, never off-**spine**. |
| `client-copy` (M3) | conversion-copywriter | The engine posts the client's finished copy VERBATIM; `AF-SM-CLIENT-COPY-MUTATED` hash-guarantees the published bytes (modulo a programmatic ctaLink append). It packages/de-dupes/certifies but NEVER authors. |
| `reactive` (M4) | community-manager | Trend / newsjack single post — a fast lane, not a loose lane. Full form+safety chain incl. de-dup against the scheduled week. |

Flags on `week`/`day`: `--brief FILE` (tilt the default engine) / `--override FILE` (client-exact band numbers — logged or the run fails via `AF-SM-OVERRIDE-UNLOGGED`).

## 2. THE TWELVE INJECTION POINTS (I1-I12)

I1 theme of week · I2 wildcard/queued themes · I3 brand voice/tone/avatar · I4 custom hooks/angles · I5 one-off campaigns · I6 client-supplied copy · I7 seasonal/reactive · I8 per-platform voice · I9 visual art direction · I10 persona layer (config baseline day one; adapter v0.5.0) · I11 narrative-arc controls · I12 CTA/comment mechanics. Each enters through its slot (SOP-01); provers touch FORM only, and several touch nothing at all.

## 3. WHAT PROVERS GATE VS NEVER GATE (§4.2)

- **GATED (form + safety, every mode):** character/count bands (ranges, client-overridable logged) · per-platform JSON contracts · JSON-safety of machine-reinjected strings (never overridable — technical) · no-double-post de-dup · zero-Anthropic + provenance · no-secret/no-client-name scrub · preflight readiness · process integrity (nonce, hash-pin, certificate-before-publish, BYPASS-SCAN) · client-copy verbatim · override logging · 20-column write-back.
- **NEVER gated (content, structurally out of reach):** topic/theme · angle/hook/wit · tone/voice/persona · word choice/literary form · arc shape · which hashtags · image aesthetic/style · CTA phrasing · on- vs off-template · creative merit. The human-voice report (SOP-04) is ADVISORY ONLY.

### 3a. Image prompt FORM vs image AESTHETIC — the durable P3-05 fix (never let the successor reopen the gap)

Skill 35 (`35-social-media-planner`) had a pre-generation prompt-quality gap that a form/content split closes cleanly: `image_prompt_carousel`/`image_prompt_series` (`config/bands.json`, `AF-SM-IMGPROMPT-BAND`) already gate image-prompt LENGTH the same way every other creative field is banded — but the gap that damaged Skill 35 was never about length alone. Splitting explicitly, so the fix cannot resurrect when Skill 35 archives and Skill 57 becomes the sole engine (`cc-compat.json` `supersedes: 35-social-media-planner`):

- **GATED — image prompt FORM (provable, structural, added to the same class as every other band/contract check above):** the platform ratio + pixel spec is declared and matches a real placement slot · legibility (headline word-count ceiling, `headline_words` band) · a merged negative/avoid-list is present · the mandatory brand-safety clause is present (`45-design-intelligence-library/library/social-media-designs/_RULES.md`) · text-overlay/quote-card prompts route to a text-rendering-capable model (Ideogram V3 DESIGN) and never to a non-text-rendering model — this is a FORM/routing fact about the deliverable, not a creative judgment, and is gated exactly like `image_prompt_carousel`/`image_prompt_series` length today.
- **NEVER gated — image AESTHETIC/content:** subject matter, mood, lighting style, composition choice, color grading taste, which reference image inspired the shot, artistic interpretation. This stays fully sovereign to the client/creative-mode injection points (I9 visual art direction) exactly as §3 already states — the FORM split above adds provable structural checks, it does not touch a single aesthetic decision.

A future prover pass MAY extend `prove_bands.py`/`config/bands.json` with the FORM checks above (ratio/pixel/legibility/avoid-list/brand-safety/routing) using the same band-file pattern `image_prompt_carousel` already establishes; until then, this section is the binding doctrine so the FORM/aesthetic line is never redrawn ad hoc during the 35->57 migration. Skill 57 supersedes Skill 35 per `cc-compat.json`; the skill-campaign 7-03 HOLD still governs rollout of both (repo-only until released).

## 4. OVERRIDE LOGGING IS THE ONLY DISCIPLINE

Every applied band override (`working/creative/applied.json`) MUST have a matching logged entry in `working/creative/overrides.json` (who asked, verbatim ask, scope). An applied band that differs from `config/bands.json` with no matching log refuses the certificate: `AF-SM-OVERRIDE-UNLOGGED`. Deviation is free (the client gets EXACTLY what they asked for, never floored/capped); a SILENT deviation is the only forbidden deviation. The certificate records a `creative` block (mode, brief sha, theme source, per-band overrides with verbatim refs, client-copy shas, persona choice, em-dash policy, series length, arc, style pick) — proving BOTH "nothing unsafe happened" AND "the client got exactly what they asked for."

## 5. NO-DOUBLE-POST UNDER CREATIVITY (§4.4)

Creative modes raise double-post risk, so de-dup is a named prover: one poster per location; a content-fingerprint ledger in SQLite; a fail-closed P7 gate `AF-SM-DOUBLE-POST` (same content-sha in the lookback window -> BLOCK; occupied slot -> BLOCK) reconciled against the LIVE GHL post-listing. A deliberate identical re-post goes through ONLY via a logged owner-approved re-post token recorded on the certificate. Handle a block per SOP-04.
