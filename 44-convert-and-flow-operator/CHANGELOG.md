# Changelog — convert-and-flow-operator (Skill 44)

## [1.0.1] - 2026-06-11 — Chrome extension: switch to load-unpacked (no Chrome Web Store)

### Changed
- Chrome extension delivery method: NOT publishing to the Chrome Web Store.
  Clients load the extension unpacked via chrome://extensions → Developer mode ON →
  "Load unpacked" → select tools/chrome-extension/.
- INSTALL.md: added Action 5b with full load-unpacked steps (get folder, install,
  grab token, store as GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN, reload after edits).
- SKILL.md: added "Chrome Extension: Token Grabber" section documenting the no-web-store
  decision, what the extension does (zero network calls, IndexedDB reader), and the
  tools/chrome-extension/ file manifest.
- tools/chrome-extension/: added as top-level client-facing copy of the extension
  (manifest.json, popup.html, popup.js, icon48.png — identical to the zip the operator
  ships). Skill is now self-contained.

## [1.0.0] - 2026-06-10 — Initial release

### Added
- Full Tier 0 GHL operator: caf/convertandflow/ghl CLI wrapper over the de-branded
  Convert and Flow engine (Jay's zip, stripped of Nextcloud/Blotato, de-branded builders,
  Chrome extension rebranded, UNIVERSAL templates).
- Token-aware routing: PIT for standard ops; Firebase refresh token for workflow writes;
  graceful fall-through to Tier 4 when Firebase token absent.
- Write-safety posture: dry-run, draft-only default (GOHIGHLEVEL_DRAFT_ONLY=true),
  location whitelist, approval gate, ZHC- standing approval.
- Workflow-write data rollback: pre-write snapshot before every mutation; `workflows restore`.
- TRINITY gate: any conversational workflow build auto-invokes skill 38; qc-convert-and-flow.sh
  calls qc-trinity-registry.sh as a hard gate.
- Dependency-first contract from skill 41: refuses to build if dependencies don't exist.
- Engine vendored at tools/engine/ (from skill44-build/engine).
- Platform overlays: platform/mac/ (venv at ~/.openclaw/tools/..., auto-re-grab recipe) +
  platform/vps/ (venv at /data/.openclaw/tools/..., owner-nudge on expired token).
- Client-facing plain-language auto-re-grab disclosure in INSTALL.md (binding transparency).
- qc-convert-and-flow.sh with assertions for all acceptance criteria.
