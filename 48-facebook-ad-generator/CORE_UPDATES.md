# Skill 48 — Core files this skill may update

This skill is additive. The files it touches outside its own folder, and how:

| File / path | Change | Blast radius |
|---|---|---|
| `universal-sops/fb-ad-craft/` | NEW cluster: manifest + ruleset + SOP-FBAD-01..08 | new dir, additive |
| `23-ai-workforce-blueprint/templates/role-library/paid-advertisement/facebook-instagram-ad-run-producer.md` | NEW role seat | additive |
| `23-ai-workforce-blueprint/templates/role-library/paid-advertisement/direct-response-ad-copywriter.md` | NEW role seat | additive |
| `23-ai-workforce-blueprint/templates/role-library/_index.json` | register the 2 new seats (+ content hashes) | append-only block |
| `23-ai-workforce-blueprint/templates/role-library/paid-advertisement/how-to-use-this-department.md` | REGENERATE (doc-freshness gate) | dept doc |
| `23-ai-workforce-blueprint/templates/suggested-roles/paid-advertisement-suggested-roles.md` | add the 2 seats to the roster menu | append-only |
| `persona-selector-v2.py` `DEPT_DOMAIN_TAGS` | one-line add `"paid-advertisement": ["marketing","copywriting","strategy-innovation"]` | shared picker backstop |
| `.github/workflows/ad-pipeline-lockstep.yml` | NEW path-filtered CI | additive |
| root `install.sh` / `update-skills.sh` | append-only Skill-48 registration block (copied from the Skill 47 block) | shared installer; additive only |
| `cc-compat.json` | bump only IF a newer Command Center is required (the `/api/ad-campaigns` endpoint) | fleet — pauses for approval |

## What it NEVER touches
- The Gemini index / persona blueprints (no new author; proven no-op).
- Operator keys (the skill uses the client's own KIE + GoHighLevel keys only).
- Meta's API (PLAI is the only ad path).
- Any other department's enforcement spine.
