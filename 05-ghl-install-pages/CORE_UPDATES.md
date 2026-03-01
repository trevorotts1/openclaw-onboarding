# GHL / Convert and Flow - Install Pages - Core File Updates

Update ONLY the files listed below. Use the EXACT text provided.
Do not update files marked NO UPDATE NEEDED.

---

## AGENTS.md - UPDATE REQUIRED

Add:

```
## GHL Page Deployment [PRIORITY: HIGH]
- Full guide: [MASTER_FILES_FOLDER]/OpenClaw Onboarding/05-ghl-install-pages/ghl-install-pages-full.md
- Use Playwright with launchPersistentContext (NEVER launch())
- Always verify correct sub-account before building
- Credentials: ~/clawd/secrets/.env (GHL_EMAIL, GHL_PASSWORD)
```

---

## TOOLS.md - UPDATE REQUIRED

Add:

```
## GHL Page Builder (Playwright Automation)
- Full guide: [MASTER_FILES_FOLDER]/OpenClaw Onboarding/05-ghl-install-pages/ghl-install-pages-full.md
- Viewport minimum: 1440x900
- Builder loads inside nested iframes - use get_builder_frame()
- Default to Funnels over Websites
- Generate deployment report after every deployment
```

---

## MEMORY.md - UPDATE REQUIRED

Add:

```
## GHL Page Deployment Skill - Installed [DATE]
- Full guide: [MASTER_FILES_FOLDER]/OpenClaw Onboarding/05-ghl-install-pages/ghl-install-pages-full.md
- Covers: funnel creation, multi-page deploy, existing page updates, iframe method
- Sub-account switching, credential storage, deployment reporting documented
```

---

## IDENTITY.md - NO UPDATE NEEDED

---

## HEARTBEAT.md - NO UPDATE NEEDED

---

## USER.md - NO UPDATE NEEDED

---

## SOUL.md - NO UPDATE NEEDED
