# Drama Song Ad Factory — Department Wiring (Skill 75)

Workforce-routing document for `drama-song-ad-factory`. It says which **existing**
departments own, support and route the factory, which **worker roles** may be
spawned for each, how workers are spawned, and how the run connects to Command
Center context.

| | |
|---|---|
| Unit | W3-02-U4 |
| Source | build directive §25 steps 6–7, §23 (Skill 23 AI Workforce Blueprint), §5.4, §20 |
| Staging path | `onboarding/department-wiring/drama-song-ad-factory.md` (build root) |
| Canonical map | `23-ai-workforce-blueprint/skill-department-map.json` → skill `75`, slug `drama-song-ad-factory` |
| Canonical floor | `23-ai-workforce-blueprint/department-naming-map.json` via `23-ai-workforce-blueprint/scripts/department-floor.py` |
| Skill folder | `75-drama-song-ad-factory/` (OpenClaw) / `999-setup/.claude/skills/drama-song-ad-factory/` (Claude-Nine twin) |
| Status | builder candidate — evidence in the unit lane; **no self-approval**, verdict is the judge's |

This file **does not** change `department-naming-map.json`, `skill-department-map.json`,
`templates/role-library/_index.json`, or any role/SOP/persona file. It is
read-only routing documentation. No department, role, SOP or persona is created here.

---

## 1. Department routing — existing departments only

Directive §23: integrate with existing departments such as Video, Audio, Paid
Advertisement and Copywriting/Creative as appropriate; **do not create duplicate
departments when the capability belongs in an existing one**.

Four capability departments are in scope. All four already exist:

| Department | Role in this factory | Floor status |
|---|---|---|
| `video` | **owner** — runs the run end to end | mandatory floor |
| `audio` | supporting — music/voice production inside the pipeline | mandatory floor |
| `paid-advertisement` | supporting — paid-media framing, ad copy, paid QC | mandatory floor |
| `copywriting` | supporting — lyric/direct-response copy craft | live role-library department; **not** on the floor |

These four are the departments directive §23 names (Video, Audio, Paid
Advertisement, Copywriting/Creative). `copywriting` is a real department in
`templates/role-library/copywriting/` carrying `director-of-copywriting`; it is
not one of the `department-naming-map.json` mandatory ids and has no
`suggested-roles/` roster, so nothing here treats it as a floor department.

Floor status in that table means "appears in `department-naming-map.json`'s
mandatory ids", confirmed live by `department-floor.py --json` (its `mandatory`
and `expected_floor` fields). This file intentionally does **not** hardcode a
floor count; run that command for the value, because the raw naming-map total and
the post-decline `expected_floor` are two different numbers.

### 1.1 Owning department — `video`

Canonical binding, `skill-department-map.json` skill `75` (already registered; not
written by this unit):

- `dept_owner`: `video`
- `departments`: `["video"]`
- owning roles (exactly these three):

| Role slug | Capacity | Primary |
|---|---|---|
| `video-editor` | owner / primary | yes |
| `head-of-video-production` | owner support | no |
| `storyboard-pre-production-specialist` | owner support | no |

`execution_sops`: `video-pipeline-craft` (cluster lives at
`universal-sops/video-pipeline-craft/`, shipped with
`VIDEO-PIPELINE-MANIFEST.json` and `MASTER-VIDEO-QC-AUTOFAIL-RULESET.md`).

The owning department owns intake, stage claims, the ledger, the stage manifest,
retakes, delivery and escalation. Supporting departments below never own a run.

### 1.2 Supporting departments

Cross-department supporters assist inside the pipeline at the invitation of a
`video` owner. They never own a run, never claim the run's stages, and never
authorise spend. Their roles are recorded **here** in the wiring spec, not in the
map's owning-roles list — the same split the podcast and anthology wiring
recorded for their audio supporters.

| Department | Roles | Contributes |
|---|---|---|
| `audio` | `music-and-audio-producer`, `audio-mastering-specialist`, `qc-specialist-audio`, `head-of-audio-production` | song/section generation, extend and continuity, loudness mastering, independent music/audio QC |
| `paid-advertisement` | `director-of-paid-advertisement`, `direct-response-ad-copywriter`, `qc-role--paid-advertisement` | paid-media framing, direct-response ad copy review, paid-campaign QC |
| `copywriting` | `director-of-copywriting` | lyric and CTA copy craft, voice/tone review |

