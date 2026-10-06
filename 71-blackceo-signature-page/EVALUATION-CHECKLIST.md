# Phase 1 Evaluation Checklist

Mark each item PASS, FAIL, or BLOCKED and include evidence.

## Discovery and loading

- Runtime discovers `blackceo-signature-page`.
- `SKILL.md` triggers for BlackCEO Signature page requests.
- Large references load on demand rather than all at once.
- Asset paths resolve, including the Master Visual Reference Guide.

## Methodology preservation

- Standard and Long-Form remain separate selectable copy systems.
- Production stage order is preserved.
- Private/public separation is preserved.
- Failed work cannot advance.
- Passing work is not repeatedly rewritten.
- Failed work gets at most three focused repair attempts.
- One page uses one external Creative Direction family/style or Secret-Sauce-only.
- Secret Sauce adapts around conflicts instead of overwriting the selected style.
- Image prompts follow the KIE prompt budget (95 to 100 percent of the model maximum, never below 80 percent; `kie-common-rules.md` rule 12), checked with Skill 74 `prompt-budget --check`.

## Scripts

- `validate_state.py` accepts the valid fixture and rejects the invalid fixture.
- `validate_prompt.py` accepts the valid fixture and rejects the too-short fixture.
- `validate_image_manifest.py` accepts the valid fixture and rejects duplicate IDs/filenames.
- `validate_public_copy.py` rejects definite private-label leakage.
- `combine_review_pdf.py` builds a multi-page PDF in manifest order.
- `validate_review_pdf.py` confirms expected page count and manifest order.
- `install_local.py --dry-run` does not overwrite existing content.

## Live integrations

Evaluate only integrations actually configured in this runtime. A missing connector is BLOCKED, not FAIL, unless the runtime claims it should be present.

- Kie.ai / selected image engine can be reached if configured.
- GHL can be reached if configured.
- Browser/computer control works if required and configured.
- GitHub/Vercel work if required and configured.

## Required report

Return:

- runtime and version;
- skill discovery path;
- PASS/FAIL/BLOCKED checklist;
- exact compatibility changes made;
- files changed;
- tests run and results;
- unresolved blockers;
- confirmation that BlackCEO methodology was not intentionally changed.
