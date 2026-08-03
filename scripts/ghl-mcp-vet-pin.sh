#!/usr/bin/env bash
# ghl-mcp-vet-pin.sh — the ONLY thing permitted to write the GHL Community MCP
# vetting record. Review a candidate commit, then seal the verdict to it.
#
# ── THE PROBLEM THIS SOLVES ──────────────────────────────────────────────────
# The pin used to be bumped by hand-editing three files and remembering a rule
# written in a comment. Nothing checked the rule, so the verdict drifted away
# from the commit it was a verdict ABOUT, silently, and the review it claimed to
# record may never have happened. Making CI assert VERDICT == CLEAN would not
# fix that: it is one word to edit, and it teaches whoever edits it which word
# makes the build green.
#
# So the enforcement mechanism IS the ergonomics. This tool performs the review
# and seals the result in one motion, and it is the cheapest way to get a valid
# record -- cheaper than the hand-edit it replaces. Nothing else can produce a
# digest that the CI job, the pre-push hook and the box-side installer accept.
# Forgetting to re-vet does not slip through; it fails closed everywhere.
#
# ── WORKFLOW: A LEGITIMATE PIN BUMP IS TWO COMMANDS ──────────────────────────
#   1. REVIEW (read-only, writes nothing, safe to run any time):
#        scripts/ghl-mcp-vet-pin.sh <candidate-sha>
#      Prints a mechanical report over the four dimensions that decide whether a
#      third-party MCP is safe to run next to a CRM credential:
#        1. Credential layer     -- what touches the token
#        2. Outbound surface     -- what hosts the tree can now talk to
#        3. Endpoint construction-- can a response redirect a request off-origin
#        4. Dependency graph     -- what the lockfile pulls in
#      Reading this report is the ONLY part of the job that needs judgment.
#
#   2. SEAL (writes the pin file and the built-in fallbacks):
#        scripts/ghl-mcp-vet-pin.sh <candidate-sha> --verdict clean
#      There is no default verdict and there is no "reseal" shortcut: sealing
#      always reprints the review first, so the record can never be refreshed
#      without the review being put back in front of a human.
#
#   3. PROVE IT ON ONE BOX (the commands are printed for you when the seal succeeds).
#
# ── OPTIONS ──────────────────────────────────────────────────────────────────
#   --verdict clean|dirty   Required to write anything. No default, ever.
#   --by "text"             Reviewer attribution. Defaults to a generic, non-
#                           identifying string -- this repository is public and
#                           must never carry an operator or client identity.
#   --mirror URL            Override the mirror to review against. Defaults to
#                           GHL_MCP_REPO_URL from the pin file.
#   --pin-file PATH         Override the pin file location.
#   --dry-run               Do the whole seal but print the result instead of
#                           writing it.
#   --max-lines N           Cap per-dimension report output (default 60).
#
# ── EXIT CODES ───────────────────────────────────────────────────────────────
#   0  sealed (or, in review mode, report printed and the tree is reviewable)
#   1  refused -- bad candidate, unreachable commit, verdict dirty, write failed
#   2  environment problem (no git / no python3 / mirror unreachable)
#   3  review-only run: report printed, nothing written, no verdict supplied
#
# ── WHY THE MIRROR AND NOT UPSTREAM ──────────────────────────────────────────
# Upstream force-pushes rewritten history and publishes no tags and no releases.
# A commit reachable there today can be garbage-collected tomorrow, taking every
# fresh install with it and making the previously vetted tree un-re-reviewable.
# The mirror is the trust root precisely because we control its garbage
# collection; resolving a candidate anywhere else would make the review a
# statement about something that may no longer exist.

set -uo pipefail

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
REPO_ROOT="$(cd "$SELF_DIR/.." && pwd)"

PIN_FILE=""
CANDIDATE=""
VERDICT=""
VET_BY="openclaw-onboarding commit-vetting review (credential layer, outbound hosts, endpoint construction, dependency graph)"
MIRROR_URL=""
DRY_RUN=0
MAX_LINES=60

