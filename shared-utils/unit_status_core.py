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

# A leg tag shape LEG_TAG_RE (ledger_reconciler_core.py, shared with the
# reconciler) cannot parse AT ALL: a nested-paren "live" tag like
# "(live (read-only), P1)" / "(live (operator), P0)". LEG_TAG_RE's
# "[^,)]+" capture (no comma/close-paren before the first comma) breaks on
# the inner "(read-only)"/"(operator)" -- it stops matching at that inner
# ")" and then requires a literal "," immediately after, which isn't there
# (a ")" is instead), so the WHOLE match fails and parse_leg_requirement()
# returns None. Same disease class as the parenthesized-compound tag
# COMPOUND_LEG_TAG_RE already exists to catch (a "CC (+ONB)" primary), just
# with a "live" primary instead of a "CC"/"ONB" one. Deliberately scoped to
# THIS file only (not a change to the shared LEG_TAG_RE/COMPOUND_LEG_TAG_RE
# in ledger_reconciler_core.py, which the reconciler's own patch/alarm logic
# also depends on and this fix does not touch) -- it recognizes ONLY this
# specific nested-paren "live" shape and confirms it as a genuine
# zero-repo-leg tag; it does not attempt to parse the "<detail>" itself
# (read-only/operator are informational only, never independently checked).
NESTED_LIVE_TAG_RE = re.compile(r"^\s*(?:\[[^\]]*\]\s*)?\(live\s*\([^)]*\)\s*,", re.IGNORECASE)

