# Pointer References playbook (skill 70)

System: Pointer References (core-file upkeep)
Last verified: 2026-09-28
Triggers: core files, core.md files, bootstrap files, bloat, slim down, 40,000 characters, playbook, pointer, AGENTS.md too long, MEMORY.md too long, TOOLS.md too long

This is the one and only playbook for keeping core files lean. Read it top to
bottom the first time. After that, jump to the section you need:

1. What this is and why it makes the agent faster
2. How this relates to the Teach Yourself Protocol (skill 01)
3. The pointer format (with good and bad examples)
4. The earn-your-place rule and what must stay inline
5. One system, one playbook: storage, template, master index
6. Contradiction handling
7. Safety rules
8. Step-by-step procedure (a run someone asked for)
9. Weekly run procedure (the unattended cron job)
10. When a human decision is needed
11. Test battery (after every run)
12. The weekly cron job: model order and how to check it
13. Gaps, loopholes and landmines
14. Sourced rationale
15. What changed

---

## 1. What this is and why it makes the agent faster

**Core files** (also called **core.md files** or **bootstrap files**) are the six
workspace files OpenClaw sends to the model with every single message:
AGENTS.md, TOOLS.md, MEMORY.md, USER.md, IDENTITY.md and SOUL.md. Three of them
collect almost all the bloat, because every new rule, tool note and memory gets
appended to them: **AGENTS.md, TOOLS.md and MEMORY.md**. Those three are this
playbook's focus.

**The target: no core file above 40,000 characters.** OpenClaw can be
configured to accept far more per file (fleet boxes allow up to 200,000), but
the limit is not the goal. Every character in a core file is paid for on every
message.

Why smaller core files make the agent faster and better:

- **Speed and cost.** Core files are re-sent with every message. A smaller
  prompt is read faster and costs less on every single turn.
- **Fewer compaction cycles.** Compaction is the agent stopping mid-work to
  squeeze its conversation memory because the context window is full. A large
  fixed prompt leaves less room for the conversation, so compaction comes
  sooner and more often.
- **No silent cut-off.** When a file or the running total is over its limit,
  OpenClaw does not refuse; it silently cuts the **middle** out of the file and
  keeps the beginning and the end (verified in the installed OpenClaw
  2026.9.6 code: ordinary files keep 75 percent head and 25 percent tail;
  AGENTS.md keeps 45 percent head, a short policy digest, and 15 percent tail).
  Files load in a fixed order (AGENTS.md, SOUL.md, IDENTITY.md, USER.md, then
  MEMORY.md) and each takes its share of the total budget in that order, so
  **MEMORY.md loads last and is the first to be cut** when the total runs out.
  The model is told only that "some files were truncated", not which rules
  vanished.
- **Better instruction following.** Models follow instructions less reliably
  as the prompt grows and as the number of simultaneous instructions grows,
  and they use material in the middle of a long prompt worst of all (see
  section 14). Lean core files keep the always-on rules where the model
  actually attends to them.
- **Cache friendliness.** Core files sit in the stable part of the prompt that
  model providers can cache. Every edit to a core file invalidates that cache
  for the next turns, which is why this work is done in one batch per week,
  not a little on every message.

**The trade-off.** Moving a block out costs one extra file read when the topic
comes up. That is worth it only when the pointer's WHEN is specific enough that
the agent reliably opens the playbook at the right moment. A vague pointer is
worse than the original block. Everything in this playbook serves that one
condition.

---

## 2. How this relates to the Teach Yourself Protocol (skill 01)

The two skills do different jobs:

- **Skill 01, Teach Yourself Protocol:** how the agent LEARNS new knowledge and
  where the full document is stored (the master files folder, playbooks in the
  `playbooks/` subfolder).
- **Skill 70, Pointer References (this playbook):** how the agent keeps the
  core files LEAN over time: what is allowed to stay in a core file, the exact
  pointer format, one playbook per system, the master index, contradiction
  handling, and the weekly upkeep.

Where the two used to differ, this playbook is the newer rule and wins for
anything that lands in a core file (the install conflict rule in every
INSTALL.md says the same: the skill governs core-file content):

| Topic | Teach Yourself Protocol (older) | This playbook (current) |
| --- | --- | --- |
| What a core file holds for a topic | a 10 to 25 line summary plus a path | ONE pointer line, at most two sentences |
| Parts of a pointer | WHAT, WHEN, WHY, POINTER | WHAT (the why folds into it), WHERE (the exact path), WHEN (trigger words) |
| Storage | master files folder, `playbooks/` subfolder | the same folder, unchanged |
| Index | README.md index for API folders | the same README.md convention, used for `playbooks/` |

