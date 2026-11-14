#!/usr/bin/env bash
# =============================================================================
# RESCUE RANGERS :: stamp-rescue-escalation-section.sh
# Renders scripts/rescue-escalation-section.md.tpl with a box's real tokens and
# stamps it into that box's AGENTS.md: appends it when the file has no section,
# and refreshes an old marked section in place (idempotent).
# (Topic-4 FIX 4-E — kills R5 "template drift risk at onboarding". Runnable now;
#  install.sh wiring on a fresh box is DEFERRED to the operator/onboarding roll.)
# -----------------------------------------------------------------------------
# The repo template stays the SINGLE SOURCE OF TRUTH. This script is what an
# install.sh client-role step (or the operator's propagate roll) calls so a newly
# onboarded box gets the escalation INSTRUCTIONS, not just the env vars.
#
# MARKERS: "<!-- RESCUE_ESCALATION_BOXNAME_V<n> -->" and its END line. The
# rendered template is compared with the section already in the file: identical
# => no-op; an older marked section is refreshed in place; a heading with no
# markers is refused (exit 3) so nothing is duplicated or guessed at.
#
# USAGE:
#   stamp-rescue-escalation-section.sh --agents PATH/AGENTS.md \
#       --person "Jane" --client "acme" --agent "Aria" \
#       --box-name "acme-mac" --box-type "Mac Mini" \
#       --oc-version "2026.5.22" --return-to "123456" [--tpl PATH]
#   stamp-rescue-escalation-section.sh --self-test
# =============================================================================
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Default template: walk up to the repo root and find scripts/rescue-escalation-section.md.tpl.
_default_tpl() {
  local d="$HERE"
  for _ in 1 2 3 4 5 6 7 8; do
    if [ -f "$d/scripts/rescue-escalation-section.md.tpl" ]; then
      echo "$d/scripts/rescue-escalation-section.md.tpl"; return 0
    fi
    d="$(dirname "$d")"
  done
  return 1
}

render() {
  # render TPL PERSON CLIENT AGENT BOX_NAME BOX_TYPE OC_VERSION RETURN_TO
  local tpl="$1"; shift
  local person="$1" client="$2" agent="$3" box_name="$4" box_type="$5" oc_version="$6" return_to="$7"
  # Use python for safe substitution (no sed metachar pitfalls in tokens).
  PERSON="$person" CLIENT="$client" AGENT="$agent" BOX_NAME="$box_name" \
  BOX_TYPE="$box_type" OC_VERSION="$oc_version" RETURN_TO="$return_to" \
  python3 - "$tpl" <<'PY'
import os, sys
tpl = open(sys.argv[1], encoding="utf-8").read()
for k in ("PERSON","CLIENT","AGENT","BOX_NAME","BOX_TYPE","OC_VERSION","RETURN_TO"):
    tpl = tpl.replace("{{%s}}" % k, os.environ.get(k, ""))
sys.stdout.write(tpl)
PY
}

