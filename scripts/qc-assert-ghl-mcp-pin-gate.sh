#!/usr/bin/env bash
# qc-assert-ghl-mcp-pin-gate.sh — the repo-side GHL MCP supply-chain pin gate.
#
# One script, three callers, identical verdict:
#   * CI job `ghl-mcp-pin-gate`  — with --network (has connectivity, must be
#     able to prove the pin is actually fetchable and the lockfile actually
#     matches, not merely that the file says so)
#   * the pre-push hook          — offline, fast, catches the realistic mistake
#     before it ever reaches origin
#   * a human, any time          — `bash scripts/qc-assert-ghl-mcp-pin-gate.sh`
#
# Three implementations of "is this pin OK" would be three chances to disagree,
# and when two gates disagree the effective policy is whichever one somebody
# turned off.
#
# CHECKS
#   1. The vetting record is well-formed, sealed, and the digest recomputes,
#      and the verdict is CLEAN. Delegated to ghl-mcp-check-pin-digest.sh, which
#      owns the canonical form.
#   2. The built-in fallback constants in the launch scripts equal the pin.
#      A box that cannot read the pin file falls back to constants baked into
#      the scripts; if those drift, a roll writes one pin while every later
#      off-roll run (probe --heal, manual remediation, Step 14a) uses another.
#      That split-brain is invisible from the repo, so CI has to look for it.
#      If a script carries no fallback at all, that is fine and is reported --
#      whether to keep a fallback or refuse outright is the installer's call,
#      not this gate's.
#   3. Every pin-file search path any consumer uses is also searched by the
#      digest checker (delegated to qc-assert-ghl-mcp-pin-resolvers.py), so the
#      gate can never validate a different file from the one the box executes.
#   4. --network: the pinned commit is fetchable BY SHA from the mirror. This is
#      the check that would have caught the original fragility -- the pin used to
#      resolve only because it happened to be upstream main's tip.
#   5. --network: sha256(package-lock.json at the pinned commit, fetched from the
#      mirror) equals GHL_MCP_DEPS_LOCK_SHA256. The verdict claims the dependency
#      graph was reviewed; this proves the claim is about the tree that will
#      actually be installed.
#   6. --base-ref REF: if GHL_MCP_VETTED_COMMIT changed in this diff, the review
#      date must have advanced too. Largely subsumed by the digest (a bare SHA
#      swap breaks it), but it catches a re-seal that reuses a stale date.
#
# USAGE
#   qc-assert-ghl-mcp-pin-gate.sh [--network] [--base-ref REF] [--quiet]
#
# EXIT
#   0 = every applicable check passed
#   1 = at least one check FAILED
#   2 = the gate could not run (missing dependency script, no network when
#       --network was requested). Never treat 2 as a pass.

set -uo pipefail

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
REPO_ROOT="$(cd "$SELF_DIR/.." && pwd)"

DO_NETWORK=0
BASE_REF=""
QUIET=0
while [ $# -gt 0 ]; do
  case "$1" in
    --network)  DO_NETWORK=1 ;;
    --base-ref) BASE_REF="${2:-}"; shift ;;
    --quiet|-q) QUIET=1 ;;
    -h|--help)  sed -n '2,50p' "$0"; exit 0 ;;
    *) echo "qc-assert-ghl-mcp-pin-gate.sh: unknown argument '$1'" >&2; exit 2 ;;
  esac
  shift
done

FAILURES=0
say()   { [ "$QUIET" -eq 1 ] || printf '%s\n' "$*"; }
_pass() { say "PASS  $*"; }
_info() { say "INFO  $*"; }
_fail() { printf 'FAIL  %s\n' "$*" >&2; FAILURES=$((FAILURES+1)); }
_stop() { printf 'CANNOT RUN  %s\n' "$*" >&2; exit 2; }

PIN_FILE="$REPO_ROOT/config/ghl-mcp-pin.env"
CHECKER="$REPO_ROOT/scripts/ghl-mcp-check-pin-digest.sh"
RESOLVERS="$REPO_ROOT/scripts/qc-assert-ghl-mcp-pin-resolvers.py"

