# INSTALL.md - Agent Browser (Vercel)

## Goal

Ensure `agent-browser` is installed and available as the primary browser automation tool.

## Step 4 - Smoke test a simple browser session

Run:
```bash
agent-browser open https://example.com
agent-browser snapshot -i
agent-browser close
```

If the snapshot shows interactive elements with refs like `@e1`, `@e2`, installation is good.