stamp() {
  # stamp AGENTS TPL PERSON CLIENT AGENT BOX_NAME BOX_TYPE OC_VERSION RETURN_TO
  local agents="$1" tpl="$2"; shift 2
  local rendered
  # A sentinel byte keeps the template's trailing newline through the capture.
  rendered="$(render "$tpl" "$@"; printf 'x')"
  rendered="${rendered%x}"
  STAMP_AGENTS="$agents" STAMP_RENDERED="$rendered" python3 - <<'PY'
import os, stat, sys, tempfile

agents_path = os.environ["STAMP_AGENTS"]
rendered = os.environ["STAMP_RENDERED"]

START = "<!-- RESCUE_ESCALATION_BOXNAME_V"
END = "<!-- END RESCUE_ESCALATION_BOXNAME_V"
HEADING = "## Escalate to Rescue Rangers (when you are stuck)"
REFUSED = ("[stamp-rescue] REFUSED: the existing section is not marked the way "
           "this tool expects; nothing was changed.\n")


def first_line(lines, prefix):
    for i, line in enumerate(lines):
        if line.startswith(prefix):
            return i
    return None


new_lines = rendered.splitlines(keepends=True)
new_start = first_line(new_lines, START)
new_end = first_line(new_lines, END)
if new_start is None or new_end is None or new_end < new_start:
    sys.stderr.write("[stamp-rescue] REFUSED: the rendered template has no usable "
                     "marker pair; nothing was changed.\n")
    sys.exit(3)
new_block = "".join(new_lines[new_start:new_end + 1])
trailing = "".join(new_lines[new_end + 1:])

exists = os.path.exists(agents_path)
existing = ""
if exists:
    with open(agents_path, encoding="utf-8") as f:
        existing = f.read()

ex_lines = existing.splitlines(keepends=True)
old_start = first_line(ex_lines, START)
old_end = first_line(ex_lines, END)

if old_start is not None and old_end is not None and old_start < old_end:
    old_block = "".join(ex_lines[old_start:old_end + 1])
    if old_block == new_block:
        print("[stamp-rescue] section is current - no-op.")
        sys.exit(0)
    old_marker = ex_lines[old_start].strip()
    new_marker = new_lines[new_start].strip()
    old_trailing = "".join(ex_lines[old_end + 1:])
    if trailing and old_trailing.startswith(trailing):
        # The template's tail is already sitting after the end marker: replace
        # it with itself so a later step can never write it twice.
        new_trailing = trailing + old_trailing[len(trailing):]
    else:
        new_trailing = old_trailing
    result = "".join(ex_lines[:old_start]) + new_block + new_trailing
    print("[stamp-rescue] refreshed escalation section (old marker %s, new marker %s)."
          % (old_marker, new_marker))
elif old_start is None and old_end is None:
    if any(line.rstrip("\r\n") == HEADING for line in ex_lines):
        sys.stderr.write(REFUSED)
        sys.exit(3)
    result = (existing + "\n" if exists else "") + rendered
    print("[stamp-rescue] appended escalation section.")
else:
    sys.stderr.write(REFUSED)
    sys.exit(3)

folder = os.path.dirname(os.path.abspath(agents_path))
os.makedirs(folder, exist_ok=True)
fd, tmp_path = tempfile.mkstemp(dir=folder, prefix=".stamp-rescue-", suffix=".tmp")
try:
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(result)
    if exists:
        os.chmod(tmp_path, stat.S_IMODE(os.stat(agents_path).st_mode))
    os.replace(tmp_path, agents_path)
except BaseException:
    try:
        os.unlink(tmp_path)
    except OSError:
        pass
    raise
PY
}

