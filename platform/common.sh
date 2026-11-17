#!/usr/bin/env bash
# Shared read-only platform/topology and path resolution. Bash 3.2 compatible.
# Source this before selecting platform/<mac|vps>/bootstrap.sh. Hosting-provider
# names do not determine an operating system, container, or client directory.

oc_detect_platform() {
  case "$(uname -s)" in
    Darwin) printf '%s\n' mac ;;
    Linux) printf '%s\n' vps ;;
    *) echo "Unsupported onboarding OS: $(uname -s)" >&2; return 1 ;;
  esac
}

# Canonicalize a directory path so two SPELLINGS of one directory compare equal.
# A container image whose /data is a symlink to the node user's home makes
# /data/.openclaw and $HOME/.openclaw the same inode reached by two names; a
# string comparison calls that two installations and aborts the updater.
# Portable on purpose: `cd -P` + `pwd -P` are POSIX builtins that work in bash
# 3.2 and in the minimal shells the Docker images ship. `readlink -f` is GNU
# only (macOS shipped no -f for years) and python3 is not present in every
# image, so both are fallbacks, tried only when the builtin cannot answer.
# Never fails: an unresolvable path is returned unchanged, so a caller can
# always still compare and report what it was handed.
oc_canonical_path() {
  local target resolved
  target="$1"
  resolved=""
  [ -n "$target" ] || return 1
  if [ -d "$target" ]; then
    resolved="$(cd -P -- "$target" 2>/dev/null && pwd -P)" || resolved=""
  fi
  if [ -z "$resolved" ]; then
    resolved="$(readlink -f -- "$target" 2>/dev/null)" || resolved=""
  fi
  if [ -z "$resolved" ] && command -v python3 >/dev/null 2>&1; then
    resolved="$(python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$target" 2>/dev/null)" || resolved=""
  fi
  [ -n "$resolved" ] || resolved="$target"
  case "$resolved" in
    /) ;;
    *) resolved="${resolved%/}" ;;
  esac
  printf '%s\n' "$resolved"
}

# True when <dir> is a mount point. Needs util-linux `mountpoint` (absent on
# macOS, where it simply answers false).
oc_is_mount() {
  [ -d "$1" ] && command -v mountpoint >/dev/null 2>&1 && mountpoint -q "$1"
}

# ONE rule for "where does durable data live" (D04/D05/D06). On Contabo the node
# user's $HOME is the container image's throwaway layer and only the OpenClaw
# root (~/.openclaw) is a mounted volume, so ~/Downloads, ~/999-setup and the
# like vanish on every recreate. Prints the OpenClaw root when it is a mount and
# $HOME is not (Linux only); prints nothing and returns 1 everywhere else (Mac,
# Hostinger where $HOME=/data is itself the volume, a bare VPS). Callers then use
#   <root>/openclaw-master-files   <root>/backups   <root>/persist-home/999-setup
# Same rule as shared-utils/detect_platform.py _home_master_files().
oc_persist_root() {
  local root="${1:-${OPENCLAW_ROOT:-$HOME/.openclaw}}"
  [ "$(uname -s)" = Linux ] || return 1
  oc_is_mount "$root" || return 1
  oc_is_mount "$HOME" && return 1
  printf '%s' "${root%/}"
}

oc_container_marked() {
  [[ -f /.dockerenv || -f /run/.containerenv ]] && return 0
  [[ -r /proc/1/cgroup ]] && grep -qE '(^|/)(docker|kubepods|libpod)(/|[-.])' /proc/1/cgroup && return 0
  return 1
}

oc_runtime_topology() {
  if [[ "$(uname -s)" == Linux ]] && oc_container_marked; then
    printf '%s\n' container
  else
    printf '%s\n' native
  fi
}

