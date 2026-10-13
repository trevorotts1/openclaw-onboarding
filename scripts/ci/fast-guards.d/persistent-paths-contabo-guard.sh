#!/usr/bin/env bash
# D04/D05/D06: Contabo durable paths (master files, backups, 999-setup, skill 41 workspace) land on the volume; Mac/Hostinger unchanged.
set -e
cd "$GITHUB_WORKSPACE"
bash tests/unit/persistent-paths-contabo.test.sh
