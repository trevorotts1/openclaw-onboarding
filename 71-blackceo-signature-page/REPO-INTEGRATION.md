# Repository Integration — Skill 71 BlackCEO Signature Page

This file is written for the OpenClaw/onboarding-repo agent that receives this folder.

## 1. Canonical folder and number

Install this folder as:

`71-blackceo-signature-page/`

The current repository numbering reaches Skill 70 (`70-lean-core-file-system`, v1.0.0), so this capability is Skill 71.

## 2. Native skill binding

The onboarding repo's source of truth is:

`23-ai-workforce-blueprint/skill-department-map.json`

Add the object in `repo-integration/skill-department-map-entry.json` to `skills[]`.

Primary owner:

- department: `web-development`
- role: `landing-page-specialist`

Do not create a new department or a duplicate landing-page role.

## 3. Craft SOP cluster

Copy `repo-integration/universal-sops/signature-page-craft/README.md` to:

`universal-sops/signature-page-craft/README.md`

The cluster is a pointer/playbook. The detailed BlackCEO methodology remains inside Skill 71 references; do not duplicate hundreds of pages into universal-sops.

## 4. Refresh Layer B from the map

From `23-ai-workforce-blueprint/` run the canonical Scenario-E sequence:

```bash
python3 scripts/check-skill-department-map.py
python3 scripts/stamp-skills-you-operate.py
python3 scripts/hash-content-manifest.py
python3 scripts/qc-assert-repo-consistency.py
```

The stamper updates the Landing Page Specialist's marker-guarded `Skills You Operate` block. Do not hand-edit that generated block.

Because `web-development` already owns client-facing skills and already participates in the routing reflex, do not add a new department reflex merely for Skill 71 unless the current repo gate proves one is actually missing.

## 5. Landing Page Specialist SOP

Outside the generated `Skills You Operate` block, update the Web Development Landing Page Specialist's page-build SOP so that a landing-page assignment first resolves the native page methodology before building:

- BlackCEO single-page request -> Skill 71
- multi-step Signature Funnel -> Skill 49
- Direct-Response/VSL stack -> Skill 56
- cinematic scroll/animated page -> Skill 62

Use the ready insert in `repo-integration/landing-page-specialist-sop-insert.md` and adapt placement to the current role file without deleting existing duties.

## 6. Remove routing collision with Skill 49

Skill 49 is the multi-step Signature Funnel engine. Its current map/selector language includes generic `build me a landing page` / `signature landing page` phrases that overlap Skill 71.

After Skill 71 lands:

- move generic single-page BlackCEO landing-page intent to Skill 71;
- preserve Skill 49 triggers for multi-step Signature Funnel / 3-5-7 / checkout / upsell / downsell / OTO intent;
- preserve Skill 56 for Direct-Response/VSL/high-ticket/bump;
- preserve Skill 62 for animated/cinematic/scroll experiences.

The ready intent changes are documented in `repo-integration/routing-boundary.md`.

## 7. GHL and image execution

Do not fork existing execution rails:

- Skill 71 authors/plans the single page.
- Kie image execution -> Skill 66.
- Agnes image execution -> Skill 63 when selected.
- GHL build/media -> Skill 6.
- Vercel prerequisite/deploy -> Skill 8 when selected.

## 8. Verification

Run Skill 71's local maintenance verifier once:

```bash
bash 71-blackceo-signature-page/verify.sh
```

Then run the repository gates used by Scenario E and the frontmatter-version guard:

```bash
python3 23-ai-workforce-blueprint/scripts/check-skill-department-map.py
python3 23-ai-workforce-blueprint/scripts/stamp-skills-you-operate.py
python3 23-ai-workforce-blueprint/scripts/hash-content-manifest.py
python3 23-ai-workforce-blueprint/scripts/qc-assert-repo-consistency.py
bash scripts/qc-assert-skill-frontmatter-version.sh
```

Use the repo's normal CI/gates after the actual merge. Do not invent a parallel installation/test framework.