oc_set_platform_paths() {
  local detected root workspace configured home_canonical data_canonical
  detected="$(oc_detect_platform)" || return 1
  if [[ -n "${OPENCLAW_PLATFORM:-}" && "${OPENCLAW_PLATFORM}" != "$detected" ]]; then
    echo "OPENCLAW_PLATFORM=${OPENCLAW_PLATFORM} conflicts with the actual OS ($detected)." >&2
    return 1
  fi
  OC_PLATFORM="$detected"
  OPENCLAW_PLATFORM="$detected"
  OPENCLAW_RUNTIME_TOPOLOGY="$(oc_runtime_topology)"
  root="${OPENCLAW_ROOT:-${OC_ROOT:-${OC_CONFIG:-}}}"
  if [[ -z "$root" ]]; then
    # Preserve an existing /data installation on Linux, but an unrelated /data
    # directory on a native VPS is not evidence of Docker or client ownership.
    root="$HOME/.openclaw"
    if [[ "$detected" == vps && -d /data/.openclaw ]]; then
      root=/data/.openclaw
      if [[ -d "$HOME/.openclaw" && "$HOME/.openclaw" != /data/.openclaw ]]; then
        # Two names can be one directory. Resolve both before deciding, and
        # abort only when they are genuinely separate installations.
        home_canonical="$(oc_canonical_path "$HOME/.openclaw")"
        data_canonical="$(oc_canonical_path /data/.openclaw)"
        if [[ "$home_canonical" == "$data_canonical" ]]; then
          echo "One OpenClaw root reached by two paths: $HOME/.openclaw and /data/.openclaw both resolve to $home_canonical." >&2
          echo "Using $HOME/.openclaw; no OPENCLAW_ROOT is needed." >&2
          root="$HOME/.openclaw"
        else
          echo "Two OpenClaw roots exist; set OPENCLAW_ROOT to the intended client installation." >&2
          echo "  $HOME/.openclaw resolves to $home_canonical" >&2
          echo "  /data/.openclaw resolves to $data_canonical" >&2
          return 1
        fi
      fi
    elif [[ "$detected" == vps && "$OPENCLAW_RUNTIME_TOPOLOGY" == container && -d /data && ! -d "$HOME/.openclaw" ]]; then
      root=/data/.openclaw
    fi
  fi
  case "$root" in /*) ;; *) echo "OPENCLAW_ROOT must be an absolute path." >&2; return 1 ;; esac
  root="${root%/}"
  [[ -n "$root" && "$root" != / ]] || { echo "OpenClaw root cannot be the filesystem root." >&2; return 1; }
  if [[ -n "${OPENCLAW_WORKSPACE_PATH:-}" && -n "${OPENCLAW_WORKSPACE_ROOT:-}" && "${OPENCLAW_WORKSPACE_PATH%/}" != "${OPENCLAW_WORKSPACE_ROOT%/}" ]]; then
    echo "OPENCLAW_WORKSPACE_PATH and OPENCLAW_WORKSPACE_ROOT conflict." >&2
    return 1
  fi
  workspace="${OPENCLAW_WORKSPACE_PATH:-${OPENCLAW_WORKSPACE_ROOT:-}}"
  if [[ -z "$workspace" && -f "$root/openclaw.json" ]] && command -v python3 >/dev/null 2>&1; then
    configured="$(python3 - "$root/openclaw.json" <<'PY'
import json, os, sys
try:
    data = json.load(open(sys.argv[1]))
    value = data.get('agents', {}).get('defaults', {}).get('workspace', '')
    if isinstance(value, str) and value.strip():
        print(os.path.expanduser(value.strip()))
except (OSError, ValueError, AttributeError):
    sys.exit(1)
PY
)" || { echo "Cannot read the configured client workspace; refusing a replacement default." >&2; return 1; }
    workspace="$configured"
  fi
  workspace="${workspace:-$root/workspace}"
  case "$workspace" in /*) ;; *) echo "The client workspace must be an absolute path." >&2; return 1 ;; esac
  OC_CONFIG="$root"
  OC_ROOT="$root"
  OPENCLAW_ROOT="$root"
  OC_WORKSPACE_DEFAULT="${workspace%/}"
  OPENCLAW_WORKSPACE_PATH="$OC_WORKSPACE_DEFAULT"
  OPENCLAW_WORKSPACE_ROOT="$OC_WORKSPACE_DEFAULT"
  OC_JSON="$root/openclaw.json"
  OC_SECRETS_ENV="$root/secrets/.env"
  OC_CREDENTIALS="$root/credentials"
  OC_AGENTS="$root/agents"
  OC_SKILLS_DIR="$root/skills"
  OC_LOGS="$root/logs"
  OC_AUTH_PROFILES="$root/agents/main/agent/auth-profiles.json"
  OC_LEGACY_CLAWD="$HOME/clawd"
  if [[ "$detected" == mac ]]; then
    OC_DOWNLOADS="$HOME/Downloads"
    OC_BACKUPS="$HOME/Downloads/openclaw-backups"
    OC_INSTALL_LOG_DIR="$OC_BACKUPS/install-logs"
  else
    OC_DOWNLOADS="${root%/*}/Downloads"
    # Contabo: the volume is the OpenClaw root, not $HOME (D04), so the master
    # files folder ($OC_DOWNLOADS/openclaw-master-files) lives at <root>/openclaw-master-files.
    oc_persist_root "$root" >/dev/null && OC_DOWNLOADS="$root"
    OC_BACKUPS="$root/backups"
    OC_INSTALL_LOG_DIR="$root/logs/install"
  fi
  export OPENCLAW_PLATFORM OPENCLAW_RUNTIME_TOPOLOGY OPENCLAW_ROOT
  export OPENCLAW_WORKSPACE_PATH OPENCLAW_WORKSPACE_ROOT
}

# >>> OC-ONE-PYTHON BEGIN (v27.1.80) >>>
# ONE canonical Python interpreter per box. Every installer, skill wire script
# and agent instruction that installs a Python package or creates a venv goes
# through these functions; scripts/ci/one-python-guard.py fails CI on any
# install site outside this block. Bash 3.2 compatible.
#
# WHY: installers said bare `python3`, `pip3`, `uv` or `python3 -m venv` and let
# PATH decide. On a Hostinger container `docker exec` puts Homebrew python 3.14
# first while the gateway (the agent) runs Debian /usr/bin/python3 (3.13), so
# every box grew two or three user-package trees and venvs on two interpreters.
#
# Resolution (oc_python prints ONE absolute path, never consults PATH order on
# Linux unless the image has no /usr/bin/python3):
#   OC_PYTHON (env)  honoured when executable; on Linux refused when Homebrew.
#   Linux (VPS / Docker / Contabo / native): realpath of /usr/bin/python3
#     (Debian image: /usr/bin/python3.13). If absent: the stamp, then the first
#     NON-Homebrew python3 on PATH. Never a Homebrew/Linuxbrew python, even when
#     Homebrew is first on PATH.
#   macOS: `command -v python3`, exactly the resolution every Mac installer used
#     before this block (Mac boxes are unchanged).
# The answer is recorded in <openclaw root>/.oc-python by oc_python_record_stamp
# (install.sh and update-skills.sh call it) so skills, docs and the agent read
# the same answer and an image that changes its Python is reported, not silent.
#
# Installs:
#   oc_pip_install <pip args...>  "<canonical> -m pip install --user ..."; when
#     the interpreter carries the PEP 668 EXTERNALLY-MANAGED marker (Debian's
#     python, a Homebrew python on a Mac) --break-system-packages is added, ONLY
#     together with --user (writes go to the user site, never /usr or Homebrew's
#     own site-packages). A venv interpreter installs into its own venv. On Linux
#     without an NVIDIA GPU, torch / torchvision / torchaudio (and openai-whisper's
#     torch), also when named in a -r requirements file, come from the CPU-only
#     index: no nvidia-* / CUDA wheels.
#   oc_venv <dir>  creates (or repairs a hollow) venv on the canonical python:
#     `uv venv --python <canonical> --seed` (Debian's 3.13 has no ensurepip, so
#     `-m venv` makes hollow venvs there), `-m venv` only when ensurepip exists,
#     and a loud failure otherwise. A healthy existing venv is left untouched; a
#     venv that has packages but no pip (a uv-managed venv) only gets pip seeded
#     into it with its OWN interpreter, never rebuilt.
#   oc_uv_tool_install <args...>  `uv tool install --python <canonical> ...`.
# OC_UV pins the uv binary (empty = search PATH and the usual install paths).
# Test seams (never set on a box): _OC_PY_SYSTEM (default /usr/bin/python3),
# _OC_PY_DEV (default /dev).

OC_TORCH_CPU_INDEX="${OC_TORCH_CPU_INDEX:-https://download.pytorch.org/whl/cpu}"

oc_python_is_homebrew() {   # oc_python_is_homebrew <path>: 0 when it is a Homebrew/Linuxbrew python
  local p="$1" r=""
  [ -n "$p" ] || return 1
  r="$(readlink -f -- "$p" 2>/dev/null || true)"
  case "$p:$r" in
    *linuxbrew*|*/Homebrew/*|*/homebrew/*|*/Cellar/*|*/opt/python@*) return 0 ;;
  esac
  return 1
}

