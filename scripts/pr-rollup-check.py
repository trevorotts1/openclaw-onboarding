#!/usr/bin/env python3
"""pr-rollup-check.py — the ONLY question that matters before you report a PR
green: what does the PR's OWN required-check rollup say, right now.

WHY THIS EXISTS
----------------
"Branch green" (a workflow run on a ref, `gh run list --branch <b>`, a local
`gh run watch`) and "PR green" (the PR's required-check rollup, the thing the
Merge button actually reads) are TWO DIFFERENT QUESTIONS, and this repo paid
for confusing them three times in one session: PR #941 showed 5 red gates at
PR level after being called green; #943 and #946 each hit gate G3 at PR level
after being called green too (see CONTROL/DELAY-DIAGNOSIS-FABLE.md #3 row 12,
#7 item 4). A branch-scoped check can be fully green while the PR rollup is
red, because the PR rollup includes required contexts a branch-scoped check
never runs (G1/G1b/G2/G3 version-ceremony gates, ghl-mcp-pin-gate, etc.) and
because the SAME context name can legitimately appear MORE THAN ONCE in a
PR's rollup (re-runs, or two workflow triggers producing two check runs with
identical names) with DIFFERENT states — this script hit that live on PR #955
(`ghl-mcp-pin-gate` reporting both `pending` and `pass` in the same rollup).

THE RULE (also in AGENTS.md N42): BRANCH GREEN IS NOT GREEN. ONLY THE PR
ROLLUP IS GREEN. Never report a PR mergeable from a branch-scoped check, a
partial `gh pr checks` glance, or a memory of what the last run showed.
Run this script against the PR NUMBER and read its exit code.

WHAT THIS CHECKS
----------------
The exact set of required status-check CONTEXTS this repo's branch-protection
ruleset (or classic branch-protection required_status_checks, whichever is
configured) demands for the PR's base branch — fetched LIVE from the GitHub
API by default, never a guessed or hand-maintained list. As of the
investigation that shipped this script (2026-08-20), that live source is the
ruleset "main-required-checks" (id 20330619) on `trevorotts1/openclaw-onboarding`,
and it names exactly EIGHT contexts:
  1. ghl-mcp-pin-gate
  2. GHL MCP supervision + install regression guard
  3. QC static invariants
  4. G1 — version file change requires a matching annotated tag (push to main)
  5. G1b — every release on main must keep a truthful annotated tag
  6. G2 — every v11+ annotated tag must have a CHANGELOG entry
  7. G3 — skill content change requires skill-version.txt bump
  8. Verify all version markers agree (scripts/bump-version.sh --check)
This script re-fetches that list live on every run (`gh api
repos/<repo>/rulesets` + `/rulesets/<id>`, unioned with classic branch
protection `required_status_checks` if that is ALSO configured) so it can
never go stale the way a hardcoded copy would. If the live fetch fails for a
real reason (network, permission — NOT a clean 404 meaning "not configured"),
it falls back to a checked-in, provenance-stamped snapshot
(`scripts/pr-rollup-required-contexts.fallback.json`) and says so LOUDLY —
a degraded run is never reported as equivalent to a live one.

For each required context, every matching check-run entry in the PR's rollup
is inspected (not just the first match — see the duplicate-name trap above)
and reduced with FAIL beats PENDING beats PASS: any failing run makes that
context FAILED; otherwise any non-terminal run makes it PENDING; a `skipping`
conclusion counts as PASS (this is GitHub's own merge-gate behavior — see
PR #941/#943/#946/#952, all merged while G1 reported `skipping` on every one).
A required context with ZERO matching runs in the rollup is reported as
EXPECTED — this is the literal state a real merge attempt on PR #952 showed
("8 of 8 required status checks are expected") and it is NOT green.

LOAD-BEARING GH-CLI TRAP THIS SCRIPT WORKS AROUND
--------------------------------------------------
`gh pr checks <N> --required` (no --json) sets its OWN process exit code from
the check states (0 pass / 1 fail / 8 pending) — but the INSTANT you add
`--json`, gh's exit code reverts to "did the query succeed", not "did checks
pass": a PR with a live FAILING required context returns JSON exit 0. Proven
live on PR #956 during the investigation that shipped this script (G1b was
`bucket:"fail"` in the JSON; `gh pr checks 956 --required --json ...; echo $?`
still printed 0). This script NEVER trusts gh's own exit code from a --json
invocation for the pass/fail verdict — it parses the `bucket` field itself and
computes its own exit code, which IS reliable and IS what a pipeline should use.

EXIT CODES (the only thing a pipeline should branch on)
---------------------------------------------------------
  0  GREEN   — every required context is PASS (or SKIPPED, which counts as pass)
  1  RED     — at least one required context has actually FAILED
  2  RED     — no context has failed, but at least one is PENDING or EXPECTED
               (not started / still running) — NOT mergeable, NOT a failure either
  3  ERROR   — could not determine the answer at all (gh missing, PR not
               found, API/auth failure, malformed response). NEVER printed as
               green. Per this repo's negative-result contract, this is a
               correct, distinct answer — not a bug in the tool being probed.

USAGE
-----
  scripts/pr-rollup-check.py 955
  scripts/pr-rollup-check.py 955 --repo trevorotts1/openclaw-onboarding
  scripts/pr-rollup-check.py 955 --json          # machine-readable report
                                                  # (still uses the exit codes
                                                  # above — see the gh trap
                                                  # note; this script does NOT
                                                  # repeat that mistake)

NEVER modifies branch protection, rulesets, or any check. Read-only.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import shutil
import subprocess
import sys
from pathlib import Path

DEFAULT_REPO = "trevorotts1/openclaw-onboarding"
FALLBACK_FILE = Path(__file__).resolve().parent / "pr-rollup-required-contexts.fallback.json"

EXIT_GREEN = 0
EXIT_RED_FAILED = 1
EXIT_RED_PENDING = 2
EXIT_ERROR = 3

TERMINAL_PASS = {"SUCCESS", "SKIPPED", "NEUTRAL"}
TERMINAL_FAIL = {"FAILURE", "CANCELLED", "TIMED_OUT", "ACTION_REQUIRED", "STALE", "ERROR"}
# Anything else observed (QUEUED, IN_PROGRESS, PENDING, REQUESTED, WAITING, "")
# is treated as PENDING — not terminal, not green.

BUCKET_PASS = {"pass", "skipping"}
BUCKET_FAIL = {"fail", "cancel"}
# gh's own "pending" bucket is treated as PENDING (see TERMINAL_* above for the
# raw-state equivalent used when this script computes bucket_of() itself).


def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


def find_gh():
    """Return the resolved path to `gh`, or None. Never assumes PATH is sane —
    this is the exact class of bug (a Homebrew binary missing from cron's
    PATH) this whole hardening campaign exists to kill."""
    return shutil.which("gh")


def run_gh(gh_path, args, timeout=60):
    """Run gh with the given args. Returns (rc, stdout, stderr). Never raises
    on a nonzero exit — the caller decides what a nonzero rc means. Captures
    stderr explicitly (2>&1 is NOT used — stdout/stderr are kept separate so
    JSON parsing of stdout is never corrupted by a warning on stderr)."""
    try:
        proc = subprocess.run(
            [gh_path] + args,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired as e:
        return 124, "", "TIMEOUT after %ss running: gh %s (%s)" % (timeout, " ".join(args), e)
    except OSError as e:
        return 127, "", "OSError invoking gh: %s" % e


def ref_matches(branch, patterns):
    full = "refs/heads/%s" % branch
    for p in patterns:
        if p in (full, branch):
            return True
        if "*" in p and fnmatch.fnmatch(full, p):
            return True
    return False


def fetch_required_contexts_live(gh_path, repo, branch):
    """Returns (contexts:set[str], errors:list[str], sources:list[str]).
    `errors` is non-empty only for REAL failures (auth, network, malformed
    JSON) — a clean 404 meaning "no classic branch protection configured" is
    NOT an error, it's a legitimate empty result from that one source."""
    contexts = set()
    errors = []
    sources = []

    # Source 1: rulesets (this repo's actual enforcement mechanism as of the
    # investigation that shipped this script — but this script does NOT
    # assume that stays true; it queries live every run).
    rc, out, err = run_gh(gh_path, ["api", "repos/%s/rulesets" % repo])
    if rc != 0:
        if "404" not in err:
            errors.append("rulesets list failed (rc=%d): %s" % (rc, err.strip()))
    else:
        try:
            rulesets = json.loads(out)
        except json.JSONDecodeError as e:
            errors.append("rulesets list returned unparseable JSON: %s" % e)
            rulesets = []
        for rs in rulesets:
            if rs.get("target") != "branch":
                continue
            if rs.get("enforcement") != "active":
                continue  # "evaluate"/"disabled" rulesets don't block merges
            rc2, out2, err2 = run_gh(gh_path, ["api", "repos/%s/rulesets/%s" % (repo, rs["id"])])
            if rc2 != 0:
                errors.append("ruleset %s detail fetch failed (rc=%d): %s" % (rs.get("id"), rc2, err2.strip()))
                continue
            try:
                detail = json.loads(out2)
            except json.JSONDecodeError as e:
                errors.append("ruleset %s detail unparseable: %s" % (rs.get("id"), e))
                continue
            include = detail.get("conditions", {}).get("ref_name", {}).get("include", [])
            if not ref_matches(branch, include):
                continue
            for rule in detail.get("rules", []):
                if rule.get("type") != "required_status_checks":
                    continue
                for c in rule.get("parameters", {}).get("required_status_checks", []):
                    ctx = c.get("context")
                    if ctx:
                        contexts.add(ctx)
                        sources.append("ruleset:%s(%s)" % (detail.get("name"), rs.get("id")))

    # Source 2: classic branch protection (unioned in if ALSO configured).
    rc, out, err = run_gh(gh_path, ["api", "repos/%s/branches/%s/protection" % (repo, branch)])
    if rc != 0:
        if "404" not in err:
            errors.append("branch protection fetch failed (rc=%d): %s" % (rc, err.strip()))
    else:
        try:
            prot = json.loads(out)
        except json.JSONDecodeError as e:
            errors.append("branch protection returned unparseable JSON: %s" % e)
            prot = {}
        rsc = prot.get("required_status_checks") or {}
        for ctx in rsc.get("contexts", []) or []:
            contexts.add(ctx)
            sources.append("classic-protection")
        for chk in rsc.get("checks", []) or []:
            ctx = chk.get("context")
            if ctx:
                contexts.add(ctx)
                sources.append("classic-protection")

    return contexts, errors, sorted(set(sources))