[ -f "$PIN_FILE" ] || _stop "config/ghl-mcp-pin.env is missing — there is no pin to gate."
[ -f "$CHECKER" ]  || _stop "scripts/ghl-mcp-check-pin-digest.sh is missing — this gate will not reimplement the digest."

say "=== ghl-mcp-pin-gate ==="

# ── 1. Sealed, self-consistent, CLEAN ────────────────────────────────────────
DIGEST_OUT="$(bash "$CHECKER" --pin-file "$PIN_FILE" 2>&1)"
DIGEST_RC=$?
case "$DIGEST_RC" in
  0) _pass "vetting record is sealed, the digest recomputes, and the verdict is CLEAN" ;;
  3) _stop "no sha256 utility available — the digest was NOT verified. This is not a pass." ;;
  *) _fail "vetting record rejected by ghl-mcp-check-pin-digest.sh:"
     printf '%s\n' "$DIGEST_OUT" | sed 's/^/        /' >&2 ;;
esac

field() {
  awk -v key="$1" '
    $0 ~ "^" key "=\"" {
      line = $0; sub("^" key "=\"", "", line)
      idx = index(line, "\""); val = (idx > 0) ? substr(line, 1, idx - 1) : ""
      found = 1
    } END { if (found) print val }' "$PIN_FILE"
}
PIN_COMMIT="$(field GHL_MCP_VETTED_COMMIT)"
PIN_REPO="$(field GHL_MCP_REPO_URL)"
PIN_LOCK="$(field GHL_MCP_DEPS_LOCK_SHA256)"

# ── 2. Built-in fallback constants must equal the pin ────────────────────────
for rel in scripts/ghl-mcp-autostart.sh platform/vps/36-ghl-mcp-setup-scripts/start-ghl-mcp-server.sh; do
  f="$REPO_ROOT/$rel"
  if [ ! -f "$f" ]; then
    _info "$rel is absent — no fallback to compare"
    continue
  fi
  fb_commit="$(sed -n 's|^[[:space:]]*GHL_MCP_VETTED_COMMIT="${GHL_MCP_VETTED_COMMIT:-\([0-9a-f]*\)}".*|\1|p' "$f" | tail -1)"
  fb_repo="$(sed -n 's|^[[:space:]]*GHL_MCP_REPO_URL="${GHL_MCP_REPO_URL:-\([^}]*\)}".*|\1|p' "$f" | tail -1)"
  if [ -z "$fb_commit" ]; then
    _info "$rel carries no built-in commit fallback (the installer refuses instead) — nothing to keep in lockstep"
  elif [ "$fb_commit" = "$PIN_COMMIT" ]; then
    _pass "$rel built-in commit fallback equals the pin"
  else
    _fail "$rel built-in commit fallback is $fb_commit but the pin is $PIN_COMMIT — split-brain pin: a roll would use one and every later off-roll run the other. Re-run scripts/ghl-mcp-vet-pin.sh, which writes both."
  fi
  if [ -z "$fb_repo" ]; then
    _info "$rel carries no built-in repo-URL fallback"
  elif [ "$fb_repo" = "$PIN_REPO" ]; then
    _pass "$rel built-in repo-URL fallback equals the pin"
  else
    _fail "$rel built-in repo-URL fallback is $fb_repo but the pin is $PIN_REPO — a box falling back would clone from a different source than the one the verdict covers."
  fi
done

# ── 3. Resolver-path sync ────────────────────────────────────────────────────
if [ -f "$RESOLVERS" ]; then
  if RES_OUT="$(python3 "$RESOLVERS" 2>&1)"; then
    _pass "every consumer's pin-file search path is covered by the digest checker"
  else
    _fail "pin-file resolver drift — the gate could validate a different file from the one a box reads:"
    printf '%s\n' "$RES_OUT" | sed 's/^/        /' >&2
  fi
else
  _fail "scripts/qc-assert-ghl-mcp-pin-resolvers.py is missing — resolver sync unverified."
fi