Nothing else in skill 01 changes. Storage paths are identical on purpose, so
there is exactly one playbooks folder on every box.

---

## 3. The pointer format

A pointer is **one line, at most two sentences**, and it answers three
questions:

- **WHAT** it is (the system or topic, in the words a person would use),
- **WHERE** it lives (the exact absolute path, never a relative path and never
  a placeholder like `[MASTER_FILES_FOLDER]`),
- **WHEN** to open it (concrete trigger words a user would actually say).

**Template:**
`<System>: <what the playbook covers> lives at <absolute path>. Read it whenever the user mentions <trigger>, <trigger>, or <trigger>.`

**Good examples**

- `QuickBooks Online: rules and playbook live at ~/Downloads/openclaw-master-files/playbooks/quickbooks-online.md. Read it whenever the user mentions QuickBooks, invoices, or bookkeeping.`
- `Podcast publishing: the upload, scheduling and show-notes rules live at /data/.openclaw/master-files/playbooks/podcast-publishing.md. Read it whenever the user mentions an episode, show notes, or publishing the podcast.`
- `Kie.ai images: prompt limits, model choice and retries live at ~/Downloads/openclaw-master-files/playbooks/kie-ai-images.md. Read it before any Kie.ai image request or whenever the user asks for an image, a thumbnail, or a graphic.`

**Bad examples (and why)**

| Bad pointer | What is wrong |
| --- | --- |
| `See playbooks/quickbooks.md for more.` | No WHAT, no WHEN, relative path. The agent has no reason to ever open it. |
| `QuickBooks: ~/Downloads/openclaw-master-files/playbooks/quickbooks-online.md` | No WHEN. The agent does not know that "send the invoice" is its cue. |
| `Read the QuickBooks playbook when relevant.` | "When relevant" is not a trigger. Use words the user says. |
| `QuickBooks: [MASTER_FILES_FOLDER]/playbooks/quickbooks-online.md ...` | Unresolved placeholder; the path exists nowhere. |
| A pointer followed by five bullet points of "key facts" | That is the old block growing back. The pointer is one line. |

**Writing trigger words that fire.** Pick three to six words or short phrases
that a person really types: product names ("QuickBooks"), the nouns of the
task ("invoice", "episode", "thumbnail") and the verbs ("publish", "bill").
Include the everyday synonym, not only the official name. If the system has a
common misspelling or nickname, include it. Put the most common trigger first.

**Where the pointer goes.** In the core file and section where the original
block was, so related pointers stay together. Tool and command knowledge goes
in TOOLS.md (or the `## Tools` section of AGENTS.md on OpenClaw 2026.9 and
later), behavior rules in AGENTS.md, and facts about history or the owner in
MEMORY.md.

---

## 4. The earn-your-place rule and what must stay inline

**Earn-your-place rule.** Any block longer than a short paragraph (about five
sentences, or about 1,000 characters) is a candidate to move into its own
playbook and be replaced by a pointer. The audit script lists these as
"candidate blocks". A candidate is a question, not an order: the decision is
yours, block by block.

**CRITICAL EXCEPTION: always-on rules stay inline, shortened.** The agent only
opens a playbook when the WHEN fires. A rule that must hold on every message
cannot depend on a trigger, so it stays in the core file. Only situational
knowledge moves.

| Stays inline (shorten it, keep it) | Moves to a playbook (pointer left behind) |
| --- | --- |
| Safety rules ("never share credentials") | How a specific tool or service works |
| Never-do rules and hard constraints | Step-by-step procedures for one task |
| Identity essentials (who the agent is, who the owner is) | Reference tables, model lists, limits, prices |
| Rules about when to ask the owner before acting | History of a project, past incidents |
| Anything whose absence would cause harm before a trigger could fire | Anything only needed when a named topic comes up |

**How to shorten an always-on rule.** Keep the rule itself and cut the story
behind it. "Never delete a file without asking the owner first" stays; the
three paragraphs about the incident that caused the rule go to the playbook of
the system involved (or to `core-rules-archive.md`, see section 5), together
with a pointer if the story is ever needed.

**Blocks managed by another skill's installer.** A block between
`<!-- BEGIN skill:NN-name:... -->` and `<!-- END skill:NN-name:... -->`
markers is rewritten by that skill's installer on every fleet update. Never
move or edit it by hand: the installer puts it straight back, and the moved
copy becomes a duplicate. The audit tags these "MANAGED". If one is too long,
report it (section 10); the fix belongs in that skill's CORE_UPDATES.md.

