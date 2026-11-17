#!/usr/bin/env bash
# oc-python.sh: command-line front door to the ONE-PYTHON resolver.
#
# The resolver itself lives in platform/common.sh (oc_python, oc_pip_install,
# oc_venv, oc_uv_tool_install). This wrapper lets an agent, a doc or an operator
# use it without sourcing anything:
#
#   bash <root>/skills/shared-utils/oc-python.sh path                 # the ONE interpreter
#   bash <root>/skills/shared-utils/oc-python.sh pip-install <pkg...> # <python> -m pip install --user ...
#   bash <root>/skills/shared-utils/oc-python.sh venv <dir>           # venv on the ONE interpreter
#   bash <root>/skills/shared-utils/oc-python.sh tool-install <pkg>   # uv tool install --python <python>
#   bash <root>/skills/shared-utils/oc-python.sh stamp                # record <root>/.oc-python
#
# <root> is ~/.openclaw on a Mac and /data/.openclaw on a Hostinger VPS.
# Works from the repo (shared-utils/ next to platform/) and from an installed
# box (<root>/skills/shared-utils/ with <root>/platform/).
set -uo pipefail

_here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_common=""
for _c in "$_here/../platform/common.sh" "$_here/../../platform/common.sh" \
          "${OPENCLAW_ROOT:-/nonexistent}/platform/common.sh"; do
  [ -f "$_c" ] && { _common="$_c"; break; }
done
if [ -z "$_common" ]; then
  echo "oc-python: platform/common.sh not found next to $_here; refresh the onboarding bundle" >&2
  exit 2
fi
# shellcheck source=/dev/null
source "$_common"

cmd="${1:-path}"
[ "$#" -gt 0 ] && shift
case "$cmd" in
  path)         oc_python && echo ;;
  pip-install)  [ "$#" -gt 0 ] || { echo "usage: oc-python.sh pip-install <pkg...>" >&2; exit 2; }; oc_pip_install "$@" ;;
  venv)         [ "$#" -eq 1 ] || { echo "usage: oc-python.sh venv <dir>" >&2; exit 2; }; oc_venv "$1" ;;
  tool-install) [ "$#" -gt 0 ] || { echo "usage: oc-python.sh tool-install <pkg...>" >&2; exit 2; }; oc_uv_tool_install "$@" ;;
  stamp)        oc_python_record_stamp ;;
  -h|--help|help) sed -n '2,16p' "${BASH_SOURCE[0]}" ;;
  *) echo "oc-python: unknown command '$cmd' (path | pip-install | venv | tool-install | stamp)" >&2; exit 2 ;;
esac
