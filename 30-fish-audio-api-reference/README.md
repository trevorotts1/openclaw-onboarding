# Skill 30 - Fish Audio API Reference

**What it does:** Installs the complete Fish Audio API reference into your master files and indexes it with Gemini Engine so your agent knows exactly how to make Fish Audio API calls - podcasts, phone calls, voice generation, and more.

**Standalone:** Yes. This skill is self-contained.
**Required by:** (none)

**Start here:** Read `INSTALL.md` and follow every step in order.

**Full reference:** `SKILL.md` covers TYP instructions, standard curl templates, emotion tags, and long-form content splitting.

**API docs:** `references/fish-audio-api-reference.md` (all endpoints)

**Model default:** `drama-3` (PAID) is the client/production default, with `s2.1-pro` permitted only as an explicit client/operator selection, without automatic fallback. The free `s2.1-pro-free` tier is operator-internal dev/prototyping ONLY — no SLA, data-retention risk, a $1M ARR commercial restriction, and it expires end of July 2026. Never use it for client production. See SKILL.md "Model Selection: Paid vs Free" and `references/fish-audio-api-reference.md` for full detail and sources.

**Client voice:** configuration QC and the production helper require a company-bound approval fingerprint, supplied independently of the active voice setting. See [client voice approval](references/client-voice-approval.md). Existing installations remain pending until that record is provided. No client record is bundled.
