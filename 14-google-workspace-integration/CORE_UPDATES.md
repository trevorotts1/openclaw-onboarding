# Google Workspace Integration - Core File Updates

Update ONLY the files listed below. Use the EXACT text provided.
Do not update files marked NO UPDATE NEEDED.

---

## AGENTS.md - UPDATE REQUIRED

Add:

```
## Google Workspace Integration [PRIORITY: CRITICAL]
- @gmail.com = GOG CLI (OAuth). @workspace.com = Service Account + Impersonation.
- NEVER mix these methods. They are incompatible.
- Playwright uses launchPersistentContext (NEVER launch())
- 70 OAuth scopes configured
- Full guide: ~/Downloads/openclaw-master-files/OpenClaw Onboarding/14-google-workspace-integration/google-workspace-integration-full.md
```

---

## TOOLS.md - UPDATE REQUIRED

Add:

```
## Google Workspace Integration [PRIORITY: CRITICAL]
- SA key location: configured during setup
- Impersonation: use the primary admin email for your domain
- GOG CLI: for personal @gmail.com accounts only
- Places API: uses API Key, NOT service account
- Full guide: ~/Downloads/openclaw-master-files/OpenClaw Onboarding/14-google-workspace-integration/google-workspace-integration-full.md
```

---

## MEMORY.md - UPDATE REQUIRED

Add:

```
## Google Workspace Integration - Installed [DATE]
- Two paths: Workspace = service account + DWD; Gmail = GOG CLI OAuth
- 70 OAuth scopes configured (Workspace path)
- Full guide: ~/Downloads/openclaw-master-files/OpenClaw Onboarding/14-google-workspace-integration/google-workspace-integration-full.md
```

---

## IDENTITY.md - NO UPDATE NEEDED

---

## HEARTBEAT.md - NO UPDATE NEEDED

---

## USER.md - NO UPDATE NEEDED

---

## SOUL.md - NO UPDATE NEEDED