oc_python_root() {   # the OpenClaw root the stamp lives in
  local root="${OPENCLAW_ROOT:-${OC_ROOT:-${OC_CONFIG:-}}}"
  if [ -z "$root" ]; then
    root="$HOME/.openclaw"
    if [ "$(uname -s)" = Linux ] && [ -d /data/.openclaw ] && [ ! -d "$HOME/.openclaw" ]; then
      root=/data/.openclaw
    fi
  fi
  printf '%s' "${root%/}"
}

oc_python_stamp_path() { printf '%s/.oc-python' "$(oc_python_root)"; }

oc_python_stamp_read() {   # prints the recorded interpreter (first line), rc 1 when none
  local f v=""
  f="$(oc_python_stamp_path)"
  [ -f "$f" ] || return 1
  IFS= read -r v < "$f" || true
  [ -n "$v" ] || return 1
  printf '%s' "$v"
}

oc_python() {
  local plat cand real d IFS_SAVE
  plat="$(oc_detect_platform 2>/dev/null)" || plat=""
  if [ -n "${OC_PYTHON:-}" ]; then
    if [ ! -x "$OC_PYTHON" ]; then
      echo "one-python: OC_PYTHON=$OC_PYTHON is not executable; ignoring it" >&2
    elif [ "$plat" = vps ] && oc_python_is_homebrew "$OC_PYTHON"; then
      echo "one-python: OC_PYTHON=$OC_PYTHON is a Homebrew python; refused on Linux" >&2
    else
      printf '%s' "$OC_PYTHON"; return 0
    fi
  fi
  if [ "$plat" = mac ]; then
    command -v python3 2>/dev/null || { echo "one-python: no python3 on PATH" >&2; return 1; }
    return 0
  fi
  # Linux: the image's own interpreter, by absolute path, never PATH order.
  cand="${_OC_PY_SYSTEM:-/usr/bin/python3}"
  if [ -x "$cand" ]; then
    real="$(readlink -f -- "$cand" 2>/dev/null || true)"
    [ -n "$real" ] && [ -x "$real" ] || real="$cand"
    if ! oc_python_is_homebrew "$real"; then printf '%s' "$real"; return 0; fi
  fi
  cand="$(oc_python_stamp_read 2>/dev/null || true)"
  if [ -n "$cand" ] && [ -x "$cand" ] && ! oc_python_is_homebrew "$cand"; then
    printf '%s' "$cand"; return 0
  fi
  IFS_SAVE="$IFS"; IFS=:
  for d in $PATH; do
    [ -n "$d" ] && [ -x "$d/python3" ] || continue
    oc_python_is_homebrew "$d/python3" && continue
    IFS="$IFS_SAVE"; printf '%s' "$d/python3"; return 0
  done
  IFS="$IFS_SAVE"
  echo "one-python: no non-Homebrew python3 found (looked at ${_OC_PY_SYSTEM:-/usr/bin/python3}, the .oc-python stamp and PATH)" >&2
  return 1
}

