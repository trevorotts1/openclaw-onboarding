# OpenRouter Setup - Core File Updates

Update ONLY the files listed below. Use the EXACT text provided.
Do not update files marked NO UPDATE NEEDED.

---

## AGENTS.md - UPDATE REQUIRED

Add:

```
## OpenRouter Model Routing [PRIORITY: CRITICAL]
- Before any task, evaluate: What kind of work is this? Which of the client's chosen models fits it best, or the client's configured default model? What thinking level?
- Route each task to the client's choice for that kind of work. Never route a tool-call task to a model that does not support tool calls.
- Recommendation: match the model to the task (a large context window for long documents, reliable tool calling for tool-heavy work, strong reasoning for planning and QC), because capability fit gives better results at lower cost. A recommendation is guidance only; the client's selection always wins.
- ALWAYS back up config before adding/changing models
- Full guide: [MASTER_FILES_FOLDER]/OpenClaw Onboarding/12-openrouter-setup/openrouter-setup-full.md
```

---

## TOOLS.md - UPDATE REQUIRED

Add:

```
## OpenRouter [PRIORITY: CRITICAL]
- Config: ~/.openclaw/openclaw.json (models section)
- API key: OPENROUTER_API_KEY in secrets/.env
- Model aliases: /model <alias> to switch
- Thinking: /reasoning <low|medium|high>
- Full model matrix and routing guide: [MASTER_FILES_FOLDER]/OpenClaw Onboarding/12-openrouter-setup/openrouter-setup-full.md
```

---

## MEMORY.md - UPDATE REQUIRED

Add:

```
## OpenRouter Setup - Installed [DATE]
- 200+ models available through single API
- Model routing guide with cost/capability matrix
- Full guide: [MASTER_FILES_FOLDER]/OpenClaw Onboarding/12-openrouter-setup/openrouter-setup-full.md
```

---

## IDENTITY.md - NO UPDATE NEEDED

---

## HEARTBEAT.md - NO UPDATE NEEDED

---

## USER.md - NO UPDATE NEEDED

---

## SOUL.md - NO UPDATE NEEDED