---

## 5. One system, one playbook: storage, template, master index

**One system = one playbook.** Everything about QuickBooks lives in one
QuickBooks playbook. A later update about QuickBooks updates that playbook; it
never creates `quickbooks-rules-2.md`. Before creating any playbook, search the
master index and the `System:` lines of every playbook for the system name and
its synonyms. Improve the content while moving it: remove repetition, put
current rules first, fix obvious staleness.

**Storage paths (identical to skill 01):**

| | Playbooks folder | Master index |
| --- | --- | --- |
| Mac | `~/Downloads/openclaw-master-files/playbooks/` | `~/Downloads/openclaw-master-files/playbooks/README.md` |
| Server (Docker) | `/data/.openclaw/master-files/playbooks/` | `/data/.openclaw/master-files/playbooks/README.md` |

On a server, everything must live under `/data/.openclaw/`; files anywhere else
are wiped when the container restarts. File names are the system name in
lowercase with hyphens: `quickbooks-online.md`, `podcast-publishing.md`.

**Playbook template (copy exactly, fill in):**

```
# <System name> playbook
System: <System name>
Last verified: YYYY-MM-DD
Triggers: <the same trigger words the pointer uses>

## Rules (current)
<the rules that apply today, newest wording, most important first>

## How to
<procedures, steps, commands, examples>

## Reference
<tables, limits, identifiers, links>

## What changed
- YYYY-MM-DD: created from AGENTS.md (moved block "<heading>").

## Moved-text archive (historical record, not instructions)
If anything in this archive disagrees with the sections above, the sections above win.
<!-- moved from AGENTS.md on YYYY-MM-DD -->
<the moved block, VERBATIM, exactly as it was in the core file>
```

Why the verbatim archive: the safety rule is "never delete, only move", and the
audit's proof step (section 7) checks that every removed paragraph exists
somewhere in the playbooks folder. Pasting the original text into the archive
first makes that proof mechanical, and the improved sections above it are what
the agent actually follows. Never edit the archive later; add new moved text
below the old.

**`core-rules-archive.md`.** When an always-on rule is shortened and its long
wording belongs to no particular system, the long wording goes into
`playbooks/core-rules-archive.md` (System: Core rules archive), which is
indexed and pointed to like any other playbook:
`Always-on rules, full wording and background: <path>/core-rules-archive.md. Read it whenever a short rule in this file is unclear or the user asks why a rule exists.`

**Master index format** (`playbooks/README.md`), one line per playbook, sorted
by system name:

```
- [QuickBooks Online](quickbooks-online.md) - invoicing and bookkeeping rules - last verified 2026-09-28
```

Every playbook appears in the index exactly once, and every playbook has a
pointer in a core file. The audit fails on a playbook that is missing from
either (an "orphan"), on an index line whose file does not exist, and on an
index line listed twice.

---

## 6. Contradiction handling

Run this check every time you move, add or update anything:

1. **Look for the same topic elsewhere:** the target playbook, the master
   index, every core file, and any other playbook whose `Triggers:` overlap.
2. **Newest rule wins.** Decide which statement is newer from the dates in the
   "What changed" logs, the backup timestamps, or the owner's most recent
   message. Keep the newest as the current rule.
3. **Mark the old rule superseded, with a date, in the "What changed" log.**
   Never silently overwrite. Example:
   `- 2026-09-28: Kie.ai image prompt limit changed from 25,000 to 20,000 characters after the model upgrade. The 25,000 rule is superseded.`
   Then change the current rule in "Rules (current)" to 20,000.
4. **Remove the stale copy from the core file** (move it into the archive, do
   not delete it) so only one current statement exists anywhere.
5. **Update `Last verified:`** to today's date on every playbook you checked,
   even when nothing changed. A date older than 90 days is a prompt to
   re-verify at the next opportunity.
6. **When you cannot tell which rule is newer**, do not guess. Keep both, mark
   the conflict at the top of "Rules (current)" as `UNRESOLVED CONFLICT
   (YYYY-MM-DD): <both statements>`, and ask the owner (section 10).

---

## 7. Safety rules

- **Back up every touched file first.** Run the audit script with `--backup`
  before the first edit of a run; it copies every core file and the whole
  playbooks folder into a timestamped folder and prints its path. Mac:
  `~/Downloads/openclaw-backups/pointer-references/<stamp>/`; server:
  `/data/.openclaw/backups/pointer-references/<stamp>/`.
