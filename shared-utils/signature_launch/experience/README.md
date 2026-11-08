# Harness experience (LANE-HARNESS)

One experience across claude-nine, Claude Code, Codex (`claude-codex`) and OpenClaw. Stdlib only; no network, no credentials, nothing is sent: the agent says the output in its own session.

## Two distributions, one source

This directory is the **source of truth**: this repository is a source repo, and it never
vendors or pins a copy of itself. Its own distribution is a straight copy — `install.sh`
and the repo-root `update-skills.sh` copy skills and sync `shared-utils` verbatim into the
installed box (see `UPDATE-PLAYBOOK.md`); there is no `installer-registration/` here.

The **999 setup repository** is the distribution that installs. It vendors this tree under
`installer-registration/helpers/shared-utils/` and pins every file in
`installer-registration/helper-dependencies.json`, produced only by
`python3 installer-registration/helper-deps.py repin`. `check-helper-pins.py --onboarding
<checkout>` fails when a vendored byte or pin differs from the onboarding ref, so the
vendored copy can never drift quietly. A change here must land here first, then be
re-vendored and re-pinned in 999; the pins are never edited by hand.

| File | Job |
|---|---|
| `harness_profile.py` | Detect the harness: `--harness` flag, then answers file, then environment, then `plain`. Never guesses a skills path. |
| `render_question.py` | ONE canonical question to the structured tool payload (Claude Code, claude-nine) or a numbered chat message (OpenClaw, plain). Which question is not decided here: `pending` asks `shared-utils/client_intake/engine.py` for the single next APPLICABLE question (conditions evaluated, confirmed answers never re-asked, suggestions still asked), and `render` gives that one its shape. `parse_reply`, resume from the answers file. |
| `progress_report.py` | Status table (Claude Code, claude-nine) or one message per finished page (OpenClaw, plain). |
| `launch_progress_report.py` | Launch-level progress derived from `signature_launch/progress.py`: the same percent and unit facts render as a human table/lines and as the Command Center projection. Draft created, design ready for review, approved, installed and live stay distinct; a `done` row without current evidence is printed as NOT COUNTED. |
| `delivery_report.py` | Pages by deliverables (desktop and mobile), "To confirm" list with a one-line change, spend. Says INCOMPLETE and MISSING plainly. |
| `skill-md-harness-block.md` | Marked block for the three SKILL.md files, pasted at integration. |
| `fixtures/`, `test_experience.py` | Sample question bank slice, partial answers file, a nine-page funnel status, a ledger. Run: `python3 test_experience.py`. |

Inputs it expects from the other lanes: questions in the bank's shape (`id`, `text`/`prompt`, `why`/`reason`, `choices` up to 3, optional `example`, `header`, `group`, `safe_default`, `never_default`), the answers file (`answers` keyed by id or listed, each with `value`/`status`, plus `to_confirm`), and page rows (`page_key`, `state`, `wireframe`/`mockup` with `desktop`/`mobile`, `labels`, `qc`). Page labels come from Skill 71 `deliverable_labels.py` when present.
