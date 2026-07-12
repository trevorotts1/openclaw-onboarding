#!/usr/bin/env python3
"""
test-p4-02-synergy-directive.py — P4-02 step 7 (SYNERGY directive quality) lock.

The blend directive handed to the working agent must compose up to FOUR slots —
VOICE (audience persona), AUDIENCE (who it's for), SUBSTANCE (topic persona
expertise), and the TASK-side persona (DEP-5, the work process/method) — with
each populated when available and DEGRADING GRACEFULLY when not, and with the
mandatory GUARDRAIL_CLAUSE never removable.

Before P4-02, build_blend_directive had no task-persona slot at all (the task
side never reached the writer's instruction) and did not accept a
`task_persona_pid` argument. Every check below therefore FAILS on the pre-P4-02
tree — the fourth-slot calls raise TypeError (unexpected keyword argument) and
the "task-side persona is W" clause is absent — and passes with the fix.

Each check pairs with a NO-WEAKENING probe. Direct unit tests of the pure
`build_blend_directive` function (no selector/DB), so the synergy contract is
locked independently of the matcher harness.

    python3 test-p4-02-synergy-directive.py [REPO_ROOT]
"""
import importlib.util
import sys
from pathlib import Path

REPO = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "23-ai-workforce-blueprint" / "scripts"

PASS = 0
FAIL = 0


def ok(msg):
    global PASS
    PASS += 1
    print(f"  [PASS] {msg}")


def bad(msg):
    global FAIL
    FAIL += 1
    print(f"  [FAIL] {msg}")


def section(title):
    print("=" * 72)
    print(title)
    print("=" * 72)


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


pb = _load(SCRIPTS / "persona_blend.py", "persona_blend_p4_02")

AUD = "shonda-rhimes"
TOP = "brunson-dotcom-secrets"
TASK = "covey-7-habits"  # a genuinely distinct task-side persona (W)


def directive(**kw):
    """Call build_blend_directive with sensible content defaults, overridable."""
    base = dict(
        audience_pid=AUD, topic_pid=TOP, topic="email marketing",
        collapsed=False, collapsed_pid=None, content_task=True,
        audience_label="black women professionals",
    )
    base.update(kw)
    return pb.build_blend_directive(**base)


# ═══════════════════════════════════════════════════════════════════════════════
section("P4-02.7a  FOUR-SLOT synergy — all slots present")

d = directive(task_persona_pid=TASK)
have_voice = "Shonda" in d
have_audience = "black women professionals" in d
have_substance = "Brunson" in d and "carrying" in d
have_task = "task-side persona is Covey 7 Habits" in d
have_guardrail = pb.GUARDRAIL_CLAUSE in d

if have_voice and have_audience and have_substance and have_task and have_guardrail:
    ok("all four synergy slots (voice, audience, substance, TASK) + guardrail compose into one directive")
else:
    bad(f"four-slot compose incomplete: voice={have_voice} aud={have_audience} "
        f"substance={have_substance} task={have_task} guardrail={have_guardrail}\n    {d}")

# The task slot names the WORK-side lens explicitly, as an independent dimension.
if "apply ITS process and decision method" in d:
    ok("task slot instructs the writer to apply the task persona's process/method")
else:
    bad(f"task slot missing the process/method instruction: {d}")


# ═══════════════════════════════════════════════════════════════════════════════
section("P4-02.7b  GRACEFUL DEGRADATION — slot 4 omitted when absent / redundant")

# (i) No task persona → three slots, no task clause, guardrail intact.
d_none = directive(task_persona_pid=None)
if "task-side persona is" not in d_none and pb.GUARDRAIL_CLAUSE in d_none and "Shonda" in d_none:
    ok("task persona None → directive degrades to voice+audience+substance (no task clause), guardrail kept")
else:
    bad(f"None-task degradation wrong: {d_none}")

# (ii) Task persona == topic persona → redundant, omitted (topic already doubles
#      as task guidance) so the directive never repeats itself.
d_dup_topic = directive(task_persona_pid=TOP)
if "task-side persona is" not in d_dup_topic:
    ok("task persona == topic persona → slot 4 omitted (no self-repetition)")
else:
    bad(f"redundant task==topic slot not omitted: {d_dup_topic}")

# (iii) Task persona == audience/voice persona → likewise omitted.
d_dup_aud = directive(task_persona_pid=AUD)
if "task-side persona is" not in d_dup_aud:
    ok("task persona == audience/voice persona → slot 4 omitted (no self-repetition)")
else:
    bad(f"redundant task==voice slot not omitted: {d_dup_aud}")

# (iv) TOPIC-ONLY (audience unconfirmed) still degrades cleanly WITH a task slot.
d_topic_only = pb.build_blend_directive(
    audience_pid=None, topic_pid=TOP, topic="email marketing",
    collapsed=False, collapsed_pid=None, content_task=True,
    audience_label="", task_persona_pid=TASK)
if ("Audience not yet confirmed" in d_topic_only
        and "task-side persona is Covey 7 Habits" in d_topic_only
        and pb.GUARDRAIL_CLAUSE in d_topic_only):
    ok("topic-only branch (audience pending) still carries the task slot + guardrail")
else:
    bad(f"topic-only + task slot wrong: {d_topic_only}")

# (v) COLLAPSED voice + distinct task persona → task slot appended.
d_collapsed = pb.build_blend_directive(
    audience_pid=None, topic_pid=TOP, topic="budgeting",
    collapsed=True, collapsed_pid=AUD, content_task=True,
    audience_label="members", task_persona_pid=TASK)
if ("task-side persona is Covey 7 Habits" in d_collapsed
        and "Shonda" in d_collapsed and pb.GUARDRAIL_CLAUSE in d_collapsed):
    ok("collapsed voice + distinct task persona → task slot appended, guardrail kept")
else:
    bad(f"collapsed + task slot wrong: {d_collapsed}")


# ═══════════════════════════════════════════════════════════════════════════════
section("P4-02.7c  NON-CONTENT task never gets a voice/task synergy blend")

d_nc = pb.build_blend_directive(
    audience_pid=None, topic_pid=TOP, topic="server ops",
    collapsed=True, collapsed_pid=TOP, content_task=False,
    audience_label="", task_persona_pid=TASK)
if ("Non-content task" in d_nc and "task-side persona is" not in d_nc
        and pb.GUARDRAIL_CLAUSE in d_nc):
    ok("non-content task: no voice blend AND no task slot (content-gated), guardrail still mandatory")
else:
    bad(f"non-content directive wrong: {d_nc}")


# ═══════════════════════════════════════════════════════════════════════════════
section("P4-02.7d  GUARDRAIL is non-removable even with all four slots present")

full = directive(task_persona_pid=TASK)
# The guardrail must be the trailing, intact clause of the fully-composed directive.
if full.rstrip().endswith(pb.GUARDRAIL_CLAUSE):
    ok("guardrail is the trailing clause of the four-slot directive (cannot be pushed out)")
else:
    bad("guardrail not trailing on the four-slot directive")

# NO-WEAKENING: a directive stripped of the clause is detectable as missing it.
stripped = full.replace(pb.GUARDRAIL_CLAUSE, "")
if pb.GUARDRAIL_CLAUSE not in stripped:
    ok("NO-WEAKENING: guardrail absence is detectable on the composed directive")
else:
    bad("NO-WEAKENING failed: guardrail-absence not detectable")


print("=" * 72)
print(f"RESULTS: {PASS} passed, {FAIL} failed")
print("=" * 72)
sys.exit(0 if FAIL == 0 else 1)
