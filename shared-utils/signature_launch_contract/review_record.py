#!/usr/bin/env python3
"""review_record.py - the one check for "this page was independently reviewed"
(ENF-10 / F19; schema signature-launch-review-record/v1).

A caller-typed reviewer string proves nothing (reviewer 'a' vs author 'b' is
two letters). A review record counts ONLY when:
  * it carries a recognised SUCCESSFUL verdict - a present-but-any verdict, or
    no verdict at all, is not an approval (S1/W11 admission boundary);
  * its reviewer session id is in the dispatch ledger (a session the harness
    recorded when it dispatched work - not a string the author typed);
  * that reviewer session differs from the author session, and any recorded
    author identity agrees with the author the caller names;
  * it names a reviewer model (matching the ledger entry's model when the
    ledger carries one);
  * it echoes the request it reviewed (request_id), and the dispatch identity
    it was issued for, when the caller/ledger knows either;
  * it lists the sha256 of EVERY artifact reviewed: a review of nothing, or of
    only some of the artifacts, is not a review of the page;
  * under a policy that requires independence it declares independent review,
    and its reviewer model differs from the author model - a separate session
    is not model independence, and an unknown author model cannot prove it;
  * with exact_artifact_set, it reviewed exactly this artifact set - not that
    set plus bytes that no longer exist;
  * an attempt/revision-scoped review binds the current attempt and is not
    marked stale (F19 item 6);
  * a scope is at least as strong as the closure it is asked to close: an
    asset/item review cannot close a page/stage (F19 item 2);
  * a reviewer that repaired the reviewed bytes cannot keep its own verdict;
    changed bytes need a fresh decision from another reviewer (F19 item 4);
  * a transformed/derivative delivery binds source sha, derivative sha and
    transformation identity - the master's PASS does not certify changed
    delivered bytes (F19 item 13).

Dispatch ledger shape: a JSON list of session ids, or
{"sessions": [<id> | {"session_id": ..., "model": ..., "dispatch_id": ...}, ...]}.

Deterministic, stdlib only. Exit 0 ok, 2 refused, 3 usage.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

SCHEMA = "signature-launch-review-record/v1"
VERDICTS = ("pass", "passed", "approved", "approve", "success", "succeeded",
            "verified")
#: Review scopes, weakest first. A record can close its own scope or any
#: weaker one; it cannot close a stronger one (F19 item 2).
REVIEW_SCOPES = ("asset", "item", "page", "stage", "launch")
_SCOPE_RANK = {name: rank for rank, name in enumerate(REVIEW_SCOPES, start=1)}
_HEX64 = re.compile(r"^[a-f0-9]{64}$")
_AUTHENTICATED_CLASSES = ("authenticated_platform_record",
                          "recorded_consent_not_cryptographically_sealed")


def verdict_of(record: Any) -> Optional[str]:
    """The recognised successful verdict, or None. A bare nonempty string is
    not a verdict: it has to be one of the recognised successes."""
    if not isinstance(record, dict):
        return None
    raw = record.get("verdict", record.get("decision"))
    if isinstance(raw, bool):
        return "pass" if raw else None
    if isinstance(raw, str) and raw.strip().lower() in VERDICTS:
        return raw.strip().lower()
    if record.get("passed") is True:
        return "pass"
    return None


def ledger_sessions(ledger: Any) -> Dict[str, Dict[str, Any]]:
    """Normalise a dispatch ledger to {session_id: entry}. Anything that is
    not a list or a {"sessions": [...]} object is an empty ledger (fail closed)."""
    items = ledger.get("sessions") if isinstance(ledger, dict) else ledger
    out: Dict[str, Dict[str, Any]] = {}
    for it in items if isinstance(items, list) else []:
        if isinstance(it, str) and it.strip():
            out[it] = {}
        elif isinstance(it, dict) and isinstance(it.get("session_id"), str) \
                and it["session_id"].strip():
            out[it["session_id"]] = it
    return out


def _scope_rank(value: Any) -> Optional[int]:
    if not isinstance(value, str):
        return None
    return _SCOPE_RANK.get(value.strip().lower())


def _artifact_shas(artifacts: Iterable[Dict[str, Any]]) -> List[str]:
    return [a.get("sha256") if isinstance(a, dict) else None for a in artifacts]


def _derivative_fails(record: dict, artifacts: List[Any], seen: set) -> List[str]:
    """F19 item 13: a changed delivery byte needs its own review binding."""
    fails: List[str] = []
    bindings = {}
    raw = record.get("derivatives")
    for item in raw if isinstance(raw, list) else []:
        if isinstance(item, dict) and isinstance(item.get("sha256"), str):
            bindings[item["sha256"]] = item
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            continue
        transformed = bool(artifact.get("transformation")
                           or artifact.get("derivative_of")
                           or artifact.get("derivative") is True)
        if not transformed:
            continue
        sha = artifact.get("sha256")
        label = str(artifact.get("path") or artifact.get("kind") or "derivative")
        binding = bindings.get(sha) if isinstance(sha, str) else None
        if binding is None:
            fails.append(
                f"artifact {label!r} is a transformed/derivative delivery but the "
                "record carries no derivative binding for its sha256; the master's "
                "PASS does not certify changed delivered bytes")
            continue
        source = binding.get("from_sha256")
        if not (isinstance(source, str) and _HEX64.match(source)):
            fails.append(
                f"derivative binding for {label!r} carries no 64-hex from_sha256 "
                "(source bytes are not bound)")
        if not str(binding.get("transformation") or "").strip():
            fails.append(
                f"derivative binding for {label!r} names no transformation identity "
                "(crop/format conversion is unproven)")
        if isinstance(sha, str) and sha not in seen:
            fails.append(
                f"derivative sha256 {sha[:12]}... was not itself reviewed")
    return fails


def validate_review_record(record: Any, *, ledger: Any, author_session: Any,
                           artifacts: Iterable[Dict[str, Any]],
                           request_id: Optional[str] = None,
                           author_model: Optional[str] = None,
                           require_independence: bool = False,
                           require_model_independence: bool = False,
                           exact_artifact_set: bool = False,
                           expected_scope: Optional[str] = None,
                           min_scope: Optional[str] = None,
                           dispatch_id: Optional[str] = None,
                           require_attempt_identity: bool = False,
                           attempt_id: Optional[str] = None,
                           revision: Optional[str] = None,
                           prior_review: Optional[Dict[str, Any]] = None
                           ) -> List[str]:
    """Return the list of refusals; empty means the record is accepted.

    Every added condition is fail-closed and is only enforced when the caller
    declares the policy or the record itself makes the claim. An old caller
    that passes the original arguments keeps the original semantics plus the
    recognised-verdict and current-bytes checks.
    """
    if not isinstance(record, dict):
        return ["review record is absent or not an object"]
    fails: List[str] = []
    if record.get("schema") != SCHEMA:
        fails.append(f"review record schema is not {SCHEMA}")
    if verdict_of(record) is None:
        fails.append("review record carries no recognised successful verdict "
                     f"(need one of: {', '.join(VERDICTS)}); any verdict, or a "
                     "declared status, is not a pass")
    sessions = ledger_sessions(ledger)
    reviewer = record.get("reviewer_session")
    if not isinstance(reviewer, str) or not reviewer.strip():
        fails.append("review record names no reviewer_session")
    elif reviewer not in sessions:
        fails.append(f"reviewer session {reviewer!r} is not in the dispatch "
                     "ledger (a typed reviewer string is not an execution "
                     "the harness recorded)")
    elif reviewer == author_session:
        fails.append("reviewer session == author session (an artifact's "
                     "reviewer is never its author)")
    declared_author = record.get("author_session")
    if isinstance(declared_author, str) and declared_author.strip() \
            and isinstance(author_session, str) and author_session.strip() \
            and declared_author != author_session:
        fails.append(
            f"review record binds author {declared_author!r} but the artifact "
            f"author is {author_session!r} (identity mismatch)")
    model = record.get("reviewer_model")
    if not isinstance(model, str) or not model.strip():
        fails.append("review record names no reviewer_model")
    elif isinstance(reviewer, str) and sessions.get(reviewer, {}).get("model") \
            not in (None, model):
        fails.append("reviewer_model disagrees with the dispatch ledger's "
                     f"recorded model for session {reviewer!r}")
    entry = sessions.get(reviewer, {}) if isinstance(reviewer, str) else {}
    recorded_dispatch = entry.get("dispatch_id")
    declared_dispatch = record.get("dispatch_id")
    if dispatch_id is not None:
        if declared_dispatch != dispatch_id:
            fails.append(
                "review record does not echo the dispatch it was issued for "
                f"({declared_dispatch!r} != {dispatch_id!r})")
        if isinstance(recorded_dispatch, str) and recorded_dispatch.strip() \
                and declared_dispatch != recorded_dispatch:
            fails.append(
                f"review dispatch_id {declared_dispatch!r} disagrees with the "
                f"ledger's recorded dispatch {recorded_dispatch!r}")
    elif isinstance(declared_dispatch, str) and declared_dispatch.strip() \
            and isinstance(recorded_dispatch, str) and recorded_dispatch.strip() \
            and declared_dispatch != recorded_dispatch:
        fails.append("review dispatch_id disagrees with the dispatch ledger")
    if request_id is not None and record.get("request_id") != request_id:
        fails.append("review record does not echo the request it reviewed "
                     f"({record.get('request_id')!r} != {request_id!r})")
    reviewed = record.get("reviewed_artifacts")
    seen = set()
    for a in reviewed if isinstance(reviewed, list) else []:
        sha = a.get("sha256") if isinstance(a, dict) else None
        if isinstance(sha, str) and _HEX64.match(sha):
            seen.add(sha)
        else:
            fails.append("a reviewed_artifacts entry lacks a 64-hex sha256")
    if not seen:
        fails.append("review record lists no reviewed artifact sha256")
    shas = _artifact_shas(artifacts)
    if not shas:
        fails.append("the result has no artifacts: nothing was reviewed")
    for sha in shas:
        if sha not in seen:
            fails.append(f"artifact sha256 {str(sha)[:12]}... was not listed "
                         "as reviewed")

    # F19 item 6 - attempt/revision identity.
    current_attempt = record.get("attempt_id")
    current_revision = record.get("revision")
    if record.get("stale") is True:
        fails.append("review record is marked stale; a prior attempt's result "
                     "cannot certify the current attempt")
    if require_attempt_identity:
        if not (isinstance(current_attempt, str) and current_attempt.strip()):
            fails.append("the policy requires attempt identity and the review "
                         "record names no attempt_id")
        if attempt_id is not None and current_attempt != attempt_id:
            fails.append(
                f"review attempt_id {current_attempt!r} is not the current "
                f"attempt {attempt_id!r} (a prior attempt's result cannot "
                "survive a failure and be mistaken for this one)")
        if revision is not None and current_revision != revision:
            fails.append(
                f"review revision {current_revision!r} is not the current "
                f"revision {revision!r}")
    elif attempt_id is not None and isinstance(current_attempt, str) \
            and current_attempt.strip() and current_attempt != attempt_id:
        fails.append("review record was issued for a different attempt")

    # F19 items 1/3 - independence declaration and real model separation.
    independence = record.get("independent_review")
    claimed = independence is True or (
        isinstance(independence, str)
        and independence.strip().lower() in ("independent", "separate"))
    if (require_independence or require_model_independence) and not claimed:
        fails.append("the governing policy requires independent review and "
                     "the record does not declare it")
    if require_model_independence:
        if not (isinstance(author_model, str) and author_model.strip()):
            fails.append("the policy requires model independence but the "
                         "author model is unknown: separation cannot be proven")
        ledger_model = entry.get("model")
        if not (isinstance(ledger_model, str) and ledger_model.strip()):
            fails.append("the policy requires model independence but the "
                         "dispatch ledger records no model for the reviewer "
                         "session: separation cannot be proven")
        if isinstance(author_model, str) and author_model.strip() \
                and isinstance(model, str) and model.strip():
            if model.strip().lower() == author_model.strip().lower():
                fails.append("reviewer model == author model: a separate "
                             "session on the same configured model is not "
                             "model independence")

    # F19 item 2 - a weaker scope cannot close a stronger closure.
    wanted_scope = expected_scope if expected_scope is not None else min_scope
    if wanted_scope is not None:
        want_rank = _scope_rank(wanted_scope)
        if want_rank is None:
            fails.append(f"unknown expected review scope {wanted_scope!r}")
        else:
            have_rank = _scope_rank(record.get("scope"))
            if have_rank is None:
                fails.append("review record names no recognised scope; the "
                             f"{wanted_scope} closure requires one")
            elif have_rank < want_rank:
                fails.append(
                    f"a {record.get('scope')!r}-scope review cannot close the "
                    f"{wanted_scope!r} closure (an item cannot unlock generation "
                    "under a weaker rule than the stage that contains it)")

    # F19 item 4 - a reviewer that repaired the bytes cannot keep its verdict.
    repaired_by = record.get("repaired_by")
    if isinstance(repaired_by, str) and repaired_by.strip() \
            and repaired_by == reviewer:
        fails.append(
            "reviewer repaired the reviewed bytes and then certified them; its "
            "prior verdict does not cover the new bytes - a fresh decision from "
            "another reviewer is required")
    if isinstance(prior_review, dict):
        prior_reviewer = prior_review.get("reviewer_session")
        prior_shas = set()
        for a in (prior_review.get("reviewed_artifacts") or []):
            if isinstance(a, dict) and isinstance(a.get("sha256"), str):
                prior_shas.add(a["sha256"])
        current_shas = {sha for sha in shas if isinstance(sha, str)}
        if prior_reviewer == reviewer and current_shas != prior_shas:
            fails.append(
                "the prior verdict belongs to the same reviewer and covers "
                "different bytes; changed bytes need a fresh independent "
                "decision from another available reviewer")

    # F19 item 13 - derivatives.
    fails.extend(_derivative_fails(record, list(artifacts or []), seen))

    if exact_artifact_set:
        current = {sha for sha in shas if isinstance(sha, str)}
        extra = sorted(seen - current)
        if extra:
            fails.append("review record reviewed artifact(s) that are not the "
                         "current artifact set: "
                         + ", ".join(item[:12] + "..." for item in extra))
    return fails


def validate_review_closure(record: Any, *, scope: str, ledger: Any,
                            author_session: Any,
                            artifacts: Iterable[Dict[str, Any]],
                            policy: Optional[Dict[str, Any]] = None,
                            **kwargs) -> List[str]:
    """F19 item 2: the SAME semantic conditions close items and whole stages.

    ``scope`` is the closure being closed (asset/item/page/stage/launch).
    ``policy`` supplies the governing independence requirements - the same
    policy object is used for an item and for the stage that contains it.
    """
    policy = policy if isinstance(policy, dict) else {}
    require_independence = bool(policy.get("require_independent_review",
                                           policy.get("require_independence",
                                                      False)))
    require_model = bool(policy.get("require_model_independence", False))
    author_model = policy.get("author_model")
    kwargs.setdefault("expected_scope", scope)
    kwargs.setdefault("require_independence", require_independence)
    kwargs.setdefault("require_model_independence", require_model)
    kwargs.setdefault("author_model", author_model)
    return validate_review_record(record, ledger=ledger,
                                  author_session=author_session,
                                  artifacts=artifacts, **kwargs)


def validate_review_after_repair(record: Any, *, repaired_by: str,
                                 repaired_model: Optional[str] = None,
                                 ledger: Any, author_session: Any,
                                 artifacts: Iterable[Dict[str, Any]],
                                 prior_review: Optional[Dict[str, Any]] = None,
                                 **kwargs) -> List[str]:
    """F19 item 4: the corrected bytes need a decision from ANOTHER reviewer.

    A short handoff, not an endless loop: the caller re-runs the ONE validator
    on the repaired output with the repairing identity declared. The repairer's
    own verdict, or the same configured model, is refused.
    """
    kwargs.setdefault("require_independence", True)
    if repaired_model:
        kwargs.setdefault("require_model_independence", True)
        kwargs.setdefault("author_model", repaired_model)
    kwargs.setdefault("prior_review", prior_review)
    fails = validate_review_record(record, ledger=ledger,
                                   author_session=author_session,
                                   artifacts=artifacts, **kwargs)
    reviewer = record.get("reviewer_session") if isinstance(record, dict) else None
    model = record.get("reviewer_model") if isinstance(record, dict) else None
    if isinstance(reviewer, str) and reviewer == repaired_by:
        fails.append(
            "the repairing reviewer cannot certify the bytes it repaired; "
            "obtain the required independent final decision from another "
            "available reviewer")
    if repaired_model and isinstance(model, str) and model.strip().lower() == \
            repaired_model.strip().lower():
        fails.append(
            "the repairing model cannot certify the bytes it repaired; a "
            "separate configured model is required")
    return fails


def validate_image_review_criteria(evidence: Any, *, applicable: Iterable[str],
                                   kind: Optional[str] = None) -> List[str]:
    """F19 item 11: the Image Guide's thresholds, with no denominator shrink.

    Each applicable criterion scores at least 8; the prompt/image average is at
    least 8.5; auto-fails are zero. An applicable criterion that is omitted
    from the evidence is a refusal, not a smaller denominator.
    """
    fails: List[str] = []
    applicable = [str(c) for c in applicable if str(c).strip()]
    if not applicable:
        fails.append("no applicable criteria were declared: the review "
                     "denominator cannot be empty")
    if not isinstance(evidence, dict):
        return fails + ["image review evidence is absent or not an object"]
    declared_kind = evidence.get("kind")
    if kind is not None and declared_kind is not None and declared_kind != kind:
        fails.append(f"image review evidence is for {declared_kind!r}, not {kind!r}")
    raw = evidence.get("criteria")
    scores: Dict[str, float] = {}
    if isinstance(raw, dict):
        for key, value in raw.items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                scores[str(key)] = float(value)
    elif isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict) and isinstance(item.get("score"), (int, float)) \
                    and not isinstance(item.get("score"), bool):
                name = item.get("criterion") or item.get("id") or item.get("name")
                if name:
                    scores[str(name)] = float(item["score"])
    missing = [c for c in applicable if c not in scores]
    if missing:
        fails.append("applicable criteria omitted from the review evidence "
                     "(they do not leave the denominator): " + ", ".join(missing))
    below = [c for c in applicable if c in scores and scores[c] < 8]
    if below:
        fails.append("applicable criteria below 8: " + ", ".join(below))
    present = [scores[c] for c in applicable if c in scores]
    if present:
        average = sum(present) / len(present)
        if average < 8.5:
            fails.append(f"criteria average {average:.2f} is below 8.5")
    else:
        fails.append("no criterion scores were present: average is unproven")
    autofails = evidence.get("autofails", evidence.get("triggered_autofails",
                                                       evidence.get("auto_fails")))
    if autofails:
        fails.append("auto-fails are present; the Image Guide requires zero")
    return fails


def repair_budget(attempts: Any, *, max_repairs: int = 3) -> Dict[str, Any]:
    """F19 item 12: failed-only repairs, stop on the first PASS.

    ``attempts`` is the ordered review history: each item is a dict with a
    ``result``/``verdict`` or a plain string. Returns
    ``{"action": "stop_pass"|"repair"|"escalate", "reviews": n, "reason": ...}``.
    """
    history = list(attempts) if isinstance(attempts, (list, tuple)) else []
    reviews = 0
    failures = 0
    for item in history:
        reviews += 1
        verdict = verdict_of(item) if isinstance(item, dict) else (
            item.strip().lower() if isinstance(item, str) else None)
        if verdict is not None:
            return {"action": "stop_pass", "reviews": reviews,
                    "reason": "a PASS was recorded; stop reviewing accepted work"}
        failures += 1
    if failures > max_repairs:
        return {"action": "escalate", "reviews": reviews,
                "reason": f"{failures} failed repairs exceed the {max_repairs}-attempt limit"}
    return {"action": "repair" if failures else "stop_pass", "reviews": reviews,
            "reason": ("continue unaffected work" if failures
                       else "no failed attempt to repair")}


def validate_repair_budget(attempts: Any, *, max_repairs: int = 3) -> List[str]:
    """Refusals for a review history that must not re-review accepted work."""
    history = list(attempts) if isinstance(attempts, (list, tuple)) else []
    fails: List[str] = []
    passed_at = None
    for index, item in enumerate(history, start=1):
        verdict = verdict_of(item) if isinstance(item, dict) else (
            item.strip().lower() if isinstance(item, str) else None)
        if verdict is not None:
            passed_at = index
            break
    if passed_at is not None and passed_at != len(history):
        fails.append("a PASS was recorded before later reviews: accepted work "
                     "must not be repeatedly reviewed to chase 10/10")
    if passed_at is None and len(history) > max_repairs:
        fails.append(f"{len(history)} failed repair/recheck attempts exceed "
                     f"the {max_repairs}-attempt limit; escalate under the "
                     "existing stricter rules")
    return fails


def validate_upload_waiver(waiver: Any, *,
                           required_scope: str = "graphics_upload_waiver",
                           test_only: bool = False,
                           now: Optional[str] = None) -> List[str]:
    """F19 items 5/14: a waiver must be an F20-scoped authoritative approval.

    A local ``waiver: true`` or an empty auto-fail list is not authority. The
    value must be the result of the approval verifier (``approval_record.verify``
    output): ok, approval id, a recognised kind, a 64-hex plan hash, a scope
    that covers the requested waiver, a live verification class and an
    unexpired, unrevoked record.
    """
    fails: List[str] = []
    if not isinstance(waiver, dict):
        return ["upload waiver is absent or not an approval record "
                "(a local flag is not F20-scoped authority)"]
    if waiver.get("ok") is not True:
        fails.append("upload waiver is not a verified approval")
    if not str(waiver.get("approval_id") or "").strip():
        fails.append("upload waiver names no approval_id")
    if not str(waiver.get("plan_hash") or "").strip():
        fails.append("upload waiver is bound to no plan hash")
    try:
        # Same package, resolved by path so an import path cannot pick up a
        # different (or planted) module of the same name.
        import importlib.util as _ilu
        _path = Path(__file__).with_name("approval_record.py")
        _spec = _ilu.spec_from_file_location("_approval_record_for_waiver", str(_path))
        _approval = _ilu.module_from_spec(_spec)
        _spec.loader.exec_module(_approval)  # type: ignore[union-attr]
        kind = _approval.canonical_kind(waiver.get("kind"))
        if kind is None:
            fails.append("upload waiver names an unknown approval kind")
        scopes = _approval.normalize_scope(waiver.get("scope")) or []
    except Exception:  # noqa: BLE001 - a missing verifier fails closed
        fails.append("upload waiver cannot be checked: the F20 approval verifier "
                     "is unavailable (fail closed)")
        kind = None
        raw = waiver.get("scope")
        scopes = [raw] if isinstance(raw, str) else list(raw or [])
    if required_scope not in scopes:
        fails.append(f"upload waiver scope does not cover {required_scope!r}")
    verification = waiver.get("verification_class")
    if test_only:
        if verification not in ("local_test_record",) + _AUTHENTICATED_CLASSES:
            fails.append("test-only upload waiver has no recognised verification class")
    elif verification not in _AUTHENTICATED_CLASSES:
        fails.append("upload waiver is not an authenticated authority record "
                     f"(verification_class={verification!r}); a local test "
                     "record cannot waive production delivery")
    if waiver.get("revoked") is not False:
        fails.append("upload waiver is revoked or its revocation state is unknown")
    expires = waiver.get("expires_at")
    if not isinstance(expires, str) or not expires.strip():
        fails.append("upload waiver has no expiry")
    elif now is not None and expires <= now:
        fails.append("upload waiver is expired")
    return fails


def validate_delivery_admission(result: Any, *, ledger: Any,
                                author_session: Any,
                                artifacts: Iterable[Dict[str, Any]],
                                policy: Optional[Dict[str, Any]] = None,
                                waiver: Any = None,
                                required_waiver_scope: str = "graphics_upload_waiver",
                                **kwargs) -> List[str]:
    """F19 item 5/14: a wrapper result cannot launder a checkpoint into a page.

    A ``locally_verified`` copy checkpoint remains a checkpoint. A skip-images
    or upload waiver is only admissible through the F20-scoped authority.
    """
    if not isinstance(result, dict):
        return ["wrapper result is absent or not an object"]
    fails: List[str] = []
    claimed = str(result.get("completion") or result.get("stage") or "").lower()
    if result.get("locally_verified") is True and claimed in (
            "page", "design", "complete", "completed", "final", "published"):
        fails.append(
            "a locally_verified copy checkpoint is not a completed designed "
            "page; checkpoint evidence cannot launder a page into completion")
    waiver_items = [waiver] if waiver is not None else []
    for key in ("upload_waiver", "skip_images_waiver", "skip_images"):
        if result.get(key) is not None:
            waiver_items.append(result.get(key))
    if waiver_items:
        for item in waiver_items:
            fails.extend(validate_upload_waiver(
                item, required_scope=required_waiver_scope,
                test_only=bool(kwargs.get("test_only"))))
    elif result.get("skip_images") is True:
        fails.append("skip_images is asserted without an F20-scoped approval")
    review = result.get("review_record")
    if review is None:
        fails.append("wrapper result carries no review record: a local flag "
                     "cannot establish independent review")
    else:
        fails.extend(validate_review_closure(
            review, scope=str(result.get("scope") or "page"),
            ledger=ledger, author_session=author_session, artifacts=artifacts,
            policy=policy if isinstance(policy, dict) else {},
            **{k: v for k, v in kwargs.items() if k != "test_only"}))
    return fails


def main(argv: List[str]) -> int:
    if len(argv) != 4:
        print("usage: review_record.py <record.json> <ledger.json> "
              "<result.json>")
        return 3
    rec, led, res = (json.load(open(p, encoding="utf-8")) for p in argv[1:])
    fails = validate_review_record(
        rec, ledger=led, author_session=res.get("author_session"),
        artifacts=res.get("artifacts") or [], request_id=res.get("request_id"))
    print("\n".join(fails) or "review record accepted")
    return 2 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