while [ $# -gt 0 ]; do
  case "$1" in
    --verdict)   VERDICT="$(printf '%s' "${2:-}" | tr '[:upper:]' '[:lower:]')"; shift ;;
    --by)        VET_BY="${2:-}"; shift ;;
    --mirror)    MIRROR_URL="${2:-}"; shift ;;
    --pin-file)  PIN_FILE="${2:-}"; shift ;;
    --max-lines) MAX_LINES="${2:-60}"; shift ;;
    --dry-run)   DRY_RUN=1 ;;
    -h|--help)   sed -n '2,60p' "$0"; exit 0 ;;
    -*)          echo "ghl-mcp-vet-pin.sh: unknown option '$1'" >&2; exit 1 ;;
    *)           CANDIDATE="$1" ;;
  esac
  shift
done

die()  { printf '\nREFUSED: %s\n' "$*" >&2; exit 1; }
envdie(){ printf '\nCANNOT RUN: %s\n' "$*" >&2; exit 2; }
hr()   { printf '%s\n' "────────────────────────────────────────────────────────────────────────"; }
head_n(){ awk -v n="$MAX_LINES" 'NR<=n{print} END{if(NR>n) printf "  … %d more line(s) suppressed — see the full-diff command above\n", NR-n}'; }

command -v git     >/dev/null 2>&1 || envdie "git is not on PATH."
command -v python3 >/dev/null 2>&1 || envdie "python3 is not on PATH (needed to compare lockfiles structurally)."

CHECKER="$SELF_DIR/ghl-mcp-check-pin-digest.sh"
[ -f "$CHECKER" ] || envdie "scripts/ghl-mcp-check-pin-digest.sh is missing — it owns the canonical digest form and this tool will not reimplement it."

[ -n "$PIN_FILE" ] || PIN_FILE="$REPO_ROOT/config/ghl-mcp-pin.env"
[ -f "$PIN_FILE" ] || die "pin file not found at $PIN_FILE"

if [ -z "$CANDIDATE" ]; then
  echo "usage: ghl-mcp-vet-pin.sh <candidate-sha> [--verdict clean|dirty] [--by \"...\"]" >&2
  echo "       run with no --verdict first to read the review report." >&2
  exit 1
fi

case "$VERDICT" in
  ""|clean|dirty) : ;;
  *) die "--verdict must be 'clean' or 'dirty' (got '$VERDICT'). There is no default." ;;
esac

# ── Read the record currently in force ───────────────────────────────────────
cur_field() {
  awk -v key="$1" '
    $0 ~ "^" key "=\"" {
      line = $0; sub("^" key "=\"", "", line)
      idx = index(line, "\""); val = (idx > 0) ? substr(line, 1, idx - 1) : ""
      found = 1
    } END { if (found) print val }' "$PIN_FILE"
}
CUR_COMMIT="$(cur_field GHL_MCP_VETTED_COMMIT)"
CUR_REPO="$(cur_field GHL_MCP_REPO_URL)"
[ -n "$MIRROR_URL" ] || MIRROR_URL="$CUR_REPO"
[ -n "$MIRROR_URL" ] || die "no mirror URL: the pin file declares no GHL_MCP_REPO_URL and --mirror was not given."

case "$MIRROR_URL" in
  https://*|http://*) : ;;
  *) die "mirror URL '$MIRROR_URL' is not an http(s) URL." ;;
esac

# ── The candidate must be a SHA. A branch name is not a pin ──────────────────
case "$CANDIDATE" in
  *[!0-9a-f]*) die "candidate '$CANDIDATE' is not a hex commit SHA. A branch name or tag is not a pin — 'git checkout main' keeps succeeding forever while the tree underneath it changes." ;;
esac
[ "${#CANDIDATE}" -ge 7 ] || die "candidate '$CANDIDATE' is too short to resolve unambiguously."

# ── Fetch the mirror into a cache ────────────────────────────────────────────
CACHE_ROOT="${GHL_MCP_VET_CACHE:-$HOME/.cache/ghl-mcp-vet}"
mkdir -p "$CACHE_ROOT" 2>/dev/null || envdie "cannot create cache dir $CACHE_ROOT"
MIRROR_GIT="$CACHE_ROOT/mirror.git"

echo "Vetting against mirror: $MIRROR_URL"
if [ ! -d "$MIRROR_GIT" ]; then
  echo "  (first run — cloning the mirror into $MIRROR_GIT)"
  git clone --quiet --bare "$MIRROR_URL" "$MIRROR_GIT" >/dev/null 2>&1 \
    || envdie "could not clone the mirror at $MIRROR_URL"
