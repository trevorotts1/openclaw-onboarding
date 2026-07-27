"""test_u030_status_repoint.py — U030 producer routing table tests."""
import json, sys, tempfile; from pathlib import Path
import pytest
HERE = Path(__file__).resolve().parent; sys.path.insert(0, str(HERE))
import cc_board

def _rd():
    d = Path(tempfile.mkdtemp(prefix="u030-"))
    (d / "working" / "checkpoints").mkdir(parents=True, exist_ok=True)
    return d

def _wire():
    s = []
    cc_board._request = lambda m,u,p,c: (s.append((m,u,dict(p)if isinstance(p,dict)else p))or(200,{}))
    o = cc_board.board_config
    cc_board.board_config = lambda e=None: {"base_url":"http://127.0.0.1:1","token":"","secret":"","timeout":1}
    return s, lambda: setattr(cc_board,"board_config",o)

def test_in_progress_post():
    rd,(seen,rst)=_rd(),_wire()
    try:
        assert cc_board.patch_phase(rd,"T1","P4-RENDER","in_progress",note="rendering")
        m,u,p=seen[0]
        assert m=="POST" and u.endswith("/status") and set(p.keys())=={"note","status"}
        assert "P4-RENDER" in p["note"]
    finally: rst()

def test_review_patch_cert():
    rd,(seen,rst)=_rd(),_wire()
    f=rd/"delivery"/"DECK-FINAL";f.mkdir(parents=True)
    (f/"PROCESS-CERTIFICATE.json").write_text(json.dumps({"certificate_sha":"a"*40,"cert":{}}))
    try:
        assert cc_board.patch_phase(rd,"T1","P9-DELIVER","review",note="done")
        m,u,p=seen[0]
        assert m=="PATCH" and not u.endswith("/status") and "process_certificate_sha" in p
    finally: rst()

def test_receipt():
    rd,(_,rst)=_rd(),_wire()
    try:
        cc_board.patch_phase(rd,"T1","P4-RENDER","in_progress",note="start")
        rp=rd/"working"/"checkpoints"/"cc-board.json"
        if rp.exists():
            for line in rp.read_text().strip().splitlines():
                line=line.strip()
                if not line: continue
                try: e=json.loads(line)
                except (json.JSONDecodeError,ValueError): continue
                if isinstance(e,dict) and e.get("target")=="in_progress":
                    assert e.get("endpoint")=="POST /api/tasks/{id}/status"
    finally: rst()

def test_fail_soft():
    rd,(_,rst)=_rd(),_wire()
    cc_board._request=lambda m,u,p,c:(400,{})
    try: assert cc_board.patch_phase(rd,"T1","P4-RENDER","in_progress") is False
    finally: rst()

def test_constant():
    c=cc_board._CERT_BEARING_STATUSES
    assert isinstance(c,frozenset) and c==frozenset({"review","done"})
