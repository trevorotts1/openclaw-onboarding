#!/usr/bin/env bash
# WF23 prep matrix leg stub: mac-native. NOT acceptance.
# W6 leg installs exact artifact on native Mac and runs full HOST-ACCEPTANCE.
# This stub prints NOT-RUN and exits 3. It never prints PASS.
set -u
echo "WF23-MATRIX-LEG id=mac-native op=${1:-all} status=NOT-RUN (prep stub; W6 runs this leg against the exact released artifact)"
exit 3