else
  git -C "$MIRROR_GIT" remote set-url origin "$MIRROR_URL" >/dev/null 2>&1 || true
fi
git -C "$MIRROR_GIT" fetch --quiet --prune --force origin '+refs/heads/*:refs/heads/*' >/dev/null 2>&1 \
  || envdie "could not fetch from the mirror at $MIRROR_URL"

G() { git -C "$MIRROR_GIT" "$@"; }

FULL_SHA="$(G rev-parse --verify --quiet "${CANDIDATE}^{commit}" 2>/dev/null || true)"
[ -n "$FULL_SHA" ] || die "candidate '$CANDIDATE' does not resolve to a commit in the mirror.
  If upstream has it but the mirror does not, the mirror has not been advanced yet.
  Advancing the mirror is fast-forward-only and is a separate, deliberate step —
  see the mirror's mirror-meta README. Vetting a commit the mirror cannot serve
  would pin the fleet to something a fresh box could never fetch."

# Reachability: an object that exists only as a loose/dangling blob is not a
# thing a fresh clone can fetch by SHA, so it is not pinnable.
REACHABLE_FROM=""
for _b in $(G for-each-ref --format='%(refname:short)' refs/heads/); do
  if G merge-base --is-ancestor "$FULL_SHA" "$_b" 2>/dev/null; then
    REACHABLE_FROM="$REACHABLE_FROM $_b"
  fi
done
[ -n "$REACHABLE_FROM" ] || die "candidate $FULL_SHA exists in the mirror but is not reachable from any branch — a fresh clone could not fetch it."

echo "Candidate resolves to: $FULL_SHA"
echo "Reachable from branch(es):$REACHABLE_FROM"
echo "Currently vetted:      ${CUR_COMMIT:-<none>}"
echo

if [ -n "$CUR_COMMIT" ] && ! G cat-file -e "${CUR_COMMIT}^{commit}" 2>/dev/null; then
  echo "NOTE: the currently vetted commit $CUR_COMMIT is NOT in the mirror, so no"
  echo "      differential review is possible. The report below covers the candidate"
  echo "      tree in full rather than the change since the last review."
  echo
  BASE=""
else
  BASE="$CUR_COMMIT"
fi

RANGE_DESC="whole tree at $FULL_SHA"
FULL_DIFF_CMD="git -C $MIRROR_GIT show $FULL_SHA"
if [ -n "$BASE" ] && [ "$BASE" != "$FULL_SHA" ]; then
  RANGE_DESC="$BASE..$FULL_SHA"
  FULL_DIFF_CMD="git -C $MIRROR_GIT diff $BASE $FULL_SHA"
elif [ "$BASE" = "$FULL_SHA" ]; then
  RANGE_DESC="no change ($FULL_SHA is already the pin)"
  FULL_DIFF_CMD="git -C $MIRROR_GIT show $FULL_SHA   # nothing to diff"
fi

# ── Assemble the diff once ───────────────────────────────────────────────────
WORK="$(mktemp -d "${TMPDIR:-/tmp}/ghl-mcp-vet.XXXXXX")" || envdie "cannot create a work dir"
trap 'rm -rf "$WORK"' EXIT

if [ -n "$BASE" ] && [ "$BASE" != "$FULL_SHA" ]; then
  G diff --name-status "$BASE" "$FULL_SHA" > "$WORK/names.txt" 2>/dev/null || true
  G diff -U0          "$BASE" "$FULL_SHA" > "$WORK/diff.txt"  2>/dev/null || true
elif [ "$BASE" = "$FULL_SHA" ]; then
  : > "$WORK/names.txt"; : > "$WORK/diff.txt"
else
  G ls-tree -r --name-only "$FULL_SHA" | sed 's/^/A\t/' > "$WORK/names.txt" 2>/dev/null || true
  : > "$WORK/diff.txt"
fi

CHANGED_COUNT=$(wc -l < "$WORK/names.txt" | tr -d ' ')

hr
echo "REVIEW REPORT — $RANGE_DESC"
echo "  files changed: $CHANGED_COUNT"
echo "  full diff:     $FULL_DIFF_CMD"
hr