oc_python_record_stamp() {   # write <root>/.oc-python; reports a changed interpreter
  local py root f old=""
  py="$(oc_python)" || return 1
  root="$(oc_python_root)"
  [ -d "$root" ] || { echo "one-python: OpenClaw root $root missing; stamp not written" >&2; return 1; }
  f="$root/.oc-python"
  old="$(oc_python_stamp_read 2>/dev/null || true)"
  if [ "$old" = "$py" ]; then return 0; fi
  if printf '%s\n' "$py" > "$f.tmp.$$" && mv -f "$f.tmp.$$" "$f"; then
    if [ -n "$old" ]; then
      echo "one-python: canonical interpreter CHANGED $old -> $py (packages installed for $old are not visible to $py; reinstall them with oc_pip_install)" >&2
    else
      echo "one-python: canonical interpreter recorded: $py ($f)"
    fi
    return 0
  fi
  rm -f "$f.tmp.$$" 2>/dev/null
  echo "one-python: could not write $f" >&2
  return 1
}

oc_python_is_venv() {   # 0 when <py> runs inside a virtual environment
  "$1" -c 'import sys; sys.exit(0 if sys.prefix != sys.base_prefix else 1)' >/dev/null 2>&1
}

oc_python_externally_managed() {   # 0 when <py> carries the PEP 668 marker
  "$1" -c 'import os, sys, sysconfig
sys.exit(0 if os.path.isfile(os.path.join(sysconfig.get_path("stdlib"), "EXTERNALLY-MANAGED")) else 1)' >/dev/null 2>&1
}