def fetch_required_contexts_fallback():
    if not FALLBACK_FILE.exists():
        return set(), "no fallback file at %s" % FALLBACK_FILE
    try:
        data = json.loads(FALLBACK_FILE.read_text())
    except (OSError, json.JSONDecodeError) as e:
        return set(), "fallback file unreadable/unparseable: %s" % e
    return set(data.get("required_contexts", [])), data.get("provenance", "no provenance recorded")


def get_required_contexts(gh_path, repo, branch):
    """Returns (contexts:set[str], mode:str, detail:str)."""
    live_contexts, errors, sources = fetch_required_contexts_live(gh_path, repo, branch)
    if not errors:
        return live_contexts, "live", "sources=%s" % (sources or ["none configured"])
    # Real error(s) occurred. If live still found something, prefer it but
    # warn; only fall all the way back to the cache if live found NOTHING.
    if live_contexts:
        return live_contexts, "live-with-errors", "errors=%s" % errors
    fb_contexts, fb_provenance = fetch_required_contexts_fallback()
    if fb_contexts:
        return fb_contexts, "FALLBACK-CACHED", "live errors=%s | fallback provenance=%s" % (errors, fb_provenance)
    return set(), "ERROR", "live errors=%s | fallback also empty/unavailable: %s" % (errors, fb_provenance)


