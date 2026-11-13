#!/usr/bin/env bash
# Folded from .github/workflows/persona-set-asset-consistency-guard.yml (job "Persona-SET count triad (offline)"). Step bodies are the workflow's run: blocks, verbatim and in order;
# each runs in its own subshell like a workflow step (own cwd, env and shell options). A failing step prints a
# ::error:: annotation naming the guard and the step, so blame stays exact.
set -e
cd "${GITHUB_WORKSPACE:-$(git rev-parse --show-toplevel)}"
( # step: Assert persona-SET count triad agrees
echo "--- step: Assert persona-SET count triad agrees"
set -e
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards persona-set-asset-consistency-guard: step \"Assert persona-SET count triad agrees\" failed (exit $fg_rc)"' EXIT
export GH_REF="${GITHUB_REF:-}"
export GH_EVENT="${GITHUB_EVENT_NAME:-}"
python3 - <<'PYEOF'
import json, os, sys
from pathlib import Path

root = Path(".")
sk22 = root / "22-book-to-persona-coaching-leadership-system"
personas_dir = sk22 / "personas"
cats_path = sk22 / "persona-categories.json"
manifest_path = root / "shared-utils" / "prebuilt-index" / "INDEX-MANIFEST.json"

ref = os.environ.get("GH_REF", "")
event = os.environ.get("GH_EVENT", "")
# Protected = a real ref update (push/dispatch/tag) onto main, a
# release/* branch, or a version tag. pull_request events are NEVER
# protected (that is the staging carve-out).
protected = event != "pull_request" and (
    ref == "refs/heads/main"
    or ref.startswith("refs/heads/release/")
    or ref.startswith("refs/tags/")
)

fails = []
dir_count = sum(1 for p in personas_dir.iterdir() if p.is_dir()) if personas_dir.is_dir() else None
if dir_count is None:
    fails.append(f"blueprint dir missing: {personas_dir}")

cats_count = None
if cats_path.is_file():
    cats_count = len(json.loads(cats_path.read_text()).get("personas", {}))
else:
    fails.append(f"persona-categories.json missing: {cats_path}")

man_count = man_canon = None
man_embedded = None
asset_rebuild = False
if manifest_path.is_file():
    m = json.loads(manifest_path.read_text())
    man_count = int(m.get("persona_count", -1))
    man_canon = int(m.get("canonical_persona_count", -1))
    if "embedded_persona_count" in m:
        man_embedded = int(m.get("embedded_persona_count", -1))
    asset_rebuild = bool(m.get("asset_rebuild_required", False))
else:
    fails.append(f"INDEX-MANIFEST.json missing: {manifest_path}")

# The four SET-count members must ALWAYS agree (original N38 invariant).
vals = {
    "blueprint_dirs": dir_count,
    "categories.json_keys": cats_count,
    "manifest.persona_count": man_count,
    "manifest.canonical_persona_count": man_canon,
}
print(f"Ref: {ref or '<none>'}  event: {event or '<none>'}  protected: {protected}")
print("Persona-SET count triad:")
for k, v in vals.items():
    print(f"  {k} = {v}")
print(f"  manifest.embedded_persona_count = {man_embedded if man_embedded is not None else '<absent>'}")
print(f"  manifest.asset_rebuild_required = {asset_rebuild}")

present = {k: v for k, v in vals.items() if v is not None}
if len(set(present.values())) > 1:
    fails.append("triad DISAGREES — a persona shipped to the SET without "
                 "an embedded asset, or the manifest was bumped without a "
                 "blueprint. Run shared-utils/prebuilt-index/build-and-publish.sh "
                 "and commit the bumped INDEX-MANIFEST.json. See "
                 "23-ai-workforce-blueprint/ADDING-PERSONAS.md.")

# ── FDN-7 / F1.3 gate 1: asset_rebuild_required on a protected ref ────
if asset_rebuild:
    if protected:
        fails.append(
            "asset_rebuild_required:true on a PROTECTED ref (main / "
            "release/* / tag). The manifest was count-synced by a "
            "--no-asset staging bump; the published gemini-index.sqlite.gz "
            "still lacks vectors for the newest persona(s), so every "
            "client box would download a counted-but-vector-less asset. "
            "Rebuild + publish a REAL asset (which clears the flag) "
            "before merging: shared-utils/prebuilt-index/build-and-publish.sh")
    else:
        print("\nNOTE: asset_rebuild_required:true is ALLOWED on this "
              "non-protected ref (staging). It MUST be cleared (rebuild "
              "the asset) before this manifest reaches main/release.")

# ── FDN-7 / F1.3 gate 3: 5th triad member (embedded_persona_count) ───
# When the manifest claims a fresh asset (asset_rebuild_required:false)
# but embedded_persona_count still disagrees with the SET count, the
# SET carries a counted-but-vector-less persona → FAIL on every ref.
# When asset_rebuild_required:true, this member lags BY DESIGN — the
# gate-1 check above already governs it — so it is carved out here with
# an explanatory message rather than a confusing generic mismatch.
if man_embedded is not None and man_embedded >= 0 and man_count is not None:
    if man_embedded != man_count:
        if asset_rebuild:
            print(f"\nNOTE (--no-asset carve-out): embedded_persona_count="
                  f"{man_embedded} lags SET count={man_count} because "
                  "asset_rebuild_required:true. Real cause is the pending "
                  "asset rebuild (governed by gate 1 above), not a count "
                  "drift.")
        else:
            fails.append(
                f"embedded_persona_count={man_embedded} != SET count="
                f"{man_count} while asset_rebuild_required is false — the "
                "served asset (gemini-index.sqlite.gz) lacks vectors for "
                f"{man_count - man_embedded} persona(s) "
                "(counted-but-vector-less; Layer-5 degrades to keyword for "
                "them). Rebuild + publish via "
                "shared-utils/prebuilt-index/build-and-publish.sh.")

if fails:
    print("\nFAIL:")
    for f in fails:
        print(f"  - {f}")
    sys.exit(1)
print("\nPASS: persona-SET count triad + asset freshness OK (" + str(next(iter(present.values()))) + " personas)")
PYEOF
)
( # step: Assert INSTALL.md persona count is not stale (F1.5 docs-consistency)
echo "--- step: Assert INSTALL.md persona count is not stale (F1.5 docs-consistency)"
set -e
trap 'fg_rc=$?; [ "$fg_rc" -eq 0 ] || echo "::error::fast-guards persona-set-asset-consistency-guard: step \"Assert INSTALL.md persona count is not stale (F1.5 docs-consistency)\" failed (exit $fg_rc)"' EXIT
python3 shared-utils/prebuilt-index/assert-install-doc-consistency.py
)
