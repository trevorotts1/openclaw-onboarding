# Deprecated `suggested-roles` Files (v2.1 cleanup)

These files were part of pre-v2.1 department structure. As of v2.1 (Zero-Human Company Spec), the following responsibilities have moved:

| Deprecated file | Replaced by |
|---|---|
| `creative-suggested-roles.md` | Folded into **Graphics**, **Video**, and **Audio** departments. The Creative Director role no longer exists as a standalone — each medium has its own director. |
| `hr-people-suggested-roles.md` | **Removed.** A zero-human company has no human employees to manage. Performance tracking of AI roles is handled by the v2.0 Ch 11 Learning Loop. |
| `it-tech-suggested-roles.md` | **Replaced by OpenClaw Maintenance department** (`openclaw-maintenance-suggested-roles.md`). Where IT-Tech historically covered general technology, OpenClaw Maintenance is the more accurate description for a zero-human company: the system IS OpenClaw. |
| `operations-suggested-roles.md` | **Distributed.** Operations responsibilities are embedded inside each department's procedures rather than aggregated as a standalone team. |

## Why preserve them at all?

For existing client workspaces built with v9.x or earlier, the OpenClaw system may still reference these by name during audits (Option C — Audit / Resume Mode). Keeping them under `_deprecated/` means audits don't fail, but new builds use the v2.1 mandatory list from `department-naming-map.json`.

## Don't reference these in new INSTRUCTIONS.md flows.

If you're working in Skill 23 v10.4.0 or later, use:
- `crm-suggested-roles.md`
- `openclaw-maintenance-suggested-roles.md`
- `social-media-suggested-roles.md`
- `paid-advertisement-suggested-roles.md`

…instead of any of the deprecated files in this folder.
