#!/usr/bin/env bash
# tests/unit/one-python-box-check.test.sh
# -----------------------------------------------------------------------------
# scripts/one-python-box-check.sh (READ-ONLY fleet check) against fixture boxes.
# Linux is simulated with a uname stub; /usr/bin/python3 with the resolver's
# _OC_PY_SYSTEM seam (a stub reporting 3.13); /dev with _OC_PY_DEV.
#   B1 healthy box -> exit 0, one line
#   B2 a second user tree (python3.14) -> exit 1 naming it
#   B3 a renamed quarantine tree is not counted -> exit 0
#   B4 the only tree is not the canonical version -> exit 1
#   B5 a venv on Homebrew python -> exit 1 naming the venv; --allow-venv exempts it
#   B6 nvidia wheels without a GPU -> exit 1; with a GPU -> exit 0
#   B7 nothing on the fixture changed (read-only)
# -----------------------------------------------------------------------------
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CHECK="$REPO/scripts/one-python-box-check.sh"
PASS=0; FAIL=0
ok()  { PASS=$((PASS+1)); echo "  PASS: $*"; }
bad() { FAIL=$((FAIL+1)); echo "  FAIL: $*"; }

T="$(mktemp -d)"; T="$(cd -P "$T" && pwd)"
trap 'rm -rf "$T"' EXIT
mkdir -p "$T/stub" "$T/sys/usr/bin" "$T/dev" "$T/oc" "$T/home/.local/lib/python3.13/site-packages"
printf '#!/bin/sh\necho Linux\n' > "$T/stub/uname"
cat > "$T/sys/usr/bin/python3.13" <<'EOS'
#!/bin/sh
case "$*" in
  *version_info*) echo 3.13 ;;
  *getuserbase*) echo "$FAKE_USER_BASE" ;;
esac
exit 0
EOS
chmod +x "$T/stub/uname" "$T/sys/usr/bin/python3.13"; ln -s python3.13 "$T/sys/usr/bin/python3"
mkvenv() { mkdir -p "$1/lib/python3.13/site-packages"; printf 'home = %s\nversion = 3.13.5\n' "$2" > "$1/pyvenv.cfg"; }
mkvenv "$T/oc/venvs/video-creator" /usr/bin
mkvenv "$T/oc/.venv-presentations" /usr/bin

chk() {   # chk <args...>: prints "<rc>|<output>"
  local out rc=0
  out="$(env PATH="$T/stub:$PATH" HOME="$T/home" _OC_PY_SYSTEM="$T/sys/usr/bin/python3" _OC_PY_DEV="$T/dev" \
           FAKE_USER_BASE="$T/home/.local" OPENCLAW_ROOT="$T/oc" UV_TOOL_DIR="$T/uv-tools" \
           bash "$CHECK" "$@" 2>&1)" || rc=$?
  printf '%s|%s' "$rc" "$out"
}
before="$(cd "$T" && find . -print0 | xargs -0 ls -ld 2>/dev/null | md5sum 2>/dev/null || find "$T" | sort)"

r="$(chk)"; [ "${r%%|*}" = 0 ] && [ "$(printf '%s' "${r#*|}" | wc -l | tr -d ' ')" = 0 ] \
  && ok "B1 healthy box: ${r#*|}" || bad "B1 $r"

mkdir -p "$T/home/.local/lib/python3.14"
r="$(chk)"; case "$r" in 1\|*"2 user-site trees"*python3.14*) ok "B2 second tree: ${r#*|}" ;; *) bad "B2 $r" ;; esac
mv "$T/home/.local/lib/python3.14" "$T/home/.local/lib/python3.14.QUARANTINED-2026-11-17"
r="$(chk)"; [ "${r%%|*}" = 0 ] && ok "B3 quarantined tree not counted" || bad "B3 $r"

mv "$T/home/.local/lib/python3.13" "$T/home/.local/lib/python3.12"
r="$(chk)"; case "$r" in 1\|*"not the canonical python3.13"*) ok "B4 wrong-version tree: ${r#*|}" ;; *) bad "B4 $r" ;; esac
mv "$T/home/.local/lib/python3.12" "$T/home/.local/lib/python3.13"

mkvenv "$T/oc/tools/convert-and-flow-cli/.venv" /data/linuxbrew/.linuxbrew/opt/python@3.14/bin
r="$(chk)"; case "$r" in 1\|*"not on /usr/bin python"*convert-and-flow-cli*) ok "B5 Homebrew venv: ${r#*|}" ;; *) bad "B5 $r" ;; esac
r="$(chk --allow-venv "$T/oc/tools/convert-and-flow-cli/.venv")"; [ "${r%%|*}" = 0 ] && ok "B5 --allow-venv exempts a deliberate venv" || bad "B5 allow $r"
rm -rf "$T/oc/tools"

mkdir -p "$T/home/.local/lib/python3.13/site-packages/nvidia" "$T/oc/venvs/video-creator/lib/python3.13/site-packages/nvidia_cublas_cu12-12.0.dist-info"
r="$(chk)"; case "$r" in 1\|*"nvidia/CUDA"*) ok "B6 CUDA wheels without a GPU: ${r#*|}" ;; *) bad "B6 $r" ;; esac
touch "$T/dev/nvidia0"
r="$(chk)"; [ "${r%%|*}" = 0 ] && ok "B6 same wheels with a GPU present: OK" || bad "B6 gpu $r"
rm -f "$T/dev/nvidia0"; rm -rf "$T/home/.local/lib/python3.13/site-packages/nvidia" "$T/oc/venvs/video-creator/lib/python3.13/site-packages/nvidia_cublas_cu12-12.0.dist-info"

after="$(cd "$T" && find . -print0 | xargs -0 ls -ld 2>/dev/null | md5sum 2>/dev/null || find "$T" | sort)"
r="$(chk)"
after2="$(cd "$T" && find . -print0 | xargs -0 ls -ld 2>/dev/null | md5sum 2>/dev/null || find "$T" | sort)"
[ "$after" = "$after2" ] && [ ! -e "$T/oc/.oc-python" ] && ok "B7 read-only: the check wrote nothing (no stamp, no file changed)" || bad "B7 the check changed the fixture"
: "$before"

echo
echo "one-python-box-check: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
