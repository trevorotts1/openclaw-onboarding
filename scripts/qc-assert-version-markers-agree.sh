#!/usr/bin/env bash
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

normalize_version() {
  local v="$1"
  v="${v//$'\r'/}"; v="${v#"${v%%[![:space:]]*}"}"; v="${v%"${v##*[![:space:]]}"}"
  case "$v" in \"*\") v="${v#\"}"; v="${v%\"}" ;; \'*\') v="${v#\'}"; v="${v%\'}" ;; esac
  v="${v#"${v%%[![:space:]]*}"}"; v="${v%"${v##*[![:space:]]}"}"
  case "$v" in [vV][0-9]*) v="${v#?}" ;; esac
  printf '%s' "$v"
}

extract_frontmatter_version() {
  awk 'BEGIN{f=0}{if($0=="---"){f++;if(f>=2)exit;next}if(f==1&&$0~/^version:/){v=$0;sub(/^version:[ \t]*/,"",v);print v;exit}}' "$1"
}

extract_qc_version() {
  awk '/^\*\*Version:\*\*/{v=$0;sub(/^\*\*Version:\*\*[ \t]*/,"",v);print v;exit}' "$1"
}

cl_has_version() {
  grep -qE "^## +\[?v?${2//\./\\.}\]?([[:space:]]|\$)" "$1" 2>/dev/null
}

scan_root() {
  local root="$1"; local -a log=(); local e=0 c=0 ssk=0 sqc=0
  while IFS= read -r vf; do
    local d b sv svn
    d="$(dirname "$vf")"; b="$(basename "$d")"
    sv="$(cat "$vf")"; svn="$(normalize_version "$sv")"
    c=$((c+1))

    # Check 1: SKILL.md frontmatter
    local smd="$d/SKILL.md"
    if [ -f "$smd" ]; then
      local fm
      fm="$(extract_frontmatter_version "$smd")"
      if [ -n "$fm" ]; then
        local fmn
        fmn="$(normalize_version "$fm")"
        if [ "$fmn" != "$svn" ]; then
          log+=("DRIFT|${b}|SKILL.md fm:|${fm}|skill-version.txt|${sv}"); e=$((e+1))
        fi
      else ssk=$((ssk+1)); fi
    fi

    # Check 2: QC.md **Version:**
    local qc="$d/QC.md"
    if [ -f "$qc" ]; then
      local qr
      qr="$(extract_qc_version "$qc")"
      if [ -n "$qr" ]; then
        local qn
        qn="$(normalize_version "$qr")"
        if [ "$qn" != "$svn" ]; then
          log+=("DRIFT|${b}|QC.md Version:|${qr}|skill-version.txt|${sv}"); e=$((e+1))
        fi
      else sqc=$((sqc+1)); fi
    fi

    # Check 3: CHANGELOG.md header
    local cl="$d/CHANGELOG.md"
    if [ -f "$cl" ]; then
      cl_has_version "$cl" "$svn" || { log+=("MISSING|${b}|CHANGELOG missing header for ${sv}"); e=$((e+1)); }
    fi
  done < <(find "$root" -type f -name skill-version.txt -not -path '*/node_modules/*' -not -path '*/.git/*' 2>/dev/null | LC_ALL=C sort)

  [ "$c" -eq 0 ] && { echo "CANNOT RESOLVE" >&2; return 2; }
  echo "Checked ${c} skills (SKILL.md skipped: ${ssk}, QC.md absent: ${sqc})"
  [ "$e" -eq 0 ] && { echo "PASS"; return 0; }
  echo "INVARIANT VIOLATED (${e}):" >&2
  for entry in "${log[@]}"; do
    local k="${entry%%|*}"; local rest="${entry#*|}"
    local n="${rest%%|*}"; rest="${rest#*|}"
    local s1="${rest%%|*}"; rest="${rest#*|}"; local v1="${rest%%|*}"; rest="${rest#*|}"
    local s2="${rest%%|*}"; local v2="${rest#*|}"
    case "$k" in
      DRIFT) printf '  %-38s %-16s %-10s != %-16s %s\n' "$n" "$s1" "$v1" "$s2" "$v2" >&2 ;;
      MISSING) printf '  %-38s %s\n' "$n" "$s1" >&2 ;;
    esac
  done
  return 1
}

