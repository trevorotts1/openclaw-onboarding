#!/usr/bin/env bash
# scripts/one-python-box-check.sh: READ-ONLY ONE-PYTHON check for one box.
#
# For fleet rolls (verify step) and operators. Writes nothing, installs
# nothing, changes nothing. Prints ONE line and exits:
#   0  OK   (the box uses one Python)
#   1  FAIL (one-line reason: the first violation found, plus a count)
#   2  the check itself could not run (resolver missing, bad argument)
#
# Checks on a Linux box (Hostinger / Docker / Contabo / native VPS):
#   1. the ONE canonical interpreter resolves (oc_python, platform/common.sh) and
#      is not a Homebrew python
#   2. exactly ONE user-site tree <user base>/lib/python3.X, and it is the
#      canonical interpreter's X (renamed *.QUARANTINED-* trees are not counted)
#   3. every venv (pyvenv.cfg under the scan roots) has `home` under /usr/bin
#   4. no nvidia-* / CUDA wheels in the user tree or any venv on a box with no
#      NVIDIA GPU
# On a Mac the Linux layout rules do not apply: it prints the canonical
# interpreter and exits 0.
#
# Usage:
#   bash scripts/one-python-box-check.sh [--root DIR] [--user-base DIR]
#        [--scan DIR]... [--allow-venv DIR]...
#   --root        OpenClaw root (default: /data/.openclaw on a Linux box with it,
#                 else ~/.openclaw)
#   --user-base   python user base (default: what the canonical python reports)
#   --scan        a directory searched for venvs (default: the OpenClaw root and
#                 ${UV_TOOL_DIR:-~/.local/share/uv/tools}); repeatable
#   --allow-venv  a venv deliberately on another interpreter (e.g. a project
#                 pinned to 3.10); repeatable. OC_ONE_PYTHON_ALLOW_VENVS
#                 (colon-separated) adds more.
set -uo pipefail

ROOT_ARG="" USER_BASE="" SCANS=() ALLOWS=()
while [ "$#" -gt 0 ]; do
  case "$1" in
    --root)       ROOT_ARG="${2:-}"; shift 2 ;;
    --user-base)  USER_BASE="${2:-}"; shift 2 ;;
    --scan)       SCANS+=("${2:-}"); shift 2 ;;
    --allow-venv) ALLOWS+=("${2%/}"); shift 2 ;;
    -h|--help)    sed -n '2,34p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "one-python-check: ERROR: unknown argument '$1'"; exit 2 ;;
  esac
done
if [ -n "${OC_ONE_PYTHON_ALLOW_VENVS:-}" ]; then
  _old_ifs="$IFS"; IFS=:
  for _a in $OC_ONE_PYTHON_ALLOW_VENVS; do [ -n "$_a" ] && ALLOWS+=("${_a%/}"); done
  IFS="$_old_ifs"
fi
[ -n "$ROOT_ARG" ] && export OPENCLAW_ROOT="$ROOT_ARG"

_here="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd || pwd)"
_common=""
for _c in "$_here/../platform/common.sh" "${OPENCLAW_ROOT:-/nonexistent}/platform/common.sh" \
          /data/.openclaw/platform/common.sh "$HOME/.openclaw/platform/common.sh"; do
  [ -f "$_c" ] && { _common="$_c"; break; }
done
if [ -z "$_common" ]; then
  echo "one-python-check: ERROR: platform/common.sh (the one-python resolver) not found"; exit 2
fi
# shellcheck source=/dev/null
. "$_common"

PLAT="$(oc_detect_platform 2>/dev/null || true)"
PY="$(oc_python 2>/dev/null || true)"
if [ "$PLAT" = mac ]; then
  echo "one-python-check: OK mac: canonical interpreter ${PY:-<none>} (Linux tree/venv rules do not apply)"
  exit 0
fi
if [ -z "$PY" ]; then
  echo "one-python-check: FAIL no canonical python3 (looked at /usr/bin/python3, the .oc-python stamp and PATH)"; exit 1
