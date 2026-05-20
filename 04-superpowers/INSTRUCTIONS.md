# Superpowers — Runtime Execution Instructions

**Version:** v10.13.0 (closes Audit Phase 11 + 12 — INSTRUCTIONS.md was missing)
**Skill:** 04-superpowers
**Status:** Required runtime guide. Referenced from `SKILL.md` as part of the TYP read-order.

`INSTALL.md` covers one-time installation. `SKILL.md` covers what the skill is and the 14 Iron-Law-bound sub-skills. **This file covers how an agent actually uses Superpowers in day-to-day work.**

---

## TYP read-order (mandatory before any execution)

1. `SKILL.md` — what Superpowers is and the 4 Iron Laws
2. **`INSTRUCTIONS.md` (this file)** — how to invoke the 14 sub-skills
3. `INSTALL.md` — re-read only when troubleshooting an install issue
4. `QC.md` — runtime QC rubric
5. `EXAMPLES.md` — calibration examples (good vs bad work)
6. `superpowers-full.md` — deep technical reference (the full 14-skill source)

Skipping is an N4 violation.

---

## The 4 Iron Laws (always on, every task)

These bind every line of code, every fix, every "done" claim. They are not opt-in.

1. **No fix without finding the real problem first.** Don't guess. Investigate. Reproduce the failure. State the root cause in plain language before writing a single character of fix code.
2. **No code without a failing test first.** Write the test. Watch it fail. THEN write the code. THEN watch the test pass. This is the TDD loop — no exceptions, even for "trivial" changes.
3. **No claiming "done" without proof.** Run it. Show the command + the output. "Should work" / "I think it works" / "Looks right" are NOT proof. Exit code 0 + correct output is proof.
4. **Evidence before claims, always.** Never say "fixed" before testing it. Never say "implemented" before running it. Never say "verified" before showing the verification output.

If an Iron Law was broken on a piece of work, the work is NOT done. Loop back, satisfy the law, then re-claim.

---

## The 14 sub-skills — when to use each

| Sub-skill | Use when | Trigger phrase |
|-----------|----------|----------------|
| `brainstorming` | Starting any non-trivial task — surface options before committing | "let's think about X", "what should we do about Y" |
| `gather-context` | Before ANY edit, when you don't have full picture of the surrounding code | "I don't know how this works yet" — STOP and gather |
| `condition-based-waiting` | Anywhere you'd `sleep 5` — replace with a real condition check | Replacing polling with `until <cond>; do sleep 1; done` |
| `using-git-worktrees` | Long-running parallel work, agent isolation, throwaway experiments | "let me try this without touching main" |
| `verification-before-completion` | Right before claiming "done" | Iron Law #3 enforcement |
| `tdd` | Any new feature, any bug fix | Iron Law #2 enforcement |
| `debugging` | Any failure investigation | "this doesn't work" / "the test is failing" |
| `root-cause-analysis` | Any "why is this happening" question | Iron Law #1 enforcement |
| `code-review` | Before merging your own work, before approving someone else's | Even for small PRs |
| `defensive-programming` | Anywhere you're tempted to skip a guard "because nothing should reach here" | Untrusted input, async boundaries, parsers |
| `error-handling` | Any try/except design | "what should happen when this fails?" |
| `logging-and-observability` | Adding production-bound code | "how will we know if this breaks at 3am?" |
| `refactoring` | Changing behavior-free, then changing behavior | Never both in one commit |
| `working-with-llms` | Building agentic features, prompt design | Anywhere you wrap an LLM call |

---

## How to invoke a sub-skill mid-task

These are **rules of thinking**, not commands. You don't run a CLI. You invoke them by **announcing the discipline you're entering**, then following its protocol from `superpowers-full.md`.

Example (entering `tdd`):
```
Entering tdd discipline (Iron Law #2 binding):
  Step 1: write failing test → <write test>
  Step 2: run test, confirm RED → <run + show output>
  Step 3: write minimum code to pass → <write code>
  Step 4: run test, confirm GREEN → <run + show output>
  Step 5: refactor (if needed) — separate commit
```

The "announce" step matters. It tells the user (and the QC sub-agent) which protocol your next actions will be measured against.

---

## When NOT to invoke a sub-skill

- For pure documentation changes (no code execution) → `tdd` is not needed.
- For one-line config tweaks where the failure mode is "config is wrong" → `verification-before-completion` is enough; full TDD is overkill.
- For investigations that don't touch code → `gather-context` + `root-cause-analysis` are the relevant ones.

**The Iron Laws still bind even when no sub-skill applies.** "I'm just changing a comment" still requires running the affected code path before claiming done.

---

## Integration with OpenClaw core

Superpowers binds **every** dispatch via the master orchestrator's standing rules in `AGENTS.md`:

- **N2** — Master orchestrator does no work; sub-agents do. Superpowers apply to every sub-agent invocation, not the orchestrator's coordination.
- **N3 / N4** — Read before act, follow declared step order. These pair with `gather-context` and `tdd` respectively.
- **N5** — No self-QC. The QC sub-agent that scores a piece of work is a DIFFERENT sub-agent than the one that wrote it. Superpowers' `code-review` discipline applies on the QC side.
- **N6** — Max 5 retry loops. If a TDD loop fails 5 times, escalate. Don't fake-pass the test.
- **N16** — Persona governance on every non-mechanical task. The persona may shape *how* the discipline is applied (e.g., a "Hormozi-style" persona might emphasize blunt assessment in `code-review`), but it does NOT override the Iron Laws.

---

## Common failure modes and fixes

| Symptom | Iron Law being broken | Fix |
|---------|----------------------|-----|
| Agent says "I think this fixes it" | #4 (evidence before claims) | Run the test. Show the output. Re-claim with evidence. |
| Agent writes code without a test first | #2 (no code without failing test) | Roll back the code. Write the test. Watch it fail. THEN re-write the code. |
| Agent guesses at the bug location | #1 (find real problem) | Stop. Reproduce. Bisect. Get the actual stack trace. |
| Agent says "all tests pass" without running them | #3 (no done without proof) | Run them. Show the command + output. |
| Agent dives in without context | gather-context | Stop. Read the surrounding code. State what's currently going on before proposing a change. |

---

## Cross-references

- `SKILL.md` — Iron Laws + sub-skill catalog
- `INSTALL.md` — one-time setup (TYP + Back Yourself Up prerequisites)
- `QC.md` — runtime QC rubric (gate ≥ 8.5)
- `EXAMPLES.md` — calibration: good Iron-Law adherence vs degenerate
- `superpowers-full.md` — deep technical reference for each of the 14 sub-skills
- `AGENTS.md` N3 / N4 / N5 / N6 / N16 — the OpenClaw rules that Superpowers reinforces
- Upstream source: github.com/obra/superpowers

---

*End of INSTRUCTIONS.md for Skill 04.*
