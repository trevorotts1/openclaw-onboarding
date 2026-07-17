#!/usr/bin/env python3
"""
unit_status_core.py -- logic engine for `unit-status.sh <unit-id>`.

THE DISEASE this tool exists to make structurally unreachable: status
asserted from a NAME or a POINTER instead of DIFFED from CONTENT. Every
function below either (a) independently re-derives a fact from git/GitHub
API truth, or (b) explicitly labels a fact INFERRED (derived from a citation
inside ledger prose, but then INDEPENDENTLY VERIFIED against live git -- the
citation is only ever used to know WHERE to look, never trusted on its own).
Nothing in this file trusts a ledger row's own status cell, ever. See
resolve_unit() for the top-level algorithm and its docstring for the two
historical cases (U108, U79) this file's tests must reproduce.

Reuses shared-utils/ledger_reconciler_core.py for the leg-requirement-tag
parsing regexes (LEG_TAG_RE / COMPOUND_LEG_TAG_RE) and the low-level git
helpers (sh/sh_ok/find_merge_commit_for_tip/nearest_tag_containing) --
those are already the validated, battle-tested convention for this exact
ledger's row shape (see that file's own docstrings for the empirical
evidence behind each regex). Duplicating that logic here would itself be a
disease vector (two parsers that can silently drift apart).
"""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location(
    "ledger_reconciler_core", _HERE / "ledger_reconciler_core.py"
)
assert _spec is not None and _spec.loader is not None
lrc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(lrc)  # type: ignore

sh = lrc.sh
sh_ok = lrc.sh_ok
find_merge_commit_for_tip = lrc.find_merge_commit_for_tip
nearest_tag_containing = lrc.nearest_tag_containing
parse_leg_requirement = lrc.parse_leg_requirement
parse_compound_leg_primary = lrc.parse_compound_leg_primary

UNIT_ROW_RE = re.compile(r"^\|\s*(U\d+)\s*\|")
BACKTICK_RE = re.compile(r"`([^`]+)`")
# A candidate git SHA cited in ledger prose: pure lowercase/uppercase hex,
# 7-40 chars, inside backticks. Deliberately excludes tags (`v6.0.55` fails
# this -- starts with 'v') and branch names (contain '/', '-', letters
# outside a-f) so it never over-matches those as SHAs.
SHA_TOKEN_RE = re.compile(r"^[0-9a-fA-F]{7,40}$")

REPO_LABELS = {
    "onb": "openclaw-onboarding",
    "cc": "blackceo-command-center",
}

# Non-repo leg tokens recognized inside a flat, un-parenthesized "+"-joined
# compound leg tag (e.g. "ONB + live", "CC + live", "ONB + n8n", "n8n + ONB",
# "ONB + GHL") -- see resolve_required_legs()'s '+' branch. Each names a leg
# this tool cannot git-check at all (proven by execution/live-run, never by
# a branch/merge), so a component that IS one of these is flagged OWED, not
# silently dropped. This set is deliberately used ONLY to classify '+'-
# joined parts, never to reclassify an existing bare single-token tag
# (e.g. a lone "(n8n, ...)" row keeps its pre-existing classification --
# widening that is a separate, out-of-scope decision this fix does not make).
NON_REPO_LEG_TOKENS = frozenset({"live", "read-only", "n8n", "ghl", "n/a", "na", "doc", "none"})


# --------------------------------------------------------------------------
# Ledger row lookup
# --------------------------------------------------------------------------

def find_ledger_row(ledger_paths, unit_id):
    """Search every given ledger file, in order, for a row starting with
    `| <unit_id> |`. Returns (path, full_row_text) for the FIRST match, or
    (None, None) if no ledger anywhere has a row for this unit id. Never
    guesses a row from a partial/fuzzy match."""
    for path in ledger_paths:
        p = Path(path)
        if not p.is_file():
            continue
        text = p.read_text(errors="replace")
        for line in text.splitlines():
            m = UNIT_ROW_RE.match(line)
            if m and m.group(1) == unit_id:
                return str(p), line
    return None, None