fi
if oc_python_is_homebrew "$PY"; then
  echo "one-python-check: FAIL canonical interpreter $PY is a Homebrew python"; exit 1
fi
PYVER="$("$PY" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || true)"
[ -n "$PYVER" ] || { echo "one-python-check: FAIL canonical interpreter $PY does not run"; exit 1; }
ROOT="$(oc_python_root)"
[ -n "$USER_BASE" ] || USER_BASE="$("$PY" -c 'import site; print(site.getuserbase())' 2>/dev/null || true)"
[ -n "$USER_BASE" ] || { echo "one-python-check: ERROR: cannot read the user base of $PY"; exit 2; }
[ "${#SCANS[@]}" -gt 0 ] || SCANS=("$ROOT" "${UV_TOOL_DIR:-$HOME/.local/share/uv/tools}")

# --- 2. exactly one user-site tree, matching the canonical version -------------
TREES=()
for _t in "$USER_BASE"/lib/python3.*; do
  [ -d "$_t" ] || continue
  case "$(basename "$_t")" in python3.[0-9]|python3.[0-9][0-9]) TREES+=("$_t") ;; esac
done
if [ "${#TREES[@]}" -ne 1 ]; then
  echo "one-python-check: FAIL ${#TREES[@]} user-site trees under $USER_BASE/lib (want exactly 1, python$PYVER): ${TREES[*]:-none}"; exit 1
fi
if [ "$(basename "${TREES[0]}")" != "python$PYVER" ]; then
  echo "one-python-check: FAIL user-site tree ${TREES[0]} is not the canonical python$PYVER ($PY)"; exit 1
fi

# --- 3. every venv's home under /usr/bin ---------------------------------------
_allowed() {
  local d="$1" a
  for a in "${ALLOWS[@]+"${ALLOWS[@]}"}"; do [ "$d" = "$a" ] && return 0; done
  return 1
}
VENVS=() BAD_VENVS=()
for _s in "${SCANS[@]}"; do
  [ -d "$_s" ] || continue
  while IFS= read -r _cfg; do
    [ -n "$_cfg" ] || continue
    _v="$(dirname "$_cfg")"
    _allowed "$_v" && continue
    VENVS+=("$_v")
    _home="$(sed -n 's/^home[[:space:]]*=[[:space:]]*//p' "$_cfg" | head -1)"
    case "$_home" in /usr/bin|/usr/bin/*) ;; *) BAD_VENVS+=("$_v (home=${_home:-<none>})") ;; esac
  done < <(find "$_s" \( -name node_modules -o -name linuxbrew -o -name '*.QUARANTINED*' \) -prune \
             -o -name pyvenv.cfg -type f -print 2>/dev/null)
done
if [ "${#BAD_VENVS[@]}" -gt 0 ]; then
  echo "one-python-check: FAIL ${#BAD_VENVS[@]} venv(s) not on /usr/bin python, first: ${BAD_VENVS[0]}"; exit 1
fi

# --- 4. no CUDA wheels without a GPU -------------------------------------------
if ! oc_has_nvidia_gpu; then
  NV=()
  for _sp in "${TREES[0]}/site-packages" ; do
    for _n in "$_sp"/nvidia "$_sp"/nvidia_*.dist-info "$_sp"/nvidia-*.dist-info; do [ -e "$_n" ] && NV+=("$_n"); done
  done
  for _v in "${VENVS[@]+"${VENVS[@]}"}"; do
    for _n in "$_v"/lib/python3*/site-packages/nvidia "$_v"/lib/python3*/site-packages/nvidia_*.dist-info; do
      [ -e "$_n" ] && NV+=("$_n")
    done
  done
  if [ "${#NV[@]}" -gt 0 ]; then
    echo "one-python-check: FAIL ${#NV[@]} nvidia/CUDA package(s) on a box with no NVIDIA GPU, first: ${NV[0]}"; exit 1
  fi
fi

echo "one-python-check: OK $PY; one user tree ${TREES[0]}; ${#VENVS[@]} venv(s) on /usr/bin; no CUDA wheels without a GPU"
exit 0
