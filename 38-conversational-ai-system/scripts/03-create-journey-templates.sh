#!/usr/bin/env bash
# 03-create-journey-templates.sh — Skill 38 / Step 9.28 (Customer Journey Templates Library, v5.11)
# Copies the 8 journey templates + registry from this skill's templates/ folder
# into <MASTER_FILES_DIR>/journey-templates/. Idempotent (does NOT overwrite).

set -euo pipefail
# The pointer file written by 01-locate-master-files-folder.sh contains a BARE PATH
# (one line: the master-files directory), NOT shell `KEY=value` assignments. It must be
# READ, never `source`d — `. <file>` tries to EXECUTE its contents, and when the path is
# a directory bash errors "Is a directory" (or runs the path as a command). Read it into
# MASTER_FILES_DIR with cat instead.
MASTER_FILES_POINTER="$HOME/.openclaw/.skill-38-master-files-dir"
if [ -z "${MASTER_FILES_DIR:-}" ] && [ -f "$MASTER_FILES_POINTER" ]; then
  MASTER_FILES_DIR="$(head -n1 "$MASTER_FILES_POINTER" | tr -d '\r')"
fi
: "${MASTER_FILES_DIR:?MASTER_FILES_DIR not set — run 01-locate-master-files-folder.sh first}"

SKILL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$SKILL_DIR/templates/journey-templates"
DST="$MASTER_FILES_DIR/journey-templates"

[ -d "$SRC" ] || { echo "[skill 38] ERR: $SRC not found"; exit 1; }
mkdir -p "$DST"

# Provisioning goes through the canonical engine (T-36): it is idempotent,
# creates only what the operator permitted, never overwrites an object it does
# not own, and writes a step receipt for every completed step so a re-run
# resumes instead of restarting. The two kinds below are the only permissions
# this step grants.
ENGINE="$SKILL_DIR/tools/bootstrap_engine.py"
[ -f "$ENGINE" ] || { echo "[skill 38] ERR: $ENGINE not found"; exit 1; }

SKILL38_SKILL_DIR="$SKILL_DIR" SKILL38_SRC="$SRC" SKILL38_DST="$DST" python3 - <<'PY'
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(os.environ["SKILL38_SKILL_DIR"]) / "tools"))
from bootstrap_engine import BootstrapEngine, ResourceSpec  # noqa: E402

src = Path(os.environ["SKILL38_SRC"])
dst = os.environ["SKILL38_DST"]

TYPES = ("coach", "e-commerce", "saas", "service-provider",
         "course-creator", "real-estate", "consulting", "wellness")

specs = [
    ResourceSpec(
        "journey.%s" % type_name,
        "journey_template",
        "%s/journey.md" % type_name,
        (src / type_name / "journey.md").read_bytes(),
        adopt_existing=True,
    )
    for type_name in TYPES
]
specs.append(
    ResourceSpec(
        "journey.registry",
        "journey_registry",
        "registry.md",
        (src / "registry.md").read_bytes(),
        adopt_existing=True,
    )
)

engine = BootstrapEngine(
    dst,
    permissions=("kind:journey_template", "kind:journey_registry"),
)
report = engine.run(specs)

status = {}
for key in ("created", "adopted", "unchanged", "blocked", "skipped",
            "refused", "failed"):
    for step in getattr(report, key):
        status[step["resource_id"]] = key

for spec in specs:
    state = status.get(spec.resource_id)
    if state == "created":
        print("[skill 38] installed %s" % spec.path)
    elif state in ("adopted", "unchanged", "blocked"):
        print("[skill 38] %s already exists — preserved" % spec.path)
    else:
        print("[skill 38] ERR: %s not provisioned (%s)"
              % (spec.path, state), file=sys.stderr)

if any(status.get(spec.resource_id) not in
       ("created", "adopted", "unchanged", "blocked") for spec in specs):
    sys.exit(1)
PY

echo "[skill 38] journey templates installed at $DST"
