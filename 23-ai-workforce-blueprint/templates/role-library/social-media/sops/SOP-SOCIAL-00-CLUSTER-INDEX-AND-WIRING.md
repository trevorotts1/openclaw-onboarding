# SOP-SOCIAL-00 — CLUSTER INDEX + WIRING (Social Media in a Box, Skill 57)

**Cluster:** Social-Media-Craft Rules (`universal-sops/social-media-craft/`)
**Master authority:** `universal-sops/social-media-craft/SOCIAL-PIPELINE-MANIFEST.json` + `57-social-media-in-a-box/SOCIAL-MANIFEST.json` + `universal-sops/social-media-craft/MASTER-SOCIAL-QC-AUTOFAIL-RULESET.md`
**Owning department:** social-media (PRIMARY OWNER); shared with marketing / podcast / graphics / crm
**Purpose:** the dept-level index that registers the shared **Social Media in a Box** procedure in the role library and points every consuming seat at the ONE authoritative engine. It does NOT re-implement the engine — the machine spine lives in the skill.

---

## 0. WHY THIS SOP EXISTS

`Social Media in a Box` (Skill 57) is a REUSABLE engine, not a per-role script: five departments drive the client's entire weekly organic social presence through ONE fail-closed front door. This index is the role-library's registered pointer to the shared `universal-sops/social-media-craft/` cluster (so the artifact-coverage gate sees it) and the map from an owner ask to the right SOP + the enforcing gate. Supersedes Skill 35 (`social-media-planner`); per-client retirement is PARKED.

## 1. THE SHARED PROCEDURE (the five-SOP chain)

The authored, cross-department procedure lives in `universal-sops/social-media-craft/`:

| Stage | SOP | What it governs | Owning role |
|---|---|---|---|
| S0 INTAKE | `SOP-SOCIAL-01-INTAKE.md` | Normalize the owner ask (theme / brief / client-exact override / client-copy) into the right slot; never negotiate; never floor/cap a stated number. | content-marketing-strategist |
| S1 RUN | `SOP-SOCIAL-02-RUN.md` | The ONE front door + the mode table; fail-closed preflight; no phase skips; PODCAST_DEFERRED-style graceful skips. | director-of-social-media |
| S2 CREATIVE | `SOP-SOCIAL-03-CREATIVE-INTERJECTION.md` | M1–M4 lanes + I1–I12 injection points; the FORM-vs-CONTENT law; every applied override is logged. | content-marketing-strategist |
| S3 VERIFY | `SOP-SOCIAL-04-VERIFY.md` | Scrub + signed certificate + a LIVE GHL post-listing = the only `done`; advisory voice report triage; de-dup re-post token. | qc-role--social-media |
| S4 ENGAGE | `SOP-SOCIAL-05-ENGAGE-REPORT.md` | Read-only 7-day metrics poll → anomaly report; mints no certificate; never blocks a publish run. | community-manager |

Machine mirror + the full auto-fail table: `SOCIAL-PIPELINE-MANIFEST.json` + `MASTER-SOCIAL-QC-AUTOFAIL-RULESET.md` in the same cluster.

## 2. THE AUTHORITATIVE ENGINE (do not re-implement)

- Single source of truth: `57-social-media-in-a-box/SOCIAL-MANIFEST.json` (the phase machine P0→P8 + fold/creative/defer phases + every `AF-SM-*` code).
- Fail-closed, model-free provers (`57-social-media-in-a-box/scripts/`): `prove_bands.py`, `validate_contract.py`, `preflight_gate.py`, `scrub_gate.py`, `build_manifest.py`, `ledger.py`, `defer_stub.py`.
- Deterministic orchestrator: `run_social_media.py`, front-door-nonce gated by the ONE sanctioned entry `social-media-entry.sh`.
- SACRED bands: `57-social-media-in-a-box/config/bands.json`. Mode map: `57-social-media-in-a-box/modes.md`.
- Weekly-theme cron registrar: `57-social-media-in-a-box/scripts/register-social-cron.sh` (`social-media-weekly-theme`, `0 8 * * 6`).
- Skill self-verify battery: `bash 57-social-media-in-a-box/verify.sh`.

## 3. SACRED LAW (binding)

Enforcement, not description. Provers freeze the FRAME, never the PICTURE. SACRED bands are the DEFAULT floor; a logged client-exact override wins and is recorded on the process certificate (the client gets EXACTLY what they ask for — never floored or capped). Client runtime uses the CLIENT's own provider chain + own GoHighLevel PIT + social accounts — NEVER Anthropic / `claude-*` ids or operator keys, machine-proven per run (`AF-SM-NOANTHROPIC`). There is NO n8n and NO Airtable at runtime. GHL-direct is the only sanctioned posting path; a hand-rolled poster is refused by BYPASS-SCAN (`AF-SM-POST-BYPASS`). `done` is claimed ONLY from the signed certificate PLUS a live GHL post-listing.

## 4. WHERE THE ENGINE IS WIRED (the five insertion-point kinds)

1. A bold `## 8. Tools` row in each consuming role file (10 social-media + 4 marketing + 2 podcast + 2 graphics + 2 crm = 20 seats).
2. The shared `universal-sops/social-media-craft/` SOP cluster (this index registers it in the role library).
3. The `Start Here.md` reusable-engine bullet.
4. The `README.md` skill-inventory row (`57-social-media-in-a-box`) + the `install.sh` universal-sops install + the Skill-57 wiring block (`scripts/wire-social-media.sh`, invoked from `install.sh`) + the active-skill count.
5. The Command Center `sops` row, backed by `57-social-media-in-a-box/cc-compat.json` (`supersedes: 35-social-media-planner`).

## 5. VERIFY THE WIRING

```
bash scripts/verify-social-media.sh                       # all five insertion-point kinds present
bash 57-social-media-in-a-box/verify.sh                    # the skill's own fail-closed battery (ALL GREEN)
python3 57-social-media-in-a-box/scripts/prove_bands.py --self-test
```

A change to any SOP, band, or gate MUST stay in lockstep with `57-social-media-in-a-box/SOCIAL-MANIFEST.json` and the provers (SOP-LOCKED).
