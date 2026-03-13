# Google Workspace Setup - Core File Updates

Update ONLY the files listed below. Use the EXACT text provided.
Do not update files marked NO UPDATE NEEDED.

---

## AGENTS.md - UPDATE REQUIRED

Add:

```
## Google Workspace Setup [PRIORITY: CRITICAL]
- Service account: configured via Google Cloud Console
- Domain-wide delegation: MANDATORY for workspace email access
- Full guide: [MASTER_FILES_FOLDER]/OpenClaw Onboarding/13-google-workspace-setup/google-workspace-setup-full.md
```

---

## TOOLS.md - UPDATE REQUIRED

Add:

```
## Google Workspace API Setup
- Google Cloud Console: https://console.cloud.google.com/
- APIs to enable: Gmail, Calendar, Drive, Docs, Sheets, People
- Service account with domain-wide delegation required
- Full guide: [MASTER_FILES_FOLDER]/OpenClaw Onboarding/13-google-workspace-setup/google-workspace-setup-full.md
```

---

## MEMORY.md - UPDATE REQUIRED

Add:

```
## Google Workspace Setup - Installed [DATE]
- Google Cloud project created, APIs enabled
- Service account with domain-wide delegation configured
- Full guide: [MASTER_FILES_FOLDER]/OpenClaw Onboarding/13-google-workspace-setup/google-workspace-setup-full.md
```

---

## IDENTITY.md - NO UPDATE NEEDED

---

## HEARTBEAT.md - NO UPDATE NEEDED

---

## USER.md - NO UPDATE NEEDED

---

## SOUL.md - NO UPDATE NEEDED

## ADDITIONAL DETECTION INTELLIGENCE

[ADD TO AGENTS.md]
Preflight: Detect existing GOG or Google Workspace setup for the target account before running this skill. If detected, ask the user: "We've already detected that this has already been set up for you. Did you want to add an additional Gmail account or Google Workspace account?" If user answers yes, run the Add-Account flow in this skill. If no, mark this skill skipped and proceed to the next skill.

[ADD TO TOOLS.md]
How to detect existing Google setup: 1) Look for GOG config or service account JSON in expected paths (for example, ~/.gogcli/, ~/clawd/secrets/, ~/Downloads/*.json). 2) Check auth state with `gog auth list` and existing env values like GOG_DEFAULT_ACCOUNT or GCP_IMPERSONATE_USER. 3) For Workspace, attempt a minimal API call with stored service account credentials to verify access. Return a boolean setup_present and the detected email when possible.

[ADD TO MEMORY.md]
When Google setup detection runs, record: {type: 'google-setup-detection', email: '<detected-email-or-null>', method: 'gog|service-account|api-check', user_choice: 'add|skip', timestamp: '<human-readable date>'}.

