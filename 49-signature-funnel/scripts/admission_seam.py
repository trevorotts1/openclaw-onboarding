#!/usr/bin/env python3
"""admission_seam.py - Skill 49's caller into the one admission service (F14 item 2).

Skill 49 owns the launch entry (dispatch_launch, page_swarm, landing_bridge). It
does not own an admission implementation. This module loads Skill 71's
`governed_runner.py` by path -- the single caller of
`shared-utils/signature_launch/admission.py` -- and exposes the four entries F14
requires to consult the same rules:

  entry        admit_entry()          initial launch / a page run's first visit
  resume       admit_resume()         picking a run back up
  delegation   admit_delegation()     a lane handed to a delegated worker
  paid dispatch admit_paid_dispatch() a paid provider call

Plus the boundaries the F14 "Important limit" names as enforceable:
installation, publishing and the Complete transition.

AUTHORITY
---------
`authority="local"` records the decision and can never claim production
completion. The authoritative authorities (paid_dispatch, installation,
publishing, complete) REFUSE on a failed canonical stage check, on
out-of-pipeline output and, for complete, on unverified evidence.

NO RUN ROOT, NO RECORD. A lane that has no run root yet is reported as
`recorded: false` with the reason named -- never as an admission that happened
when it did not.

Stdlib only.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL71_ROOT = HERE.parents[1] / "71-blackceo-signature-page"
GOVERNED_RUNNER = SKILL71_ROOT / "scripts" / "governed_runner.py"

_RUNNER = None


def runner():
    """Skill 71's governed runner, loaded by path (one implementation)."""
    global _RUNNER
    if _RUNNER is None:
        if not GOVERNED_RUNNER.is_file():
            raise RuntimeError(
                "the governed runner is missing at %s; Skill 49 cannot admit work "
                "without it" % GOVERNED_RUNNER)
        spec = importlib.util.spec_from_file_location(
            "signature_launch_governed_runner", GOVERNED_RUNNER)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _RUNNER = module
    return _RUNNER


def refusal_type():
    return runner().AdmissionRefused


class SeamError(RuntimeError):
    """A 49 boundary that cannot record admission at all."""


def _admit(run_dir, kind, authority, **kwargs):
    if run_dir is None or not str(run_dir).strip():
        if authority in runner().AUTHORITATIVE_AUTHORITIES:
            raise SeamError(
                "the %s boundary needs a run root: an authoritative admission cannot "
                "be recorded without one" % kind)
        return {"admitted": True, "recorded": False, "kind": kind,
                "authority": authority,
                "reason": "no run root was supplied; nothing was recorded"}
    return runner().admit(Path(run_dir), kind=kind, authority=authority, **kwargs)


def admit_entry(run_dir, *, owner="skill49", stage=None, item=None, plan=None,
                authority="local", **kwargs):
    """The initial launch. With no approved plan yet, the decision is recorded
    before the run's canonical inputs exist; with a plan it is the full gate."""
    if run_dir is None or not str(run_dir).strip():
        return _admit(run_dir, "entry", authority, owner=owner, stage=stage,
                      item=item, plan=plan, **kwargs)
    if plan is None and authority in runner().NON_PRODUCTION:
        return runner().record_entry(Path(run_dir), kind="entry", owner=owner,
                                     authority=authority, stage=stage, item=item)
    return _admit(run_dir, "entry", authority, owner=owner, stage=stage, item=item,
                  plan=plan, **kwargs)


def admit_resume(run_dir, *, owner="skill49", stage=None, item=None, plan=None,
                 authority="local", **kwargs):
    if run_dir is not None and plan is None and authority in runner().NON_PRODUCTION:
        return runner().record_entry(Path(run_dir), kind="resume", owner=owner,
                                     authority=authority, stage=stage, item=item)
    return _admit(run_dir, "resume", authority, owner=owner, stage=stage, item=item,
                  plan=plan, **kwargs)


def admit_checkpoint(run_dir, *, owner="skill49", stage=None, item=None, plan=None,
                     authority="local", **kwargs):
    if run_dir is not None and plan is None and authority in runner().NON_PRODUCTION:
        return runner().record_entry(Path(run_dir), kind="checkpoint", owner=owner,
                                     authority=authority, stage=stage, item=item)
    return _admit(run_dir, "checkpoint", authority, owner=owner, stage=stage,
                  item=item, plan=plan, **kwargs)


