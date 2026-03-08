# EXAMPLES.md

## Example 1 - Install + verify
```bash
brew install steipete/tap/summarize
summarize --help | head
```

## Example 2 - OpenAI first
```bash
set -a
source .env
set +a
export OPENAI_API_KEY="$OPENAI_API_KEY"
summarize "https://youtu.be/dQw4w9WgXcQ" --youtube auto --length short
```

## Example 3 - Gemini fallback
```bash
export GEMINI_API_KEY="$GEMINI_API_KEY"
summarize "https://youtu.be/dQw4w9WgXcQ" --youtube auto --length short
```

## Example 4 - Transcript extraction
```bash
summarize "https://youtu.be/dQw4w9WgXcQ" --youtube auto --extract-only
```