- **Never delete, only move.** Text leaves a core file only after it exists in
  a playbook archive. Playbooks are never deleted; duplicates are merged into
  one and the merged-away file's content goes into the survivor's archive.
  (Merging the file away is a move, and it is done only after the proof.)
- **Prove before removing.** After editing a core file, run
  `pointer-audit.sh --prove-moved <backup>/core/AGENTS.md <workspace>/AGENTS.md`.
  Exit 0 means every paragraph that left the core file exists verbatim in the
  playbooks folder. Exit 1 lists each UNPROVEN paragraph: paste it into the
  right archive (or put it back in the core file) and run the proof again. Do
  this for each core file you edited.
- **The first run shows a dry-run diff.** On a box's first run, nothing in the
  core files changes. Prepare the edited copies in `<backup>/proposed/`, show
  `diff -u` of each core file against its proposed copy, and save that diff to
  `<master-files>/70-pointer-references/first-dry-run.md`. A run someone asked
  for then asks "Apply these moves?" once and continues on yes. The unattended
  weekly job applies nothing on its first run; from the second run on (the
  file above exists) it applies normally.
- **HARD WALL:** never touch `agents.defaults.bootstrapMaxChars` or
  `agents.defaults.bootstrapTotalMaxChars` in any way: do not read them, raise
  them, lower them or suggest changing them. The fix for a big core file is
  always moving content, never a bigger limit.
- Never change a model, provider, credential, channel or cron setting as part
  of this work.

---

## 8. Step-by-step procedure (a run someone asked for)

Paths below: `$AUDIT` is the audit script, `$WS` the workspace, `$PB` the
playbooks folder.

| | Mac | Server (inside the container) |
| --- | --- | --- |
| `$AUDIT` | `~/.openclaw/skills/70-pointer-references/scripts/pointer-audit.sh` | `/data/.openclaw/skills/70-pointer-references/scripts/pointer-audit.sh` |
| `$PB` | `~/Downloads/openclaw-master-files/playbooks` | `/data/.openclaw/master-files/playbooks` |

`$WS` is the main agent's workspace; the audit prints it on its first line.

1. **Back up:** `bash $AUDIT --backup`. Write down the printed folder (`$BK`).
2. **Audit:** `bash $AUDIT --dry-run`. Read the size table, the findings and the
   candidate blocks.
3. **Fix findings first** (broken pointers, orphans, duplicates, missing index
   lines, missing hygiene lines). They are cheap and they make the next steps
   reliable.
4. **Decide each candidate block** with section 4: situational (move),
   always-on (shorten inline), managed (leave, report).
5. **For each block to move**, in this order:
   a. Find its system's playbook (index and `System:` lines). None? Create one
      from the template in section 5.
   b. Paste the block VERBATIM into the playbook's "Moved-text archive".
   c. Merge its content into "Rules (current)", "How to" and "Reference",
      improving as you go, and run the contradiction check (section 6).
   d. Update `Last verified:` and add a "What changed" line.
   e. Add or refresh the playbook's line in the master index.
   f. Replace the block in the core file with ONE pointer line (section 3).
6. **First run on this box?** (No `first-dry-run.md` yet.) Do steps 5a to 5f on
   copies in `$BK/proposed/`, show the diff, save it as `first-dry-run.md`,
   ask once, and apply only on yes.
7. **Prove:** `bash $AUDIT --prove-moved $BK/core/AGENTS.md $WS/AGENTS.md` (and
   the same for TOOLS.md and MEMORY.md if you edited them). Must exit 0.
8. **Final audit:** `bash $AUDIT` (writes the report). Must exit 0, or exit 1
   only with findings you are reporting to the owner.
9. **Recall test** (section 11) for every pointer you added or changed.
10. **Tell the user** what moved, where it lives now, the before and after
    character counts, and the report path.

---

## 9. Weekly run procedure (the unattended cron job)

The weekly job starts a fresh isolated session with this playbook's path, the
audit script's path and the reports folder. Nobody is watching, so:

1. `bash $AUDIT --backup` and note `$BK`.
2. `bash $AUDIT --dry-run` and read it.
3. If the audit exits 2 (tooling error): stop, write the report, and message
   the owner (section 10). Do not guess around a broken instrument.
4. If there are no findings and no core file is above 40,000 characters and
   there is no candidate block you judge situational: write a short report
   ("clean, sizes: ...") and finish with NO_REPLY.
