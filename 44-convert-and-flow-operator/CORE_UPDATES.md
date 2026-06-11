# Skill 44 — Convert and Flow Operator: Core File Updates

Update ONLY the files listed below. Use the EXACT text provided.
Do not update files marked NO UPDATE NEEDED.

Sentinel: <!-- skill:44-convert-and-flow-operator:core-update-applied -->

---

## AGENTS.md — UPDATE REQUIRED

Add this section:

```
## Convert and Flow Operator — Tier 0 (skill 44)

Skill 44 is the FIRST STOP in the 6-tier GHL access chain. Try it before any MCP.

### When to use Tier 0

- Any GHL operation the CLI covers (contacts, opportunities, calendars, conversations,
  documents, payments, forms, social, locations, workflow reads): use `caf <command>`.
- Workflow BUILD or EDIT: check Firebase token first (see token-aware routing in skill 36
  AGENTS.md). Present + healthy = Tier 0 builds directly. Absent = Tier 4 backstop.
- Media upload: SKIP Tier 0. Always Tier 3 (POST /medias/upload-file).
- Rate limit (429): STOP. Never fall through. Surface reset time in plain English.

### Per-operation routing

See the full 6-tier table in skill 36's AGENTS.md block. Skill 44 owns Tier 0;
skill 36 owns the routing law for all 6 tiers.

### Disclosure format

[GHL tier used: 0 — convertandflow <command>]
```

---

## TOOLS.md — UPDATE REQUIRED

Add this section:

```
## Convert and Flow CLI — Tier 0 GHL operator (skill 44)

Commands: caf / convertandflow / ghl

Installed at: ~/.openclaw/tools/convert-and-flow-cli/caf (Mac) or /data/.openclaw/tools/convert-and-flow-cli/caf (VPS)
Health: caf doctor

| Domain | Commands |
|---|---|
| contacts | caf contacts list/get/create/update/tag/untag |
| opportunities | caf opportunities list/get/update |
| calendars | caf calendars list/appointments |
| conversations | caf conversations list/get/send |
| documents | caf documents list/get/send |
| payments | caf payments invoices list/create/send; transactions list |
| forms | caf forms list/submissions |
| social | caf social accounts/post/schedule |
| locations | caf locations get/customfields/customvalues |
| workflows (read) | caf workflows list/get/export |
| workflows (write) | caf workflows build/patch-email/patch-trigger/restore [Firebase token required] |

Credentials: GOHIGHLEVEL_API_KEY (PIT), GOHIGHLEVEL_LOCATION_ID, GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN (workflow writes only).
```

---

## MEMORY.md — UPDATE REQUIRED

```
## Convert and Flow Operator — Installed [DATE]

Skill 44 (Tier 0) installed. CLI at ~/.openclaw/tools/convert-and-flow-cli/.
Credentials: GOHIGHLEVEL_API_KEY (PIT), GOHIGHLEVEL_LOCATION_ID.
Firebase token for workflow writes: GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN (optional at install).
Write safety: GOHIGHLEVEL_DRAFT_ONLY=true, location whitelist, approval gate.
Health: caf doctor
```

---

## SOUL.md — NO UPDATE NEEDED

---

## IDENTITY.md — NO UPDATE NEEDED

---

## HEARTBEAT.md — NO UPDATE NEEDED

---

## USER.md — NO UPDATE NEEDED
