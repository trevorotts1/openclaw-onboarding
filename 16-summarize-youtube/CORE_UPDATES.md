# CORE_UPDATES.md

## AGENTS.md snippet
## Summarize Skill (YouTube Transcript + Summary)
- Installed summarize via Homebrew (`steipete/tap/summarize`)
- Pull keys from `.env`
- Try `OPENAI_API_KEY` first, fallback to `GEMINI_API_KEY`
- Summary: `summarize "https://youtube.com/watch?v=VIDEO_ID" --youtube auto`
- Transcript: `summarize "https://youtube.com/watch?v=VIDEO_ID" --youtube auto --extract-only`

## TOOLS.md snippet
## summarize CLI
- Install: `brew install steipete/tap/summarize`
- Summary: `summarize "https://youtu.be/VIDEO_ID" --youtube auto`
- Transcript: `summarize "https://youtu.be/VIDEO_ID" --youtube auto --extract-only`
- Key order: OpenAI first, Gemini fallback

## MEMORY.md snippet
## Installed: summarize tool
- Installed summarize and verified help output
- Loaded keys from `.env`
- OpenAI-first test executed
- Gemini fallback available
- Transcript extraction test executed