def fetch_pr_meta(gh_path, repo, pr):
    rc, out, err = run_gh(gh_path, [
        "pr", "view", str(pr), "--repo", repo,
        "--json", "number,url,title,state,baseRefName,headRefName,mergeStateStatus,mergeable",
    ])
    if rc != 0:
        return None, "gh pr view failed (rc=%d): %s" % (rc, err.strip() or out.strip() or "(no output)")
    try:
        return json.loads(out), None
    except json.JSONDecodeError as e:
        return None, "gh pr view returned unparseable JSON: %s" % e


def fetch_required_checks(gh_path, repo, pr):
    rc, out, err = run_gh(gh_path, [
        "pr", "checks", str(pr), "--repo", repo, "--required",
        "--json", "name,bucket,state,workflow,link,description,completedAt",
    ])
    if rc != 0:
        # Note: with --required and zero required checks configured, gh
        # still exits 0 with `[]`; a nonzero rc here is a real query failure
        # (bad PR number, auth, network), never "no required checks."
        return None, "gh pr checks --required failed (rc=%d): %s" % (rc, err.strip() or out.strip() or "(no output)")
    try:
        return json.loads(out), None
    except json.JSONDecodeError as e:
        return None, "gh pr checks returned unparseable JSON: %s" % e


def bucket_of(entry):
    b = (entry.get("bucket") or "").lower()
    if b:
        return b
    # Fall back to raw state if gh ever omits bucket for a shape we didn't expect.
    state = (entry.get("state") or "").upper()
    if state in TERMINAL_PASS:
        return "pass"
    if state in TERMINAL_FAIL:
        return "fail"
    return "pending"