def find_sibling_rows_mentioning(ledger_paths, unit_id):
    """Every OTHER unit's row, in every given ledger file, whose raw text
    contains unit_id as a whole word (not a substring of a longer token --
    e.g. a row mentioning "U108" must not match on "U1080"). This is the
    generalized form of 'follow spec cross-references': the real U108 case
    is resolved because U108's OWN row already cites U110's branch/SHAs,
    but a differently-shaped future case might only be documented on the
    OTHER unit's row (U110 mentioning U108) -- so both directions are
    searched. Returns a list of (path, unit_id_of_row, full_row_text)."""
    token_re = re.compile(rf"\b{re.escape(unit_id)}\b")
    out = []
    for path in ledger_paths:
        p = Path(path)
        if not p.is_file():
            continue
        text = p.read_text(errors="replace")
        for line in text.splitlines():
            m = UNIT_ROW_RE.match(line)
            if not m:
                continue
            row_uid = m.group(1)
            if row_uid == unit_id:
                continue
            if token_re.search(line):
                out.append((str(p), row_uid, line))
    return out


# --------------------------------------------------------------------------
# Leg-requirement resolution (never from a branch name -- from the row's
# own leg-tag column, §E.2's "Repo/surface" declaration)
# --------------------------------------------------------------------------

def resolve_required_legs(description):
    """Returns (legs, mode, note) where legs is a subset of {"onb","cc"},
    mode is one of "both" / "single" / "compound" / "zero-leg" / "unknown",
    and note explains the classification. NEVER returns legs=None silently
    -- "unknown" with an empty legs set is the fail-closed default for a tag
    shape this function cannot classify, forcing the caller to print
    UNKNOWN rather than guess DONE or NOT-DONE."""
    if not description:
        return set(), "unknown", "empty description column -- cannot read a leg tag at all."

    compound_primary = parse_compound_leg_primary(description)
    if compound_primary:
        primary_key = "onb" if compound_primary == "ONB" else "cc"
        return (
            {primary_key},
            "compound",
            f"compound leg tag (primary={compound_primary}); only the PRIMARY leg is "
            f"mechanically required by this tool -- the parenthesized '(+...)' secondary "
            f"hint has no consistent grammar across rows and is not independently checked.",
        )

    tag = parse_leg_requirement(description)
    if tag is None:
        return set(), "unknown", "leg tag does not match the '(<tag>, P#)' convention at all."

    tag_l = tag.strip().lower()
    if tag_l == "both":
        return {"onb", "cc"}, "both", "literal '(both, ...)' tag -- both repo legs required."
    if tag_l == "onb":
        return {"onb"}, "single", "literal '(ONB, ...)' tag -- openclaw-onboarding leg only."
    if tag_l == "cc":
        return {"cc"}, "single", "literal '(CC, ...)' tag -- blackceo-command-center leg only."

    # A DIFFERENT compound shape than parse_compound_leg_primary()'s
    # parenthesized "(CC (+ONB), ...)" form above: a flat, un-parenthesized
    # "+"-joined tag like "ONB + live" / "CC + live" / "ONB + n8n" /
    # "n8n + ONB" / "ONB + GHL". THE BUG this branch fixes: the substring
    # check below ("live" in tag_l) used to fire on this shape too --
    # "live" IS a substring of "onb + live" -- so a tag like "ONB + live"
    # fell straight into the zero-leg return, meaning NO repo git check ran
    # at all and the verdict fell through to trusting the ledger's own
    # status cell (resolve_unit()'s zero-leg branch). That is exactly the
    # disease this tool exists to make unreachable: status asserted from a
    # ledger claim instead of diffed from content. Every "+"-joined part
    # that names a real repo (onb/cc) MUST be mechanically required and
    # independently git-checked -- never silently collapsed to zero legs.
    if "+" in tag_l:
        parts = [p.strip() for p in tag_l.split("+")]
        repo_parts = [p for p in parts if p in ("onb", "cc")]
        other_parts = [p for p in parts if p not in ("onb", "cc")]
        if repo_parts:
            legs = set(repo_parts)
            return (
                legs,
                "compound",
                f"flat '+'-joined compound leg tag '{tag}' -- repo leg(s) {sorted(legs)} are "
                f"ALL mechanically required and independently git-checked by this tool "
                f"(never collapsed to zero-leg); non-repo component(s) {other_parts} are "
                f"flagged OWED separately -- proven by execution/live-run (e.g. live/n8n/GHL), "
                f"never by this tool's git check and never by trusting the ledger's own status "
                f"cell for that component.",
            )
        # No onb/cc token among the '+'-joined parts. This is legitimately
        # zero-repo-leg ONLY if every part is a recognized non-repo token --
        # an unrecognized part could be a garbled/mistyped repo token, and
        # defaulting THAT to zero-leg silently would resurrect the exact
        # bug this branch exists to kill. Fail loud instead of guessing.
        if all(p in NON_REPO_LEG_TOKENS for p in parts):
            return (
                set(),
                "zero-leg",
                f"flat '+'-joined compound leg tag '{tag}' -- every component ({parts}) is a "
                f"recognized non-repo (live/doc/evidence-only) token; no repo leg present -- "
                f"no branch/merge to check.",
            )
        return (
            set(),
            "unknown",
            f"leg tag '{tag}' is a '+'-joined compound but at least one component is neither "
            f"a repo token (onb/cc) nor a recognized non-repo token "
            f"({sorted(NON_REPO_LEG_TOKENS)}) -- refusing to guess zero-leg or a repo leg.",
        )

    if "live" in tag_l or "read-only" in tag_l or tag_l in ("n/a", "na", "doc", "none"):
        return set(), "zero-leg", f"leg tag '{tag}' declares a non-repo (live/doc/evidence-only) unit -- no branch/merge to check."
    return set(), "unknown", f"leg tag '{tag}' does not match any known convention (both/ONB/CC/compound/zero-leg)."