# ── 4/5. Network: the pin must actually be fetchable, and the lockfile must match
if [ "$DO_NETWORK" -eq 1 ]; then
  command -v git >/dev/null 2>&1 || _stop "--network requested but git is not on PATH."
  case "$PIN_REPO" in
    https://*|http://*) : ;;
    *) _fail "GHL_MCP_REPO_URL='$PIN_REPO' is not an http(s) URL — cannot verify reachability."; PIN_REPO="" ;;
  esac
  if [ -n "$PIN_REPO" ] && [ -n "$PIN_COMMIT" ]; then
    NETDIR="$(mktemp -d "${TMPDIR:-/tmp}/ghl-pin-gate.XXXXXX")" || _stop "cannot create a temp dir"
    trap 'rm -rf "$NETDIR"' EXIT
    (
      cd "$NETDIR" || exit 1
      git init --quiet . >/dev/null 2>&1 || exit 1
      git remote add origin "$PIN_REPO" >/dev/null 2>&1 || exit 1
      git fetch --quiet --depth 1 origin "$PIN_COMMIT" >/dev/null 2>&1
    )
    if [ -d "$NETDIR/.git" ] && git -C "$NETDIR" cat-file -e "${PIN_COMMIT}^{commit}" 2>/dev/null; then
      _pass "pinned commit is fetchable BY SHA from $PIN_REPO (a fresh box can provision)"
      LOCK_ACTUAL="$(git -C "$NETDIR" show "${PIN_COMMIT}:package-lock.json" 2>/dev/null | { shasum -a 256 2>/dev/null || sha256sum 2>/dev/null; } | awk '{print $1}')"
      if [ -z "$LOCK_ACTUAL" ]; then
        _fail "could not read package-lock.json at $PIN_COMMIT from the mirror — the dependency half of the verdict is unverifiable."
      elif [ "$LOCK_ACTUAL" = "$PIN_LOCK" ]; then
        _pass "sha256(package-lock.json @ pin) matches GHL_MCP_DEPS_LOCK_SHA256"
      else
        _fail "lockfile hash mismatch — pin file says $PIN_LOCK, the mirror serves $LOCK_ACTUAL. The dependency graph the verdict covers is not the one that would be installed."
      fi
    else
      _fail "pinned commit $PIN_COMMIT is NOT fetchable by SHA from $PIN_REPO. Every FRESH provisioning would fail with PIN_MISMATCH. If the source was just repointed, the mirror has not been seeded with this commit."
    fi
  fi
else
  _info "network checks skipped (pass --network to prove the pin is fetchable and the lockfile matches)"
fi

# ── 6. A changed commit must carry a changed review date ────────────────────
if [ -n "$BASE_REF" ]; then
  if OLD_PIN="$(git -C "$REPO_ROOT" show "${BASE_REF}:config/ghl-mcp-pin.env" 2>/dev/null)"; then
    old_field() {
      printf '%s\n' "$OLD_PIN" | awk -v key="$1" '
        $0 ~ "^" key "=\"" {
          line = $0; sub("^" key "=\"", "", line)
          idx = index(line, "\""); val = (idx > 0) ? substr(line, 1, idx - 1) : ""
          found = 1
        } END { if (found) print val }'
    }
    OLD_COMMIT="$(old_field GHL_MCP_VETTED_COMMIT)"
    OLD_ON="$(old_field GHL_MCP_PIN_VETTED_ON)"
    NEW_ON="$(field GHL_MCP_PIN_VETTED_ON)"
    if [ -z "$OLD_COMMIT" ]; then
      _info "no comparable pin at $BASE_REF — skipping the date-advance check"
    elif [ "$OLD_COMMIT" = "$PIN_COMMIT" ]; then
      _pass "pinned commit unchanged since $BASE_REF"
    elif [ "$OLD_ON" = "$NEW_ON" ]; then
      _fail "the pinned commit changed ($OLD_COMMIT -> $PIN_COMMIT) but GHL_MCP_PIN_VETTED_ON is still $NEW_ON. A new commit was not reviewed on the same day the old one was."
    else
      _pass "pinned commit changed and the review date advanced ($OLD_ON -> $NEW_ON)"
    fi
  else
    _info "could not read config/ghl-mcp-pin.env at $BASE_REF — skipping the date-advance check"
  fi
fi

say ""
if [ "$FAILURES" -eq 0 ]; then
  say "ghl-mcp-pin-gate: OK"
  exit 0
fi
printf 'ghl-mcp-pin-gate: %d FAILURE(S)\n' "$FAILURES" >&2
exit 1