if [ "$BASE" = "$FULL_SHA" ]; then
  echo
  echo "The candidate IS the commit already in force. There is nothing new to review."
  echo "Sealing from here re-records the SAME judgment with a fresh date and reviewer."
  echo
fi

# ── DIMENSION 1 — credential layer ───────────────────────────────────────────
echo
echo "1. CREDENTIAL LAYER — does anything new read, store, forward or log the token?"
CRED_FILES="$(awk '{print $NF}' "$WORK/names.txt" | grep -Ei '(auth|client|config|credential|secret|token|env)' || true)"
if [ -z "$CRED_FILES" ]; then
  echo "   No changed file sits on an auth/client/config/credential/token/env path."
else
  echo "   Changed files on credential-adjacent paths:"
  printf '%s\n' "$CRED_FILES" | sed 's/^/     /' | head_n
fi
CRED_LINES="$(grep -E '^[-+]' "$WORK/diff.txt" 2>/dev/null | grep -vE '^(\+\+\+|---)' \
  | grep -E 'GHL_API_KEY|Authorization|Bearer|process\.env|apiKey|api_key|privateIntegration|PIT\b' || true)"
if [ -z "$CRED_LINES" ]; then
  echo "   No added or removed line references a credential symbol."
else
  echo "   Added/removed lines referencing credential symbols:"
  printf '%s\n' "$CRED_LINES" | sed 's/^/     /' | head_n
fi

# ── DIMENSION 2 — outbound surface ───────────────────────────────────────────
echo
echo "2. OUTBOUND SURFACE — which hosts can this tree talk to that it could not before?"
hosts_from() { grep -oE 'https?://[A-Za-z0-9._~%-]+' 2>/dev/null | sed 's|^https\{0,1\}://||' | sort -u; }
grep -E '^\+' "$WORK/diff.txt" 2>/dev/null | grep -v '^+++' | hosts_from > "$WORK/hosts_added.txt" || true
grep -E '^-' "$WORK/diff.txt" 2>/dev/null | grep -v '^---' | hosts_from > "$WORK/hosts_removed.txt" || true
NEW_HOSTS="$(comm -23 "$WORK/hosts_added.txt" "$WORK/hosts_removed.txt" 2>/dev/null || true)"
GONE_HOSTS="$(comm -13 "$WORK/hosts_added.txt" "$WORK/hosts_removed.txt" 2>/dev/null || true)"
if [ -z "$NEW_HOSTS" ]; then echo "   No NEW outbound host literal appears in the diff."
else echo "   NEW outbound hosts (each one needs a reason):"; printf '%s\n' "$NEW_HOSTS" | sed 's/^/     + /' | head_n; fi
if [ -n "$GONE_HOSTS" ]; then echo "   Hosts no longer referenced:"; printf '%s\n' "$GONE_HOSTS" | sed 's/^/     - /' | head_n; fi

# ── DIMENSION 3 — endpoint construction ──────────────────────────────────────
echo
echo "3. ENDPOINT CONSTRUCTION — can a request be redirected off-origin by data?"
ABS_EP="$(grep -E '^\+' "$WORK/diff.txt" 2>/dev/null | grep -v '^+++' \
  | grep -E '(fetch|axios|request|url|endpoint|baseURL|href)' \
  | grep -Ei 'https?://' || true)"
if [ -z "$ABS_EP" ]; then
  echo "   No added request/endpoint line carries an ABSOLUTE URL literal."
  echo "   (Relative paths built against a configured base cannot be repointed by a response.)"
else
  echo "   Added request/endpoint lines carrying an ABSOLUTE URL — read every one:"
  printf '%s\n' "$ABS_EP" | sed 's/^/     /' | head_n
fi
TEMPLATED="$(grep -E '^\+' "$WORK/diff.txt" 2>/dev/null | grep -v '^+++' \
  | grep -E 'https?://\$\{|https?://.*\+ *[A-Za-z_]' || true)"
if [ -n "$TEMPLATED" ]; then
  echo "   Added lines where a URL is BUILT from a variable (host could come from data):"
  printf '%s\n' "$TEMPLATED" | sed 's/^/     /' | head_n
fi

