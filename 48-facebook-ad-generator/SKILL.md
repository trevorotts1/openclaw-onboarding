---
name: facebook-ad-generator
description: Turns two client documents (a show/product bio + an audience profile) into a complete, ready-to-run batch of 10 Facebook & Instagram ads — ~70 overlay lines, a human pick-10, 10 bodies + 10 headlines + 10 image prompts, 10 square images via Kie gpt-image (text baked in), a verified PLAI-shape targeting brief, GoHighLevel-hosted image links, a copy-paste ad-text doc, and a PLAI-ready handoff package. Dependency-map foreman, money ceiling, run-id no-double-charge, two human pauses, independent QC. PLAI is the only ad path; no direct Meta API.
---

# Facebook & Instagram Ad Generator (Skill 48)

An autonomous creative assembly line for the Paid Advertisement department. A client
(e.g. a podcast host) hands two documents — a show/product bio and an audience profile
— and the skill produces a finished batch of **10 Facebook + Instagram ads**, pausing
at exactly two human gates.

## What a run produces

1. ~70 short **overlay lines** (baked-in image text) — `s1-overlays.md`
2. **Pick-10** (human pause #1) — the owner picks their favourite 10 — `s1-selection.json`
3. 10 **primary-text bodies** (125-char hook / exactly 3 CTAs / controlled emoji) — `s2-primary-text.md`
4. 10 **headlines** (only four locked shapes) — `s3-headlines.md`
5. 10 **image-instruction prompts** (3,500–18,000 chars; creativity/typography/color-grading/quality/facial-intelligence) — `s4-image-prompts.md`
6. 10 **square 1500×1500 images** with the text **baked in** via Kie `gpt-image-*` (auto-adopts future gpt-image versions) — `s5-image-receipt.json`
7. A **verified targeting brief** in PLAI's three-tier shape (every interest real or flagged-unverified) — `s6-targeting.json`
8. Images **hosted in GoHighLevel** (public, login-free links)
9. A **copy-paste ad-text doc** — Headline + Body as two separate blocks per ad (Notion → Google Doc → plain text)
10. A **PLAI-ready package** (hosted links + copy variants + targeting table) + **approve-to-publish** (human pause #2)

## The enforcement spine (mirrors Skill 47, with a dependency-map foreman)

- **Single source of truth:** `universal-sops/fb-ad-craft/AD-PIPELINE-MANIFEST.json` — every stage, owning role, produced file, `depends_on[]` map, and gate code.
- **Foreman:** `scripts/ad_director.py` — a DEPENDENCY-MAP gate-and-attest driver (NOT Skill 47's straight line): S2/S3/S4 run in parallel after PICK-10; S5 waits on S4; S6 on S2+S3; S7 on S5+S6. The two human gates (PICK-10, PUBLISH) are NON-skippable.
- **Receipt validators + money gates:** `scripts/ad_build_check.py` — 35 offline checkers + the Phase-0 Kie balance preflight.
- **Rule book:** `universal-sops/fb-ad-craft/MASTER-AD-QC-AUTOFAIL-RULESET.md` — one machine-checkable row per autofail.
- **Lockstep + Guard A + negative suite:** `scripts/ad_sync_check.py` (incl. recovery R1-R4), `scripts/ad_gate_integrity_check.py`, `scripts/test_ad_preflight.py` (37 autofails, all negative-tested).
- **Self-correct + park-and-resume:** `scripts/ad_recovery.py` (the engine) + `ad_director.py --recover/--resume/--status`. A recoverable (`recovery:auto`) failure redoes ONLY the failing artifact with the gate feedback, re-runs the REAL check, up to a bounded budget, then continues; a non-recoverable (`recovery:park`) condition — over the money ceiling / out of balance, a fabrication/tampering check, a missing human approval — writes a DURABLE save-point (`PARKED.json` + a box pointer under `OC_ROOT/workspace/.park/fbad/`, exit 5) and PAUSES, never self-correcting past it. `--resume` re-enters at the exact last-incomplete phase, idempotent on the run-id ledger (never re-charges, never re-uploads). Per-gate policy lives in the manifest (`recovery` + `max_fix_attempts`), is mirrored in the ruleset Section-7 + Recovery column, and is proven by `scripts/test_ad_recovery.py`. Operators inspect/clear parks with `scripts/unpark-ad-run.sh`.
- **CI:** `.github/workflows/ad-pipeline-lockstep.yml` — sync + negative test + recovery proof + Guard A + GOOD/BAD fixture self-test on every change.

## Money control (LOCKED)

Estimate up front → per-job ceiling (HARD-fail if the estimate is over, before any spend) → a cheap LOCAL running tally that stops before crossing → a single balance preflight at start. **Never** a balance lookup per image. A unique **run-id** namespaces every receipt so a retry never re-spends or double-uploads.

## Independent QC

Five scored gates (Words / Image Prompts / Images / Targeting / Package). A gate opens only with zero autofails AND an 8.5+ average (no category < 7) from a DIFFERENT worker than the maker (`AF-FBAD-QC-INDEPENDENCE`). Below the line auto-redoes only the failing piece; escalates to the owner only after the redo budget is spent.

## Boundaries

- **PLAI is the only ad path** — no direct Meta/Facebook API call.
- **No ad-policy gate** and **no separate text-reading/OCR step** (by decision) — text stays baked in; legibility is judged by an independent VISION reviewer at Gate C + the human at the approve pause.
- Images are hosted **only** in the client's own GoHighLevel (client's own location PIT, never the operator's key). Generation uses the client's own `KIE_API_KEY`.

## Roles

2 new seats (`facebook-instagram-ad-run-producer`, `direct-response-ad-copywriter`) + 6 reused (AI Image Generator Specialist, Audience Research Specialist, Facebook/Instagram Ads Specialists, Devil's Advocate, QC Role, Director of Paid Advertisement). Author-personas are PINNED per stage (overlays = Brendan Kane + Phil Jones + Shelle Rose Charvet; bodies = Robert Bly + Joanna Wiebe + Donald Miller + Alex Hormozi; headlines = Robert Bly + Brendan Kane). Only the 42 built blueprints are runnable.

## Files in this skill

- `SKILL.md` / `INSTALL.md` / `INSTRUCTIONS.md` / `EXAMPLES.md` / `CORE_UPDATES.md` / `DEPENDENCY-MANIFEST.md` / `skill-version.txt` / `facebook-ad-generator.skill`
- `install.sh` / `preflight.sh` / `verify-deps.sh` / `qc-facebook-ad-generator.sh`
- `scripts/` — `ad_director.py`, `ad_build_check.py`, `ad_sync_check.py`, `ad_gate_integrity_check.py`, `test_ad_preflight.py`, `ad_recovery.py` (self-correct/park engine), `test_ad_recovery.py` (recovery proof), plus the live-integration helpers `ad_run_ledger.py`, `ad_selection.py`, `ad_ghl_push.py`, `ad_targeting_resolve.py`, `build_ad_text_doc.py`, `build_plai_brief.py`, and `test_kie_adapter_resultjson_decode.py` (reused). Operator un-park tool: repo-root `scripts/unpark-ad-run.sh`.
- `tools/ghl_media.py` (reused + the new `create_media_folder()`)
- `test-fixtures/make-ad-fixtures.sh`
