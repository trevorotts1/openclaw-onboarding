#!/usr/bin/env bash
# tests/unit/one-python-resolver.test.sh
# -----------------------------------------------------------------------------
# ONE PYTHON (v27.1.80): the resolver in platform/common.sh (oc_python,
# oc_python_record_stamp, oc_pip_install, oc_venv, oc_uv_tool_install).
#
# Hermetic: every interpreter, uv and uname is a stub that logs its argv; no
# network, no real pip, nothing outside a temp dir is touched.
#
#   R1  VPS layout, Homebrew python FIRST on PATH -> /usr/bin/python3's realpath
#   R2  VPS without /usr/bin/python3 -> first NON-Homebrew python3 on PATH
#   R3  VPS with only a Homebrew python -> fails (never resolves to it)
#   R4  OC_PYTHON=<Homebrew python> on Linux is refused
#   R5  Mac layout unchanged: `command -v python3` (Homebrew allowed); OC_PYTHON honoured
#   R6  stamp written to <root>/.oc-python, read back, used when /usr/bin/python3 is gone,
#       a changed interpreter is reported
#   R7  oc_pip_install: <canonical> -m pip install --user; --break-system-packages
#       only on Linux, only with the PEP 668 marker, always next to --user
#   R8  torch / openai-whisper on Linux without a GPU: CPU-only index first, then a
#       constraint pin; with a GPU: no CPU index
#   R9  oc_venv: uv venv --python <canonical> --seed; hollow venv repaired with
#       --allow-existing; healthy venv untouched; no uv + no ensurepip = loud failure
#   R10 oc_uv_tool_install passes --python <canonical>
#   M1  MUTATION: a resolver that falls back to PATH python3 on Linux FAILS R1
# -----------------------------------------------------------------------------
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
COMMON="${ONE_PYTHON_COMMON:-$REPO/platform/common.sh}"
PASS=0; FAIL=0
ok()  { PASS=$((PASS+1)); echo "  PASS: $*"; }
bad() { FAIL=$((FAIL+1)); echo "  FAIL: $*"; }

T="$(mktemp -d)"; T="$(cd -P "$T" && pwd)"
trap 'rm -rf "$T"' EXIT
CALLS="$T/calls.log"; : > "$CALLS"

# ---- stubs -------------------------------------------------------------------
mkdir -p "$T/stub" "$T/sys/usr/bin" "$T/brew/linuxbrew/.linuxbrew/bin" "$T/other/bin" "$T/dev" "$T/oc"
cat > "$T/stub/uname" <<'EOS'
#!/bin/sh
[ "${1:-}" = "-s" ] && { echo "${FAKE_UNAME:-Linux}"; exit 0; }
echo "${FAKE_UNAME:-Linux}"
EOS
# A fake interpreter: logs argv (prefixed with its own path) and answers probes.
cat > "$T/fakepy" <<'EOS'
#!/usr/bin/env bash
echo "$0 $*" >> "$CALLS"
case "$*" in
  *EXTERNALLY-MANAGED*) [ "${FAKE_EM:-0}" = 1 ]; exit $? ;;
  *"import ensurepip"*) [ "${FAKE_ENSUREPIP:-1}" = 1 ]; exit $? ;;
  *importlib.metadata*) n="torch"; case "$*" in *torchvision*) n=torchvision ;; *torchaudio*) n=torchaudio ;; esac
                        [ -f "$CALLS.$n" ] && { cat "$CALLS.$n"; exit 0; }; exit 1 ;;
  *version_info*) echo "3.13"; exit 0 ;;
  *"-m pip --version"*) [ -f "$(dirname "$0")/.hollow" ] && exit 1; exit 0 ;;
  *"-m pip install"*"--index-url"*) echo "2.12.0+cpu" > "$CALLS.torch"; exit 0 ;;
  *"-m pip"*) exit 0 ;;
esac
exit 0
EOS
chmod +x "$T/stub/uname" "$T/fakepy"
cp "$T/fakepy" "$T/sys/usr/bin/python3.13"; ln -s python3.13 "$T/sys/usr/bin/python3"
cp "$T/fakepy" "$T/brew/linuxbrew/.linuxbrew/bin/python3"
cp "$T/fakepy" "$T/other/bin/python3"
# Fake uv: logs argv; `uv venv ... <dir>` builds <dir>/bin/python as a healthy fake.
cat > "$T/stub/uv" <<'EOS'
#!/usr/bin/env bash
echo "uv $*" >> "$CALLS"
if [ "${1:-}" = venv ]; then
  for d in "$@"; do :; done
  mkdir -p "$d/bin"; cp "$FAKEPY" "$d/bin/python"; rm -f "$d/bin/.hollow"
