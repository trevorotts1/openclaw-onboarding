#!/usr/bin/env python3
"""
canonical_decline.py — the ONE shared reader for owner department decisions.

SINGLE SOURCE OF TRUTH (Issue #2 / Bulletproofing a): the provenance-gated
decline model was previously duplicated in THREE places — build-workforce.py
(_canonical_decline_set), department-floor.py (declined_set) and
qc-interview-completion.py (check_decline_provenance). The copies drifted: the
builder stored RAW ids and tested `cid in declined` against them, while the
floor checker NORMALIZED ids (strip hyphens, lowercase). A decline recorded as
"Video" or "billing_finance" therefore passed the floor gate (which normalized)
but was IGNORED by the builder (which did not), silently OVER-PROVISIONING the
box — the decline-normalization mismatch vector. This module is imported by ALL of them so
the normalization and the provenance rule can never drift again.

PROVENANCE-GATED DECLINE MODEL:
A decline ("no") is ONLY honored when it carries an explicit, attributable
owner-decision record. The default (provenance absent) is NO decline — fail-safe
to the LARGER floor. Accepted forms:

  1. decisions[cid] OBJECT form {decision:"no", source, decidedAt, decidedBy}
     — all four fields required (the shape record-dept-decision.sh writes).
  2. canonicalReconciliation.ownerDeclineConfirmed == true + decisions[cid]=="no"
     (bare string honored under the block-level owner gate, backward-compat).
  3. declinedDepartments[] DICT entry with a per-entry provenance TRIPLE
     {id, decidedBy, decidedAt} — read from BOTH the canonicalReconciliation
     block AND the build-state top level. Each dict self-attributes its decline,
     so a complete triple is honored WITHOUT the block-level ownerDeclineConfirmed
     flag (the finalize-directive shape). A dict missing any of id/decidedBy/
     decidedAt is REJECTED and its dept STAYS in the floor (fail-safe).
  4. canonicalReconciliation.ownerDeclineConfirmed == true + declinedDepartments[]
     BARE STRING entries (flat list honored under the block-level owner gate).

ALL ids returned by this module are NORMALIZED via norm() so every caller
compares in the SAME normalized space.

Import-safe and dependency-free (stdlib re/sys only). Read-only. Never writes.
"""

import re
import sys

# The three decision tokens the interview records for every canonical / custom
# department (record-dept-decision.sh --decision yes|no|later). Only "no"
# shrinks the floor; "yes"/"later" are BUILD-NOW (Issue #7) and never subtract.
VALID_DECISIONS = ("yes", "no", "later")

# Provenance fields the OBJECT form must carry for a "no" to be honored.
_REQUIRED_PROVENANCE = ("decision", "source", "decidedAt", "decidedBy")