def admit_delegation(run_dir, *, lane=None, owner="skill49", stage=None, item=None,
                     plan=None, authority="local", worker_cmd=None, **kwargs):
    """One lane handed to a delegated worker, carrying the canonical instructions."""
    if run_dir is None or not str(run_dir).strip():
        if authority in runner().AUTHORITATIVE_AUTHORITIES:
            raise SeamError(
                "the delegation boundary for lane %r needs a run root" % lane)
        return {"admitted": True, "recorded": False, "kind": "delegation",
                "lane": lane, "authority": authority,
                "reason": "no run root was supplied; nothing was recorded"}
    decision = runner().delegate(Path(run_dir), stage=stage, item=item, owner=owner,
                                 authority=authority, plan=plan,
                                 worker_cmd=worker_cmd)
    decision["lane"] = lane
    return decision


def admit_paid_dispatch(run_dir, *, stage, item=None, owner="skill49", plan=None,
                        **kwargs):
    """A paid provider call. Refuses before the call, not after a package check."""
    return _admit(run_dir, "direct_executor", "paid_dispatch", owner=owner,
                  stage=stage, item=item, plan=plan, **kwargs)


def admit_direct_executor(run_dir, *, stage, item=None, owner="skill49", plan=None,
                          authority="local", **kwargs):
    return _admit(run_dir, "direct_executor", authority, owner=owner, stage=stage,
                  item=item, plan=plan, **kwargs)


def admit_installation(run_dir, *, stage="ghl-install-test", owner="skill49",
                       plan=None, **kwargs):
    return _admit(run_dir, "installation", "installation", owner=owner, stage=stage,
                  plan=plan, **kwargs)


def admit_publishing(run_dir, *, stage="publish-verify", owner="skill49", plan=None,
                     **kwargs):
    return _admit(run_dir, "publishing", "publishing", owner=owner, stage=stage,
                  plan=plan, **kwargs)


def admit_complete(run_dir, *, evidence, unit=None, plan=None, **kwargs):
    return runner().complete(Path(run_dir), evidence=evidence, unit=unit, plan=plan,
                             **kwargs)


def scan(run_dir, *, receipts=None, declared_native=None):
    return runner().scan(Path(run_dir), receipts=receipts,
                         declared_native=declared_native)


def delivery(run_dir, artifacts, *, receipts=None):
    return runner().delivery(Path(run_dir), artifacts, receipts=receipts)


def record_lane(run_dir, lane, *, stage=None, owner="skill49"):
    """Record one page_swarm lane's delegation.

    A lane root that is not a governed run root (no canonical intake.json) has
    nothing to bind: the answer says `recorded: false` and names why. It never
    reports a decision that was not made.
    """
    if run_dir is None or not str(run_dir).strip():
        return {"admitted": True, "recorded": False, "kind": "delegation", "lane": lane,
                "reason": "no run root was supplied; nothing was recorded"}
    base = Path(run_dir)
    if not (base / "intake.json").is_file():
        return {"admitted": True, "recorded": False, "kind": "delegation", "lane": lane,
                "reason": "%s is not a governed run root (no intake.json); "
                          "nothing was recorded" % base}
    return admit_delegation(base, lane=lane, stage=stage, owner=owner)


def self_test():
    assert GOVERNED_RUNNER.is_file(), GOVERNED_RUNNER
    module = runner()
    assert module.SCHEMA == "signature-launch-runner/v1"
    assert "entry" in module.ENTRY_KINDS and "delegation" in module.ENTRY_KINDS
    # no run root: a local record is explicitly "nothing recorded", not a pass
    answer = admit_entry(None, authority="local")
    assert answer["recorded"] is False and "no run root" in answer["reason"]
    try:
        admit_paid_dispatch(None, stage="visual-mockup")
    except SeamError:
        pass
    else:
        raise AssertionError("a paid dispatch with no run root was not refused")


if __name__ == "__main__":
    self_test()
    print("admission_seam self-test: PASS")
