## 🔴🔴🔴 GOOGLE WORKSPACE - FINAL FIX (Feb 28, 2026 - PERMANENT - DO NOT OVERRIDE)

> **Full guide:** See `~/Downloads/openclaw-master-files/OpenClaw Onboarding/13-google-workspace-integration/`

**Trevor gave me a full Google Workspace setup guide. I never implemented Section 14. That's why I kept failing.**

**THE TOOL: `google-api.js` in ~/clawd/**
- Zero dependencies (Node.js builtins only: crypto, https, fs)
- Replaces ALL GOG CLI usage for @blackceo.com accounts
- Built Feb 28, 2026 from Trevor's guide (Section 11-13)

**ENV VARS (set in ~/.zshrc AND current session):**
```
GOOGLE_SA_KEY_FILE="/Users/blackceomacmini/Library/Application Support/gogcli/sa-dHJldm9yQGJsYWNrY2VvLmNvbQ.json"
GOOGLE_IMPERSONATE_USER="trevor@blackceo.com"
```

**HOW TO USE IT:**
```bash
node ~/clawd/google-api.js gmail unread --limit 10 --pretty
node ~/clawd/google-api.js calendar today --pretty
node ~/clawd/google-api.js docs read <docId> --pretty
node ~/clawd/google-api.js drive list --limit 10 --pretty
node ~/clawd/google-api.js docs list --pretty
```

**ACCOUNT ROUTING - MEMORIZE:**
| Account | Tool | Example |
|---------|------|---------|
| @blackceo.com | `node ~/clawd/google-api.js` | trevor@blackceo.com |
| @gmail.com | `gog` CLI | trevelynotts@gmail.com |

**IF I GET A 401 USING google-api.js:**
1. Check: are the env vars set? `echo $GOOGLE_SA_KEY_FILE`
2. Check: is the SA key file readable? `cat "$GOOGLE_SA_KEY_FILE" | head -1`
3. Export both vars and retry. That's it.

**BROWSER IS BANNED. GOG IS BANNED FOR @blackceo.com. PERIOD.**
