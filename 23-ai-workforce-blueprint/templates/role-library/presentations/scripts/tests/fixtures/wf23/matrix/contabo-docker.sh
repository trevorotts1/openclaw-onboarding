#!/usr/bin/env bash
# WF23 prep matrix leg stub: contabo-docker. NOT acceptance.
# W6 leg runs Contabo Docker profile fresh/upgrade/restart + CC/GHL legs.
# This stub prints NOT-RUN and exits 3. It never prints PASS.
set -u
echo "WF23-MATRIX-LEG id=contabo-docker op=${1:-all} status=NOT-RUN (prep stub; W6 runs this leg against the exact released artifact)"
exit 3
