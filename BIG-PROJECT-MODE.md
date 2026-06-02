# BIG PROJECT MODE

**Trigger:** the owner says "big project mode" — or hands the agent a large,
multi-part build or document with many deliverables (a manual, a course, a
multi-chapter report, a batch of dozens of pages/SOPs/assets).

**Audience:** the orchestrating agent. This is an operating standard, not a
client feature. It applies to every managed agent regardless of business,
model, or routing.

---

## WHY THIS EXISTS

On per-token models that support prompt caching, structuring fleet work
correctly cuts **input cost 80-95%** and finishes faster:

- **DeepSeek direct** — cache hits bill at roughly **1/120th** of a miss.
- **Anthropic** and **OpenAI** — large cache-read discounts on the cached prefix.

On flat-rate routes (e.g. **Ollama Cloud**) there is no per-token bill, but the
same structure still wins: it runs faster, triggers fewer timeouts, and produces
cleaner QC. So Big Project Mode is correct on **every** route — it is never wrong
to use it.

The whole game is: send the big shared block **once, byte-identical, at the
front of every worker**, and let the cache (or just clean structure) carry it.

---

## THE NINE RULES

### RULE 0 — THE ECHO-BACK GATE
Before executing ANY big-project mission, the orchestrator must reply to the
owner **FIRST** with:
**(a)** every execution rule restated in its own words, one line each;
**(b)** the full work-slice list;
**(c)** the EXACT model strings it will use for writers and QC.

It does **NOT** spawn anything until the owner replies **GO**.

**Why each element:** paraphrasing the rules is a comprehension test — parroting
back the words without understanding breaks on the first edge case; restating in
your own words proves you understood. Exact model strings let the owner verify
character-by-character — "deepseek-chat" vs "deepseek-coder" is a silent wrong
turn caught when it costs one message, not a failed run. The work-slice list
makes scope visible before any resources are committed. And the echoed plan
becomes a standing contract in-context for the whole run — the orchestrator
cannot silently drift from it mid-project.

**If the orchestrator believes a different model, route, or approach would be
better — it does not decide that. It asks.**

### RULE 1 — ORCHESTRATOR PASTES; OWNERS SEND FILES
The owner sends the project document as a **file** (a Telegram attachment is
fine). The orchestrator reads it **once** and embeds the **FULL TEXT,
word-for-word**, at the **top** of every worker sub-agent's birth instructions.
Never tell workers "read the file yourself" — that is one full-price read **per
agent** instead of one read **per fleet**.

### RULE 2 — IDENTICAL BYTES FIRST, UNIQUE ASSIGNMENT LAST
Every spawn = **[shared document, byte-identical]** + **[that worker's
assignment at the very bottom]**. Never paraphrase or summarize the shared
block; never put the assignment first. **One changed character at the front
re-prices everything behind it** (the cache prefix breaks).

### RULE 3 — WARM-UP THEN FLEET
Spawn **one** worker first and let it finish — this **warms the cache**. Then
launch the rest in batches. Firing all workers at once before the prefix is
cached means every worker pays the full miss price.

### RULE 4 — WORKERS LIVE SHORT
Every assignment ends with: *"everything you need is above — do not read other
files; write your deliverable, save it, return a one-line status."* Workers that
**forage** (read extra files, explore the repo) live long and cost **20-50x**.

### RULE 5 — SKINNY ORCHESTRATOR
Track progress in a **ledger file on disk**. Deliverables go **to disk**. Only
**one-line statuses** flow back through the orchestrator conversation. Nothing
bulky ever lives in the orchestrator transcript — a fat transcript re-prices on
every turn.

### RULE 6 — INDEPENDENT QC, REAL SCORES
QC runs on a **different model** than the writers, scores **0-10 against a
rubric**, gates at **>= 8.5**, and **defect-loops on fails (max 3)**. Numeric
scores are recorded — never free-text "PASS" stamps.

### RULE 7 — NO WORKER DIES SILENTLY
Use the **ledger + a watchdog**. Restart a dead worker **once** as a fresh
worker, then **flag** it. The completion gate counts **delivered files on
disk**, not hopes.

### RULE 8 — TOKENS ONLY IN TEMPLATE/MASTER CONTENT
In any template or master content the build produces, use **placeholder tokens**
— never real owner/client data the agent happens to know.

---

## VERIFY CACHING ACTUALLY WORKED

On **DeepSeek direct**, the API usage object exposes
`prompt_cache_hit_tokens` and `prompt_cache_miss_tokens`. After the warm-up
worker (Rule 3), **hits should cover the shared document** on every subsequent
worker. If hits stay at zero, the shared prefix is drifting — re-check Rule 2
(a single changed byte at the front is the usual culprit).

---

## ONE-PARAGRAPH SUMMARY

**Before anything else:** echo back every rule in your own words + the full
work-slice list + the exact model strings you will use — and wait for GO.
Then: owner sends a file. Orchestrator reads it once and pastes the full text,
byte-identical, at the top of every worker — assignment last. Warm one worker,
then fan out in batches. Workers write one deliverable and die. The orchestrator
stays skinny (ledger + deliverables on disk, one-line statuses only). A
different model QCs to a numeric rubric (gate 8.5, defect-loop max 3). A
watchdog restarts the dead once and flags. Templates use tokens, never real
client data.
