# OPERATOR-LIVE-CHECKLIST — Skill 06 PENDING-LIVE-RUN receipts (P1-11)

Nothing below has been run. Every box is UNCHECKED by design. These steps clear
ONLY the **STILL OWED** half of the STATUS banner in `SKILL.md`; the
**PAID / OFFLINE EVIDENCE** half (gates 1+27 captured, build methods A/B/C
`captured` on the operator fixture, `token_only_auth` PASS, Skill 62 U22
registration wiring + offline build COMPLETE) is already paid for and is not
touched by any step here.

Ground rules for every step:
- Evidence root is `<OPERATOR_HOME>/clawd/skill6-fix/v2-<RUN_ID>/` — never `/tmp`
  (durable receipts only; a receipt under a wiped `/tmp` clears nothing).
- Token-only auth throughout (§2/D7): a fresh Firebase refresh token seed is the
  sole auth path. No UI login, no two-factor, attended or otherwise.
- Never print, paste, or log a token/secret value into any transcript or receipt.
- Fixture: the designated operator test sub-account (BlackCEO LLC
  FIXTURE0LOCATION0000 / BCEO Client Sandbox XCgFTEA1oDvsPnTqqgoB) — NO client data.
- A run clears its item only when the named receipt exists at the named path and
  shows the named PASS. No receipt, no clear.

- [ ] **1. Mint a fresh Firebase refresh token (sole auth blocker).**
      Use the Convert and Flow Token Grabber (Skill 44 operator extension,
      `44-convert-and-flow-operator/tools/chrome-extension/`) to mint a fresh
      refresh token; store it ONLY in the operator env store
      (`~/.openclaw/secrets/.env` as `GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN`,
      `chmod 600`). Never print the value.
      Verify (exit 0 = token present, exit 2 = none — it never echoes the value):
      ```bash
      python3 06-ghl-install-pages/tools/seed-ghl-auth.py --check
      ```
      Expected evidence: the `--check` exit code 0 in this transcript; NO token
      material anywhere in it.

- [ ] **2. One Mac build, Lane 1 (agent-browser via browser_manager).**
      ```bash
      bash 06-ghl-install-pages/tools/browser_manager.sh ensure
      bash 06-ghl-install-pages/tools/browser_manager.sh probe
      python3 06-ghl-install-pages/tools/capability_probe.py
      python3 06-ghl-install-pages/tools/seed-ghl-auth.py --print-seed --out <EVIDENCE_ROOT>/ghl-auth-seed.json
      bash 06-ghl-install-pages/tools/inject-ghl-auth.sh <session-name> <EVIDENCE_ROOT>/ghl-auth-seed.json --pre-open
      ```
      Then drive ONE full build through the bounded dispatcher
      (`python3 06-ghl-install-pages/tools/v2_dispatcher.py --selftest` must pass
      first; the dispatcher — not a free-hand agent loop — runs the build).
      Expected evidence: `<EVIDENCE_ROOT>/working/skill6-capability.json` (probe
      lane 1 healthy) + the build receipt (preview URL curl 200 + marker present
      + draft-not-published) written under `<EVIDENCE_ROOT>/`.

- [ ] **3. One OpenClaw-managed-browser build — IF probe lane 2 is available.**
      Only if the capability probe reports the OpenClaw managed-browser lane
      available (skip and note otherwise; `tools/openclaw_browser_adapter.sh` is
      a parallel-unit landing — do not hand-roll its job). Frame-scoped proof
      that the same build works under the managed browser:
      ```bash
      openclaw browser snapshot --frame "iframe#<builder-frame-id>" --interactive
      ```
      Expected evidence: frame-scoped snapshot/act receipt + an updated
      `<EVIDENCE_ROOT>/working/iframe-map.json` entry recording the frame id and
      epoch for the managed-browser lane.

- [ ] **4. One VPS mount proof (live).**
      ```bash
      bash 06-ghl-install-pages/scripts/vps-mount-proof.sh --live \
        --path <vps-dir-under-proof> --run-id <RUN_ID> \
        --compose-file <path-to-client-compose.yml> \
        --evidence-root <EVIDENCE_ROOT> --box-label <box-name>
      ```
      Expected evidence: `<EVIDENCE_ROOT>/routing/vps-mount-receipt.json` with the
      live mount assertions PASS.

- [ ] **5. ENV ground-truth parity (Mac + VPS).**
      ```bash
      python3 06-ghl-install-pages/tools/ghl_env_matrix_ground_truth.py run --evidence-root <EVIDENCE_ROOT> --box-label <box-name>
      ```
      Run the same command on the VPS box (its own `--box-label`), then compare:
      ```bash
      python3 06-ghl-install-pages/tools/ghl_env_matrix_ground_truth.py compare <EVIDENCE_ROOT>/routing/env-matrix-mac-receipt.json <EVIDENCE_ROOT>/routing/env-matrix-<box>-receipt.json
      ```
      Expected evidence: `<EVIDENCE_ROOT>/routing/env-matrix-ground-truth-receipt.json`
      with parity verdict PASS (or an explicit drift list — that is a finding, not a pass).

- [ ] **6. Full-funnel P4→P5 with Skill 44 token recovery.**
      With the bounded dispatcher, drive the funnel through P4 (build) →
      `qc-built-funnel.sh` (FAB-QC ≥ 8.5) → P5 handoff:
      event `{from_dept: "web-development", to_dept: "crm", artifact:
      "page_ids+form_ids+funnel_template_id+linked_automations", job_id: <RUN_ID>}`.
      If the Skill 44 side stalls on auth, recover with its own Token Grabber
      (per `44-convert-and-flow-operator` INSTALL — token recovery is Skill 44's
      own path, never a Skill 6 login).
      Expected evidence: `<EVIDENCE_ROOT>/routing/skill44-handoff.json` recording
      the handoff event + the FAB-QC score ≥ 8.5 in the build QC receipt.

- [ ] **7. iframe-heavy page proof (cross-origin drag + gates 29-30).**
      ```bash
      python3 06-ghl-install-pages/tools/ghl_iframe_drag.py --live-selftest
      python3 06-ghl-install-pages/tools/ghl_iframe_drag.py smoke_first --session <session-name>
      ```
      Then drive a real `drive_drag` / `drive_frame_click` inside the
      iframe-heavy target listed in
      `06-ghl-install-pages/working/iframe-survival-targets.json`
      (`form` → `iframe[src*="form-builder-v2"]`, `survey` →
      `survey-builder-v2`, `page_code` → page-builder). The
      `tools/iframe_router.py` contract (correct-frame-before-edit,
      refreshed-snapshot-after-panel-open) is the gates 29-30 protocol; its
      module lands via the parallel unit — until then the drag tool's own
      fail-closed behavior (IframeDragError, exit 2) is the guard.
      Expected evidence: drag/click receipts under `<EVIDENCE_ROOT>/` +
      `working/iframe-map.json` updated with `frame_epoch` bumps proving the
      correct frame was targeted before edit and re-snapshotted after panel open.

## Clearing the banner

When items 1-7 ALL hold dated receipts under the durable evidence root, clear
ONLY the **STILL OWED** half of the `SKILL.md` STATUS banner (REST_autosave
wired path, Skill 62 U26 live proof, full-funnel publish E2E). Replace that half
with the receipt citations. The **PAID / OFFLINE EVIDENCE** half stays verbatim.
Any item without its receipt keeps its owed line — a partial sweep clears
nothing wholesale.