def classify(required_contexts, entries):
    """Returns (per_context: dict[str, dict], overall: str) where overall is
    one of GREEN / RED_FAILED / RED_PENDING."""
    by_name = {}
    for e in entries:
        by_name.setdefault(e.get("name", ""), []).append(e)

    reported_names = set(by_name.keys())
    per_context = {}

    for ctx in sorted(required_contexts):
        matches = by_name.get(ctx, [])
        if not matches:
            per_context[ctx] = {"verdict": "EXPECTED", "detail": "no check run found in this PR's rollup yet", "runs": []}
            continue
        buckets = [bucket_of(m) for m in matches]
        if any(b in BUCKET_FAIL for b in buckets):
            per_context[ctx] = {"verdict": "FAILED", "detail": "%d run(s), >=1 failing" % len(matches), "runs": matches}
        elif any(b not in BUCKET_PASS for b in buckets):
            per_context[ctx] = {"verdict": "PENDING", "detail": "%d run(s), >=1 not yet resolved" % len(matches), "runs": matches}
        else:
            per_context[ctx] = {"verdict": "PASS", "detail": "%d run(s), all pass/skipped" % len(matches), "runs": matches}

    extra = reported_names - set(required_contexts) - {""}

    if any(v["verdict"] == "FAILED" for v in per_context.values()):
        overall = "RED_FAILED"
    elif any(v["verdict"] in ("PENDING", "EXPECTED") for v in per_context.values()):
        overall = "RED_PENDING"
    else:
        overall = "GREEN"

    return per_context, overall, extra