# ── DIMENSION 4 — dependency graph ───────────────────────────────────────────
echo
echo "4. DEPENDENCY GRAPH — what does the lockfile pull in?"
LOCK_PATH="package-lock.json"
if ! G cat-file -e "${FULL_SHA}:${LOCK_PATH}" 2>/dev/null; then
  echo "   REFUSING TO VOUCH: the candidate tree has no $LOCK_PATH."
  echo "   Without a lockfile the dependency tree is resolved fresh at install time on"
  echo "   every box, so no verdict about it can be honest."
  die "candidate $FULL_SHA has no $LOCK_PATH — the dependency dimension cannot be reviewed."
fi
G show "${FULL_SHA}:${LOCK_PATH}" > "$WORK/lock.new" 2>/dev/null || die "could not read $LOCK_PATH at $FULL_SHA"
if [ -n "$BASE" ] && G cat-file -e "${BASE}:${LOCK_PATH}" 2>/dev/null; then
  G show "${BASE}:${LOCK_PATH}" > "$WORK/lock.old" 2>/dev/null || : > "$WORK/lock.old"
else
  : > "$WORK/lock.old"
fi
python3 - "$WORK/lock.old" "$WORK/lock.new" <<'PY'
import json, sys

def load(p):
    """Return {name: (version, resolved_url)} for lockfile v1, v2 and v3."""
    try:
        with open(p) as fh:
            d = json.load(fh)
    except Exception:
        return None
    out = {}
    pkgs = d.get("packages")
    if isinstance(pkgs, dict):
        for path, meta in pkgs.items():
            if not path:
                continue                      # the root project itself
            name = path.split("node_modules/")[-1]
            if isinstance(meta, dict):
                out[name] = (meta.get("version", ""), meta.get("resolved", ""))
    deps = d.get("dependencies")
    if isinstance(deps, dict):
        def walk(tree):
            for name, meta in tree.items():
                if isinstance(meta, dict):
                    out.setdefault(name, (meta.get("version", ""), meta.get("resolved", "")))
                    if isinstance(meta.get("dependencies"), dict):
                        walk(meta["dependencies"])
        walk(deps)
    return out

old = load(sys.argv[1])
new = load(sys.argv[2])
if new is None:
    print("   Could not parse the candidate lockfile as JSON — treat that as DIRTY.")
    sys.exit(0)
if old is None:
    print("   No comparable baseline lockfile; candidate declares %d resolved packages." % len(new))
    sys.exit(0)

added   = sorted(set(new) - set(old))
removed = sorted(set(old) - set(new))
moved   = sorted(n for n in (set(new) & set(old)) if old[n] != new[n])

if not (added or removed or moved):
    print("   UNCHANGED — no package added, removed or re-pointed (%d resolved packages)." % len(new))
else:
    print("   CHANGED — every line below is new third-party code that will execute on a client box:")
    for n in added:
        print("     + %s@%s  %s" % (n, new[n][0], new[n][1]))
    for n in removed:
        print("     - %s@%s" % (n, old[n][0]))
    for n in moved:
        print("     ~ %s: %s -> %s" % (n, old[n][0], new[n][0]))
        if old[n][1] and new[n][1] and old[n][1] != new[n][1]:
            print("         resolved: %s -> %s" % (old[n][1], new[n][1]))
PY

LOCK_SHA256="$(shasum -a 256 < "$WORK/lock.new" 2>/dev/null | awk '{print $1}')"
[ -n "$LOCK_SHA256" ] || LOCK_SHA256="$(sha256sum < "$WORK/lock.new" 2>/dev/null | awk '{print $1}')"
[ -n "$LOCK_SHA256" ] || envdie "no shasum/sha256sum on PATH — cannot bind the lockfile to the verdict."
echo "   sha256(package-lock.json @ candidate) = $LOCK_SHA256"

echo
hr

# ── Review-only mode stops here ──────────────────────────────────────────────
if [ -z "$VERDICT" ]; then
  cat <<EOF

REVIEW ONLY — nothing was written.

Read the four dimensions above. If and only if all four are acceptable, seal it:

    scripts/ghl-mcp-vet-pin.sh $FULL_SHA --verdict clean

If any dimension is not acceptable, record that instead — a DIRTY record is
sealed too, and the installer refuses to run it, which is the point:

    scripts/ghl-mcp-vet-pin.sh $FULL_SHA --verdict dirty