### 1.3 Routing only

| Department | Capacity |
|---|---|
| `master-orchestrator` | routing — dispatches an inbound factory job to the `video` department head agent per the master routing doctrine; **executes no pipeline stage**. Infrastructure, not a capability mapping. |

### 1.4 No access

Default deny. Every department not named above — including `sales`,
`billing-finance`, `legal`, `customer-support`, `personal-assistant` — has **no**
access to the factory's engine or state. Customer messaging belongs to Convert and
Flow; no department messages a customer about a running campaign directly.

Client-side humans interact only through the board, the intake and the approved
delivery surface, never with the engine's internals.

---

## 2. Worker spawn rules (§25 step 7)

1. **Spawn through the box's current OpenClaw workforce/dispatch mechanism — never
   a second, private worker scheme.** The factory does not invent a parallel
   agent registry, a private thread pool, or its own role directory.
2. **Only the roles named in §1 may be spawned**, and only inside their declared
   capacity. A supporting role never claims an owning role's stage.
3. **Register every real worker under Command Center context** through the current
   canonical subagent/session path (§20.3): `POST /api/tasks/{TASK_ID}/subagent`.
   An unregistered worker is an unresolved launch, not free capacity.
4. **Workers claim stages through `state_store.py` leases** — explicit owner,
   expiry and fencing/version checks (§24.4). A stale worker cannot overwrite a
   newer result; a worker cannot advance a stale or unqualified stage. An expired
   lease on an uncertain paid submission never makes that submission safe to repeat.
5. **Independent QC.** The persona/role that drafted never grades its own work as
   the deciding vote, and a builder never writes its own accepted QC verdict
   (§24.6). `video-editor` drafts; `qc-specialist-video` decides video, and so on
   per department.
6. **Bounded work.** Every spawned worker carries a distinct owned result and
   acceptance criteria. Stage and repair attempts are bounded and persist across
   restart; a repeated no-progress state hands back structurally instead of looping.
7. **Ceilings when the factory is driven as a Claude-Nine swarm** (§3.1/§3.2 of
   the build directive, which take precedence over any broader default): at most
   50 reserved/admitted unfinished workflows concurrently, at most 10 live agents
   per workflow counting leads, builders, checkers, repair workers, helpers and
   descendants; register identity and reserve capacity before launch; no nested
   workflow launches and no undeclared helper spawning. Never evade a cap by
   renaming failed root work.
8. **Model selection belongs to the current router rules**, not to a hardcoded
   table in this skill.

---

## 3. Command Center context connection (§25 step 6)

**When present:** connect and read context — campaign record, board state,
approvals — through the current canonical API. Command Center keeps lifecycle
authority; the factory consumes it and never re-implements the server's TypeScript
lifecycle. **When absent:** continue on local run state; never block on its absence.

### 3.1 Canonical endpoints

```text
POST   /api/tasks/{TASK_ID}/subagent        register a spawned worker
POST   /api/tasks/{TASK_ID}/activities      significant stage transitions
POST   /api/tasks/{TASK_ID}/deliverables    deliverables — only after they exist
PATCH  /api/tasks/{TASK_ID}                 lifecycle moves
PATCH  /api/openclaw/sessions/{SESSION_ID}  mark a worker session complete
```

**Board (stage-card) family — `core/cc_sync.py` owns this contract:**

```text
POST   /api/ad-campaigns          create, idempotent on job_id (201/200), GET poll
PATCH  /api/ad-campaigns/{id}     move one stage card; ILLEGAL_TRANSITION -> 409
```

NOT `/api/campaigns`, and not Skill 47 `cc_board.py`'s default URL — that default
sends a stage-card payload to a route that does not accept it.

### 3.2 Rules

- **Register only real artifacts that exist.** A deliverable is registered after
  the file exists and passes delivery verification, never before.
- **Durable outbox, no loss and no duplicates.** `core/cc_sync.py` writes
  `pending -> sent -> acked`; `rejected` is terminal and is never sent. Replay does
  not duplicate cards.
