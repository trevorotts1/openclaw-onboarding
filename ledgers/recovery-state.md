# Ledger / Session-Log Reconciler — Recovery Snapshot

AUTHORITATIVE, machine-derived-from-git-truth recovery source for the Skill 6 (blended persona kanban v2) and Skill 62 (cinematic web funnel engine) builds. Rewritten in full every reconciler run (every 10 minutes via cron). If a build session is lost to a context/session limit, this file is the fastest path back to real state — every fact below was independently re-derived from `git` (fetch + ancestry + direct-parent merge-commit match + annotated-tag lookup), never copied from a prior run or from ledger prose.

Generated: 2026-07-15T09:50:01Z
openclaw-onboarding `origin/main` HEAD: `f81017aa966430ec4fe715ef96ac33a681e7522f`
blackceo-command-center `origin/main` HEAD: `2a9b39bdd5d81bc1eeaca1c0a97615d3553b11e3`

## Skill 6 — openclaw-onboarding (`skill6-v2/*` branches)

| unit | branch | headSha | mergedIntoMain | mergeSha | tag | ledgerStatus | qcScore(prose) |
|---|---|---|---|---|---|---|---|
| U1 | `skill6-v2/U1` | `6a31a7fe` | True | `292f4ee4` | v20.0.17 | verified | 9.35 |
| U111 | `skill6-v2/U111` | `6b24b2b8` | True | `f2be7dcd` | v20.0.24 | verified | 8.9 |
| U18 | `skill6-v2/U18` | `0b72ee80` | True | `706aff5d` | v20.0.27 | verified | 9.3 |
| U2 | `skill6-v2/U2` | `1cb2c874` | True | `86420ff7` | v20.0.18 | verified | 8.9 |
| U20 | `skill6-v2/U20` | `1bbfe0f0` | True | `ea371000` | v20.0.23 | verified | 9.1 |
| U21 | `skill6-v2/U21` | `ad92145d` | True | `0d3f31a0` | v20.0.33 | verified (ONB half) | - |
| U22 | `skill6-v2/U22` | `50ff2e79` | True | `b64c8166` | v20.0.35 | merged (OFFLINE/CODE-MERGE tier, both repos) — LIVE-PROOF tier pending, own receipt | - |
| U22-offline | `skill6-v2/U22-offline` | `8195fb4c` | False | - | - | (no row) | - |
| U24 | `skill6-v2/U24` | `fc9e636e` | True | `1de2099a` | v20.0.30 | verified | 9.0 |
| U25 | `skill6-v2/U25` | `f95e3fe3` | True | `d177e7e7` | v20.0.21 | verified | - |
| U27 | `skill6-v2/U27` | `cba9065a` | True | `6234014b` | v20.0.25 | verified | 9.0 |
| U3 | `skill6-v2/U3` | `033d223d` | True | `ba89a65d` | v20.0.22 | verified | 9.3 |
| U4 | `skill6-v2/U4` | `ee42a22a` | True | `7dfbad1a` | v20.0.31 | verified (ONB half) | - |
| U5 | `skill6-v2/U5` | `616084f2` | True | `e979d09d` | v20.0.32 | verified (ONB half) | - |
| U6 | `skill6-v2/U6` | `da5dd284` | True | `ada71006` | v20.0.27 | verified | 9.0 |
| U63 | `skill6-v2/U63` | `bf601e7a` | False | - | - | deferred (operator-gated) | - |
| U7 | `skill6-v2/U7` | `f06ce74c` | True | `8004d0b2` | v20.0.34 | verified | - |
| U8 | `skill6-v2/U8` | `2034ad79` | True | `3abbafe5` | v20.0.29 | verified | 8.9 |
| chainA | `skill6-v2/chainA` | `3161e8fa` | True | `f6636fc0` | v20.0.19 | (no row) | - |
| chainB | `skill6-v2/chainB` | `2e9907d7` | True | `7de4a73e` | v20.0.20 | (no row) | - |

## Skill 6 — blackceo-command-center (`skill6-v2/*` branches)