oc_has_nvidia_gpu() {
  local dev="${_OC_PY_DEV:-/dev}"
  [ -e "$dev/nvidia0" ] || [ -e "$dev/nvidiactl" ]
}

oc_uv() {   # prints a uv binary (a Rust binary; brew's uv is fine, brew's python is not)
  local c
  if [ -n "${OC_UV:-}" ]; then   # explicit pin: that binary or nothing
    [ -x "$OC_UV" ] && { printf '%s' "$OC_UV"; return 0; }
    return 1
  fi
  for c in "$(command -v uv 2>/dev/null || true)" "$HOME/.local/bin/uv" /data/.local/bin/uv \
           /data/linuxbrew/.linuxbrew/bin/uv /home/linuxbrew/.linuxbrew/bin/uv \
           /opt/homebrew/bin/uv /usr/local/bin/uv "$HOME/.cargo/bin/uv"; do
    [ -n "$c" ] && [ -x "$c" ] && { printf '%s' "$c"; return 0; }
  done
  return 1
}

oc_pip() {   # oc_pip <pip args>: pip of the canonical python; `install` goes through oc_pip_install
  if [ "${1:-}" = install ]; then shift; oc_pip_install "$@"; return $?; fi
  local py; py="$(oc_python)" || return 1
  "$py" -m pip "$@"
}

oc_pip_install() {
  local py plat a name skip_next=0 want_torch=0 have_torch="" cpu_specs=() base=() cons="" rc=0 v
  py="$(oc_python)" || return 1
  plat="$(oc_detect_platform 2>/dev/null)" || plat=""
  # A venv interpreter installs into its own venv (--user is invalid there).
  # Otherwise --user, plus the PEP 668 override ONLY when the interpreter carries
  # the EXTERNALLY-MANAGED marker, on any platform (a Homebrew python on a Mac
  # needs it exactly like Debian's does; the Mac installers passed it before).
  base=(--user --disable-pip-version-check)
  if oc_python_is_venv "$py"; then
    base=(--disable-pip-version-check)
  elif oc_python_externally_managed "$py"; then
    base=(--user --break-system-packages --disable-pip-version-check)
  fi
  if [ "$plat" = vps ] && ! oc_has_nvidia_gpu; then
    for a in "$@"; do
      if [ "$skip_next" = req ]; then
        # torch named inside a requirements file counts the same as on the command line
        skip_next=0
        if [ -f "$a" ]; then
          while IFS= read -r v; do
            v="${v%%#*}"; v="$(printf '%s' "$v" | tr -d '[:space:]')"
            name="$(printf '%s' "${v%%[<>=!~;[]*}" | tr '[:upper:]' '[:lower:]')"; name="${name//_/-}"
            case "$name" in
              torch|torchvision|torchaudio) cpu_specs+=("$v"); want_torch=1 ;;
              openai-whisper) want_torch=1 ;;
            esac
          done < "$a"
        fi
        continue
      fi
      if [ "$skip_next" = 1 ]; then skip_next=0; continue; fi
      case "$a" in
        -r|--requirement) skip_next=req; continue ;;
        -c|-e|-i|-f|-t|--constraint|--editable|--index-url|--extra-index-url|--find-links|--target|--prefix|--root|--platform|--python-version)
          skip_next=1; continue ;;
        -*) continue ;;
      esac
      name="$(printf '%s' "${a%%[<>=!~;[ ]*}" | tr '[:upper:]' '[:lower:]')"; name="${name//_/-}"
      case "$name" in
        torch|torchvision|torchaudio) cpu_specs+=("$a"); want_torch=1 ;;
        openai-whisper) want_torch=1 ;;
      esac
    done
    if [ "$want_torch" = 1 ]; then
      have_torch="$("$py" -c 'import importlib.metadata as m; print(m.version("torch"))' 2>/dev/null || true)"
      [ "${#cpu_specs[@]}" -eq 0 ] && [ -z "$have_torch" ] && cpu_specs=(torch)
      if [ "${#cpu_specs[@]}" -gt 0 ]; then
        echo "one-python: no NVIDIA GPU: installing ${cpu_specs[*]} from the CPU-only index ($OC_TORCH_CPU_INDEX)"
        "$py" -m pip install "${base[@]}" --index-url "$OC_TORCH_CPU_INDEX" "${cpu_specs[@]}" || return $?
      fi
      cons="$(mktemp "${TMPDIR:-/tmp}/oc-torch-cpu.XXXXXX")" || return 1
      for name in torch torchvision torchaudio; do
        v="$("$py" -c 'import importlib.metadata as m, sys; print(m.version(sys.argv[1]))' "$name" 2>/dev/null || true)"
        [ -n "$v" ] && printf '%s==%s\n' "$name" "$v" >> "$cons"
      done
    fi
  fi
  if [ -n "$cons" ]; then
    "$py" -m pip install "${base[@]}" -c "$cons" "$@" || rc=$?
    rm -f "$cons"
    return $rc
  fi
  "$py" -m pip install "${base[@]}" "$@"
}

