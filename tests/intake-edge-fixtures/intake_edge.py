#!/usr/bin/env python3
"""intake_edge.py: edge-case fixture suite for intake/preflight (unit W4-02-U1).

Source: SWARM-PLAN W4-02. Families:

  other-offer          resume carrying a DIFFERENT offer invalidates approval;
                       auth bound to the old digest then fails preflight
  ambiguous-briefs     placement-omitted / whitespace / bad-type / non-dict briefs
                       driven through BOTH intake and preflight
  injection-battery    one shipped INJECTION_RES pattern each + negative controls
  three-question-cap   at most 3 questions per reply; placement fills leftovers only
  provenance-recording provided | inherited | assumed | missing; spending never defaulted
  preflight-edges      preflight rejections carrying the same brief digests

Every scenario runs the SHIPPED CLI (core/intake_preflight/factory.py) and its
full envelope is recorded under outcomes/<scenario>.json. Expectations were
verified against live output before being asserted; nothing here asserts a
behavior the code does not have.

Exit 0 = every check, 1 = at least one failed check, 2 = resolve/tooling failure.
stdlib only, no framework, no network.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
FACTORY = os.path.join(ROOT, "core", "intake_preflight", "factory.py")
FIXTURES = os.path.join(HERE, "fixtures")
OUTDIR = os.path.join(HERE, "outcomes")
UNIT_ID = "W4-02-U1"
BOX_SLUG = os.environ.get("BOX_SLUG", "local")
TMP_PREFIX = "%s-%s-" % (BOX_SLUG, UNIT_ID)

sys.path.insert(0, os.path.join(ROOT, "core"))
try:
    from intake_preflight import EXIT, SCHEMA_VERSION
except Exception as exc:  # resolve failure, not a test failure
    sys.stderr.write("resolve-failure: cannot import intake_preflight: %s\n" % exc)
    sys.exit(2)
if not os.path.isfile(FACTORY):
    sys.stderr.write("resolve-failure: missing %s\n" % FACTORY)
    sys.exit(2)

ENVELOPE_KEYS = {"schema_version", "tool_version", "command", "run_id", "outcome",
                 "reason_code", "next_action", "evidence", "data", "state_version"}
PROV_KEYS = ("offer", "assets", "audience", "action", "budget_minor", "budget_currency",
             "placement", "aspect_ratio", "brand_rules", "creative_prefs",
             "repair_allowance", "target_length_s")

CHECKS = []
RECORDS = []
WORKDIR = tempfile.mkdtemp(prefix=TMP_PREFIX, dir="/tmp")
_STATE = {}


def chk(sid, label, ok, detail=None):
    CHECKS.append({"scenario": sid, "check": label, "pass": bool(ok),
                   "detail": detail if ok else detail})
    return bool(ok)


def cli(args, run_id):
    """Run the shipped CLI; returns (exit_code, envelope_or_error)."""
    cmd = [sys.executable, FACTORY] + list(args) + ["--run-id", run_id]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    try:
        env = json.loads(proc.stdout)
    except Exception:
        env = {"schema_version": None, "tool_version": None, "command": args[0],
               "run_id": run_id, "outcome": "unparseable", "reason_code": "unparseable",
               "next_action": proc.stdout[:200] or proc.stderr[:200],
               "evidence": [], "data": {}, "state_version": {}}
    return proc.returncode, env, cmd


def fix(name):
    return os.path.join(FIXTURES, name)


def write_tmp(name, obj):
    path = os.path.join(WORKDIR, name)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, sort_keys=True)
    return path


def record(sid, family, argv, rc, env, notes=None, extra=None):
    """Persist one scenario outcome (envelope + its checks)."""
    mine = [c for c in CHECKS if c["scenario"] == sid]
    rec = {"unit_id": UNIT_ID, "scenario": sid, "family": family, "argv": argv,
           "exit_code": rc, "envelope": env, "checks": mine,
           "checks_total": len(mine),
           "checks_failed": sum(1 for c in mine if not c["pass"]),
           "notes": notes or {}, "recorded_unix": int(time.time())}
    if extra:
        rec.update(extra)
    os.makedirs(OUTDIR, exist_ok=True)
    with open(os.path.join(OUTDIR, "%s.json" % sid), "w", encoding="utf-8") as fh:
        json.dump(rec, fh, indent=2, sort_keys=True, default=str)
    RECORDS.append(rec)
    return rec


def env_invariants(sid, rc, env, command):
    """Shared envelope contract: 10 keys, shipped schema_version, EXIT map."""
    keys = set(env)
    chk(sid, "envelope-10-key-shape", keys == ENVELOPE_KEYS, sorted(keys))
    chk(sid, "envelope-schema-version", env.get("schema_version") == SCHEMA_VERSION,
        env.get("schema_version"))
    chk(sid, "envelope-command", env.get("command") == command, env.get("command"))
    outcome = env.get("outcome")
    chk(sid, "outcome-in-EXIT-map", outcome in EXIT, outcome)
    if outcome in EXIT:
        chk(sid, "exit-code-matches-EXIT-map", rc == EXIT[outcome],
            {"rc": rc, "expected": EXIT[outcome]})


def expect(sid, rc, env, outcome, reason, exit_code):
    chk(sid, "outcome", env.get("outcome") == outcome, env.get("outcome"))
    chk(sid, "reason_code", env.get("reason_code") == reason, env.get("reason_code"))
    chk(sid, "exit_code", rc == exit_code, rc)


def qids(env):
    return [q.get("id") for q in (env.get("data", {}).get("questions") or [])]


def check_cap(sid, env, n):
    """Three-question cap: never more than n, numbered 1..n in one message."""
    qs = env.get("data", {}).get("questions") or []
    chk(sid, "question-count<=3", len(qs) <= 3, len(qs))
    chk(sid, "question-count==%d" % n, len(qs) == n, [q.get("id") for q in qs])
    msg = env.get("data", {}).get("question_message")
    if n == 0:
        chk(sid, "no-question-message", not msg, msg)
    else:
        lines = (msg or "").split("\n")
        chk(sid, "question-message-one-message", len(lines) == n, len(lines))
        chk(sid, "question-message-numbered",
            all(lines[i].startswith("%d. " % (i + 1)) for i in range(len(lines))), lines)
        # both shipped waiting paths ask everything in ONE reply
        chk(sid, "question-message-single-ask",
            env.get("next_action") in (
                "Answer the bundled questions in one reply; nothing else is asked.",
                "Answer outstanding decisions; questionnaire is not rerun."),
            env.get("next_action"))


def check_prov(sid, env, expected, forbid_assumed=()):
    prov = env.get("data", {}).get("provenance") or {}
    chk(sid, "provenance-complete", set(prov) == set(PROV_KEYS), sorted(prov))
    for key, want in expected.items():
        chk(sid, "provenance-%s==%s" % (key, want), prov.get(key) == want, prov.get(key))
    for key in forbid_assumed:
        chk(sid, "provenance-%s-never-assumed" % key, prov.get(key) != "assumed",
            prov.get(key))


# --------------------------------------------------------------------------
# family: other-offer
# --------------------------------------------------------------------------
def family_other_offer():
    sid = "oo-01-base-brief"
    rc, env, argv = cli(["intake", "--brief-file", fix("complete-brief.json")], sid)
    env_invariants(sid, rc, env, "intake")
    expect(sid, rc, env, "ok", "complete-brief-zero-questions", 0)
    check_cap(sid, env, 0)
    record(sid, "other-offer", argv, rc, env)
    _STATE["digest"] = env.get("state_version", {}).get("current")
    _STATE["summary"] = env.get("data", {}).get("summary")
    _STATE["auth"] = {"scope": "campaign", "expires_unix": int(time.time()) + 600,
                      "currency": "USD"}
    _STATE["auth_path"] = write_tmp("auth-campaign.json", _STATE["auth"])
    if not _STATE["digest"]:
        return  # later scenarios record themselves as blocked

    resume = {"digest": _STATE["digest"], "summary": _STATE["summary"],
              "outstanding": [], "next_stage": "preflight"}
    resume_path = write_tmp("resume-state.json", resume)

    sid = "oo-02-other-offer-resume"
    rc, env, argv = cli(["intake", "--brief-file", fix("other-offer-brief.json"),
                         "--resume-file", resume_path], sid)
    env_invariants(sid, rc, env, "intake")
    expect(sid, rc, env, "parked", "resume-approval-invalidated", 3)
    data = env.get("data", {})
    chk(sid, "approval-invalidated", data.get("approval_invalidated") is True,
        data.get("approval_invalidated"))
    chk(sid, "changes-is-offer-only", data.get("changes") == ["offer"], data.get("changes"))
    chk(sid, "no-questions-on-park", not data.get("questions"), data.get("questions"))
    chk(sid, "next-action-re-approve",
        str(data and env.get("next_action", "")).startswith("Re-approve scope"),
        env.get("next_action"))
    record(sid, "other-offer", argv, rc, env,
           extra={"resume_state": resume, "prior_digest": _STATE["digest"]})
    _STATE["other_digest"] = env.get("state_version", {}).get("current")

    sid = "oo-03-same-offer-resume"
    rc, env, argv = cli(["intake", "--brief-file", fix("complete-brief.json"),
                         "--resume-file", resume_path], sid)
    env_invariants(sid, rc, env, "intake")
    expect(sid, rc, env, "ok", "resume-no-changes", 0)
    data = env.get("data", {})
    chk(sid, "approval-not-invalidated", data.get("approval_invalidated") is False,
        data.get("approval_invalidated"))
    chk(sid, "no-changes", data.get("changes") == [], data.get("changes"))
    chk(sid, "digest-unchanged-on-resume",
        env.get("state_version", {}).get("current") == _STATE["digest"],
        env.get("state_version", {}).get("current"))
    record(sid, "other-offer", argv, rc, env, extra={"resume_state": resume})

    sid = "oo-04-placement-change-resume"
    rc, env, argv = cli(["intake", "--brief-file", fix("placement-change-brief.json"),
                         "--resume-file", resume_path], sid)
    env_invariants(sid, rc, env, "intake")
    expect(sid, rc, env, "ok", "resume-material-changes", 0)
    data = env.get("data", {})
    chk(sid, "placement-change-not-approval-affecting",
        data.get("approval_invalidated") is False, data.get("approval_invalidated"))
    chk(sid, "changes-is-placement", data.get("changes") == ["placement"],
        data.get("changes"))
    record(sid, "other-offer", argv, rc, env, extra={"resume_state": resume})

    # --- preflight carrying the same brief digests ---
    sid = "oo-05-preflight-campaign-auth"
    rc, env, argv = cli(["preflight", "--root", WORKDIR, "--storage-dir", WORKDIR,
                         "--auth-file", _STATE["auth_path"],
                         "--summary-digest", _STATE["digest"]], sid)
    env_invariants(sid, rc, env, "preflight")
    expect(sid, rc, env, "ok", "preflight-pass", 0)
    record(sid, "other-offer", argv, rc, env,
           extra={"brief_digest": _STATE["digest"]})

    other_digest = _STATE.get("other_digest")
    if other_digest:
        sid = "oo-06-preflight-auth-bound-to-old-digest"
        old_scope = write_tmp("auth-old-digest.json",
                              dict(_STATE["auth"], scope=_STATE["digest"]))
        rc, env, argv = cli(["preflight", "--root", WORKDIR, "--storage-dir", WORKDIR,
                             "--auth-file", old_scope,
                             "--summary-digest", other_digest], sid)
        env_invariants(sid, rc, env, "preflight")
        expect(sid, rc, env, "rejected", "approval-out-of-scope", 4)
        record(sid, "other-offer", argv, rc, env,
               extra={"auth_scope_digest": _STATE["digest"],
                      "brief_digest": other_digest})
    else:
        sid = "oo-06-preflight-auth-bound-to-old-digest"
        chk(sid, "blocked-by-oo-02", False, "other-offer digest unavailable")
        record(sid, "other-offer", ["intake", "--brief-file",
                                    fix("other-offer-brief.json")], None,
               {"outcome": "not-run"}, notes={"blocked_by": "oo-02"})

    sid = "oo-07-preflight-expired-auth"
    expired = write_tmp("auth-expired.json", dict(_STATE["auth"], expires_unix=1))
    rc, env, argv = cli(["preflight", "--root", WORKDIR, "--storage-dir", WORKDIR,
                         "--auth-file", expired, "--summary-digest", _STATE["digest"]], sid)
    env_invariants(sid, rc, env, "preflight")
    expect(sid, rc, env, "rejected", "approval-expired", 4)
    record(sid, "other-offer", argv, rc, env)

    sid = "oo-08-preflight-approval-missing"
    rc, env, argv = cli(["preflight", "--root", WORKDIR, "--storage-dir", WORKDIR,
                         "--summary-digest", _STATE["digest"]], sid)
    env_invariants(sid, rc, env, "preflight")
    expect(sid, rc, env, "rejected", "approval-missing", 4)
    record(sid, "other-offer", argv, rc, env)

    sid = "oo-09-intake-currency-out-of-scope"
    eur = write_tmp("settings-eur-auth.json",
                    {"authorization": {"scope": "campaign",
                                       "expires_unix": 4102444800, "currency": "EUR"}})
    rc, env, argv = cli(["intake", "--brief-file", fix("complete-brief.json"),
                         "--settings-file", eur], sid)
    env_invariants(sid, rc, env, "intake")
    expect(sid, rc, env, "ok", "complete-brief-zero-questions", 0)
    data = env.get("data", {})
    chk(sid, "auth-status-out-of-scope", data.get("auth_status") == "out-of-scope",
        data.get("auth_status"))
    ceiling = (data.get("summary") or {}).get("generation_ceiling") or {}
    chk(sid, "brief-currency-untouched-by-auth", ceiling.get("currency") == "USD",
        ceiling.get("currency"))
    record(sid, "other-offer", argv, rc, env)


# --------------------------------------------------------------------------
# family: ambiguous-briefs
# --------------------------------------------------------------------------
def family_ambiguous():
    sid = "amb-01-no-placement-intake"
    rc, env, argv = cli(["intake", "--brief-file", fix("ambiguous-no-placement.json")], sid)
    env_invariants(sid, rc, env, "intake")
    expect(sid, rc, env, "waiting", "missing-essentials", 2)
    check_cap(sid, env, 1)
    chk(sid, "only-placement-asked", qids(env) == ["placement"], qids(env))
    record(sid, "ambiguous-briefs", argv, rc, env)
    amb_digest = env.get("state_version", {}).get("current")

    sid = "amb-02-no-placement-preflight"
    if not amb_digest or "auth_path" not in _STATE:
        chk(sid, "blocked-by-amb-01", False, "digest or auth unavailable")
        record(sid, "ambiguous-briefs", ["preflight"], None, {"outcome": "not-run"},
               notes={"blocked_by": "amb-01"})
    else:
        rc, env, argv = cli(["preflight", "--root", WORKDIR, "--storage-dir", WORKDIR,
                             "--auth-file", _STATE["auth_path"],
                             "--summary-digest", amb_digest], sid)
        env_invariants(sid, rc, env, "preflight")
        expect(sid, rc, env, "ok", "preflight-pass", 0)
        record(sid, "ambiguous-briefs", argv, rc, env, extra={"brief_digest": amb_digest})

    sid = "amb-03-whitespace-only-fields"
    rc, env, argv = cli(["intake", "--brief-file", fix("ambiguous-whitespace.json")], sid)
    env_invariants(sid, rc, env, "intake")
    expect(sid, rc, env, "waiting", "missing-essentials", 2)
    check_cap(sid, env, 3)
    chk(sid, "whitespace-treated-as-missing",
        qids(env) == ["offer", "audience_action", "spending_authority"], qids(env))
    check_prov(sid, env, {"offer": "missing", "audience": "missing", "action": "missing",
                          "budget_minor": "missing", "budget_currency": "missing"},
               forbid_assumed=("budget_minor", "budget_currency"))
    record(sid, "ambiguous-briefs", argv, rc, env)

    sid = "amb-04-non-numeric-target-length"
    rc, env, argv = cli(["intake", "--brief-file", fix("ambiguous-bad-length.json")], sid)
    env_invariants(sid, rc, env, "intake")
    expect(sid, rc, env, "waiting", "missing-essentials", 2)
    check_cap(sid, env, 1)
    chk(sid, "only-placement-asked", qids(env) == ["placement"], qids(env))
    check_prov(sid, env, {"target_length_s": "assumed", "placement": "assumed"})
    chk(sid, "bad-length-falls-back-to-default",
        (env.get("data", {}).get("summary") or {}).get("target_length_s") == 30,
        (env.get("data", {}).get("summary") or {}).get("target_length_s"))
    record(sid, "ambiguous-briefs", argv, rc, env)

    sid = "amb-05-link-key-as-assets"
    rc, env, argv = cli(["intake", "--brief-file", fix("link-brief.json")], sid)
    env_invariants(sid, rc, env, "intake")
    expect(sid, rc, env, "waiting", "missing-essentials", 2)
    check_prov(sid, env, {"assets": "provided"})
    chk(sid, "link-normalized-to-list",
        (env.get("data", {}).get("summary") or {}).get("assets") == ["https://shop.example/p"],
        (env.get("data", {}).get("summary") or {}).get("assets"))
    record(sid, "ambiguous-briefs", argv, rc, env)

    sid = "amb-06-non-dict-brief"
    rc, env, argv = cli(["intake", "--brief-file", fix("malformed-brief.json")], sid)
    env_invariants(sid, rc, env, "intake")
    expect(sid, rc, env, "error", "intake-failed", 1)
    chk(sid, "error-is-not-acceptance",
        env.get("outcome") not in ("ok", "waiting"), env.get("outcome"))
    record(sid, "ambiguous-briefs", argv, rc, env)


# --------------------------------------------------------------------------
# family: injection-battery
# --------------------------------------------------------------------------
def family_injection():
    """One fixture per shipped INJECTION_RES pattern + negative controls."""
    pos = [
        ("inj-01-ignore-previous-instructions", "ignore-all-previous.json"),
        ("inj-02-skip-preflight", "skip-preflight.json"),
        ("inj-03-bypass-approval-guard", "bypass-guard.json"),
        ("inj-04-approve-the-budget", "approve-budget.json"),
        ("inj-05-raise-the-ceiling", "raise-ceiling.json"),
        ("inj-06-use-my-key", "use-my-key.json"),
        ("inj-07-authorization-is-approved", "authorization-approved.json"),
        ("inj-08-system-colon-prefix", "system-colon.json"),
    ]
    for sid, name in pos:
        rc, env, argv = cli(["intake", "--brief-file", fix(name)], sid)
        env_invariants(sid, rc, env, "intake")
        expect(sid, rc, env, "rejected", "untrusted-injection-blocked", 4)
        data = env.get("data", {})
        chk(sid, "untrusted-field-named", bool(data.get("untrusted_fields")),
            data.get("untrusted_fields"))
        chk(sid, "no-questions-when-blocked", not data.get("questions"),
            data.get("questions"))
        chk(sid, "approval-not-granted-by-injection",
            data.get("approval_invalidated") is False, data.get("approval_invalidated"))
        chk(sid, "blocked-is-terminal",
            env.get("next_action", "").startswith("Remove instruction language"),
            env.get("next_action"))
        record(sid, "injection-battery", argv, rc, env, extra={"fixture": name})

    controls = [
        ("inj-09-control-benign-complete", "ctrl-benign-complete.json", "ok"),
        ("inj-10-control-system-midstring", "ctrl-system-midstring.json", "waiting"),
        ("inj-11-control-nested-field-not-scanned", "ctrl-nested-dict.json", "waiting"),
    ]
    for sid, name, want in controls:
        rc, env, argv = cli(["intake", "--brief-file", fix(name)], sid)
        env_invariants(sid, rc, env, "intake")
        chk(sid, "control-not-flagged-as-injection",
            env.get("reason_code") != "untrusted-injection-blocked",
            env.get("reason_code"))
        chk(sid, "control-takes-its-own-path", env.get("outcome") == want,
            env.get("outcome"))
        chk(sid, "control-no-untrusted-fields",
            not (env.get("data", {}).get("untrusted_fields")),
            env.get("data", {}).get("untrusted_fields"))
        record(sid, "injection-battery", argv, rc, env,
               extra={"fixture": name, "control": True})

    sid = "inj-12-injection-beats-resume-path"
    if "digest" not in _STATE:
        chk(sid, "blocked-by-oo-01", False, "base digest unavailable")
        record(sid, "injection-battery", ["intake"], None, {"outcome": "not-run"},
               notes={"blocked_by": "oo-01"})
        return
    resume = {"digest": _STATE["digest"], "summary": _STATE["summary"],
              "outstanding": [], "next_stage": "preflight"}
    resume_path = write_tmp("resume-state-inj.json", resume)
    rc, env, argv = cli(["intake", "--brief-file", fix("injection-resume-brief.json"),
                         "--resume-file", resume_path], sid)
    env_invariants(sid, rc, env, "intake")
    expect(sid, rc, env, "rejected", "untrusted-injection-blocked", 4)
    data = env.get("data", {})
    chk(sid, "injection-not-resumed", env.get("outcome") != "parked",
        env.get("outcome"))
    chk(sid, "approval-untouched-on-resume-injection",
        data.get("approval_invalidated") is False, data.get("approval_invalidated"))
    record(sid, "injection-battery", argv, rc, env,
           extra={"fixture": "injection-resume-brief.json", "resume_state": resume})


# --------------------------------------------------------------------------
# family: three-question-cap
# --------------------------------------------------------------------------
def family_cap():
    sid = "cap-01-empty-brief"
    rc, env, argv = cli(["intake", "--brief-file", fix("empty-brief.json")], sid)
    env_invariants(sid, rc, env, "intake")
    expect(sid, rc, env, "waiting", "missing-essentials", 2)
    check_cap(sid, env, 3)
    chk(sid, "placement-excluded-when-slots-full",
        qids(env) == ["offer", "audience_action", "spending_authority"], qids(env))
    record(sid, "three-question-cap", argv, rc, env)

    sid = "cap-02-offer-only"
    rc, env, argv = cli(["intake", "--brief-file", fix("offer-only-brief.json")], sid)
    env_invariants(sid, rc, env, "intake")
    expect(sid, rc, env, "waiting", "missing-essentials", 2)
    check_cap(sid, env, 3)
    chk(sid, "placement-fills-leftover-slot",
        qids(env) == ["audience_action", "spending_authority", "placement"], qids(env))
    record(sid, "three-question-cap", argv, rc, env)

    sid = "cap-03-no-budget"
    rc, env, argv = cli(["intake", "--brief-file", fix("no-budget-brief.json")], sid)
    env_invariants(sid, rc, env, "intake")
    expect(sid, rc, env, "waiting", "missing-essentials", 2)
    check_cap(sid, env, 2)
    chk(sid, "spending-question-present",
        "spending_authority" in qids(env), qids(env))
    chk(sid, "placement-still-fits",
        qids(env) == ["spending_authority", "placement"], qids(env))
    record(sid, "three-question-cap", argv, rc, env)

    sid = "cap-04-resume-outstanding-capped"
    if "digest" not in _STATE:
        chk(sid, "blocked-by-oo-01", False, "base digest unavailable")
        record(sid, "three-question-cap", ["intake"], None, {"outcome": "not-run"},
               notes={"blocked_by": "oo-01"})
        return
    resume = {"digest": _STATE["digest"], "summary": _STATE["summary"],
              "outstanding": ["Mood?", "Brand colors?", "Voice?", "Tempo?",
                              "Hook word?", "End card?"],
              "next_stage": "preflight"}
    resume_path = write_tmp("resume-outstanding.json", resume)
    rc, env, argv = cli(["intake", "--brief-file", fix("complete-brief.json"),
                         "--resume-file", resume_path], sid)
    env_invariants(sid, rc, env, "intake")
    expect(sid, rc, env, "waiting", "resume-outstanding-decisions", 2)
    check_cap(sid, env, 3)
    chk(sid, "resume-question-ids", qids(env) == ["resume-0", "resume-1", "resume-2"],
        qids(env))
    chk(sid, "questionnaire-not-rerun",
        str(env.get("next_action", "")).startswith("Answer outstanding decisions"),
        env.get("next_action"))
    record(sid, "three-question-cap", argv, rc, env,
           extra={"resume_state": resume, "outstanding_submitted": 6})


# --------------------------------------------------------------------------
# family: provenance-recording
# --------------------------------------------------------------------------
def family_provenance():
    sid = "prov-01-complete-brief-provided"
    rc, env, argv = cli(["intake", "--brief-file", fix("complete-brief.json"), ], sid + "-rerun")
    env_invariants(sid, rc, env, "intake")
    expect(sid, rc, env, "ok", "complete-brief-zero-questions", 0)
    check_prov(sid, env,
               {"offer": "provided", "audience": "provided", "action": "provided",
                "budget_minor": "provided", "budget_currency": "provided",
                "placement": "provided", "aspect_ratio": "provided",
                "brand_rules": "provided", "creative_prefs": "provided",
                "repair_allowance": "provided", "target_length_s": "provided",
                # empty assets list is falsy: shipped behavior records "missing"
                "assets": "missing"})
    record(sid, "provenance-recording", argv, rc, env)

    sid = "prov-02-settings-inherited"
    settings = write_tmp("settings-inherit.json", {
        "defaults": {"offer": "inherited offer", "audience": "inherited audience",
                     "action": "inherited action", "budget_minor": 777,
                     "budget_currency": "EUR", "placement": "4:5 portrait",
                     "brand_rules": "keep logo top-left", "target_length_s": 45},
        "authorization": {"scope": "campaign", "expires_unix": 4102444800,
                          "currency": "EUR"}})
    rc, env, argv = cli(["intake", "--brief", "{}", "--settings-file", settings], sid)
    env_invariants(sid, rc, env, "intake")
    expect(sid, rc, env, "ok", "complete-brief-zero-questions", 0)
    check_prov(sid, env,
               {"offer": "inherited", "audience": "inherited", "action": "inherited",
                "budget_minor": "inherited", "budget_currency": "inherited",
                "placement": "inherited", "brand_rules": "inherited",
                "target_length_s": "inherited",
                "aspect_ratio": "assumed", "creative_prefs": "assumed",
                "repair_allowance": "assumed", "assets": "missing"},
               forbid_assumed=("budget_minor", "budget_currency"))
    data = env.get("data", {})
    chk(sid, "inherited-ceiling-recorded",
        (data.get("summary") or {}).get("generation_ceiling") ==
        {"amount_minor": 777, "currency": "EUR"},
        (data.get("summary") or {}).get("generation_ceiling"))
    chk(sid, "auth-bound-with-inherited-currency",
        data.get("auth_status") == "bound", data.get("auth_status"))
    record(sid, "provenance-recording", argv, rc, env)

    sid = "prov-03-spending-never-defaulted"
    rc, env, argv = cli(["intake", "--brief-file", fix("empty-brief.json")], sid)
    env_invariants(sid, rc, env, "intake")
    check_prov(sid, env, {"budget_minor": "missing", "budget_currency": "missing"},
               forbid_assumed=("budget_minor", "budget_currency"))
    ceiling = (env.get("data", {}).get("summary") or {}).get("generation_ceiling")
    chk(sid, "ceiling-empty-not-invented",
        ceiling == {"amount_minor": None, "currency": None}, ceiling)
    record(sid, "provenance-recording", argv, rc, env)

    sid = "prov-04-digest-determinism"
    rc1, env1, _ = cli(["intake", "--brief-file", fix("complete-brief.json")], sid + "-a")
    rc2, env2, argv = cli(["intake", "--brief-file", fix("complete-brief.json")], sid + "-b")
    d1 = (env1.get("state_version") or {}).get("current")
    d2 = (env2.get("state_version") or {}).get("current")
    chk(sid, "same-brief-same-digest", bool(d1) and d1 == d2, {"a": d1, "b": d2})
    chk(sid, "digest-is-16-hex", bool(d1) and len(d1) == 16 and
        all(c in "0123456789abcdef" for c in d1), d1)
    if "digest" in _STATE:
        chk(sid, "other-offer-digest-differs",
            _STATE.get("other_digest") != _STATE["digest"],
            {"base": _STATE.get("digest"), "other": _STATE.get("other_digest")})
    else:
        chk(sid, "base-digest-available", False, "base digest unavailable")
    record(sid, "provenance-recording", argv, rc2, env2,
           extra={"first_exit": rc1, "first_digest": d1, "second_digest": d2})

    sid = "prov-05-assumptions-listed"
    rc, env, argv = cli(["intake", "--brief-file", fix("empty-brief.json")], sid)
    env_invariants(sid, rc, env, "intake")
    assumptions = (env.get("data", {}).get("summary") or {}).get("assumptions") or []
    chk(sid, "placement-assumption-declared",
        any(str(a).startswith("placement=") and "assumed default" in str(a)
            for a in assumptions), assumptions)
    chk(sid, "assumption-list-present", isinstance(assumptions, list) and bool(assumptions),
        len(assumptions) if isinstance(assumptions, list) else assumptions)
    record(sid, "provenance-recording", argv, rc, env)


# --------------------------------------------------------------------------
# family: preflight-edges
# --------------------------------------------------------------------------
def family_preflight_edges():
    inside = os.path.join(WORKDIR, "ref-inside.txt")
    with open(inside, "w", encoding="utf-8") as fh:
        fh.write("reference payload\n")
    digest = _STATE.get("digest") or "0000000000000000"
    auth = _STATE.get("auth_path") or write_tmp(
        "auth-fallback.json", {"scope": "campaign", "expires_unix": 4102444800,
                               "currency": "USD"})
    base = ["preflight", "--root", WORKDIR, "--storage-dir", WORKDIR,
            "--auth-file", auth, "--summary-digest", digest]

    sid = "pf-01-baseline-pass-with-inside-reference"
    rc, env, argv = cli(base + ["--ref", inside], sid)
    env_invariants(sid, rc, env, "preflight")
    expect(sid, rc, env, "ok", "preflight-pass", 0)
    record(sid, "preflight-edges", argv, rc, env)

    sid = "pf-02-untrusted-schema"
    rc, env, argv = cli(base + ["--schema-version", "parity.evil/v1"], sid)
    env_invariants(sid, rc, env, "preflight")
    expect(sid, rc, env, "error", "schema-untrusted", 1)
    record(sid, "preflight-edges", argv, rc, env)

    sid = "pf-03-unknown-delivery-profile"
    rc, env, argv = cli(base + ["--profile", "weird/4x5"], sid)
    env_invariants(sid, rc, env, "preflight")
    expect(sid, rc, env, "rejected", "delivery-profile-unknown", 4)
    record(sid, "preflight-edges", argv, rc, env)

    sid = "pf-04-reference-outside-approved-storage"
    rc, env, argv = cli(base + ["--ref", "/etc/hosts"], sid)
    env_invariants(sid, rc, env, "preflight")
    expect(sid, rc, env, "rejected", "reference-outside-approved-storage", 4)
    chk(sid, "outside-path-named",
        (env.get("data", {}).get("outside") or []) == ["/etc/hosts"],
        env.get("data", {}).get("outside"))
    record(sid, "preflight-edges", argv, rc, env)

    sid = "pf-05-reference-missing"
    rc, env, argv = cli(base + ["--ref", os.path.join(WORKDIR, "nope.txt")], sid)
    env_invariants(sid, rc, env, "preflight")
    expect(sid, rc, env, "error", "reference-missing-or-truncated", 1)
    record(sid, "preflight-edges", argv, rc, env)

    sid = "pf-06-credential-presence-only"
    rc, env, argv = cli(base + ["--credential", "NOT_A_REAL_CRED_VAR_W402"], sid)
    env_invariants(sid, rc, env, "preflight")
    expect(sid, rc, env, "rejected", "credential-missing", 4)
    present = (env.get("data", {}).get("checks") or {}).get("credentials_present")
    chk(sid, "presence-recorded-not-value",
        present == {"NOT_A_REAL_CRED_VAR_W402": False}, present)
    record(sid, "preflight-edges", argv, rc, env)

    sid = "pf-07-credential-value-never-echoed"
    present_env = os.environ.get("HOME", "")
    rc, env, argv = cli(base + ["--credential", "HOME"], sid)
    env_invariants(sid, rc, env, "preflight")
    expect(sid, rc, env, "ok", "preflight-pass", 0)
    blob = json.dumps(env, sort_keys=True)
    chk(sid, "credential-value-absent-from-envelope",
        not present_env or present_env not in blob, "HOME value present in envelope")
    chk(sid, "credential-flagged-present",
        (env.get("data", {}).get("checks") or {}).get("credentials_present") ==
        {"HOME": True},
        (env.get("data", {}).get("checks") or {}).get("credentials_present"))
    record(sid, "preflight-edges", argv, rc, env)

    sid = "pf-08-disk-limit"
    rc, env, argv = cli(base + ["--min-free-bytes", str(10 ** 15)], sid)
    env_invariants(sid, rc, env, "preflight")
    expect(sid, rc, env, "error", "disk-limit", 1)
    record(sid, "preflight-edges", argv, rc, env)

    sid = "pf-09-tool-and-module-unavailable"
    rc, env, argv = cli(base + ["--require-tool", "definitely-not-a-real-tool-w402",
                                "--require-module", "definitely_not_a_real_module_w402"], sid)
    env_invariants(sid, rc, env, "preflight")
    expect(sid, rc, env, "error", "tool-unavailable", 1)
    missing = (env.get("data", {}).get("missing") or [])
    chk(sid, "missing-tool-named", "definitely-not-a-real-tool-w402" in missing, missing)
    record(sid, "preflight-edges", argv, rc, env)


# --------------------------------------------------------------------------
def main():
    started = int(time.time())
    # outcomes/ is an exact record of THIS run
    shutil.rmtree(OUTDIR, ignore_errors=True)
    os.makedirs(OUTDIR, exist_ok=True)
    for fam in (family_other_offer, family_ambiguous, family_injection,
                family_cap, family_provenance, family_preflight_edges):
        try:
            fam()
        except Exception as exc:  # a suite crash must surface, never hide
            sid = "SUITE-ERROR-%s" % fam.__name__
            chk(sid, "family-runs", False, "%s: %s" % (type(exc).__name__, exc))
            record(sid, fam.__name__.replace("family_", ""), [], None,
                   {"outcome": "error"}, notes={"exception": repr(exc)})

    # global cap sweep: no intake scenario ever exceeded three questions
    overs = []
    for rec in RECORDS:
        if rec.get("envelope", {}).get("command") != "intake":
            continue
        n = len(rec.get("envelope", {}).get("data", {}).get("questions") or [])
        if n > 3:
            overs.append({"scenario": rec["scenario"], "questions": n})
    CHECKS.append({"scenario": "SWEEP-three-question-cap",
                   "check": "no-intake-scenario-exceeds-3-questions",
                   "pass": not overs, "detail": overs})

    total = len(CHECKS)
    failed = [c for c in CHECKS if not c["pass"]]
    families = {}
    for rec in RECORDS:
        fam = rec["family"]
        f = families.setdefault(fam, {"scenarios": 0, "checks": 0, "failed": 0})
        f["scenarios"] += 1
        f["checks"] += rec["checks_total"]
        f["failed"] += rec["checks_failed"]
    summary = {"unit_id": UNIT_ID, "suite": "intake-edge-fixtures",
               "source": "SWARM-PLAN W4-02",
               "factory": FACTORY,
               "box_slug": BOX_SLUG,
               "started_unix": started, "finished_unix": int(time.time()),
               "scenarios": len(RECORDS), "checks": total, "checks_failed": len(failed),
               "families": families,
               "failed_checks": failed,
               "status": "PASS" if not failed else "FAIL"}
    os.makedirs(OUTDIR, exist_ok=True)
    with open(os.path.join(OUTDIR, "summary.json"), "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2, sort_keys=True, default=str)

    print("=== intake-edge-fixtures summary (unit %s) ===" % UNIT_ID)
    for name in sorted(families):
        f = families[name]
        print("  %-22s scenarios=%d checks=%d failed=%d"
              % (name, f["scenarios"], f["checks"], f["failed"]))
    print("  scenarios=%d checks=%d failed=%d"
          % (len(RECORDS), total, len(failed)))
    for c in failed:
        print("  FAIL %s :: %s :: %r" % (c["scenario"], c["check"], c["detail"]))
    shutil.rmtree(WORKDIR, ignore_errors=True)
    if failed:
        print("EDGE_FIXTURES_FAIL")
        return 1
    print("ALL_EDGE_FIXTURES_PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
