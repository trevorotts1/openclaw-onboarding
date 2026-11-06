# Skill 85 — Android SMS System

Answers myCRMSIM (CRM SIM) support questions from its 156-article offline documentation set: Android SMS gateway setup, SIM assignment, SMS/iMessage/WhatsApp/RCS, calling, CRM integrations and troubleshooting.

Optional — install only where myCRMSIM is used; it does nothing on boxes that do not run myCRMSIM.

The documentation set is NOT vendored here. Fetch the 156-article `mycrmsim` set on each box and place it at `docs/` beside `SKILL.md`, or set `ASMS_DOCS_DIR` to it. Images are intentionally absent; the skill runs text-only.

Install (from the onboarding repo root):

```bash
cp -R skills/85-android-sms-system ~/.openclaw/skills/
```

Verify: `bash ~/.openclaw/skills/85-android-sms-system/qc-android-sms-system.sh`