self_test() {
  echo "[stamp-rescue] self-test"
  local tpl; tpl="$(_default_tpl)" || { echo "template not found" >&2; return 1; }
  local tmp; tmp="$(mktemp -d)"
  SELF="$0" STAMP_TPL="$tpl" STAMP_TMP="$tmp" python3 - <<'PY'
import os, shutil, subprocess, sys

self_path = os.environ["SELF"]
tpl = os.environ["STAMP_TPL"]
tmp = os.environ["STAMP_TMP"]

START = "<!-- RESCUE_ESCALATION_BOXNAME_V"
END = "<!-- END RESCUE_ESCALATION_BOXNAME_V"
FLAGS = ["--person", "--client", "--agent", "--box-name", "--box-type",
         "--oc-version", "--return-to"]
VALUES = ["Jane Doe", "acme", "Aria", "acme-mac", "Mac Mini", "2026.5.22", "123456"]

failures = []


def run(agents):
    cmd = ["bash", self_path, "--agents", agents, "--tpl", tpl]
    for flag, value in zip(FLAGS, VALUES):
        cmd += [flag, value]
    return subprocess.run(cmd, capture_output=True, text=True)


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


try:
    agents = os.path.join(tmp, "AGENTS.md")
    with open(agents, "w", encoding="utf-8") as f:
        f.write("# Agent Instructions\n\nExisting content.\n")
    r = run(agents)
    text = read(agents)
    if r.returncode != 0 or "appended escalation section" not in r.stdout:
        failures.append("case 1 append")
    elif "{{PERSON}}" in text or "acme-mac" not in text:
        failures.append("case 1 tokens")
    elif text.count(START) != 1 or END not in text:
        failures.append("case 1 markers")
    else:
        print("  case 1 (append to a file with no section): PASS")

    before = read(agents)
    r = run(agents)
    after = read(agents)
    if r.returncode != 0 or "section is current - no-op" not in r.stdout:
        failures.append("case 2 no-op notice")
    elif before != after:
        failures.append("case 2 file changed")
    elif after.count(START) != 1:
        failures.append("case 2 duplicated")
    else:
        print("  case 2 (second run is a no-op): PASS")

    v2 = os.path.join(tmp, "V2-AGENTS.md")
    old_block = ("<!-- RESCUE_ESCALATION_BOXNAME_V2 -->\n"
                 "## Escalate to Rescue Rangers (when you are stuck)\n\n"
                 "Old text.\n"
                 "<!-- END RESCUE_ESCALATION_BOXNAME_V2 -->\n")
    with open(v2, "w", encoding="utf-8") as f:
        f.write("# Agent Instructions\n\nKeep me.\n\n" + old_block + "\nTrailing note.\n")
    r = run(v2)
    text = read(v2)
    if r.returncode != 0:
        failures.append("case 3 exit %d" % r.returncode)
    elif "refreshed escalation section" not in r.stdout:
        failures.append("case 3 refresh notice")
    elif "V3" not in text or text.count(START) != 1:
        failures.append("case 3 not refreshed to one V3 block")
    elif "Keep me." not in text or "Trailing note." not in text:
        failures.append("case 3 surrounding text lost")
    elif "Old text." in text:
        failures.append("case 3 old block text kept")
    else:
        print("  case 3 (a V2 block is refreshed to V3, one start marker): PASS")

    bad = os.path.join(tmp, "HEADING-ONLY.md")
    original = ("# Agent Instructions\n\n"
                "## Escalate to Rescue Rangers (when you are stuck)\n\n"
                "Hand written, no markers.\n")
    with open(bad, "w", encoding="utf-8") as f:
        f.write(original)
    r = run(bad)
    if r.returncode != 3 or "REFUSED" not in r.stderr:
        failures.append("case 4 expected exit 3 with REFUSED")
    elif read(bad) != original:
        failures.append("case 4 file changed")
    else:
        print("  case 4 (a heading without markers exits 3, file byte-identical): PASS")
finally:
    shutil.rmtree(tmp, ignore_errors=True)

if failures:
    for item in failures:
        print("[stamp-rescue] FAIL: " + item, file=sys.stderr)
    sys.exit(1)
print("[stamp-rescue] self-test: PASS")
PY
}

# ---- arg parse ----
AGENTS=""; TPL=""; PERSON=""; CLIENT=""; AGENT=""; BOX_NAME=""; BOX_TYPE=""; OC_VERSION=""; RETURN_TO=""
if [ "${1:-}" = "--self-test" ]; then self_test; exit $?; fi
while [ $# -gt 0 ]; do
  case "$1" in
    --agents) AGENTS="$2"; shift 2 ;;
    --tpl) TPL="$2"; shift 2 ;;
    --person) PERSON="$2"; shift 2 ;;
    --client) CLIENT="$2"; shift 2 ;;
    --agent) AGENT="$2"; shift 2 ;;
    --box-name) BOX_NAME="$2"; shift 2 ;;
    --box-type) BOX_TYPE="$2"; shift 2 ;;
    --oc-version) OC_VERSION="$2"; shift 2 ;;
    --return-to) RETURN_TO="$2"; shift 2 ;;
    -h|--help) sed -n '2,25p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done
[ -n "$AGENTS" ] || { echo "--agents is required (or --self-test)" >&2; exit 2; }
[ -n "$TPL" ] || TPL="$(_default_tpl)" || { echo "template not found; pass --tpl" >&2; exit 2; }
stamp "$AGENTS" "$TPL" "$PERSON" "$CLIENT" "$AGENT" "$BOX_NAME" "$BOX_TYPE" "$OC_VERSION" "$RETURN_TO"
