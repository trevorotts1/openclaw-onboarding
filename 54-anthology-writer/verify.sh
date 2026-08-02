#!/usr/bin/env bash
set -euo pipefail
diff 54-anthology-writer/mc_board.py 50-email-engine/mc_board.py || exit 1
echo "OK: mc_board.py is byte-identical"
