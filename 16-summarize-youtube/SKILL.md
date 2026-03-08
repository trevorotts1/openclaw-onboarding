---
name: summarize-youtube
description: Install and configure summarize CLI for YouTube transcript extraction and summaries. Use when setting up YouTube transcript and summary capabilities in OpenClaw.
metadata:
  author: Trevor Otts, BlackCEO
  version: "1.0"
  priority: HIGH
---

# Summarize YouTube Setup

This skill installs the summarize CLI and configures it to use API keys from `.env`.

## When to use this skill
- User wants YouTube transcript extraction
- User wants quick summaries from YouTube links
- User asks to install summarize.sh or summarize CLI

## Key execution rule
- Always try `OPENAI_API_KEY` first.
- If OpenAI attempt fails, retry with `GEMINI_API_KEY`.
- Keys must be pulled from `.env`.

## Files in this folder (read order)
1. `SKILL.md`
2. `INSTALL.md`
3. `INSTRUCTIONS.md`
4. `EXAMPLES.md`
5. `CORE_UPDATES.md`
6. `summarize-youtube-full.md`
7. `summarize-youtube.skill`