oc_venv() {   # oc_venv <dir>: a venv on the canonical python with pip in it
  local dir="${1:-}" py uv
  [ -n "$dir" ] || { echo "one-python: oc_venv needs a directory" >&2; return 1; }
  if [ -x "$dir/bin/python" ] && "$dir/bin/python" -m pip --version >/dev/null 2>&1; then
    return 0
  fi
  if [ -x "$dir/bin/python" ] && "$dir/bin/python" -c 'import os, sys, sysconfig
d = sysconfig.get_paths()["purelib"]
seed = ("pip", "setuptools", "wheel", "_distutils_hack", "pkg_resources", "__pycache__", "distutils-precedence.pth", "_virtualenv")
names = [n for n in os.listdir(d) if not n.split("-")[0].lower().startswith(seed)] if os.path.isdir(d) else []
sys.exit(0 if names else 1)' >/dev/null 2>&1; then
    # Not hollow: it holds packages, it just has no pip (a uv-managed venv).
    # Seed pip with the venv's OWN interpreter; never re-point or rebuild it.
    if uv="$(oc_uv)"; then
      UV_PYTHON_DOWNLOADS=never "$uv" pip install --python "$dir/bin/python" pip >&2 || return $?
    else
      "$dir/bin/python" -m ensurepip >&2 || { echo "one-python: $dir has packages but no pip, and neither uv nor ensurepip can add it" >&2; return 1; }
    fi
    "$dir/bin/python" -m pip --version >/dev/null 2>&1 || { echo "one-python: could not seed pip into $dir" >&2; return 1; }
    return 0
  fi
  py="$(oc_python)" || return 1
  if ! oc_uv >/dev/null && ! "$py" -c 'import ensurepip' >/dev/null 2>&1; then
    # Debian's python has no ensurepip: bootstrap uv (a static binary from PyPI)
    # into the canonical user site, so the next step never makes a hollow venv.
    echo "one-python: $py has no ensurepip and no uv is installed; installing uv into the user site" >&2
    oc_pip_install --quiet uv >&2 || true
  fi
  if uv="$(oc_uv)"; then
    if [ -e "$dir" ]; then
      UV_PYTHON_DOWNLOADS=never "$uv" venv --python "$py" --seed --allow-existing "$dir" >&2 || return $?
    else
      UV_PYTHON_DOWNLOADS=never "$uv" venv --python "$py" --seed "$dir" >&2 || return $?
    fi
  elif "$py" -c 'import ensurepip' >/dev/null 2>&1; then
    "$py" -m venv "$dir" >&2 || return $?
  else
    echo "one-python: cannot create $dir: no uv binary and $py has no ensurepip (would be a hollow venv). Install uv, then re-run." >&2
    return 1
  fi
  if ! "$dir/bin/python" -m pip --version >/dev/null 2>&1; then
    echo "one-python: venv at $dir has no working pip after creation" >&2
    return 1
  fi
}

oc_venv_repair_scripts() {   # regenerate activate/scripts of a relocated venv in place (no pip, no network)
  local dir="${1:-}"
  [ -n "$dir" ] && [ -x "$dir/bin/python" ] || return 1
  "$dir/bin/python" -m venv --without-pip "$dir"
}

oc_uv_tool_install() {   # oc_uv_tool_install <uv tool install args...>
  local py uv
  py="$(oc_python)" || return 1
  uv="$(oc_uv)" || { echo "one-python: uv not found; cannot uv tool install $*" >&2; return 1; }
  UV_PYTHON_DOWNLOADS=never "$uv" tool install --python "$py" "$@"
}
# <<< OC-ONE-PYTHON END <<<