EOF
  exit 3
fi

# ── Seal ─────────────────────────────────────────────────────────────────────
case "$VET_BY" in
  *'"'*|*'\'*) die "--by must not contain a double quote or a backslash (it is written into a shell-sourced file and hashed verbatim)." ;;
esac
[ "$(printf '%s' "$VET_BY" | wc -l | tr -d ' ')" = "0" ] || die "--by must be a single line."
[ -n "$VET_BY" ] || die "--by must not be empty — an unattributed verdict is not a verdict."

VERDICT_UP="$(printf '%s' "$VERDICT" | tr '[:lower:]' '[:upper:]')"
TODAY="$(date -u +%Y-%m-%d)"

BEGIN_MARK='# >>> GHL-MCP-VETTING-RECORD-BEGIN'
END_MARK='# <<< GHL-MCP-VETTING-RECORD-END'
grep -Fq "$BEGIN_MARK" "$PIN_FILE" || die "pin file $PIN_FILE has no '$BEGIN_MARK' block — this tool writes that block and nothing else, and will not guess where it belongs."
grep -Fq "$END_MARK"   "$PIN_FILE" || die "pin file $PIN_FILE has no '$END_MARK' marker."

NEW_PIN="$WORK/pin.env"
awk -v begin="$BEGIN_MARK" -v end="$END_MARK" \
    -v commit="$FULL_SHA" -v verdict="$VERDICT_UP" -v on="$TODAY" -v by="$VET_BY" \
    -v lock="$LOCK_SHA256" -v repo="$MIRROR_URL" '
  $0 == begin {
    print
    print "# Written by scripts/ghl-mcp-vet-pin.sh. Hand-editing any line below breaks"
    print "# the digest, and every consumer refuses a broken digest. That is deliberate."
    print "GHL_MCP_VETTED_COMMIT=\"" commit "\""
    print "GHL_MCP_PIN_VETTED_VERDICT=\"" verdict "\""
    print "GHL_MCP_PIN_VETTED_ON=\"" on "\""
    print "GHL_MCP_PIN_VETTED_BY=\"" by "\""
    print "GHL_MCP_DEPS_LOCK_SHA256=\"" lock "\""
    print "GHL_MCP_REPO_URL=\"" repo "\""
    print "GHL_MCP_PIN_VETTED_DIGEST=\"PENDING-SEAL\""
    skip = 1
    next
  }
  $0 == end { skip = 0 }
  skip != 1 { print }
' "$PIN_FILE" > "$NEW_PIN" || die "could not rewrite the vetting record block"

DIGEST="$(bash "$CHECKER" --pin-file "$NEW_PIN" --compute)" || die "digest computation failed"
case "$DIGEST" in
  [0-9a-f]*) [ "${#DIGEST}" -eq 64 ] || die "computed digest is not a sha256: $DIGEST" ;;
  *) die "computed digest is not hex: $DIGEST" ;;
esac
SEALED="$WORK/pin.sealed"
sed "s|^GHL_MCP_PIN_VETTED_DIGEST=\"PENDING-SEAL\"$|GHL_MCP_PIN_VETTED_DIGEST=\"$DIGEST\"|" "$NEW_PIN" > "$SEALED"

# Self-check BEFORE touching the working tree: if what we just built would not
# pass the gate, nothing gets written. A tool that can emit a record its own
# checker rejects is worse than no tool.
if [ "$VERDICT_UP" = "CLEAN" ]; then
  bash "$CHECKER" --pin-file "$SEALED" --quiet || die "the record this tool just built does not pass ghl-mcp-check-pin-digest.sh — refusing to write it."
else
  bash "$CHECKER" --pin-file "$SEALED" --integrity-only --quiet || die "the record this tool just built is malformed — refusing to write it."
fi