5. Otherwise follow section 8 steps 3 to 7. Two differences from a requested
   run:
   - **First run on this box** (no `first-dry-run.md`): prepare everything in
     `$BK/proposed/`, save the diff as `first-dry-run.md`, change NO core file,
     and finish. Next week's run applies.
   - **Any doubt about a block** (always-on or situational?) or about which of
     two rules is newer: leave it in place and list it for the owner. Never
     guess on an unattended run.
6. Run the mechanical recall check (section 11, part B) for every changed
   pointer.
7. Final `bash $AUDIT` writes the report file. Append a short "Agent notes"
   section to that same report: blocks moved (file, heading, destination),
   blocks kept inline and why, contradictions resolved, anything needing the
   owner.
8. Message the owner only if section 10 applies. Otherwise finish with
   NO_REPLY.

Keep the run efficient: read each playbook once, batch all edits to a core
file into one write, and do not re-read files you did not change.

---

## 10. When a human decision is needed

Send the owner ONE short plain-English message (no file dumps, no jargon) only
when at least one of these is true, and name each item:

- the audit script failed with a tooling error (exit 2);
- a core file is still above 40,000 characters after every situational block
  has moved (only always-on rules remain, so the owner must decide what to
  shorten or drop);
- two rules conflict and you cannot tell which is newer;
- you are unsure whether a block is an always-on rule or situational;
- a block managed by another skill's installer is too long (the skill needs a
  fix, not a hand edit);
- the content-preservation proof failed and you could not repair it;
- two playbooks for one system conflict and you cannot merge them safely.

Everything else is silent: the report file is the record.

---

## 11. Test battery (after every run)

**A. Mechanical (the audit script does these; exit 0 required):**

- no broken pointers (every master-files path in a core file exists);
- no unresolved placeholders, no relative playbook paths;
- every playbook pointer has a WHEN and at most two sentences;
- no orphan playbooks (every playbook is indexed AND pointed to);
- no duplicate playbooks per system (same `System:` line, same normalized file
  name, or identical content);
- the index resolves and lists nothing twice;
- every playbook has `System:`, `Last verified:` and "## What changed";
- the size report shows every core file at or under 40,000 characters (a file
  over the target is a finding);
- `--prove-moved` exits 0 for every core file you edited.

**B. Recall check (every run, including unattended ones):** for each pointer
you added or changed, write one realistic user question that needs the
playbook (use a trigger word from the pointer). Reading ONLY the core files,
decide which file you would open. Confirm that it is the file the pointer
names, that the file exists, and that its `Triggers:` line contains the word
you used. Record question, expected file and result in the report.

**C. Live recall test (only on a run someone asked for, and only on a box where
the operator allows test turns):** ask the agent in a fresh session, with no
delivery to any chat:

```
openclaw agent --agent main --session-key agent:main:pointer-recall-<YYYYMMDD> \
  --message "<the question>. Answer here only; do not send any message. At the end, name the exact file path you opened." --json
```

`--deliver` is off by default for this command, and the question tells the
agent not to message anyone. Pass if the reply names the playbook's path. Never
use `openclaw cron run` for a test on a client box: it starts a real agent turn
that can message the client.

---

## 12. The weekly cron job: model order and how to check it

The job is an OpenClaw **cron job** (an "automation"), not a heartbeat task:

| Setting | Value |
| --- | --- |
| Name | `pointer-references-weekly` |
| Schedule | `30 5 * * 0` (Sunday 05:30 gateway local time, after the Sunday 03:00 fleet update) |
| Session | isolated (fresh session every run) |
| Thinking | high |
| Delivery | none (`--no-deliver`); the agent messages the owner itself only under section 10 |
| Primary model | DeepSeek V4.1 Flash on Ollama Cloud: `ollama/deepseek-v4.1-flash:cloud` (or `ollama-cloud/deepseek-v4.1-flash:cloud`, whichever this box has) |
| Fallback model | DeepSeek V4.1 Flash on OpenRouter: `openrouter/deepseek/deepseek-v4.1-flash`, used only when the primary is full, rate-limited or unavailable |
| Never | any Anthropic or Claude model |

The installer (`scripts/install-weekly-cron.sh`) never guesses: it reads the
box's own configured model list and refuses (exit 4) if either identifier is
missing, and it checks every command-line flag against `--help` first (exit 5
if one is missing). Commands:

