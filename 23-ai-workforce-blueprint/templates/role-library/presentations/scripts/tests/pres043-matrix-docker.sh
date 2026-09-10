#!/usr/bin/env bash
# PRES-043 Docker-profile driver — Hostinger + Contabo legs, local daemon.
#
# Builds both pinned Dockerfiles, records image/OS/interpreter/font/pip
# identity receipts, runs the mocked battery INSIDE each container, and runs
# the watchdog tick + restart-resume + bounded-fault legs per profile.
#
# DOCKER UNAVAILABLE: prints NOT VERIFIED with the exact next action and
# exits 3 (never 0, never a waiver). Platform-variable runs are never
# labeled deployed proof.
#
# Usage: bash pres043-matrix-docker.sh [--evidence-dir DIR]
# Env: PROFILE=hostinger|contabo|both (default both)

set -euo pipefail

SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MATRIX_DIR="$SCRIPTS_DIR/../release-matrix"
REPO_ROOT="$(cd "$MATRIX_DIR/../../../../.." && pwd)"
PROFILE="${PROFILE:-both}"
EVIDENCE_DIR=""

while [ $# -gt 0 ]; do
  case "$1" in
    --evidence-dir=*) EVIDENCE_DIR="${1#--evidence-dir=}"; shift ;;
    --evidence-dir) EVIDENCE_DIR="${2:-}"; shift 2 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

log() { echo "[pres043-docker] $*"; }

if ! command -v docker >/dev/null 2>&1; then
  echo "NOT VERIFIED: docker CLI absent on this host. Next action: install Docker (or run this driver on a host with a Docker daemon) then re-run: bash $0 --evidence-dir <dir>" >&2
  exit 3
fi
if ! docker info >/dev/null 2>&1; then
  echo "NOT VERIFIED: docker daemon unreachable (docker info failed). Next action: start the Docker daemon (colima/docker desktop) then re-run: bash $0 --evidence-dir <dir>" >&2
  exit 3
fi

[ -n "$EVIDENCE_DIR" ] && mkdir -p "$EVIDENCE_DIR"

run_profile() {
  local profile="$1" tag="pres043-$1" dockerfile="$MATRIX_DIR/Dockerfile.$1"
  log "=== profile: $profile ==="

  log "building $tag from $dockerfile"
  docker build -f "$dockerfile" -t "$tag" "$REPO_ROOT" 2>&1 | tail -n 5

  log "image identity"
  if [ -n "$EVIDENCE_DIR" ]; then
    docker inspect "$tag" --format '{{.RepoDigests}} {{.Architecture}} {{.Os}}' | tee "$EVIDENCE_DIR/image-$profile.txt"
    # Real digests, ONE image per invocation (docker images takes at most 1
    # argument — the old evidence file captured that usage error verbatim).
    docker images --digests "$tag" 2>&1 | tee -a "$EVIDENCE_DIR/docker-images-digests.txt"
    docker inspect "$tag" --format '{{json .RepoDigests}}' | tee -a "$EVIDENCE_DIR/docker-images-digests.txt"
    docker run --rm "$tag" bash -lc 'cat /etc/os-release | head -3; python3 --version; soffice --version | head -1; pdftoppm -v 2>&1 | head -1; tesseract --version 2>&1 | head -1; echo "fonts-dejavu-liberation=$(fc-list | grep -ciE "dejavu|liberation")"; pip freeze | grep -iE "reportlab|python-pptx|pypdf|pytesseract|pillow"' | tee "$EVIDENCE_DIR/versions-$profile.txt"
  else
    docker inspect "$tag" --format '{{.RepoDigests}} {{.Architecture}} {{.Os}}'
    docker run --rm "$tag" bash -lc 'cat /etc/os-release | head -3; python3 --version; soffice --version | head -1; pdftoppm -v 2>&1 | head -1; tesseract --version 2>&1 | head -1; echo "fonts-dejavu-liberation=$(fc-list | grep -ciE "dejavu|liberation")"; pip freeze | grep -iE "reportlab|python-pptx|pypdf|pytesseract|pillow"'
  fi

  log "mocked battery inside $tag"
  if [ -n "$EVIDENCE_DIR" ]; then
    docker run --rm -v "$REPO_ROOT:/opt/engine:ro" -w /opt/engine/23-ai-workforce-blueprint/templates/role-library/presentations/scripts/tests "$tag" \
      bash -lc 'python3 -m pytest test_pres043_release_matrix.py -q -p no:cacheprovider' 2>&1 | tee "$EVIDENCE_DIR/battery-$profile.log"
  else
    docker run --rm -v "$REPO_ROOT:/opt/engine:ro" -w /opt/engine/23-ai-workforce-blueprint/templates/role-library/presentations/scripts/tests "$tag" \
      bash -lc 'python3 -m pytest test_pres043_release_matrix.py -q -p no:cacheprovider'
  fi

  log "watchdog tick inside $tag (expect exit 13 on empty root)"
  docker run --rm -v "$REPO_ROOT:/opt/engine:ro" "$tag" \
    bash -lc 'cd /opt/engine/23-ai-workforce-blueprint/templates/role-library/presentations/scripts && PRESENTATION_NOTIFY_CMD="python3 presentation-notify.py" python3 presentation_job.py --watchdog --scan-root /tmp --scan-depth 1; test $? -eq 13' \
    && log "tick-$profile=PASS(exit13-undetermined)" || { log "tick-$profile=FAIL"; return 1; }

  if [ "$profile" = "contabo" ]; then
    log "memory-bounded leg (2g) inside $tag"
    docker run --rm --memory 2g --memory-swap 2g -v "$REPO_ROOT:/opt/engine:ro" -w /opt/engine/23-ai-workforce-blueprint/templates/role-library/presentations/scripts/tests "$tag" \
      bash -lc 'python3 -m pytest test_pres043_release_matrix.py::test_fault_cgroup_memory_pressure_named test_pres043_release_matrix.py::test_restart_resume_only_incomplete_units -q -p no:cacheprovider' 2>&1 | tail -n 3
    log "read-only output leg inside $tag"
    docker run --rm -v "$REPO_ROOT:/opt/engine:ro" -w /opt/engine/23-ai-workforce-blueprint/templates/role-library/presentations/scripts/tests "$tag" \
      bash -lc 'python3 -m pytest test_pres043_release_matrix.py::test_fault_readonly_output_volume -q -p no:cacheprovider' 2>&1 | tail -n 3
  fi
  log "profile-$profile=DONE"
}

case "$PROFILE" in
  hostinger) run_profile hostinger ;;
  contabo) run_profile contabo ;;
  both) run_profile hostinger; run_profile contabo ;;
  *) echo "unknown PROFILE=$PROFILE (hostinger|contabo|both)" >&2; exit 2 ;;
esac
log "ALL DOCKER LEGS DONE"