def main():
    ap = argparse.ArgumentParser(description="Authoritative PR-rollup PASS/FAIL check. See module docstring.")
    ap.add_argument("pr", type=int, help="Pull request number")
    ap.add_argument("--repo", default=DEFAULT_REPO, help="owner/repo (default: %s)" % DEFAULT_REPO)
    ap.add_argument("--branch", default=None, help="Base branch to resolve required contexts for (default: the PR's own base branch)")
    ap.add_argument("--json", action="store_true", dest="as_json", help="Emit a machine-readable report on stdout (exit code is still the authoritative signal)")
    args = ap.parse_args()

    gh_path = find_gh()
    if not gh_path:
        eprint("ERROR: `gh` is not resolvable in PATH. This is a TOOL FAILURE, not a fact about PR #%d." % args.pr)
        eprint("PATH searched: %s" % __import__("os").environ.get("PATH", "(empty)"))
        eprint("UNDETERMINED — cannot check the PR rollup without gh. Fix PATH (gh is a Homebrew binary; cron/launchd PATHs frequently omit /opt/homebrew/bin) and retry.")
        sys.exit(EXIT_ERROR)

    pr_meta, err = fetch_pr_meta(gh_path, args.repo, args.pr)
    if err:
        eprint("ERROR: could not load PR #%d in %s: %s" % (args.pr, args.repo, err))
        eprint("UNDETERMINED — this is not a report of red or green; the PR could not be identified at all.")
        sys.exit(EXIT_ERROR)

    branch = args.branch or pr_meta.get("baseRefName") or "main"

    required_contexts, ctx_mode, ctx_detail = get_required_contexts(gh_path, args.repo, branch)
    if ctx_mode == "ERROR":
        eprint("ERROR: could not determine the required-context list for %s@%s from ANY source (live API or cached fallback)." % (args.repo, branch))
        eprint("Detail: %s" % ctx_detail)
        eprint("UNDETERMINED — refusing to guess a required-check list.")
        sys.exit(EXIT_ERROR)

    entries, err = fetch_required_checks(gh_path, args.repo, args.pr)
    if err:
        eprint("ERROR: could not load required checks for PR #%d: %s" % (args.pr, err))
        eprint("UNDETERMINED.")
        sys.exit(EXIT_ERROR)

    per_context, overall, extra = classify(required_contexts, entries)

    exit_code = {"GREEN": EXIT_GREEN, "RED_FAILED": EXIT_RED_FAILED, "RED_PENDING": EXIT_RED_PENDING}[overall]

    if args.as_json:
        report = {
            "pr": args.pr,
            "repo": args.repo,
            "url": pr_meta.get("url"),
            "base_branch": branch,
            "required_context_source": ctx_mode,
            "required_context_source_detail": ctx_detail,
            "required_context_count": len(required_contexts),
            "overall": overall,
            "exit_code": exit_code,
            "contexts": {
                ctx: {"verdict": v["verdict"], "detail": v["detail"]}
                for ctx, v in per_context.items()
            },
            "unexpected_reported_contexts": sorted(extra),
        }
        print(json.dumps(report, indent=2))
    else:
        print("PR #%d — %s" % (args.pr, pr_meta.get("url", "")))
        print("Required-context source: %s (%s)" % (ctx_mode, ctx_detail))
        if ctx_mode != "live":
            print("*** DEGRADED: not a fresh live read of branch protection — treat with suspicion. ***")
        print("Base branch: %s | %d required context(s)" % (branch, len(required_contexts)))
        print("-" * 72)
        for ctx in sorted(per_context):
            v = per_context[ctx]
            print("[%-8s] %s  (%s)" % (v["verdict"], ctx, v["detail"]))
        if extra:
            print("-" * 72)
            print("NOTE: rollup also reported context(s) not in the required list (informational, non-blocking): %s" % ", ".join(sorted(extra)))
        print("-" * 72)
        failing = [c for c, v in per_context.items() if v["verdict"] == "FAILED"]
        pending = [c for c, v in per_context.items() if v["verdict"] in ("PENDING", "EXPECTED")]
        if overall == "GREEN":
            print("PR-ROLLUP: GREEN — all %d required contexts pass." % len(required_contexts))
        elif overall == "RED_FAILED":
            print("PR-ROLLUP: RED — FAILED (%d failing): %s" % (len(failing), "; ".join(failing)))
            if pending:
                print("  also not-yet-resolved (%d): %s" % (len(pending), "; ".join(pending)))
        else:
            print("PR-ROLLUP: RED — NOT GREEN, pending/expected (%d): %s" % (len(pending), "; ".join(pending)))
        print("BRANCH GREEN IS NOT GREEN. ONLY THIS ROLLUP IS GREEN.")

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