# --------------------------------------------------------------------------
# Branch discovery (own-named branch ONLY -- the "obvious" check; never the
# sole source of truth, see resolve_leg() below for the cross-reference
# fallback this alone would miss)
# --------------------------------------------------------------------------

def list_all_remote_branches(repo_dir):
    out = sh(repo_dir, ["branch", "-r"])
    names = []
    for line in out.splitlines():
        line = line.strip()
        if "->" in line or not line.startswith("origin/"):
            continue
        names.append(line[len("origin/"):])
    return names


def find_own_named_branch(repo_dir, unit_id, prefix="skill6-v2/"):
    """Exact `<prefix><unit_id>` or a disambiguated `<prefix><unit_id>-...`
    suffix variant (same convention as ledger_reconciler_core's
    _any_branch_for_unit -- the char after the id must be non-digit, so
    `skill6-v2/U590` is never mistaken for `skill6-v2/U59`). Returns the
    matched branch name, or None."""
    all_branches = list_all_remote_branches(repo_dir)
    exact = f"{prefix}{unit_id}"
    if exact in all_branches:
        return exact
    suffix_prefix = exact + "-"
    for b in all_branches:
        if b.startswith(suffix_prefix):
            return b
    return None


# Branch-name namespaces PROVEN (empirically re-derived, not assumed -- see
# this module's own test suite) to run their OWN, unrelated unit-numbering
# scheme, colliding with skill6's U<n> ids. `skill62/*` (the cinematic web
# funnel engine build, `skill62/ce-U1`..`skill62/ce-U20` at last count) is
# the one concretely confirmed: `skill62/ce-U15` is a DIFFERENT skill's own
# "U15", nothing to do with skill6's U15 (the shipped-inside-`chainA` unit).
# A DELIMITED-TOKEN regex alone (bounded by non-alnum on both sides) is NOT
# sufficient to avoid this collision -- "ce-U15" satisfies a delimiter check
# too ('-' before, string-end after). This exclusion list is the honest fix:
# there is no general, purely-syntactic way to tell "this branch's U15
# means skill6's U15" from "this branch's U15 means skill62's own U15"
# (ledger_reconciler_core.py's COMPOUND_LEG_TAG_RE docstring reaches the
# same conclusion and rejects a token scan entirely for that reason -- this
# tool instead narrows the scan to exclude the one namespace concretely
# proven to collide, and additionally refuses to silently pick a winner
# when more than one candidate remains after that exclusion; see
# token_scan_any_branch()'s multi-hit handling in resolve_leg()).
FOREIGN_NAMESPACE_PREFIXES = ("skill62/",)


