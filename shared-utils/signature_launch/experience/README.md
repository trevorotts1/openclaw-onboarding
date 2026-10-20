# Harness experience (LANE-HARNESS)

One experience across claude-nine, Claude Code and OpenClaw. Stdlib only; no network, no credentials, nothing is sent: the agent says the output in its own session.

| File | Job |
|---|---|
| `harness_profile.py` | Detect the harness: `--harness` flag, then answers file, then environment, then `plain`. Never guesses a skills path. |
| `render_question.py` | One canonical question to the structured tool payload (Claude Code, claude-nine) or a numbered chat message (OpenClaw, plain). `parse_reply`, `pending` (resume from the answers file). |
| `progress_report.py` | Status table (Claude Code, claude-nine) or one message per finished page (OpenClaw, plain). |
| `delivery_report.py` | Pages by deliverables (desktop and mobile), "To confirm" list with a one-line change, spend. Says INCOMPLETE and MISSING plainly. |
| `skill-md-harness-block.md` | Marked block for the three SKILL.md files, pasted at integration. |
| `fixtures/`, `test_experience.py` | Sample question bank slice, partial answers file, a nine-page funnel status, a ledger. Run: `python3 test_experience.py`. |

Inputs it expects from the other lanes: questions in the bank's shape (`id`, `text`/`prompt`, `why`/`reason`, `choices` up to 3, optional `example`, `header`, `group`, `safe_default`, `never_default`), the answers file (`answers` keyed by id or listed, each with `value`/`status`, plus `to_confirm`), and page rows (`page_key`, `state`, `wireframe`/`mockup` with `desktop`/`mobile`, `labels`, `qc`). Page labels come from Skill 71 `deliverable_labels.py` when present.