fi
exit 0
EOS
chmod +x "$T/stub/uv"
export CALLS FAKEPY="$T/fakepy"
# A PATH dir holding ONLY bash + core tools (so a PATH without /usr/bin still runs
# the stubs, and cannot reach a real python3).
mkdir -p "$T/tools"
for _b in bash env cat cp mkdir rm dirname readlink mktemp tr sed head tail grep mv; do
  _p="$(command -v "$_b" 2>/dev/null)" && ln -s "$_p" "$T/tools/$_b"
done
BASH_BIN="$(command -v bash)"

BASE_PATH="$T/stub:$T/brew/linuxbrew/.linuxbrew/bin:/usr/bin:/bin"
# run <env...> -- <shell snippet>: a clean bash with the resolver sourced
run() {
  local envs=()
  while [ "$1" != "--" ]; do envs+=("$1"); shift; done; shift
  env -i HOME="$T/home" PATH="$BASE_PATH" CALLS="$CALLS" FAKEPY="$FAKEPY" \
      _OC_PY_SYSTEM="$T/sys/usr/bin/python3" _OC_PY_DEV="$T/dev" OPENCLAW_ROOT="$T/oc" \
      OC_UV="$T/stub/uv" TMPDIR="$T" "${envs[@]+"${envs[@]}"}" \
      "$BASH_BIN" -c 'source "$1"; shift; eval "$1"' _ "$COMMON" "$1"
}

SYS_REAL="$T/sys/usr/bin/python3.13"
BREW_PY="$T/brew/linuxbrew/.linuxbrew/bin/python3"

# ---- R1 ----------------------------------------------------------------------
got="$(run -- 'oc_python')"
if [ "$got" = "$SYS_REAL" ]; then ok "R1 Homebrew-first PATH on a VPS layout still resolves /usr/bin/python3 -> $got"
else bad "R1 expected $SYS_REAL, got '$got'"; fi
[ "$(run -- 'command -v python3')" = "$BREW_PY" ] && ok "R1 control: PATH really lists the Homebrew python first" \
  || bad "R1 control: fixture PATH does not put Homebrew first"

# ---- R2 / R3 / R4 ------------------------------------------------------------
got="$(run _OC_PY_SYSTEM="$T/none/python3" PATH="$T/stub:$T/brew/linuxbrew/.linuxbrew/bin:$T/other/bin:/usr/bin:/bin" -- 'oc_python')"
[ "$got" = "$T/other/bin/python3" ] && ok "R2 no /usr/bin/python3: first non-Homebrew python3 on PATH ($got)" \
  || bad "R2 expected $T/other/bin/python3, got '$got'"
rc=0; got="$(run _OC_PY_SYSTEM="$T/none/python3" PATH="$T/stub:$T/brew/linuxbrew/.linuxbrew/bin:$T/tools" -- 'oc_python' 2>"$T/r3.err")" || rc=$?
[ "$rc" -ne 0 ] && [ -z "$got" ] && grep -q 'no non-Homebrew python3' "$T/r3.err" \
  && ok "R3 only a Homebrew python available: resolver fails loudly instead of using it" \
  || bad "R3 rc=$rc got='$got' err=$(cat "$T/r3.err")"
got="$(run OC_PYTHON="$BREW_PY" -- 'oc_python' 2>"$T/r4.err")"
[ "$got" = "$SYS_REAL" ] && grep -q 'refused on Linux' "$T/r4.err" \
  && ok "R4 OC_PYTHON pointing at Homebrew is refused on Linux" || bad "R4 got '$got' err=$(cat "$T/r4.err")"
got="$(run OC_PYTHON="$T/other/bin/python3" -- 'oc_python')"
[ "$got" = "$T/other/bin/python3" ] && ok "R4 control: a non-Homebrew OC_PYTHON is honoured on Linux" || bad "R4 control got '$got'"

# ---- R5 Mac --------------------------------------------------------------------
got="$(run FAKE_UNAME=Darwin -- 'oc_python')"
[ "$got" = "$BREW_PY" ] && ok "R5 Mac layout unchanged: command -v python3 (here the Homebrew one) -> $got" \
  || bad "R5 Mac expected $BREW_PY, got '$got'"