def token_scan_any_branch(repo_dir, unit_id):
    """Whole-repo, whole-branch-list scan for the unit id as a delimited
    token (bounded by /, -, _, or string edges) ANYWHERE in a branch name,
    not just under the canonical prefix -- catches non-namespaced branches
    like `u79-gk17-cc-anthology-selfheal-banner`. Excludes branches under a
    FOREIGN_NAMESPACE_PREFIXES prefix (see that constant's docstring for
    the concrete, empirically-confirmed collision this guards against --
    `skill62/ce-U15` vs skill6's own U15). A delimiter check alone does
    NOT catch that collision (proven by this module's own test suite);
    namespace exclusion is the actual fix. Returns ALL surviving matches,
    plural -- callers must NOT assume the list has at most one entry and
    must handle ambiguity explicitly rather than silently taking hits[0]."""
    tok = re.escape(unit_id)
    pat = re.compile(rf"(?:^|[^0-9A-Za-z]){tok}(?:[^0-9A-Za-z]|$)", re.IGNORECASE)
    hits = []
    for b in list_all_remote_branches(repo_dir):
        if any(b.startswith(p) for p in FOREIGN_NAMESPACE_PREFIXES):
            continue
        if pat.search(b):
            hits.append(b)
    return hits


# --------------------------------------------------------------------------
# Cross-reference citation extraction (the "follow spec cross-references"
# requirement -- U108's CC leg has no `skill6-v2/U108` branch in CC, but
# U108's OWN ledger row cites the exact commit/branch/tag it shipped under
# inside skill6-v2/U110. This never trusts the citation's surrounding prose
# ("confirmed merged", "verified") -- it only extracts CANDIDATE SHAs from
# the citing text, then independently re-derives ancestry/merge-commit/tag
# from git for each candidate. A citation that doesn't independently verify
# is discarded, not trusted.)
# --------------------------------------------------------------------------

def extract_candidate_shas(text):
    """Every backtick-quoted token in `text` that is pure hex, 7-40 chars
    (so it looks like a git SHA and NOT a tag ('v6.0.55') or a branch name
    ('skill6-v2/U110') or a PR number). De-duplicated, order-preserved."""
    seen = []
    for tok in BACKTICK_RE.findall(text or ""):
        tok = tok.strip()
        if SHA_TOKEN_RE.match(tok) and tok not in seen:
            seen.append(tok)
    return seen


def verify_candidate_sha(repo_dir, sha):
    """Independently confirm `sha` (short or full) is a real commit in
    repo_dir AND an ancestor of that repo's origin/main. Returns a dict
    with full_sha/is_ancestor/merge_sha/tag on success, or None if `sha`
    does not even resolve to a commit in this repo (e.g. it belongs to the
    OTHER repo, or is a typo/PR-number/tag mis-parsed as hex)."""
    ok, full_sha, _ = sh_ok(repo_dir, ["rev-parse", "--verify", "-q", f"{sha}^{{commit}}"])
    if not ok or not full_sha:
        return None
    full_sha = full_sha.strip()
    is_anc_ok, _, _ = sh_ok(repo_dir, ["merge-base", "--is-ancestor", full_sha, "origin/main"])
    entry = {"cited_sha": sha, "full_sha": full_sha, "is_ancestor_of_main": bool(is_anc_ok)}
    if is_anc_ok:
        merge_sha = find_merge_commit_for_tip(repo_dir, full_sha, "origin/main")
        if not merge_sha:
            # full_sha may itself already BE the direct-parent merge target of some
            # later commit, or it may be an ancestor several hops back (e.g. a
            # commit cited mid-branch, not the branch tip). Either way, walk
            # forward: find the nearest commit on main that has full_sha as an
            # ancestor via rev-list and treat the first such (topologically
            # earliest) as its landing point for tag lookup purposes.
            merge_sha = full_sha if sh_ok(repo_dir, ["merge-base", "--is-ancestor", full_sha, "origin/main"])[0] else None
        entry["merge_sha"] = merge_sha
        entry["tag"] = nearest_tag_containing(repo_dir, merge_sha) if merge_sha else None
    else:
        entry["merge_sha"] = None
        entry["tag"] = None
    return entry