| unit | branch | headSha | mergedIntoMain | mergeSha | tag |
|---|---|---|---|---|---|
| U20 | `skill6-v2/U20` | `5e5c3bb9` | True | `ae80043b` | v6.0.4 |
| U21 | `skill6-v2/U21` | `5374c4fd` | True | `4759561a` | v6.0.18 |
| U22 | `skill6-v2/U22` | `f4f933ff` | True | `ae972738` | v6.0.20 |
| U22-offline | `skill6-v2/U22-offline` | `41e3b890` | False | - | - |
| U26 | `skill6-v2/U26` | `5e26d8d8` | True | `b3c585c1` | v6.0.3 |
| U27 | `skill6-v2/U27` | `92beccab` | True | `6dfb8bf7` | v6.0.11 |
| U32 | `skill6-v2/U32` | `6c442dfd` | True | `2da17734` | v6.0.5 |
| U4 | `skill6-v2/U4` | `ca647283` | True | `98e55842` | v6.0.17 |
| U40 | `skill6-v2/U40` | `1e9a57ce` | True | `36674061` | v6.0.6 |
| U41 | `skill6-v2/U41` | `64863d52` | True | `619b9eca` | v6.0.7 |
| U46 | `skill6-v2/U46` | `e28ea4b4` | True | `fd064907` | v6.0.8 |
| U48 | `skill6-v2/U48` | `1dc10292` | True | `7f1c6620` | v6.0.9 |
| U5 | `skill6-v2/U5` | `89229982` | True | `eb00420d` | v6.0.16 |
| U55 | `skill6-v2/U55` | `a4c54669` | True | `917ea8f0` | v6.0.12 |
| U56 | `skill6-v2/U56` | `ce1fb032` | True | `a69f0da4` | v6.0.13 |
| U6 | `skill6-v2/U6` | `d6fc0509` | True | `2d82fd6a` | v6.0.15 |
| U60 | `skill6-v2/U60` | `803a8807` | True | `5e2f8b9a` | v6.0.10 |
| U7 | `skill6-v2/U7` | `ece5ae36` | True | `e96d745b` | v6.0.19 |

## Skill 62 — cinematic-web-funnel-engine (`skill62/cinematic-engine`)

- branch tip: `708f0255`
- merge-base with `origin/main`: `de6f1157`
- commits ahead of that merge-base (cinematic-specific work so far): 32
  - `708f0255` merge(skill-62): integrate U18 — GHL whole-page iframe embed package (spec 14.2) (QC 9.0)
  - `9ec71c82` merge(skill-62): integrate U16 — conversion tracking + GHL form/webhook wiring (P12) (QC 8.8)
  - `936fc2a4` merge(skill-62): integrate U14 — seam-continuity QC (SSIM+PSNR) across boundary-frame receipts (P10) (QC 9.0)
  - `9dafcc22` merge(skill-62): integrate U11 — concept board, anchor approval, scene-image generation flow (P6-P7) (QC 9.0)
  - `855b659a` fix(skill-62): U16 QC — resolve ghl-form-embed URL at real server boundary, not inside GhlFormEmbed
  - `1f773027` fix(skill-62): U16 QC — resolve @/components in vitest.config.ts for both raw template and materialized site
  - `86f509d7` fix(skill-62): U16 QC — enforce outbound-host allowlist in conversion-webhook relay
  - `60f4d085` feat(skill-62): U11 — concept board, anchor approval, scene-image generation flow (P6-P7)
  - `087d8e7f` feat(skill-62): U16 — conversion tracking + GHL form/webhook wiring (P12)
  - `405aad85` feat(skill-62): U18 — GHL whole-page iframe embed package (spec 14.2)
  - `4efebc96` feat(skill-62): U14 — real seam-continuity QC (SSIM+PSNR) across boundary-frame receipts (P10)
  - `467ce609` merge(skill-62): integrate U15 — Next.js/TypeScript template + first-party scroll-scrub engine (P11) (QC 9.0)
  - `63ca6177` merge(skill-62): integrate U10 — visual journey and scene planner (P4) (QC 9.0)
  - `32a13608` merge(skill-62): integrate U5 — Kie video Seedance frame pinning + skill-local provider + callback relay wiring (QC 9.2)
  - `50659ed4` fix(skill-62): U15 QC — escape attribute values in sanitize_copy_fragment to close quote-breakout XSS
- merged into `origin/main`: False

## Merge queue snapshot (`onboarding-merge-queue/`)

- writer lock held at gather time: False
- ready tickets in `tickets/`: 0
- completed in `done/`: 0

## This run

- ledger-edit permitted this run (merge-queue lock was free): True
- units auto-reconciled (git showed merged/tagged, ledger still said pending) this run: none
- journal corroboration hits scanned: 25 (informational only, never authoritative)