- **Workspace (tenant) binding is mandatory.** Every event carries the bound
  workspace; an event with a different workspace is rejected and **nothing is
  stored** (`CC_WORKSPACE` / `workspace=`).
- **Report stage transitions, not every poll.** Do not spam the board with poll
  traffic (§20).
- **Never self-complete.** Local completion is not server acknowledgement; a board
  outage creates durable pending events rather than a silent local success.
- **Do not modify `blackceo-command-center`** unless the current interfaces are
  genuinely insufficient; if unavoidable, isolate it as its own reviewed change set
  and prove backward compatibility (§5.4).

---

## 4. Discoverability

The repository already ships one department-wiring scanner —
`dept_wiring_dir()` in `tests/distribution-parity/parity_check.py`, the function
behind the `department-wiring-equality` family:

```python
def dept_wiring_dir(skill: Path) -> dict[str, str]:
    d = skill / "department-wiring"
    if not d.is_dir():
        return {}
    return {p.relative_to(d).as_posix(): sha256_file(p)
            for p in sorted(d.rglob("*")) if p.is_file()}
```

It takes **any** root and reports every file under that root's `department-wiring/`
directory, keyed by relative path and sha256. Pointed at the onboarding root of
this build tree it returns this file:

```bash
ONBOARDING=<build-root>/onboarding          # the staging tree's onboarding root
PARITY=<onboarding-repo>/tests/distribution-parity/parity_check.py

python3 - "$ONBOARDING" "$PARITY" <<'PY'
import importlib.util, pathlib, sys
root, parity = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
s = importlib.util.spec_from_file_location("pc", parity)
m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
print(sorted(m.dept_wiring_dir(root)))
PY
# -> ['drama-song-ad-factory.md']
```

Precisely, and so no reader over-reads it:

- **Called at a skill root** (`75-drama-song-ad-factory/`) it reports `{}` —
  correct, and deliberate: unit W3-02-U3 decided skill 75 ships **no**
  `department-wiring/` subfolder, because department ownership lives in
  `skill-department-map.json`, not in per-skill packaging.
- **Called at the onboarding root** it discovers this file, which is where the
  plan places it (`onboarding/department-wiring/drama-song-ad-factory.md`).
- It does **not** parse this file's contents. Discovery and content validation are
  separate, and the content claims below are each checked by a scanner that
  already exists.

Everything this document **names** resolves through an existing scanner:

| Claim | Discovered by |
|---|---|
| owning department + owning roles | `23-ai-workforce-blueprint/skill-department-map.json`, read by `23-ai-workforce-blueprint/scripts/check-skill-department-map.py` |
| department ids are real (no invented department) | `23-ai-workforce-blueprint/scripts/department-floor.py --json` + `department-naming-map.json` |
| every role slug is a live role in the right department | `23-ai-workforce-blueprint/templates/role-library/_index.json` (same lookup `check-skill-department-map.py` uses) |
| floor counts stated in repo docs | `23-ai-workforce-blueprint/scripts/check-floor-count-consistency.py` (explicit `DOC_FLOOR_REGISTRY`, not a directory walk) |

That last row is why this document states **no** floor number: the repo carries
two legitimate values that mean different things — the raw naming map total
(mandatory ids plus universal-primary vertical ids) and the post-decline
`expected_floor` returned by `department-floor.py` — and the floor-count guard
only checks files listed in its registry. Hardcoding either here would be a stale
claim waiting to happen; run `department-floor.py --json` for the live figure.

---

## 5. Canonical declaration block

Same wording and format the repository already uses in `SKILL.md`, so any scanner
expecting the house declaration shape finds an identical one here:

```text
## Department wiring

Owning department: **video** (per `23-ai-workforce-blueprint/skill-department-map.json`).
Primary role: `video-editor`; support roles: `head-of-video-production`,
`storyboard-pre-production-specialist`. Copy/audio QC judgment rides the
video department's SOPs; paid-media ceilings ride the run's spend ledger,
not any department's informal allowance.
```

Cross-department supporting roles (`audio`, `paid-advertisement`, `copywriting`)
belong to §1.2 of this document only — deliberately **not** to the owning-roles
list, exactly as the podcast wiring recorded its audio supporters.