# Bare (non-compound) non-repo leg tokens this resolver accepts as a
# single, un-"+"-joined tag -- e.g. "(n8n, P1)". Currently ONLY "n8n".
# NOT "ghl", even though "(GHL, P1)" is the structurally identical bare-tag
# shape (e.g. ledger rows U69/U70) and NON_REPO_LEG_TOKENS above already
# lists "ghl" for the "+"-joined case. This is a DELIBERATE, narrower scope
# than reusing the full NON_REPO_LEG_TOKENS set here: widening bare-tag
# recognition to "ghl" would also reclassify U70 from UNKNOWN to DONE as a
# side effect -- purely because U70's OWN ledger status cell already reads
# "verified (repo leg; live provisioning owed)" and this tool's existing
# zero-leg branch trusts a "verified"-prefixed status cell at face value
# (the same trust model already in production for U91/U96/U97's bare "doc"
# tag) -- but U70 is one of the Anthology-family units this pass is
# explicitly required to leave untouched (surface only, never reclassify).
# "n8n" alone is safe to add: every OTHER bare "(n8n, ...)" row in the
# ledger (U64/U65/U73/U75) has a non-"verified" status cell (partial/
# deferred/pending/pending), so it stays UNKNOWN exactly as before this fix
# -- only U72 (status "verified", explicitly in scope) flips. "GHL"
# bare-tag support is left unparseable (UNKNOWN, fail-closed, unchanged) on
# purpose -- not a limitation, a scope boundary.
BARE_NON_REPO_TOKENS = frozenset({"n8n"})


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

    if NESTED_LIVE_TAG_RE.match(description):
        return (
            set(),
            "zero-leg",
            "nested-paren live tag (e.g. 'live (read-only)'/'live (operator)') -- "
            "declares a non-repo (live/evidence-only) unit; no branch/merge to check.",
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

    if (
        "live" in tag_l
        or "read-only" in tag_l
        or tag_l in ("n/a", "na", "doc", "none")
        or tag_l in BARE_NON_REPO_TOKENS
    ):
        return set(), "zero-leg", f"leg tag '{tag}' declares a non-repo (live/doc/evidence-only) unit -- no branch/merge to check."
    return set(), "unknown", f"leg tag '{tag}' does not match any known convention (both/ONB/CC/compound/zero-leg)."


def resolve_owed_non_repo_components(description):
    """The machine-readable form of the "flagged OWED separately" prose note in
    resolve_required_legs()'s '+'-joined compound branch. Returns a sorted list
    of the non-repo components of a flat compound leg tag that ALSO carries at
    least one repo leg -- e.g. "(ONB + live, P2)" -> ["live"], "(n8n + ONB, P1)"
    -> ["n8n"], "(ONB + GHL, P1)" -> ["ghl"]. These legs can NEVER be proven by
    this tool's git check (they are proven by execution/live-run or not at all),
    so a unit whose repo legs all resolve DONE is still only
    "repo-legs-done, live-leg-OWED" -- a state a caller must be able to read
    programmatically, not infer from a comment.

    Returns [] for every other tag shape:
      - bare single-repo tags ("(ONB, ...)" / "(CC, ...)" / "(both, ...)") --
        no non-repo component exists;
      - parenthesized compound "(CC (+ONB), ...)" -- the "(+...)" secondary is a
        REPO hint with no consistent grammar (resolve_required_legs() says so);
        it is not a live/non-repo leg and stays out of scope;
      - zero-leg "+"-joined tags ("(GHL + n8n, ...)") -- no repo leg exists to
        be "done", so the repo-done/live-owed distinction does not apply (the
        zero-leg branch already owns that case);
      - unparseable / garbled tags ("(0NB + live, ...)") -- fail-closed via
        mode="unknown" in resolve_required_legs(); nothing is asserted here.

    Reuses the SAME validated primitives as resolve_required_legs()
    (parse_compound_leg_primary / parse_leg_requirement) -- no new parsing
    regex, so the two cannot drift apart."""
    if not description:
        return []
    if parse_compound_leg_primary(description):
        return []
    tag = parse_leg_requirement(description)
    if tag is None:
        return []
    tag_l = tag.strip().lower()
    if "+" not in tag_l:
        return []
    parts = [p.strip() for p in tag_l.split("+")]
    if not any(p in ("onb", "cc") for p in parts):
        return []
    return sorted(p for p in parts if p not in ("onb", "cc"))


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
#
# DEFECT-1 FIX (the reason this section now takes a "head sha" and never a
# "merge sha"): a synthetic merge commit -- the commit GitHub creates ON
# main when a PR merges -- carries ZERO check-runs on this repo's CI
# configuration. CI here runs on the `pull_request` event, so every
# check-run is recorded against the PR branch's OWN head commit, never
# against the merge commit main gets afterward. Calling ci_status_for_sha()
# with a merge sha therefore ALWAYS returns "0 check-runs found" -- not
# because the leg has no CI history, but because the tool was looking at a
# commit CI never ran on. Empirically confirmed live (U11, both legs): the
# real head sha carries 3 real check-runs (all success); the merge sha
# carries 0. See _leg_head_sha() below for how each resolution method's
# real head commit is extracted, and resolve_unit() for where it is passed
# in -- never leg_result["raw"]["merge_sha"].
#
# DEFECT-2 FIX (why "red" alone is not the final word): a real 18-unit
# triage found EVERY historic `failure > 0` on an exact head sha was noise
# that no longer exists on current main -- a client-name QC gate tripping
# on a DIFFERENT unit's evidence file during a ~2026-07-14/15 window, a
# version-bump gate firing in the same window, an infra hang, a build-guard
# flake. "Green on the exact sha" would have MISSED that those are all
# fine now; but "red on the exact sha" is ALSO not truth by itself -- it
# must be checked against what CURRENT main does for the SAME check NAME
# before any verdict is drawn. classify_ci_from_data() below is the pure,
# offline-testable classifier; ci_status_for_sha() is reused for BOTH the
# head sha and current main's sha (never a second, drifted implementation)
# so the two are always compared on equal footing.
# --------------------------------------------------------------------------

_FAILURE_CONCLUSIONS = ("failure", "cancelled", "timed_out", "action_required")
# Used for the HEAD-SHA tally only (ci_status_for_sha()'s success/failure/
# pending counts, deciding whether the leg's own head commit is red at
# all) -- "skipped" and "neutral" are legitimately non-failing outcomes for
# that purpose (a conditional check that correctly didn't need to run isn't
# a failure). Deliberately NOT reused for the main-COMPARISON side of the
# fossil check inside classify_ci_from_data(): there, "skipped"/"neutral"
# on current main means the SAME check simply didn't run this time (a
# conditional `if:` gate, path filter, or event-type gate) -- that is NOT
# proof the original failure's cause is gone, so it must never be treated
# as equivalent to a real "success" when deciding red-fossil vs
# red-main-unverifiable. See classify_ci_from_data()'s docstring.
_SUCCESS_CONCLUSIONS = ("success", "skipped", "neutral")


def _latest_conclusion_by_name(check_runs):
    """Collapse possibly-MULTIPLE run instances of the same check NAME
    (GitHub creates a new check-run id per re-run, same name) down to the
    single most-recent one per name, keyed by started_at/completed_at
    (falling back to list position if both are missing/equal) -- so a
    check that failed once and was later manually re-run to success is
    never double-counted as both a failure and a success. Returns
    {name: {"conclusion":, "status":}}."""
    latest = {}
    for idx, c in enumerate(check_runs):
        name = c.get("name")
        if name is None:
            continue
        ts = c.get("started_at") or c.get("completed_at") or ""
        key = (ts, idx)
        if name not in latest or key > latest[name][0]:
            latest[name] = (key, c)
    return {name: {"conclusion": c.get("conclusion"), "status": c.get("status")} for name, (key, c) in latest.items()}


def ci_status_for_sha(owner_repo, sha):
    """Returns dict {status: "green"|"red"|"pending"|"no-data", total, success,
    failure, pending, other, checks_by_name, failing_names}. `sha` MUST be
    the commit CI actually ran on (a leg's own head sha -- see
    _leg_head_sha() -- or, for the comparison side, current main's own
    tip) -- NEVER a synthetic merge commit (see this section's DEFECT-1
    docstring above). Uses `gh api --paginate` so check-run pages beyond
    the first (>30 by default) are not silently dropped. Never raises -- a
    `gh api` failure (e.g. sha too old / no Actions history) yields
    status="no-data", not a hard error, since older historical merges
    legitimately may have no retained check-run data (real, empirically
    confirmed case -- e.g. U5's CC leg: `total_count: 0` on its real head
    sha, a genuine old direct-push merge, not this tool's bug) and that
    must NOT be conflated with "CI failed"."""
    if not sha:
        return {"status": "no-data", "total": 0, "note": "no sha to check", "checks_by_name": {}, "failing_names": []}
    cmd = ["gh", "api", f"repos/{owner_repo}/commits/{sha}/check-runs", "--paginate"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        return {"status": "no-data", "total": 0, "note": f"gh api failed: {r.stderr.strip()[:200]}", "checks_by_name": {}, "failing_names": []}
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
        return {"status": "no-data", "total": 0, "note": "0 check-runs found for this sha", "checks_by_name": {}, "failing_names": []}
    checks_by_name = _latest_conclusion_by_name(check_runs)
    success = sum(1 for info in checks_by_name.values() if info["conclusion"] in _SUCCESS_CONCLUSIONS)
    failure = sum(1 for info in checks_by_name.values() if info["conclusion"] in _FAILURE_CONCLUSIONS)
    pending = sum(1 for info in checks_by_name.values() if info["status"] in ("in_progress", "queued") or info["conclusion"] is None)
    other = len(checks_by_name) - success - failure - pending
    if failure > 0:
        status = "red"
    elif pending > 0:
        status = "pending"
    else:
        status = "green"
    failing_names = sorted(name for name, info in checks_by_name.items() if info["conclusion"] in _FAILURE_CONCLUSIONS)
    return {
        "status": status, "total": len(checks_by_name), "success": success,
        "failure": failure, "pending": pending, "other": other,
        "checks_by_name": checks_by_name, "failing_names": failing_names,
    }


def _leg_head_sha(leg_result):
    """The commit that ACTUALLY ran CI for this leg -- never the synthetic
    merge commit a leg_result also carries under raw["merge_sha"] (see the
    DEFECT-1 docstring above `ci_status_for_sha`). Each resolution method
    stores its own independently-verified commit under a different raw
    key, so this must dispatch on method, not assume a common shape:
      own-branch / token-scan -> raw['tip']            (the branch's own
                                   head commit -- what a PR's CI actually
                                   ran against).
      cross-reference         -> raw['citation']['full_sha'] (the CITED
                                   commit itself, independently verified as
                                   a real ancestor of main -- NOT the
                                   merge_sha it happened to land via).
    Any other method (own-branch-unmerged / token-scan-ambiguous /
    none-found) has no single confirmed commit to check CI against at all
    -- returns None, and the caller must treat that as "cannot CI-check
    this leg" (never silently fall back to a merge sha)."""
    method = leg_result.get("method")
    raw = leg_result.get("raw") or {}
    if method in ("own-branch", "token-scan"):
        return raw.get("tip")
    if method == "cross-reference":
        citation = raw.get("citation") or {}
        return citation.get("full_sha")
    return None


def classify_ci_from_data(head, main_sha, main):
    """Pure function, no network/subprocess -- fully unit-testable with
    fixture dicts shaped like ci_status_for_sha()'s return value. `head`
    is the leg's own head sha's CI result (already confirmed status=="red"
    by the caller); `main` is CURRENT origin/main's CI result for the same
    owner_repo. Matches failing checks between the two BY CHECK NAME (the
    SHAs differ, so nothing else is comparable). Returns one of:
      "red-live"              -- >=1 failing check NAME on head ALSO fails
                                  (failure-class) on current main right
                                  now -- a real, present defect. This is
                                  the ONLY red-* status that should ever
                                  gate an overall NOT-DONE verdict.
      "red-fossil"             -- every failing check NAME on head now
                                  genuinely PASSES (conclusion == "success")
                                  on current main -- historic noise; the
                                  cause no longer exists. Reported WITH
                                  the check name(s) and both shas -- NEVER
                                  silently upgraded to "green" (that would
                                  be inventing a lenient ruler, the same
                                  disease class as trusting the ledger).
      "red-check-removed"      -- >=1 failing check NAME on head does not
                                  exist in current main's check-run list AT
                                  ALL (workflow renamed/retired) -- named
                                  explicitly, never guessed as fossil or
                                  live.
      "red-main-unverifiable"  -- EITHER current main's own check-run data
                                  could not be fetched at all (main itself
                                  came back "no-data"), OR a matching check
                                  name on main exists but its conclusion is
                                  NOT a genuine "success" (e.g. "skipped" /
                                  "neutral" / anything else non-affirmative
                                  -- a conditional gate, path filter, or
                                  event-type gate that simply did not run
                                  this time is NOT proof the cause is gone).
                                  Either way, live-vs-fossil genuinely
                                  cannot be determined; fails loud instead
                                  of defaulting to the lenient (fossil)
                                  read -- a "skipped" is "unverified", not
                                  "passed".
    Priority when a leg has MULTIPLE failing checks in different buckets:
    any_live wins over any_removed wins over any_unverifiable wins over
    all-fossil -- a real present defect must never be hidden behind a
    co-occurring fossil, removed check, or unverifiable check on the same
    leg."""
    detail = []
    any_live = False
    any_removed = False
    any_unverifiable = False
    for name in head.get("failing_names", []):
        head_conclusion = head["checks_by_name"][name]["conclusion"]
        if main.get("status") == "no-data":
            main_conclusion = None
            note = "current main's check-run data could not be fetched at all -- cannot verify live vs fossil"
        else:
            main_check = main.get("checks_by_name", {}).get(name)
            if main_check is None:
                main_conclusion = None
                note = "check name does not exist on current main at all -- renamed/retired, not guessed"
                any_removed = True
            else:
                main_conclusion = main_check["conclusion"]
                if main_conclusion in _FAILURE_CONCLUSIONS:
                    any_live = True
                    note = "still fails (same check name) on current main -- real, present defect"
                elif main_conclusion == "success":
                    note = "now passes on current main -- historic fossil, the cause no longer exists"
                else:
                    # "skipped" / "neutral" / any other non-failure,
                    # non-"success" conclusion (a conditional `if:` gate,
                    # path filter, or event-type gate that did not run this
                    # time on main's current tip) is NOT a re-verification --
                    # nobody re-ran the check, so its cause being gone is
                    # UNPROVEN. Must not be treated as equivalent to a real
                    # pass for fossil determination (see _SUCCESS_CONCLUSIONS'
                    # docstring -- that set is deliberately reused only for
                    # the head-sha tally, never for this main-comparison).
                    any_unverifiable = True
                    note = (
                        f"current main's matching check did not genuinely re-verify "
                        f"(conclusion={main_conclusion!r}, not \"success\") -- unproven, "
                        f"not a fossil"
                    )
        detail.append({
            "name": name, "head_conclusion": head_conclusion,
            "main_conclusion": main_conclusion, "note": note,
        })

    if main.get("status") == "no-data":
        status = "red-main-unverifiable"
    elif any_live:
        status = "red-live"
    elif any_removed:
        status = "red-check-removed"
    elif any_unverifiable:
        status = "red-main-unverifiable"
    else:
        status = "red-fossil"

    return {
        "status": status,
        "total": head.get("total"), "success": head.get("success"),
        "failure": head.get("failure"), "pending": head.get("pending"),
        "main_sha": main_sha, "failing_checks": detail,
    }


def classify_leg_ci(owner_repo, repo_dir, head_sha, main_ref="origin/main"):
    """Network-calling wrapper: fetch CI for the leg's own head_sha; if it
    isn't red (no-data / pending / green), that verdict stands as-is --
    only a red result needs the fossil-vs-live comparison against current
    main (fetched via the SAME ci_status_for_sha(), never a second,
    drifted implementation of the check-runs call). See
    classify_ci_from_data() for the pure classification logic this defers
    to, and _leg_head_sha() for how head_sha is derived per resolution
    method."""
    head = ci_status_for_sha(owner_repo, head_sha)
    if head["status"] in ("no-data", "pending", "green"):
        return {**head, "head_sha": head_sha}
    main_sha = sh(repo_dir, ["rev-parse", main_ref])
    main = ci_status_for_sha(owner_repo, main_sha)
    return {**classify_ci_from_data(head, main_sha, main), "head_sha": head_sha}


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

def _no_owed_legs():
    """The stable, always-present schema for the machine-readable live-leg
    fields (see resolve_owed_non_repo_components()): a caller never has to
    guess whether the keys exist, on ANY return path."""
    return {"owed_non_repo_components": [], "live_leg_owed": False, "completion_state": None}


def resolve_unit(unit_id, onb_dir, cc_dir, ledger_paths, skip_ci=False):
    row_path, row_text = find_ledger_row(ledger_paths, unit_id)
    if row_text is None:
        return {
            "unit": unit_id, "verdict": "UNKNOWN",
            "reason": f"No ledger row found for {unit_id} in any of: {', '.join(str(p) for p in ledger_paths)}. "
                      f"Cannot resolve required legs from §E.2 without a row to read the leg tag from. Refusing to guess.",
            "legs": {}, **_no_owed_legs(),
        }

    cells = [c.strip() for c in row_text.strip().strip("|").split("|")]
    description = cells[1] if len(cells) > 1 else ""
    ledger_status_cell = cells[3] if len(cells) > 3 else ""

    required_legs, mode, tag_note = resolve_required_legs(description)

    if mode == "unknown":
        return {
            "unit": unit_id, "verdict": "UNKNOWN",
            "reason": f"Leg tag unparseable: {tag_note} Row: {row_path}. Refusing to guess DONE or NOT-DONE.",
            "legs": {}, "ledger_status_cell": ledger_status_cell, **_no_owed_legs(),
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
            "ledger_status_cell": ledger_status_cell, **_no_owed_legs(),
        }

    repo_dirs = {"onb": onb_dir, "cc": cc_dir}
    leg_results = {}
    for leg in sorted(required_legs):
        repo_dir = repo_dirs[leg]
        repo_label = REPO_LABELS[leg]
        leg_result = resolve_leg(repo_dir, repo_label, unit_id, ledger_paths, row_text)
        if not skip_ci:
            # DEFECT-1 FIX: check CI on the leg's OWN head sha -- the commit
            # CI actually ran on -- never leg_result["raw"]["merge_sha"] (the
            # synthetic merge commit, which carries ZERO check-runs on this
            # repo's CI configuration; see ci_status_for_sha()'s docstring).
            head_sha = _leg_head_sha(leg_result)
            if head_sha:
                owner_repo = f"trevorotts1/{repo_label}"
                leg_result["ci"] = classify_leg_ci(owner_repo, repo_dir, head_sha)
        leg_results[leg] = leg_result

    any_unknown = any(r["satisfied"] is None for r in leg_results.values())
    any_false = any(r["satisfied"] is False for r in leg_results.values())
    all_true = all(r["satisfied"] is True for r in leg_results.values())

    # DEFECT-2 FIX: only "red-live" (the failing check NAME is CONFIRMED
    # still failing on current main) is a real, present defect that may
    # gate the verdict to NOT-DONE. "red-fossil" / "red-check-removed" /
    # "red-main-unverifiable" all mean the exact-sha failure does NOT
    # reflect current truth (or truth couldn't be established either way)
    # -- letting any of THOSE force NOT-DONE would be exactly the "wrong
    # answer from stale/irrelevant data" disease this tool exists to make
    # unreachable, just from the opposite direction (false negative instead
    # of false positive). They remain fully visible in leg_result["ci"] for
    # a human to read -- never hidden, never silently upgraded to "green".
    any_ci_red = any(r.get("ci", {}).get("status") == "red-live" for r in leg_results.values())

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

    # Machine-readable "(live leg OWED)" state -- the structured form of what
    # used to be prose-only inside tag_note. A compound unit ("ONB + live")
    # whose repo leg(s) all resolve DONE is NOT the same as a fully-DONE unit:
    # its live/non-repo leg is still owed (proven by execution/live-run, never
    # by this tool's git check). `verdict` deliberately stays "DONE" (the repo
    # legs ARE done -- existing callers/exit codes keep their meaning); the
    # distinction lives in these three additive fields so a caller (e.g. the
    # ledger-truth gate) can act on it programmatically:
    #   owed_non_repo_components: which non-repo legs the tag owes ([] = none)
    #   live_leg_owed:            True ONLY when verdict == DONE AND >=1
    #                             non-repo component is owed
    #   completion_state:         "fully-done" | "repo-legs-done-live-leg-owed"
    #                             for a DONE verdict; None otherwise
    owed_components = resolve_owed_non_repo_components(description)
    live_leg_owed = verdict == "DONE" and bool(owed_components)
    if verdict == "DONE":
        completion_state = "repo-legs-done-live-leg-owed" if live_leg_owed else "fully-done"
    else:
        completion_state = None

    return {
        "unit": unit_id, "verdict": verdict, "mode": mode, "tag_note": tag_note,
        "required_legs": sorted(required_legs), "legs": leg_results,
        "ledger_row_path": row_path, "ledger_status_cell": ledger_status_cell,
        "owed_non_repo_components": owed_components,
        "live_leg_owed": live_leg_owed,
        "completion_state": completion_state,
    }


# --------------------------------------------------------------------------
# Aggregate mode (--all / --units): one summary line across many units.
# Reuses resolve_unit() per unit in a loop -- NEVER a reimplementation of the
# per-unit resolution logic (a second implementation would be a drift vector,
# the same disease class this file's module docstring calls out).
# --------------------------------------------------------------------------

# Fixed tier order for the summary line -- stable, so a caller can parse it
# positionally as well as by name. "DONE-LIVE-OWED" is the machine-readable
# tier for a unit whose repo legs are DONE but a live/non-repo leg is still
# owed (see resolve_unit()'s live_leg_owed field); it is NOT a looser DONE
# and is never folded into the plain "DONE" count.
VERDICT_TIERS = ("DONE", "DONE-LIVE-OWED", "NOT-DONE", "UNKNOWN")


def result_tier(result):
    """The single tier a per-unit resolve_unit() result counts toward in the
    aggregate summary. DONE splits by live_leg_owed; every non-DONE,
    non-NOT-DONE verdict (including any future unexpected value) counts as
    UNKNOWN -- fail-closed, never silently bucketed with a pass."""
    if result.get("verdict") == "DONE":
        return "DONE-LIVE-OWED" if result.get("live_leg_owed") else "DONE"
    if result.get("verdict") == "NOT-DONE":
        return "NOT-DONE"
    return "UNKNOWN"


def list_ledger_unit_ids(ledger_paths):
    """Every unit id with a row (`| U<n> |`) in any of the given ledger files,
    de-duplicated and sorted NUMERICALLY (U2 before U10). Never guessed from
    prose mentions -- only a real row-start match counts (same UNIT_ROW_RE
    the per-unit lookup uses)."""
    seen = set()
    for path in ledger_paths:
        p = Path(path)
        if not p.is_file():
            continue
        for line in p.read_text(errors="replace").splitlines():
            m = UNIT_ROW_RE.match(line)
            if m:
                seen.add(m.group(1))
    return sorted(seen, key=lambda u: int(u[1:]))


def summarize_results(results):
    """Pure tally of resolve_unit() results into the fixed VERDICT_TIERS
    buckets plus TOTAL. Fully offline-testable."""
    counts = {t: 0 for t in VERDICT_TIERS}
    for r in results:
        counts[result_tier(r)] += 1
    counts["TOTAL"] = len(results)
    return counts


def format_summary_line(counts):
    """The ONE aggregate line this mode exists to print, e.g.:
      UNITS CHECKED: 12 -- DONE: 5, DONE-LIVE-OWED: 2, NOT-DONE: 1, UNKNOWN: 4
    All four tiers are always present in fixed order, even at 0, so the line
    is trivially greppable/diffable."""
    return (
        f"UNITS CHECKED: {counts['TOTAL']} -- "
        + ", ".join(f"{t}: {counts[t]}" for t in VERDICT_TIERS)
    )


def aggregate_exit_code(counts):
    """Same fail-closed vocabulary as single-unit mode (0 = DONE, 1 =
    NOT-DONE, 3 = UNKNOWN), applied to the aggregate: any NOT-DONE unit
    dominates (exit 1); else any UNKNOWN unit (exit 3); else 0.
    DONE-LIVE-OWED counts as DONE for exit purposes -- its repo legs ARE
    git-proven; the owed live leg is visible in the tier count, never an
    exit-code surprise."""
    if counts.get("NOT-DONE", 0) > 0:
        return 1
    if counts.get("UNKNOWN", 0) > 0:
        return 3
    return 0


def resolve_all_units(unit_ids, onb_dir, cc_dir, ledger_paths, skip_ci=False):
    """Run resolve_unit() for each unit id in order and package the aggregate:
    the per-unit results (full detail preserved), the tier counts, and the
    one-line summary. The per-unit logic itself is NEVER duplicated here --
    this is a loop over the same function single-unit mode calls."""
    results = [resolve_unit(u, onb_dir, cc_dir, ledger_paths, skip_ci=skip_ci) for u in unit_ids]
    counts = summarize_results(results)
    return {"units": results, "counts": counts, "summary_line": format_summary_line(counts)}


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def _print_human(result):
    print(f"UNIT: {result['unit']}")
    print(f"VERDICT: {result['verdict']}")
    if result.get("verdict") == "DONE":
        # VISIBLY distinguish "fully DONE" from "repo-leg-done, live-leg-OWED"
        # on the verdict line itself -- the human-output mirror of the
        # machine-readable live_leg_owed / completion_state fields.
        if result.get("live_leg_owed"):
            print(
                f"COMPLETION: repo-legs-done-live-leg-owed -- repo leg(s) git-proven; "
                f"non-repo leg(s) still OWED: {', '.join(result.get('owed_non_repo_components') or [])} "
                f"(proven by execution/live-run, never by this tool's git check)"
            )
        elif result.get("completion_state") == "fully-done":
            # Only the repo-leg path sets completion_state -- a zero-leg DONE
            # (ledger-claim-only, not independently git-checkable) is NEVER
            # labeled "fully-done" here.
            print("COMPLETION: fully-done")
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
                if str(ci.get("status", "")).startswith("red"):
                    # Legible-enough-to-see-WHY, per the operator brief: never
                    # just print "red" and move on -- show both shas and, for
                    # each failing check name, whether current main confirms
                    # it live, shows it as a fossil, or the check no longer
                    # exists there at all.
                    print(f"       head_sha={ci.get('head_sha')} main_sha={ci.get('main_sha')}")
                    for fc in ci.get("failing_checks", []):
                        print(f"       - {fc['name']!r}: head={fc['head_conclusion']} "
                              f"main={fc['main_conclusion']} -- {fc['note']}")
    if "reason" in result:
        print(f"reason: {result['reason']}")
    if "ledger_status_cell" in result:
        print(f"(ledger's own status cell -- NOT trusted for the verdict above, shown for comparison only): {result.get('ledger_status_cell')}")


def _print_all_human(aggregate):
    """Compact per-unit lines, then the ONE summary line this mode exists
    for. The summary line is always last on stdout."""
    for r in aggregate["units"]:
        line = f"{r['unit']}: {r['verdict']}"
        if r.get("live_leg_owed"):
            line += f" (live leg OWED: {', '.join(r.get('owed_non_repo_components') or [])})"
        elif r.get("verdict") != "DONE":
            reason = r.get("reason") or r.get("tag_note") or ""
            if reason:
                line += f" -- {reason[:160]}"
        print(line)
    print(aggregate["summary_line"])


def _parse_explicit_units(raw_values):
    """--units values: each is a comma-separated list (the flag is also
    repeatable). Validate every id against ^U<digits>$ -- a malformed id is
    a loud usage error (exit 2), never silently skipped."""
    out = []
    for raw in raw_values:
        for tok in raw.split(","):
            tok = tok.strip()
            if not tok:
                continue
            if not re.match(r"^U[0-9]+$", tok):
                print(f"ERROR: --units entries must look like U<digits> (e.g. U108), got '{tok}'", file=sys.stderr)
                sys.exit(2)
            if tok not in out:
                out.append(tok)
    return sorted(out, key=lambda u: int(u[1:]))


def main():
    import argparse

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("unit_id", nargs="?", help="single unit id (omit when using --all / --units)")
    ap.add_argument("--all", action="store_true", dest="all_units",
                    help="aggregate mode: check EVERY unit with a row in the searched ledgers, "
                         "print one summary line with the tier breakdown")
    ap.add_argument("--units", action="append", dest="unit_list", metavar="U1,U2,...",
                    help="aggregate mode over an explicit comma-separated list (repeatable)")
    ap.add_argument("--onb-dir", required=True)
    ap.add_argument("--cc-dir", required=True)
    ap.add_argument("--ledger", action="append", dest="ledger_paths", required=True)
    ap.add_argument("--skip-ci", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    modes = sum(1 for m in (bool(args.unit_id), args.all_units, bool(args.unit_list)) if m)
    if modes != 1:
        ap.error("exactly one of <unit-id>, --all, or --units must be given")

    if args.all_units or args.unit_list:
        if args.all_units:
            unit_ids = list_ledger_unit_ids(args.ledger_paths)
            if not unit_ids:
                print(f"ERROR: --all found no unit rows in any of: {', '.join(str(p) for p in args.ledger_paths)}",
                      file=sys.stderr)
                sys.exit(2)
        else:
            unit_ids = _parse_explicit_units(args.unit_list)
            if not unit_ids:
                print("ERROR: --units parsed to an empty list", file=sys.stderr)
                sys.exit(2)
        aggregate = resolve_all_units(unit_ids, args.onb_dir, args.cc_dir, args.ledger_paths, skip_ci=args.skip_ci)
        if args.json:
            print(json.dumps(aggregate, indent=2, default=str))
        else:
            _print_all_human(aggregate)
        sys.exit(aggregate_exit_code(aggregate["counts"]))

    result = resolve_unit(args.unit_id, args.onb_dir, args.cc_dir, args.ledger_paths, skip_ci=args.skip_ci)

    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        _print_human(result)

    sys.exit(0 if result["verdict"] in ("DONE",) else (1 if result["verdict"] == "NOT-DONE" else 3))


if __name__ == "__main__":
    main()