got="$(run FAKE_UNAME=Darwin OC_PYTHON="$BREW_PY" -- 'oc_python')"
[ "$got" = "$BREW_PY" ] && ok "R5 Mac honours OC_PYTHON even when it is Homebrew" || bad "R5 Mac OC_PYTHON got '$got'"

# ---- R6 stamp ------------------------------------------------------------------
out="$(run -- 'oc_python_record_stamp')"
[ "$(cat "$T/oc/.oc-python" 2>/dev/null)" = "$SYS_REAL" ] && ok "R6 stamp written: $T/oc/.oc-python = $SYS_REAL ($out)" \
  || bad "R6 stamp content '$(cat "$T/oc/.oc-python" 2>/dev/null)'"
[ "$(run -- 'oc_python_stamp_read')" = "$SYS_REAL" ] && ok "R6 stamp read back" || bad "R6 stamp read"
cp "$T/fakepy" "$T/other/bin/python3.12"
printf '%s\n' "$T/other/bin/python3.12" > "$T/oc/.oc-python"
got="$(run _OC_PY_SYSTEM="$T/none/python3" PATH="$T/stub:$T/other/bin:/usr/bin:/bin" -- 'oc_python')"
[ "$got" = "$T/other/bin/python3.12" ] && ok "R6 /usr/bin/python3 gone: the stamp wins over PATH ($got)" \
  || bad "R6 stamp fallback got '$got'"
err="$(run -- 'oc_python_record_stamp' 2>&1 >/dev/null)"
case "$err" in *CHANGED*"$T/other/bin/python3.12"*"$SYS_REAL"*) ok "R6 a changed interpreter is reported loudly" ;;
  *) bad "R6 change not reported: $err" ;; esac
[ "$(cat "$T/oc/.oc-python")" = "$SYS_REAL" ] && ok "R6 stamp updated to the new canonical" || bad "R6 stamp not updated"

# ---- R7 pip flags ----------------------------------------------------------------
: > "$CALLS"; run FAKE_EM=1 -- 'oc_pip_install requests' >/dev/null
line="$(grep -- '-m pip install' "$CALLS" | tail -1)"
case "$line" in "$SYS_REAL -m pip install --user --break-system-packages "*requests) ok "R7 Linux + PEP 668: $line" ;;
  *) bad "R7 Linux+EM argv: $line" ;; esac
: > "$CALLS"; run FAKE_EM=0 -- 'oc_pip_install requests' >/dev/null
line="$(grep -- '-m pip install' "$CALLS" | tail -1)"
case "$line" in *--break-system-packages*) bad "R7 no marker but flag present: $line" ;;
  "$SYS_REAL -m pip install --user "*requests) ok "R7 Linux without the marker: --user only" ;; *) bad "R7 argv: $line" ;; esac
: > "$CALLS"; run FAKE_UNAME=Darwin FAKE_EM=1 -- 'oc_pip_install requests' >/dev/null
line="$(grep -- '-m pip install' "$CALLS" | tail -1)"
case "$line" in *--break-system-packages*) bad "R7 Mac got the PEP 668 override: $line" ;;
  "$BREW_PY -m pip install --user "*requests) ok "R7 Mac: --user, never the override (behaviour unchanged)" ;; *) bad "R7 Mac argv: $line" ;; esac
if grep -vE '^[[:space:]]*#' "$COMMON" | grep -- '--break-system-packages' | grep -qv -- '--user'; then
  bad "R7 a --break-system-packages without --user exists in the resolver"
else ok "R7 every --break-system-packages in the resolver sits next to --user"; fi

# ---- R8 CPU torch ----------------------------------------------------------------
: > "$CALLS"; rm -f "$CALLS".torch*
run -- 'oc_pip_install openai-whisper' >/dev/null
first="$(grep -- '-m pip install' "$CALLS" | head -1)"; last="$(grep -- '-m pip install' "$CALLS" | tail -1)"
case "$first" in *"--index-url https://download.pytorch.org/whl/cpu torch") ok "R8 no GPU: torch from the CPU-only index first" ;;
  *) bad "R8 first install: $first" ;; esac
case "$last" in *" -c "*openai-whisper) ok "R8 then openai-whisper under a torch constraint pin" ;; *) bad "R8 second install: $last" ;; esac
: > "$CALLS"; rm -f "$CALLS".torch*; touch "$T/dev/nvidia0"
run -- 'oc_pip_install openai-whisper' >/dev/null
grep -q -- '--index-url' "$CALLS" && bad "R8 GPU box still forced the CPU index" || ok "R8 GPU box: no CPU-only index"
rm -f "$T/dev/nvidia0"
: > "$CALLS"; run FAKE_UNAME=Darwin -- 'oc_pip_install openai-whisper' >/dev/null
grep -q -- '--index-url' "$CALLS" && bad "R8 Mac forced the CPU index" || ok "R8 Mac: PyPI torch unchanged (no CUDA wheels exist for macOS)"

