#!/usr/bin/env bash
# Regression: retirement must preserve arbitrary documents under every old flag.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SWEEP="$REPO_ROOT/scripts/qmd-orphan-sweep.sh"
python3 - "$SWEEP" <<'PYTEST'
from pathlib import Path
import hashlib, os, subprocess, sys, tempfile
with tempfile.TemporaryDirectory() as d:
    root=Path(d); workspace=root/'.openclaw/workspace'; workspace.mkdir(parents=True)
    for name in ['old.qmd','new.qmd','notes.md','index.sqlite']:
        p=workspace/name;p.write_text('preserve '+name);os.utime(p,(1,1))
    def snapshot():
        return {str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file()}
    before=snapshot()
    for flags in [{},{'QMD_DRY_RUN':'1'},{'QMD_RENDER_ACK':'1','QMD_MIN_AGE_MIN':'0'}]:
        env={**os.environ,'HOME':d,'QMD_RENDER_DIR':str(workspace),**flags}
        result=subprocess.run(['bash',sys.argv[1]],env=env,capture_output=True,text=True)
        assert result.returncode==75, result.returncode
        assert 'RETIRED' in result.stderr
        assert snapshot()==before
print('PASS: retirement refuses all three legacy modes and preserves source bytes')
PYTEST
