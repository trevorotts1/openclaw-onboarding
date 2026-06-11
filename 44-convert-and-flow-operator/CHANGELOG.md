# Changelog — convert-and-flow-operator (Skill 44)

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
