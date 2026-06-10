# GHL Tag Setup Checklist — Skill 39 (template)

Copy this checklist into the operator's onboarding doc. Create each tag in GHL
**Settings → Tags FIRST**, before any workflow filters on it. A blank or
non-existent tag inside a "does not contain" filter is a known GHL gotcha that
silently strands contacts.

- [ ] `ZHC-buyer-lead` — buyer intent detected (timeline/financing/area/must-haves)
- [ ] `ZHC-seller-lead` — seller intent detected (motivation/timeline/price/occupancy)
- [ ] `ZHC-investor-lead` — investor signal (cap rate, doors, BRRRR, "as an investment")
- [ ] `ZHC-pre-foreclosure-prospect` — distressed homeowner sourced via Skill 40 (NOD / tax delinquency)

After the tags exist, run:

```bash
scripts/04-update-agents-md.sh              # wire the RE playbook into AGENTS.md
scripts/05-install-sales-brain-extension.sh # additive Sales-Brain RE overlay
```

This template ships ZERO client data — it is a universal checklist.
