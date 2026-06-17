# NAMED STYLES - {client_slug}
# Per-client alias map: plain-English name -> card ID @ pinned version + frozen refs + overrides.
# Authority: SOP-DIU-607. Owner: Style Analyst. This file lives in _local/ and is NEVER repo-committed (client data).
# Created from templates/NAMED-STYLES.md. One YAML block per approved, named style.
#
# SEED TEMPLATE. Closes design-library GAP e (the missing NAMED-STYLES seed referenced by SOP-DIU-607 step A.5
# and SOP-IMG-03 section 4). Copy this file to $OC_ROOT/master-files/design-library/_local/NAMED-STYLES.md
# on first use. A fresh client box has zero aliases below, which is correct (no styles saved yet).

named_styles_version: 1.0
client_slug: "{client_slug}"
generated_at: "{ISO_8601}"

aliases:
  # --- one block per named style; appended at client-approval time per SOP-DIU-607 section A ---
  # - alias: "Signature Style 1"        # plain-English, unique per client, verbatim from the approval record
  #   card_id: "PPT-002-C"              # resolves in INDEX.md; must be production status
  #   card_version: "v1.0"             # pinned; v1.x auto-advances, v2.0 needs CDO confirm + regression render
  #   frozen_refs:
  #     - "/abs/path/to/approved-output.png"   # ground truth for v2.0 regression checks
  #   brand_overrides:                  # only fields where this client diverges from card defaults; empty if none
  #     # BRAND_COLOR_1: "#1A1A2E"
  #   captured_at: "{ISO_8601}"
  #   captured_from_receipt: "{receipt filename}"
