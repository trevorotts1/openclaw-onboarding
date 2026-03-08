
## 🔴 API-ONLY EXECUTION LOCK (SOVEREIGN)
- For this onboarding package, do NOT use service CLIs for GitHub, Vercel, or Context7.
- Do NOT use `gh`, `vercel`, or any Context7 CLI command for setup/auth.
- Use API-driven setup and browser-based account/token creation flows only.
- The only onboarding skill allowed to rely on CLI-specific service commands is Superdesign.

# Vercel Setup - Core File Updates

Update ONLY the files listed below. Use the EXACT text provided.
Do not update files marked NO UPDATE NEEDED.

---

## AGENTS.md - UPDATE REQUIRED

Add:

```
## Vercel Deployment [PRIORITY: STANDARD]
- CLI: vercel (installed globally via npm)
- Deploy preview: vercel
- Deploy production: vercel --prod
- Full guide: [MASTER_FILES_FOLDER]/OpenClaw Onboarding/08-vercel-setup/vercel-setup-full.md
```

---

## TOOLS.md - UPDATE REQUIRED

Add:

```
## Vercel CLI & API
- Install: npm i -g vercel
- Auth: vercel login
- Commands: vercel (preview), vercel --prod (production), vercel ls (list), vercel env (manage env vars)
- Full guide: [MASTER_FILES_FOLDER]/OpenClaw Onboarding/08-vercel-setup/vercel-setup-full.md
```

---

## MEMORY.md - UPDATE REQUIRED

Add:

```
## Vercel Setup - Installed [DATE]
- CLI installed, authenticated
- Full guide: [MASTER_FILES_FOLDER]/OpenClaw Onboarding/08-vercel-setup/vercel-setup-full.md
```

---

## IDENTITY.md - NO UPDATE NEEDED

---

## HEARTBEAT.md - NO UPDATE NEEDED

---

## USER.md - NO UPDATE NEEDED

---

## SOUL.md - NO UPDATE NEEDED