def resolve_leg_via_citations(repo_dir, repo_label, unit_id, citation_pool):
    """citation_pool: list of (source_label, text) pairs to pull candidate
    SHAs from (this unit's own row, PLUS every sibling row that mentions
    this unit's id token). Returns a list of VERIFIED hits (each carrying
    which source cited it), sorted with ancestor-confirmed hits first."""
    hits = []
    seen_shas = set()
    for source_label, text in citation_pool:
        for cand in extract_candidate_shas(text):
            if cand in seen_shas:
                continue
            result = verify_candidate_sha(repo_dir, cand)
            if result is None:
                continue  # doesn't even resolve in this repo -- likely belongs to the other repo
            seen_shas.add(cand)
            result["source"] = source_label
            result["repo"] = repo_label
            hits.append(result)
    hits.sort(key=lambda h: not h["is_ancestor_of_main"])
    return hits


# --------------------------------------------------------------------------
# Per-leg resolution (the core "is this leg REALLY done" algorithm)
# --------------------------------------------------------------------------

def resolve_leg(repo_dir, repo_label, unit_id, ledger_paths, own_row_text, prefix="skill6-v2/"):
    """Returns a dict:
      satisfied: True / False / None (None == UNKNOWN, never guessed)
      proved: True (own-named branch, or broad token-scan branch, directly
               observed merged) / False (satisfied only via an INFERRED
               cross-reference citation) / None (not satisfied, N/A)
      method: "own-branch" | "cross-reference" | "token-scan" | "none-found"
      evidence: human-readable evidence trail
      raw: supporting data (branch name / sha / merge_sha / tag / citations)
    """
    # 1. The obvious check: own-named branch (exact or disambiguated suffix).
    own_branch = find_own_named_branch(repo_dir, unit_id, prefix)
    if own_branch:
        tip = sh(repo_dir, ["rev-parse", f"origin/{own_branch}"])
        is_anc_ok, _, _ = sh_ok(repo_dir, ["merge-base", "--is-ancestor", tip, "origin/main"])
        if is_anc_ok:
            merge_sha = find_merge_commit_for_tip(repo_dir, tip, "origin/main")
            tag = nearest_tag_containing(repo_dir, merge_sha) if merge_sha else None
            return {
                "satisfied": True, "proved": True, "method": "own-branch",
                "evidence": (
                    f"{repo_label}: own-named branch `{own_branch}` (tip `{tip[:8]}`) is a "
                    f"confirmed ancestor of `origin/main`" + (f" via direct-parent merge `{merge_sha[:8]}`" if merge_sha else " (ancestor, but no direct-parent merge commit identified -- likely squash/rebase)") +
                    (f", nearest tag `{tag}`." if tag else ", no tag found.")
                ),
                "raw": {"branch": own_branch, "tip": tip, "merge_sha": merge_sha, "tag": tag},
            }
        # Own-named branch exists but is NOT merged. Still worth a
        # cross-reference pass below in case the real deliverable ALSO
        # shipped via a different, already-merged route -- but absent that,
        # this is real evidence of non-completion, not silence.
        own_branch_note = (
            f"{repo_label}: own-named branch `{own_branch}` (tip `{tip[:8]}`) EXISTS but is "
            f"NOT an ancestor of `origin/main` -- unmerged."
        )
    else:
        own_branch_note = f"{repo_label}: no branch named `{prefix}{unit_id}` (exact or disambiguated suffix) exists."

    # 2. Cross-reference: this unit's OWN row's citations, plus every
    # sibling row that mentions this unit's id token (both directions --
    # see find_sibling_rows_mentioning()'s docstring).
    citation_pool = [(f"U{unit_id[1:]}'s own row" if unit_id.startswith("U") else "own row", own_row_text)]
    for path, sib_uid, sib_text in find_sibling_rows_mentioning(ledger_paths, unit_id):
        citation_pool.append((f"{sib_uid}'s row in {Path(path).name} (cross-reference)", sib_text))

    citation_hits = resolve_leg_via_citations(repo_dir, repo_label, unit_id, citation_pool)
    confirmed = [h for h in citation_hits if h["is_ancestor_of_main"]]
    if confirmed:
        best = confirmed[0]
        return {
            "satisfied": True, "proved": False, "method": "cross-reference",
            "evidence": (
                f"{own_branch_note} CROSS-REFERENCE: cited SHA `{best['cited_sha']}` "
                f"(full `{best['full_sha'][:8]}`), found in [{best['source']}], "
                f"INDEPENDENTLY VERIFIED as a commit in {repo_label} and a confirmed ancestor "
                f"of `origin/main`" + (f" via direct-parent merge `{best['merge_sha'][:8]}`" if best.get("merge_sha") else "") +
                (f", nearest tag `{best['tag']}`." if best.get("tag") else ".") +
                " INFERRED, not PROVED by own-branch name -- the citation was only used to know "
                "where to look; the merge/ancestry was re-derived independently, not trusted from prose."
            ),
            "raw": {"citation": best, "all_citation_hits": citation_hits},
        }

    # 3. Broad token-scan safety net: a non-namespaced branch bearing the
    # unit id as a delimited token anywhere in its name (e.g.
    # `u79-gk17-cc-anthology-selfheal-banner`). This is what actually
    # resolves U79's CC leg when the ledger's own citation text is
    # insufficient to prove it independently. token_scan_any_branch()
    # already excludes the one namespace PROVEN to collide (`skill62/*`,
    # see FOREIGN_NAMESPACE_PREFIXES) -- but even after that exclusion,
    # this collects ALL merged, ancestor-confirmed candidates and refuses
    # to silently pick a winner if more than one remains. Never take
    # hits[0] on faith.
    token_hits = token_scan_any_branch(repo_dir, unit_id)
    confirmed_token_hits = []
    for b in token_hits:
        if own_branch and b == own_branch:
            continue
        tip = sh(repo_dir, ["rev-parse", f"origin/{b}"])
        is_anc_ok, _, _ = sh_ok(repo_dir, ["merge-base", "--is-ancestor", tip, "origin/main"])
        if is_anc_ok:
            merge_sha = find_merge_commit_for_tip(repo_dir, tip, "origin/main")
            tag = nearest_tag_containing(repo_dir, merge_sha) if merge_sha else None
            confirmed_token_hits.append({"branch": b, "tip": tip, "merge_sha": merge_sha, "tag": tag})

    if len(confirmed_token_hits) == 1:
        h = confirmed_token_hits[0]
        return {
            "satisfied": True, "proved": True, "method": "token-scan",
            "evidence": (
                f"{own_branch_note} TOKEN-SCAN: non-namespaced branch `{h['branch']}` (tip "
                f"`{h['tip'][:8]}`) carries the unit id as a delimited token (foreign namespaces "
                f"excluded -- see FOREIGN_NAMESPACE_PREFIXES), is the ONLY such candidate, and is a "
                f"confirmed ancestor of `origin/main`" +
                (f" via direct-parent merge `{h['merge_sha'][:8]}`" if h["merge_sha"] else "") +
                (f", nearest tag `{h['tag']}`." if h["tag"] else ".")
            ),
            "raw": h,
        }
    if len(confirmed_token_hits) > 1:
        return {
            "satisfied": None, "proved": None, "method": "token-scan-ambiguous",
            "evidence": (
                f"{own_branch_note} TOKEN-SCAN found {len(confirmed_token_hits)} DIFFERENT merged "
                f"branches all carrying the unit id as a delimited token: "
                f"{[h['branch'] for h in confirmed_token_hits]}. Refusing to silently pick one -- "
                f"this is exactly the shape of the proven skill62/ce-U15 namespace collision (see "
                f"FOREIGN_NAMESPACE_PREFIXES); a human must disambiguate which branch (if any) is "
                f"actually this unit's leg. UNKNOWN."
            ),
            "raw": {"citation_hits": citation_hits, "confirmed_token_hits": confirmed_token_hits},
        }

    # 4. Nothing verified. Distinguish "confirmed unmerged own branch" (a
    # real negative) from "no branch, no citation, no token match at all"
    # (cannot prove absence either -- print UNKNOWN, never guess NOT-DONE).
    if own_branch:
        return {
            "satisfied": False, "proved": True, "method": "own-branch-unmerged",
            "evidence": own_branch_note + " No cross-reference citation or token-scan match confirmed this leg elsewhere either.",
            "raw": {"branch": own_branch},
        }
    return {
        "satisfied": None, "proved": None, "method": "none-found",
        "evidence": (
            own_branch_note + " No verifiable cross-reference citation (own row or sibling rows) "
            "resolved to a merged commit in this repo, and no non-namespaced branch carries the "
            "unit id as a token. Absence of a same-named branch does NOT prove the work was never "
            "done (see U108/U79) -- refusing to assert NOT-DONE without positive evidence. "
            "UNKNOWN: needs human/build-session review."
        ),
        "raw": {"citation_hits": citation_hits, "token_hits": token_hits},
    }