- check: `bash <skill>/scripts/install-weekly-cron.sh --check` (exit 0 = exactly one job, and it matches)
- repair or create: `bash <skill>/scripts/install-weekly-cron.sh --apply`
- inspect: `openclaw cron list --json` and look for the name above

---

## 13. Gaps, loopholes and landmines

- **Pointers never followed.** The biggest failure mode. Cause: a vague WHEN.
  Defense: concrete trigger words (section 3) and the recall check (section
  11). If the owner reports the agent "forgot" something that lives in a
  playbook, add the missing trigger word to the pointer and the `Triggers:`
  line.
- **Moving an always-on rule.** A safety rule behind a pointer is a rule that
  is off until someone says the magic word. When in doubt, keep it inline.
- **Stale playbooks.** Out of sight, out of date. `Last verified:` plus the
  weekly run keep them honest; update the playbook, never a second copy.
- **Duplicate sources of truth.** The same rule in a core file and a playbook,
  or two playbooks for one system, will drift apart. One system, one playbook,
  one pointer.
- **Orphans.** A playbook nobody points to is dead weight and confuses search.
  Every playbook is indexed and pointed to, or merged into one that is.
- **Managed blocks.** Hand-editing another skill's marked block is undone by
  the next update and leaves a duplicate. Report it instead.
- **TOOLS.md on newer OpenClaw.** From OpenClaw 2026.9, TOOLS.md is no longer a
  bootstrap file; `openclaw doctor --fix` merges it into a `## Tools` section of
  AGENTS.md and archives the original. On such a box, tool pointers belong in
  that section, and AGENTS.md carries more weight toward 40,000. The audit
  notes when both exist, so they do not say the same thing twice.
- **MEMORY.md on the Codex harness.** On the native Codex harness MEMORY.md is
  not pasted into every turn (it is searched on demand). Keep it lean anyway:
  other harnesses and fallbacks still inject it.
- **Sub-agents see only AGENTS.md.** OpenClaw sub-agent sessions get AGENTS.md
  and none of the other core files. Always-on rules a sub-agent needs must be
  in AGENTS.md, not only in MEMORY.md or SOUL.md.
- **Character counting.** OpenClaw counts characters, not bytes. The audit
  uses a UTF-8 (the standard text encoding) locale for its count and says so
  if it had to fall back to bytes.
- **Server paths.** A playbook written outside `/data/.openclaw/` on a server
  disappears at the next container restart, leaving a broken pointer.
- **Prompt cache churn.** Editing core files many times a day invalidates the
  cached prompt each time. Batch edits into one run.
- **A refused cron job is not a broken box.** If the installer exits 4, the box
  lacks one of the two model identifiers; the operator decides whether to add
  it. Never substitute a different model to make it pass.
- **No limit changes.** Raising the bootstrap limits hides bloat and makes
  every message slower. It is forbidden here (section 7).

---

## 14. Sourced rationale

- Context rot: model reliability drops continuously as input length grows,
  across 18 models, even on simple retrieval tasks.
  https://www.trychroma.com/research/context-rot
- Lost in the middle: models use information at the start and end of a long
  prompt best and in the middle worst, which is exactly the part OpenClaw's
  truncation cuts. https://arxiv.org/abs/2307.03172
- Instruction density: instruction following degrades as the number of
  simultaneous instructions grows, with a bias toward earlier instructions.
  https://arxiv.org/abs/2507.11538
- Progressive disclosure: load a short description always, the full material
  only when a task matches it. https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview
- Just-in-time context: keep lightweight identifiers (file paths) in context
  and load the content when needed; this also avoids stale copies.
  https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
- Trigger descriptions: say what it is AND when to use it, with the specific
  words that should match. https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices
- Prompt caching: any change in the cached prefix invalidates everything after
  it. https://platform.claude.com/docs/en/build-with-claude/prompt-caching and
  https://docs.openclaw.ai/reference/prompt-caching
- OpenClaw ground truth (installed package 2026.9.6): bootstrap order and
  head/tail truncation in `dist/bootstrap-*.mjs` and
  `dist/workspace-bootstrap-policy-*.mjs`; limits and truncation notice in
  `docs/concepts/system-prompt.md`; cron flags in `openclaw cron add --help`
  and `docs/automation/cron-jobs/payloads.md`; delivery modes in
  `docs/automation/cron-jobs/delivery.md`.

---

## 15. What changed

- 2026-09-28: first version (skill 70 v1.0.0). Supersedes, for core-file
  content only, the 10-to-25-line summary size and the four-part pointer block
  from the Teach Yourself Protocol (section 2).