def norm(s):
    """Normalize a slug for membership comparison: lowercase, strip every
    non-alphanumeric char (so 'Video', 'video', 'billing_finance' and
    'billing-finance' all collapse to a single comparable token). IDENTICAL to
    department-floor._norm — that identity is the whole point of this module."""
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def analyze(build_state, quiet=False):
    """
    Parse a build-state's canonicalReconciliation into a single normalized view.

    Returns a dict:
      {
        "decided":    {norm_id: "yes"|"no"|"later"},   # provenanced/honored decisions
        "declined":   set(norm_id),                    # honored "no" declines
        "later":      set(norm_id),                    # honored "later" decisions
        "yes":        set(norm_id),                    # honored "yes" decisions
        "rejections": [ {"id": raw, "reason": str} ],  # "no"s dropped for missing provenance
      }

    `decided` covers ONLY provenanced decisions (object form with all four
    provenance fields, OR bare string under ownerDeclineConfirmed). An
    un-provenanced "yes"/"later" bare string does NOT count as a covered
    decision (used by the decision-completeness gate, Issue #3).
    """
    bs = build_state or {}
    recon = bs.get("canonicalReconciliation", {})
    if not isinstance(recon, dict):
        recon = {}
    owner_confirmed = bool(recon.get("ownerDeclineConfirmed"))

    decided = {}
    declined = set()
    later = set()
    yes = set()
    rejections = []

    def _warn(msg):
        if not quiet:
            print(msg, file=sys.stderr)

    decisions = recon.get("decisions", {})
    if isinstance(decisions, dict):
        for cid, decision in decisions.items():
            ncid = norm(cid)
            if isinstance(decision, dict):
                dval = str(decision.get("decision", "")).strip().lower()
                has_provenance = all(decision.get(k) for k in _REQUIRED_PROVENANCE)
                if dval in VALID_DECISIONS and has_provenance:
                    decided[ncid] = dval
                    if dval == "no":
                        declined.add(ncid)
                    elif dval == "later":
                        later.add(ncid)
                    elif dval == "yes":
                        yes.add(ncid)
                elif dval == "no":
                    rejections.append({"id": str(cid).strip(),
                                       "reason": "object 'no' missing provenance "
                                                 "(need decision/source/decidedAt/decidedBy)"})
                    _warn(
                        f"[DECLINE REJECTED] '{str(cid).strip()}' decisions entry is missing "
                        f"provenance fields (need decision/source/decidedAt/decidedBy). "
                        f"Decline IGNORED — dept stays in floor (fail-safe). "
                        f"Provide owner-interview attribution to honor this decline.")
            else:
                sval = str(decision).strip().lower()
                if sval not in VALID_DECISIONS:
                    continue
                if owner_confirmed:
                    decided[ncid] = sval
                    if sval == "no":
                        declined.add(ncid)
                    elif sval == "later":
                        later.add(ncid)
                    elif sval == "yes":
                        yes.add(ncid)
                elif sval == "no":
                    rejections.append({"id": str(cid).strip(),
                                       "reason": "bare string 'no' without ownerDeclineConfirmed"})
                    _warn(
                        f"[DECLINE REJECTED] '{str(cid).strip()}' has bare string decision='no' "
                        f"without ownerDeclineConfirmed=true on the canonicalReconciliation block. "
                        f"Decline IGNORED — dept stays in floor (fail-safe). "
                        f"Set ownerDeclineConfirmed=true or use object-form provenance.")

    # declinedDepartments[] appears in the wild at TWO build-state levels and must
    # be read from BOTH — reading only the top level silently ignored the whole
    # finalize-directive decline set (the C1 silent-ignore bug):
    #   * canonicalReconciliation.declinedDepartments — the finalize-directive shape:
    #       a list of DICT entries {id, name, reason, decidedBy, decidedAt}.
    #   * declinedDepartments (build-state top level) — the legacy flat form.
    flat_sources = []
    recon_flat = recon.get("declinedDepartments", []) if isinstance(recon, dict) else []
    if isinstance(recon_flat, list):
        flat_sources.extend(recon_flat)
    top_flat = bs.get("declinedDepartments", [])
    if isinstance(top_flat, list):
        flat_sources.extend(top_flat)

    for entry in flat_sources:
        if isinstance(entry, dict):
            # DICT entry — the finalize directive attributes EACH decline in place.
            # A complete per-entry provenance TRIPLE (id + decidedBy + decidedAt,
            # all non-empty) honors the decline WITHOUT the block-level
            # ownerDeclineConfirmed flag. A malformed dict (any of the three
            # missing/empty) is REJECTED and the dept STAYS in the floor — a bad
            # entry must never shrink the mandatory floor (fail-safe).
            eid = str(entry.get("id", "")).strip()
            has_triple = (
                bool(eid)
                and bool(str(entry.get("decidedBy", "")).strip())
                and bool(str(entry.get("decidedAt", "")).strip())
            )
            if has_triple:
                ncid = norm(eid)
                declined.add(ncid)
                decided.setdefault(ncid, "no")
            elif owner_confirmed and eid:
                # Backward-compat: the block-level owner gate still honors an
                # id-bearing dict entry even without the per-entry triple.
                ncid = norm(eid)
                declined.add(ncid)
                decided.setdefault(ncid, "no")
            else:
                rejections.append({"id": eid or "<no-id>",
                                   "reason": "declinedDepartments[] dict entry missing provenance "
                                             "triple (need id/decidedBy/decidedAt) and no ownerDeclineConfirmed"})
                _warn(
                    f"[DECLINE REJECTED] declinedDepartments[] dict entry '{eid or '<no-id>'}' is "
                    f"missing its per-entry provenance triple (id/decidedBy/decidedAt) and "
                    f"ownerDeclineConfirmed is not true. Decline IGNORED — dept stays in floor "
                    f"(fail-safe). Provide id+decidedBy+decidedAt to honor this decline.")
        else:
            # BARE STRING entry — stays gated on the block-level owner flag exactly
            # as before (a fabricated flat string list must not silently shrink the
            # floor). Honored only under ownerDeclineConfirmed=true.
            sval = str(entry).strip()
            if not sval:
                continue
            if owner_confirmed:
                ncid = norm(sval)
                declined.add(ncid)
                decided.setdefault(ncid, "no")
            else:
                rejections.append({"id": sval,
                                   "reason": "declinedDepartments[] bare string without ownerDeclineConfirmed"})
                _warn(
                    f"[DECLINE REJECTED] declinedDepartments[] bare string '{sval}' without "
                    f"ownerDeclineConfirmed=true. Decline IGNORED — dept stays in floor (fail-safe). "
                    f"Use a dict entry with id+decidedBy+decidedAt provenance, or set "
                    f"ownerDeclineConfirmed=true.")

    return {
        "decided": decided,
        "declined": declined,
        "later": later,
        "yes": yes,
        "rejections": rejections,
    }


def canonical_decline_set(build_state, quiet=False):
    """Return the set of NORMALIZED canonical ids the owner PROVENANCE-DECLINED.
    The single reader both build-workforce.py and department-floor.py call."""
    return analyze(build_state, quiet=quiet)["declined"]


def decline_rejections(build_state):
    """Return the list of un-provenanced declines that were REJECTED (ignored)."""
    return analyze(build_state, quiet=True)["rejections"]


def later_set(build_state):
    """Return the set of NORMALIZED 'later' ids. NOTE: 'later' is BUILD-NOW
    (Issue #7) — this set is provided for auditing/receipts, NOT for exclusion."""
    return analyze(build_state, quiet=True)["later"]


def decision_coverage(build_state, expected_ids):
    """
    Issue #3 decision-completeness. Given the EXPECTED department id set
    (mandatory + universal-primary + customs), return:
        (missing_ids: list, covered_ids: list)
    where `missing_ids` are the expected ids that have NO provenanced yes/no/later
    decision recorded. `expected_ids` may be raw (they are normalized here).
    Deterministic (sorted) output.
    """
    view = analyze(build_state, quiet=True)
    decided = view["decided"]
    missing = []
    covered = []
    seen = set()
    for raw in expected_ids:
        ncid = norm(raw)
        if ncid in seen:
            continue
        seen.add(ncid)
        if ncid in decided:
            covered.append(raw)
        else:
            missing.append(raw)
    return sorted(missing), sorted(covered)