# ── Built-in fallback constants must never disagree with the pin ─────────────
# A box that cannot read the pin file falls back to constants baked into the
# scripts. If those drift from the pin, a roll writes one pin while every later
# off-roll run uses another — a split-brain pin that is invisible from the repo.
# Whether a fallback exists at all is not this tool's decision (the installer
# may have been made to refuse outright instead); if one is there, it is kept
# in lockstep, and if it is not, that is reported and accepted.
FALLBACK_FILES="scripts/ghl-mcp-autostart.sh platform/vps/36-ghl-mcp-setup-scripts/start-ghl-mcp-server.sh"
sync_fallbacks() {
  local target="$1" f full changed
  for f in $FALLBACK_FILES; do
    full="$REPO_ROOT/$f"
    [ -f "$full" ] || { echo "   (absent: $f)"; continue; }
    changed=""
    if grep -Fq 'GHL_MCP_VETTED_COMMIT="${GHL_MCP_VETTED_COMMIT:-' "$full"; then
      sed "s|^\([[:space:]]*GHL_MCP_VETTED_COMMIT=\"\${GHL_MCP_VETTED_COMMIT:-\)[0-9a-f]*\(}\"\)|\1${FULL_SHA}\2|" \
        "$full" > "$WORK/fb.tmp" && cat "$WORK/fb.tmp" > "$target/$(basename "$f").out"
      changed="commit"
    fi
    if grep -Fq 'GHL_MCP_REPO_URL="${GHL_MCP_REPO_URL:-' "$full"; then
      local src="$full"
      [ -f "$target/$(basename "$f").out" ] && src="$target/$(basename "$f").out"
      sed "s|^\([[:space:]]*GHL_MCP_REPO_URL=\"\${GHL_MCP_REPO_URL:-\)[^}]*\(}\"\)|\1${MIRROR_URL}\2|" \
        "$src" > "$WORK/fb2.tmp" && cat "$WORK/fb2.tmp" > "$target/$(basename "$f").out"
      changed="${changed:+$changed+}repo_url"
    fi
    if [ -z "$changed" ]; then
      echo "   (no built-in fallback constant in $f — nothing to keep in lockstep)"
    else
      echo "   $f — fallback $changed will be set to match the pin"
      echo "$f" >> "$WORK/fallback-list.txt"
    fi
  done
}
mkdir -p "$WORK/fb"
: > "$WORK/fallback-list.txt"
echo
echo "Built-in fallback constants:"
sync_fallbacks "$WORK/fb"

if [ "$DRY_RUN" -eq 1 ]; then
  echo
  hr
  echo "DRY RUN — nothing written. The sealed record would be:"
  hr
  sed -n "/$(printf '%s' "$BEGIN_MARK" | sed 's/[][\.*^$/]/\\&/g')/,/$(printf '%s' "$END_MARK" | sed 's/[][\.*^$/]/\\&/g')/p" "$SEALED"
  exit 0
fi

cat "$SEALED" > "$PIN_FILE" || die "could not write $PIN_FILE"
while IFS= read -r f; do
  [ -n "$f" ] || continue
  out="$WORK/fb/$(basename "$f").out"
  [ -f "$out" ] || continue
  cat "$out" > "$REPO_ROOT/$f" || die "could not write $f"
done < "$WORK/fallback-list.txt"

echo
hr
echo "SEALED — verdict $VERDICT_UP"
hr
sed -n "/$(printf '%s' "$BEGIN_MARK" | sed 's/[][\.*^$/]/\\&/g')/,/$(printf '%s' "$END_MARK" | sed 's/[][\.*^$/]/\\&/g')/p" "$PIN_FILE"
hr

if [ "$VERDICT_UP" != "CLEAN" ]; then
  cat <<EOF

The record is sealed as $VERDICT_UP. The CI gate, the pre-push hook and the
box-side installer all refuse a non-CLEAN pin, so this cannot be rolled. That is
the intended outcome of a failed review — commit it so the refusal is recorded.

EOF
  exit 0
fi

cat <<EOF

NEXT — prove it on ONE box before the fleet, not after:

  1. Verify the sealed record and the repo-side gate:
       bash scripts/ghl-mcp-check-pin-digest.sh
       bash scripts/qc-assert-ghl-mcp-supervised.sh

  2. Rebuild on ONE box only. The autostart builds the new pin in a temp dir and
     only swaps dist/ on success, so a bad pin leaves the running server alone:
       bash scripts/ghl-mcp-autostart.sh

  3. Confirm it is actually alive and answering, not merely listening:
       bash scripts/ghl-mcp-probe.sh --once

  4. Only then roll the fleet.

EOF
exit 0
