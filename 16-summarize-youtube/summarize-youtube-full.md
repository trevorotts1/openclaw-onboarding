# summarize-youtube-full.md

## Objective
Install summarize CLI and make YouTube transcript + summary available in OpenClaw onboarding.

## Required behavior
1. Read keys from `.env`.
2. Try OpenAI first.
3. If OpenAI fails, retry with Gemini.
4. If both fail, stop and return exact command and error.

## Execution block
```bash
set -e
brew --version || /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
brew install steipete/tap/summarize
summarize --help >/dev/null

set -a
source .env
set +a

test -n "$OPENAI_API_KEY"
test -n "$GEMINI_API_KEY"

# OpenAI first
summarize "https://youtu.be/dQw4w9WgXcQ" --youtube auto --length short || # Gemini fallback
summarize "https://youtu.be/dQw4w9WgXcQ" --youtube auto --length short

summarize "https://youtu.be/dQw4w9WgXcQ" --youtube auto --extract-only
```

## Post-install updates
Use `CORE_UPDATES.md` snippets for AGENTS.md, TOOLS.md, MEMORY.md.