run_self_test() {
  local tmp f=0 rc
  tmp="$(mktemp -d)"; trap "rm -rf '$tmp'" RETURN
  mkdir -p "$tmp/g/70" "$tmp/g/71" "$tmp/g/72" "$tmp/b/80" "$tmp/b/81" "$tmp/b/82"
  printf '1.2.3\n' > "$tmp/g/70/skill-version.txt"; printf -- '---\nname:a\nversion:1.2.3\n---\n' > "$tmp/g/70/SKILL.md"
  printf '# QC\n**Version:** v1.2.3\n' > "$tmp/g/70/QC.md"; printf '# CHANGELOG\n## v1.2.3\n' > "$tmp/g/70/CHANGELOG.md"
  printf '4.5.6\n' > "$tmp/g/71/skill-version.txt"; printf -- '---\nname:b\nversion:4.5.6\n---\n' > "$tmp/g/71/SKILL.md"
  printf '# CHANGELOG\n## [v4.5.6]\n' > "$tmp/g/71/CHANGELOG.md"
  printf 'v2.0.0\n' > "$tmp/g/72/skill-version.txt"; printf -- '---\nname:c\nversion:"2.0.0"\n---\n' > "$tmp/g/72/SKILL.md"
  printf '# QC\n**Version:** v2.0.0\n' > "$tmp/g/72/QC.md"; printf '# CHANGELOG\n## v2.0.0\n' > "$tmp/g/72/CHANGELOG.md"
  printf '1.0.0\n' > "$tmp/b/80/skill-version.txt"; printf -- '---\nname:d\nversion:1.0.0\n---\n' > "$tmp/b/80/SKILL.md"
  printf '# QC\n**Version:** 1.0.1\n' > "$tmp/b/80/QC.md"; printf '# CHANGELOG\n## v1.0.0\n' > "$tmp/b/80/CHANGELOG.md"
  printf '2.0.0\n' > "$tmp/b/81/skill-version.txt"; printf -- '---\nname:e\nversion:2.0.1\n---\n' > "$tmp/b/81/SKILL.md"
  printf '# QC\n**Version:** v2.0.0\n' > "$tmp/b/81/QC.md"; printf '# CHANGELOG\n## [v2.0.0]\n' > "$tmp/b/81/CHANGELOG.md"
  printf '3.0.0\n' > "$tmp/b/82/skill-version.txt"; printf -- '---\nname:f\nversion:3.0.0\n---\n' > "$tmp/b/82/SKILL.md"
  printf '# CHANGELOG\n## v2.9.0\n' > "$tmp/b/82/CHANGELOG.md"
  scan_root "$tmp/g" >/dev/null 2>&1; rc=$?
  [ "$rc" -eq 0 ] && echo "  [PASS] match" || { echo "  [FAIL] match ($rc)"; f=$((f+1)); }
  scan_root "$tmp/b" >/dev/null 2>&1; rc=$?
  [ "$rc" -eq 1 ] && echo "  [PASS] mismatch" || { echo "  [FAIL] mismatch ($rc)"; f=$((f+1)); }
  [ "$f" -eq 0 ] && echo "SELF-TEST PASS" && return 0; echo "SELF-TEST FAIL ($f)" >&2; return 1
}

main() {
  local root="$REPO_ROOT"
  while [ "$#" -gt 0 ]; do
    case "$1" in --self-test) run_self_test; exit $? ;; --root) shift; root="${1:?}" ;;
    -h|--help) grep -E '^#( |$)' "${BASH_SOURCE[0]}" | sed 's/^# //'; exit 0 ;; *) root="$1" ;; esac; shift
  done; scan_root "$root"; exit $?
}
main "$@"
