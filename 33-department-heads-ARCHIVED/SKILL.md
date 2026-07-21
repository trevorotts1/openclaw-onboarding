# ARCHIVED — DO NOT RUN — Skill 33: Permanent Department Heads

> **This skill is archived. Do not run its installer. Do not follow it as a procedure.**
>
> **Successor: Skill 23 — AI Workforce Blueprint (`23-ai-workforce-blueprint/`).**

Skill 33 installed seventeen permanent department-head agents into `agents.list[]`.
That model was replaced. Department workspace creation, SOUL.md generation and the
registry writes all live in Skill 23 now, and Skill 23 derives the departments from
the owner interview rather than from a fixed list of seventeen.

## Why you must not run this

Running `install.sh` in this folder, or following the procedure it used to
document, writes the superseded seventeen-department model into a live workforce
that Skill 23 has already built. The result is duplicate and conflicting entries
in `~/.openclaw/openclaw.json` under `agents.list[]`, and department workspaces
that no Skill 23 build state knows about.

`install.sh` in this folder refuses to run and exits non-zero. That refusal is
deliberate. Do not remove it.

## Where each capability went

| Old Skill 33 capability | Where it lives now |
|---|---|
| Department workspace creation | `23-ai-workforce-blueprint/scripts/build-workforce.py` — `create_department_workspace()` |
| SOUL.md generation | `23-ai-workforce-blueprint/scripts/build-workforce.py` — `generate_soul_md()` |
| `agents.list[]` registry writes | `23-ai-workforce-blueprint/scripts/build-workforce.py` — `add_agent_to_config()` |
| Department operation protocols | `23-ai-workforce-blueprint/SKILL.md` |
| Adding one role to an existing department | `23-ai-workforce-blueprint/scripts/add-role.sh` |

## Read instead

- `ARCHIVED.md` in this folder — the full archive record and the capability map.
- `23-ai-workforce-blueprint/SKILL.md` — the live skill.

The folder is retained only so that older client onboardings that reference
"Skill 33" in their `MEMORY.md` or `.onboarding-status` files still resolve.
Nothing here is maintained, and nothing here is to be executed.