# ---- R9 venvs --------------------------------------------------------------------
: > "$CALLS"; run -- "oc_venv '$T/v1'" >/dev/null 2>&1; rc=$?
uvline="$(grep '^uv venv' "$CALLS" | tail -1)"
[ "$rc" -eq 0 ] && [ "$uvline" = "uv venv --python $SYS_REAL --seed $T/v1" ] \
  && ok "R9 new venv: $uvline" || bad "R9 new venv rc=$rc uv='$uvline'"
mkdir -p "$T/v2/bin"; cp "$T/fakepy" "$T/v2/bin/python"; touch "$T/v2/bin/.hollow"
: > "$CALLS"; run -- "oc_venv '$T/v2'" >/dev/null 2>&1; rc=$?
uvline="$(grep '^uv venv' "$CALLS" | tail -1)"
[ "$rc" -eq 0 ] && [ "$uvline" = "uv venv --python $SYS_REAL --seed --allow-existing $T/v2" ] \
  && ok "R9 hollow venv (no pip) repaired in place: $uvline" || bad "R9 hollow rc=$rc uv='$uvline'"
: > "$CALLS"; run -- "oc_venv '$T/v1'" >/dev/null 2>&1
grep -q '^uv' "$CALLS" && bad "R9 healthy venv was rebuilt" || ok "R9 healthy venv untouched"
: > "$CALLS"; rc=0; err="$(run OC_UV="$T/no-uv" FAKE_ENSUREPIP=0 -- "oc_venv '$T/v3'" 2>&1)" || rc=$?
[ "$rc" -ne 0 ] && [ ! -e "$T/v3" ] && case "$err" in *"would be a hollow venv"*) true ;; *) false ;; esac \
  && ok "R9 no uv + no ensurepip: loud failure, no hollow venv left" || bad "R9 no-uv rc=$rc err=$err"
grep -q -- '-m pip install --user .*uv' "$CALLS" && ok "R9 ... after trying to bootstrap uv into the canonical user site" \
  || bad "R9 uv bootstrap not attempted"
: > "$CALLS"; run OC_UV="$T/no-uv" FAKE_ENSUREPIP=1 -- "oc_venv '$T/v4'" >/dev/null 2>&1
grep -q -- "$SYS_REAL -m venv $T/v4" "$CALLS" && ok "R9 no uv but ensurepip present: <canonical> -m venv" || bad "R9 ensurepip path: $(cat "$CALLS")"

# ---- R10 uv tool ---------------------------------------------------------------
: > "$CALLS"; run -- 'oc_uv_tool_install whisper-ctranslate2' >/dev/null
grep -qx "uv tool install --python $SYS_REAL whisper-ctranslate2" "$CALLS" \
  && ok "R10 uv tool install --python <canonical>" || bad "R10 $(cat "$CALLS")"

# ---- M1 mutation proof ------------------------------------------------------------
if [ -z "${ONE_PYTHON_COMMON:-}" ]; then
  MUT="$T/mutant-common.sh"
  python3 - "$COMMON" "$MUT" <<'PYM'
import sys
s = open(sys.argv[1]).read()
anchor = '  # Linux: the image\'s own interpreter, by absolute path, never PATH order.\n'
assert anchor in s, "mutation anchor missing"
s = s.replace(anchor, anchor + '  command -v python3 && return 0   # MUTANT: PATH python3\n', 1)
open(sys.argv[2], "w").write(s)
PYM
  rc=0; out="$(ONE_PYTHON_COMMON="$MUT" bash "${BASH_SOURCE[0]}" 2>&1)" || rc=$?
  if [ "$rc" -ne 0 ] && printf '%s\n' "$out" | grep -q 'FAIL: R1 expected'; then
    ok "M1 MUTATION KILLED: a resolver falling back to PATH python3 fails R1 ($(printf '%s\n' "$out" | grep -c 'FAIL:') failures)"
  else
    bad "M1 mutation SURVIVED (rc=$rc)"; printf '%s\n' "$out" | tail -5
  fi
fi

echo
echo "one-python-resolver: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