# --------------------------------------------------------------------------
# CI check-runs (paginated -- the legacy combined-status endpoint is
# meaningless per the operator brief)
# --------------------------------------------------------------------------

def ci_status_for_sha(owner_repo, sha):
    """Returns dict {status: "green"|"red"|"pending"|"no-data", total, success,
    failure, pending, other, raw_conclusions}. Uses `gh api --paginate` so
    check-run pages beyond the first (>30 by default) are not silently
    dropped. Never raises -- a `gh api` failure (e.g. sha too old / no
    Actions history) yields status="no-data", not a hard error, since older
    historical merges legitimately may have no retained check-run data and
    that must NOT be conflated with "CI failed"."""
    if not sha:
        return {"status": "no-data", "total": 0, "note": "no sha to check"}
    cmd = ["gh", "api", f"repos/{owner_repo}/commits/{sha}/check-runs", "--paginate"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        return {"status": "no-data", "total": 0, "note": f"gh api failed: {r.stderr.strip()[:200]}"}
    check_runs = []
    # --paginate concatenates one JSON object per page on stdout; each page
    # has its own top-level {"check_runs": [...], "total_count": N}.
    for chunk in _split_json_objects(r.stdout):
        try:
            page = json.loads(chunk)
        except Exception:
            continue
        check_runs.extend(page.get("check_runs", []))
    if not check_runs:
        return {"status": "no-data", "total": 0, "note": "0 check-runs found for this sha"}
    success = sum(1 for c in check_runs if c.get("conclusion") in ("success", "skipped", "neutral"))
    failure = sum(1 for c in check_runs if c.get("conclusion") in ("failure", "cancelled", "timed_out", "action_required"))
    pending = sum(1 for c in check_runs if c.get("status") in ("in_progress", "queued") or c.get("conclusion") is None)
    other = len(check_runs) - success - failure - pending
    if failure > 0:
        status = "red"
    elif pending > 0:
        status = "pending"
    else:
        status = "green"
    return {
        "status": status, "total": len(check_runs), "success": success,
        "failure": failure, "pending": pending, "other": other,
    }


def _split_json_objects(s):
    """`gh api ... --paginate` writes one JSON object per page, concatenated
    with no separator. Split on top-level '}{' boundaries."""
    s = s.strip()
    if not s:
        return []
    parts = []
    depth = 0
    start = 0
    for i, ch in enumerate(s):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                parts.append(s[start:i + 1])
                start = i + 1
    return parts


# --------------------------------------------------------------------------
# Top-level: resolve a whole unit
# --------------------------------------------------------------------------

def resolve_unit(unit_id, onb_dir, cc_dir, ledger_paths, skip_ci=False):
    row_path, row_text = find_ledger_row(ledger_paths, unit_id)
    if row_text is None:
        return {
            "unit": unit_id, "verdict": "UNKNOWN",
            "reason": f"No ledger row found for {unit_id} in any of: {', '.join(str(p) for p in ledger_paths)}. "
                      f"Cannot resolve required legs from §E.2 without a row to read the leg tag from. Refusing to guess.",
            "legs": {},
        }

    cells = [c.strip() for c in row_text.strip().strip("|").split("|")]
    description = cells[1] if len(cells) > 1 else ""
    ledger_status_cell = cells[3] if len(cells) > 3 else ""

    required_legs, mode, tag_note = resolve_required_legs(description)

    if mode == "unknown":
        return {
            "unit": unit_id, "verdict": "UNKNOWN",
            "reason": f"Leg tag unparseable: {tag_note} Row: {row_path}. Refusing to guess DONE or NOT-DONE.",
            "legs": {}, "ledger_status_cell": ledger_status_cell,
        }

    if mode == "zero-leg":
        # No repo/build leg required at all -- e.g. a live-probe / doc /
        # evidence-only unit. The ONLY honest signal available is the
        # ledger's own hand-verified status text; this is explicitly NOT a
        # git-provable claim, so it is labeled N/A, never PROVED/INFERRED.
        verified = ledger_status_cell.strip().lower().startswith("verified")
        return {
            "unit": unit_id, "verdict": "DONE" if verified else "UNKNOWN",
            "reason": f"Zero-leg unit ({tag_note}) -- no repo leg required. "
                      f"Ledger status cell reads '{ledger_status_cell}'. "
                      f"{'DONE per hand-verified ledger status.' if verified else 'Not stamped verified -- UNKNOWN, not independently git-checkable.'}",
            "legs": {}, "mode": mode, "proved": None,
            "ledger_status_cell": ledger_status_cell,
        }

    repo_dirs = {"onb": onb_dir, "cc": cc_dir}
    leg_results = {}
    for leg in sorted(required_legs):
        repo_dir = repo_dirs[leg]
        repo_label = REPO_LABELS[leg]
        leg_result = resolve_leg(repo_dir, repo_label, unit_id, ledger_paths, row_text)
        if not skip_ci and leg_result.get("raw", {}).get("merge_sha"):
            owner_repo = f"trevorotts1/{repo_label}"
            leg_result["ci"] = ci_status_for_sha(owner_repo, leg_result["raw"]["merge_sha"])
        leg_results[leg] = leg_result

    any_unknown = any(r["satisfied"] is None for r in leg_results.values())
    any_false = any(r["satisfied"] is False for r in leg_results.values())
    all_true = all(r["satisfied"] is True for r in leg_results.values())

    any_ci_red = any(r.get("ci", {}).get("status") == "red" for r in leg_results.values())

    if any_unknown and not any_false:
        verdict = "UNKNOWN"
    elif any_false:
        verdict = "NOT-DONE"
    elif all_true and any_ci_red:
        verdict = "NOT-DONE"
    elif all_true:
        verdict = "DONE"
    else:
        verdict = "UNKNOWN"

    return {
        "unit": unit_id, "verdict": verdict, "mode": mode, "tag_note": tag_note,
        "required_legs": sorted(required_legs), "legs": leg_results,
        "ledger_row_path": row_path, "ledger_status_cell": ledger_status_cell,
    }


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def _print_human(result):
    print(f"UNIT: {result['unit']}")
    print(f"VERDICT: {result['verdict']}")
    if "mode" in result:
        print(f"leg mode: {result.get('mode')} -- {result.get('tag_note', '')}")
    if result.get("required_legs") is not None and result.get("legs"):
        print(f"required legs: {result.get('required_legs')}")
        for leg, r in result["legs"].items():
            proved_str = {True: "PROVED", False: "INFERRED", None: "N/A"}[r["proved"]]
            print(f"\n  -- leg={leg} ({REPO_LABELS.get(leg, leg)}) --")
            print(f"     satisfied: {r['satisfied']}  [{proved_str}, method={r['method']}]")
            print(f"     evidence: {r['evidence']}")
            if "ci" in r:
                ci = r["ci"]
                print(f"     CI: {ci.get('status')} (total={ci.get('total')}, success={ci.get('success')}, "
                      f"failure={ci.get('failure')}, pending={ci.get('pending')}) note={ci.get('note', '')}")
    if "reason" in result:
        print(f"reason: {result['reason']}")
    if "ledger_status_cell" in result:
        print(f"(ledger's own status cell -- NOT trusted for the verdict above, shown for comparison only): {result.get('ledger_status_cell')}")


def main():
    import argparse

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("unit_id")
    ap.add_argument("--onb-dir", required=True)
    ap.add_argument("--cc-dir", required=True)
    ap.add_argument("--ledger", action="append", dest="ledger_paths", required=True)
    ap.add_argument("--skip-ci", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    result = resolve_unit(args.unit_id, args.onb_dir, args.cc_dir, args.ledger_paths, skip_ci=args.skip_ci)

    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        _print_human(result)

    sys.exit(0 if result["verdict"] in ("DONE",) else (1 if result["verdict"] == "NOT-DONE" else 3))


if __name__ == "__main__":
    main()
