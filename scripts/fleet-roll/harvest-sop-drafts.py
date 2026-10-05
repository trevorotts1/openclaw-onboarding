#!/usr/bin/env python3
"""harvest-sop-drafts.py -- operator-box tool: turn fleet SOP drafts into a reviewable library PR.

WHY
  When a box has a role the shared role library does not cover, the box's own
  author step (23-ai-workforce-blueprint/scripts/author-missing-sops.py) writes
  a client-neutral draft plus a machine-readable record into
  <OpenClaw root>/workforce/sop-harvest/<department>/ . Drafts pile up on
  boxes. This tool collects them, throws out the bad ones, and stages the
  survivors as library templates on a git branch so a HUMAN can review one pull
  request. It never merges, never pushes, never opens the pull request.

WHAT IT DOES (in order)
  1. COLLECT   read-only. Asks the fleet-access tool which boxes answer, then
               reads each box's sop-harvest folder over headless SSH (one
               `tar` read, nothing written on the box). --from-dir reads a
               folder you collected by hand instead (layout below).
  2. CHECK     every draft is checked against the SOP-Writer rubric
               (templates/role-library/_sop-writer.md, SOP 9.3 self-QC gate).
               Hard rejects: personal data, boilerplate, a token the library cannot fill, under
               the 7KB substance floor, broken integrity, unknown department.
               The rest get a weighted 0-10 score; below 8.5 is rejected.
               There is no flag to lower the bar.
  3. DE-DUPLICATE  same role from several boxes -> keep the higher score.
               A role that already exists in the library is never replaced.
  4. STAGE     with --stage: new branch, one new file per surviving role, one
               index entry per role, the library's own consistency checks, one
               commit. Without --stage nothing in the repo is touched.

SAFETY
  * Read-only on every box (BatchMode, no ControlMaster, no known_hosts write).
  * Reports name only the CLASS of a personal-data hit and its line number,
    never the matched text.
  * Fail closed: no client-name roster found -> refuses to stage unless
    --allow-no-roster (structural scans still run either way).
  * A box that could not be read is UNDETERMINED, never "empty". "No harvest
    folder" is only reported after the box answered a marker line.
  * If zero boxes answered, the run fails: the instrument is suspect.
  * Version file and changelog are NOT touched; the release train owns those.

--from-dir LAYOUT
  DIR/<box-label>/<department>/<role>.<sha8>.draft.md
  DIR/<box-label>/<department>/<role>.<sha8>.sop-needed.json

EXIT CODES
  0 ran (including "nothing to harvest")   2 tooling failure / zero boxes answered
  3 refused (dirty repo, no rubric, no roster, bad base)   5 library checks failed
"""
import argparse
import base64
import binascii
import concurrent.futures as futures
import hashlib
import importlib.util
import io
import json
import os
import re
import shlex
import subprocess
import sys
import tarfile
from datetime import datetime, timezone
from pathlib import Path

REPO_DEFAULT = Path(__file__).resolve().parents[2]
LIB_REL = Path("23-ai-workforce-blueprint") / "templates" / "role-library"
SCRIPTS_REL = Path("23-ai-workforce-blueprint") / "scripts"
HARVEST_SCHEMA = "sop-needed-harvest/1"
FLEET_ACCESS = Path.home() / ".claude" / "tools" / "fleet-access.sh"

# --- rubric constants: mirrored from _sop-writer.md SOP 9.3 (a unit test fails if they drift) ---
MIN_SUBSTANCE_BYTES = 7000      # SOP 9.3 step 1: "< 7000 bytes ... it fails"
PASS_SCORE = 8.5                # SOP 9.3 step 6: "If < 8.5 -> surgical fix"
SECTION_COUNT = 18              # SOP 9.3 step 2: "all 18 sections"
SOP_FIELDS = (("when", r"when(?: to run)?"), ("frequency", r"frequency"), ("inputs", r"inputs?"),
              ("steps", r"steps?"), ("outputs", r"outputs?"), ("hand to", r"hand[- ]?to"),
              ("failure mode", r"failure[- ]mode"))
# Same markers author-missing-sops.py rejects (a unit test checks this set is a subset of it).
BOILERPLATE_MARKERS = (
    "[Step 1 - to be personalized]", "[Step 1 — to be personalized", "to be personalized based on research",
    "PENDING - FILL FROM LIBRARY", "how-to.md (stub)", "TODO: fill", "[TBD]", "lorem ipsum",
)
WEIGHTS = {"sections": 2.0, "sop_shape": 2.0, "executability": 1.5, "api_citation": 1.0, "substance": 3.0}

SLUG = r"[a-z0-9][a-z0-9-]{0,80}"
NAME_RE = re.compile(rf"^(?:\./)?({SLUG})/({SLUG})\.([0-9a-f]{{8}})\.(draft\.md|sop-needed\.json)$")
MAX_FILE_BYTES = 256 * 1024
MAX_TAR_BYTES = 32 * 1024 * 1024


def log(msg):
    sys.stderr.write(msg + "\n")


def slugify(text):
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", str(text).lower())).strip("-")


# ------------------------------------------------------------------ personal-data scan --
_PRIVATE_HOST = re.compile(r"(?i)^.*\.(local|internal|lan|trycloudflare\.com|ngrok(?:-free)?\.(?:io|app)|"
                           r"zerohumanworkforce\.com)$")
# Documentation placeholders that are NOT personal data (kept narrow on purpose).
_PLACEHOLDER_MAIL = r"(?:example\.(?:com|org|net)|company\.com|test\.com|domain\.com|yourcompany\.com|yourdomain\.com|email\.com)"
PII_PATTERNS = (
    ("email", re.compile(r"[A-Za-z0-9._%+-]+@(?!" + _PLACEHOLDER_MAIL + r"\b)(?!\{\{)[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")),
    ("phone", re.compile(r"(?<![\d.])(?!555[\s.-]555[\s.-]5555)(?!\(?555\)?[\s.-]01\d\d)(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}(?!\d)")),
    ("long-id", re.compile(r"(?<![\w.$,/-])-?\d{9,15}(?![\w.]*\d)")),
    ("ip-address", re.compile(r"(?<![\d.])(?!(?:127\.|0\.0\.0\.0|192\.0\.2\.|198\.51\.100\.|203\.0\.113\.|169\.254\.169\.254|8\.8\.[48]\.[48]|1\.1\.1\.1))"
                              r"(?:\d{1,3}\.){3}\d{1,3}(?![\d.]*\d)")),
    ("home-path", re.compile(r"(?<![\w.-])(?:/Users|/home)/(?![{<$])[A-Za-z0-9._-]+")),
    ("secret", re.compile(r"\b(?:sk-[A-Za-z0-9_-]{16,}|ghp_[A-Za-z0-9]{20,}|xox[abp]-[A-Za-z0-9-]{10,}|AKIA[0-9A-Z]{16}|"
                          r"AIza[0-9A-Za-z_-]{30,}|eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,})")),
    ("secret-assignment", re.compile(r"(?i)\b(?:api[_-]?key|token|secret|password)\b\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{20,}")),
)
URL_RE = re.compile(r"https?://([^\s/:@)>\]\"'`]+)")


def load_roster(path=None):
    """Client-name patterns (extended regex per line). Returns (patterns, source) or (None, reason)."""
    cands = [path] if path else [os.environ.get("OPENCLAW_CLIENT_ROSTER"), str(Path.home() / ".openclaw" / "client-roster.txt")]
    for c in [x for x in cands if x]:
        p = Path(c).expanduser()
        if not p.is_file():
            continue
        pats = []
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                pats.append(re.compile(line, re.IGNORECASE))
            except re.error:
                pats.append(re.compile(re.escape(line), re.IGNORECASE))
        if pats:
            return pats, "roster file (%d patterns)" % len(pats)
    return None, "no roster file found"


def scan_personal_data(text, roster):
    """-> list of (class, line_number). Never returns matched text."""
    hits = []
    for n, line in enumerate(text.splitlines(), 1):
        for cls, rx in PII_PATTERNS:
            if rx.search(line):
                hits.append((cls, n))
        for m in URL_RE.finditer(line):
            if _PRIVATE_HOST.match(m.group(1).lower()):
                hits.append(("private-url", n))
        for rx in roster or ():
            if rx.search(line):
                hits.append(("roster-name", n))
    return hits


# --------------------------------------------------------------------------- rubric score --
def _blocks(text):
    parts = re.split(r"(?m)^(?=#{2,3}\s)", text)
    return [p for p in parts if re.match(r"###\s*SOP\s+9\.", p)]


def score_draft(text):
    """Weighted rubric score (0-10) and per-category parts. Heuristics; thresholds come from the rubric."""
    raw = text.encode("utf-8")
    real = sum(len(l.encode("utf-8")) for l in text.splitlines() if l.strip())
    parts = {"substance": min(10.0, 10.0 * real / MIN_SUBSTANCE_BYTES)}

    present = {int(n) for n in re.findall(r"(?m)^##\s+(\d{1,2})\.\s+\S", text) if 1 <= int(n) <= SECTION_COUNT}
    parts["sections"] = 10.0 * len(present) / SECTION_COUNT

    blocks = _blocks(text)
    if blocks:
        per = []
        for b in blocks:
            got = sum(1 for _, rx in SOP_FIELDS if re.search(r"\*\*\s*%s\s*:?\s*\*\*" % rx, b, re.I))
            per.append(got / len(SOP_FIELDS))
        parts["sop_shape"] = 10.0 * sum(per) / len(per)
    else:
        parts["sop_shape"] = 0.0

    steps = re.findall(r"(?m)^\s*\d+\.\s+(.*\S)", "\n".join(blocks) if blocks else text)
    anchor = re.compile(r"`[^`]+`|https?://|\b[\w-]+\.(?:md|json|py|sh|sqlite|ya?ml|csv)\b|(?:~|\.)?/[\w.-]+/[\w./-]+|"
                        r"\{\{[A-Z_]+\}\}|\bSOP\s+\d+\.\d+|\b(?:MEMORY|TOOLS|AGENTS|USER|SOUL)\b")
    if len(steps) >= 5:
        ratio = sum(1 for s in steps if anchor.search(s)) / len(steps)
        parts["executability"] = min(10.0, 10.0 * ratio / 0.3)  # ponytail: >=30% concrete steps = full marks (shipped library median is ~20%)
    else:
        parts["executability"] = 0.0

    lines = text.splitlines()
    calls = [i for i, l in enumerate(lines) if re.search(r"\b(?:GET|POST|PUT|PATCH|DELETE)\s+https?://|\bcurl\s", l)]
    if calls:
        ok = 0
        for i in calls:
            win = "\n".join(lines[max(0, i - 6):i + 7])
            cited = re.search(r"(?i)source:.*https?://", win) and re.search(r"\d{4}-\d{2}-\d{2}", win)
            if cited or "[API CONTRACT UNVERIFIED]" in win:
                ok += 1
        parts["api_citation"] = 10.0 * ok / len(calls)
    else:
        parts["api_citation"] = 10.0
    total = sum(parts[k] * w for k, w in WEIGHTS.items()) / sum(WEIGHTS.values())
    return round(total, 2), {k: round(v, 2) for k, v in parts.items()}, len(raw), real


# ---------------------------------------------------------------------------- library --
def _load_mod(path, name):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Library:
    def __init__(self, repo):
        self.repo = Path(repo)
        self.dir = self.repo / LIB_REL
        rubric = self.dir / "_sop-writer.md"
        if not rubric.is_file():
            raise FileNotFoundError("rubric not found: %s" % rubric)
        self.rubric_sha = "sha256:" + hashlib.sha256(rubric.read_bytes()).hexdigest()
        self.index = json.loads((self.dir / "_index.json").read_text(encoding="utf-8"))
        self.slugs = {r.get("slug") for r in self.index.get("roles", [])}
        self.depts = set(self.index.get("departments", {}))
        for extra in (self.repo / SCRIPTS_REL, self.repo / "shared-utils"):
            if str(extra) not in sys.path:
                sys.path.insert(0, str(extra))
        hs = self.repo / SCRIPTS_REL / "hash-content-manifest.py"
        if not hs.is_file():
            raise FileNotFoundError("hash-content-manifest.py not found: %s" % hs)
        self.hcm = _load_mod(hs, "_hcm_harvest")


def evaluate(item, lib, roster):
    """One draft -> verdict dict. Collects EVERY reason, not just the first."""
    reasons = []
    res = {"box": item["box"], "dept": item["dept"], "role_slug": item["role_slug"], "sha8": item["sha8"],
           "verdict": "REJECT", "reasons": reasons, "score": None, "parts": {}, "bytes": 0}
    try:
        text = item["draft"].decode("utf-8")
    except (UnicodeDecodeError, AttributeError):
        reasons.append("not-utf8-or-missing-draft")
        return res
    res["bytes"] = len(item["draft"])
    side = None
    try:
        side = json.loads(item["sidecar"].decode("utf-8")) if item.get("sidecar") else None
    except (UnicodeDecodeError, ValueError):
        pass
    if not isinstance(side, dict) or side.get("schema") != HARVEST_SCHEMA:
        reasons.append("missing-or-bad-record")
        side = {}
    sha = hashlib.sha256(item["draft"]).hexdigest()
    if side and (side.get("content_sha") != "sha256:" + sha or sha[:8] != item["sha8"]
                 or side.get("role_slug") != item["role_slug"] or side.get("department") != item["dept"]):
        reasons.append("integrity-mismatch")
    title = side.get("role") if isinstance(side.get("role"), str) else ""
    res["title"] = title.strip() or item["role_slug"].replace("-", " ").title()
    if len(res["title"]) > 120 or "{{" in res["title"]:
        reasons.append("bad-title")
    if item["dept"] not in lib.depts:
        reasons.append("unknown-department")
    for cls in sorted({c for c, _ in scan_personal_data(text + "\n" + title, roster)}):
        reasons.append("personal-data:" + cls)
    low = text.lower()
    if any(m.lower() in low for m in BOILERPLATE_MARKERS):
        reasons.append("boilerplate")
    rendered = lib.hcm.render_sha_of_text(text, res["title"], item["dept"].replace("-", " ").title(), False)
    if not isinstance(rendered, tuple):
        reasons.append("render-check-unavailable")  # fail closed: cannot prove the template renders cleanly
    elif lib.hcm._canonical_leaks(rendered[1]):
        reasons.append("unknown-token:%d" % len(lib.hcm._canonical_leaks(rendered[1])))
    score, parts, size, real = score_draft(text)
    res.update(score=score, parts=parts)
    if real < MIN_SUBSTANCE_BYTES:
        reasons.append("below-substance-floor:%dB<%dB" % (real, MIN_SUBSTANCE_BYTES))
    if score < PASS_SCORE:
        reasons.append("below-rubric:%.2f<%.1f" % (score, PASS_SCORE))
    if not reasons:
        res["verdict"] = "PASS"
    res["_text"] = text
    return res


def pick_winners(results, lib):
    """Identical content -> one; same role -> higher score; existing library role -> never replaced."""
    passing = [r for r in results if r["verdict"] == "PASS"]
    by_role, dup_note = {}, {}
    for r in sorted(passing, key=lambda r: (-r["score"], -r["bytes"], r["sha8"])):
        key = r["role_slug"]
        if key in lib.slugs:
            r["verdict"], r["reasons"] = "SKIP", ["already-in-library"]
        elif key in by_role:
            same = by_role[key]["sha8"] == r["sha8"]
            r["verdict"], r["reasons"] = "SKIP", ["duplicate-content" if same else "lower-scoring-duplicate"]
            dup_note[key] = dup_note.get(key, 1) + 1
        else:
            by_role[key] = r
    for k, n in dup_note.items():
        by_role[k]["seen_on_boxes"] = n
    return list(by_role.values())


# -------------------------------------------------------------------------- collection --
def parse_tar(blob, box):
    """Bytes of a tar -> (items, ignored_count). Only exact-name regular files are read."""
    files, ignored = {}, 0
    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:") as tf:
        for m in tf:
            nm = NAME_RE.match(m.name)
            if not m.isfile() or not nm or m.size > MAX_FILE_BYTES:
                ignored += 1
                continue
            dept, role, sha8, kind = nm.groups()
            files[(dept, role, sha8, kind)] = tf.extractfile(m).read()
    return _pair(box, files), ignored


def _pair(box, files):
    items = {}
    for (dept, role, sha8, kind), data in files.items():
        it = items.setdefault((dept, role, sha8), {"box": box, "dept": dept, "role_slug": role, "sha8": sha8})
        it["draft" if kind == "draft.md" else "sidecar"] = data
    return [v for v in items.values() if "draft" in v or "sidecar" in v]


def collect_dir(root):
    boxes, items = [], []
    for bd in sorted(p for p in Path(root).iterdir() if p.is_dir()):
        files = {}
        for f in bd.rglob("*"):
            nm = NAME_RE.match(f.relative_to(bd).as_posix()) if f.is_file() else None
            if nm and f.stat().st_size <= MAX_FILE_BYTES:
                files[nm.groups()] = f.read_bytes()
        got = _pair(bd.name, files)
        items += got
        boxes.append({"box": bd.name, "status": "COLLECTED" if got else "NO_DRAFTS_IN_DIR", "drafts": len(got)})
    return boxes, items


REMOTE_SCRIPT = ('for r in "$HOME/.openclaw" /data/.openclaw; do d="$r/workforce/sop-harvest"; '
                 'if [ -d "$d" ]; then echo __SOPH_DIR__; tar -C "$d" -cf - . 2>/dev/null | base64 | tr -d "\\n"; echo; '
                 'echo __SOPH_END__; exit 0; fi; done; echo __SOPH_NODIR__')


def fleet_boxes(fleet_access, only):
    """Run the fleet-access tool (--all --json). Returns (boxes, warnings) or raises RuntimeError."""
    p = subprocess.run([str(fleet_access), "--all", "--json"], capture_output=True, text=True, timeout=900)
    out = p.stdout
    start = out.find("\n{")
    start = 0 if out.startswith("{") else (start + 1 if start >= 0 else -1)
    if p.returncode not in (0, 2) or start < 0:
        raise RuntimeError("fleet-access failed rc=%d (no usable JSON)" % p.returncode)
    try:
        data, _ = json.JSONDecoder().raw_decode(out[start:])
    except ValueError as e:
        raise RuntimeError("fleet-access JSON unreadable: %s" % e)
    warn = []
    if p.returncode == 2:
        warn.append("fleet-access class control flagged a suspect class; unreachable boxes below are UNDETERMINED, not down")
    boxes = data.get("boxes", [])
    if only:
        boxes = [b for b in boxes if any(f.lower() in b.get("slug", "").lower() for f in only)]
    return boxes, warn


def pick_route(box):
    """First REACHABLE path we can SSH without knowing a redacted address."""
    for path in box.get("paths", []):
        if path.get("verdict") != "REACHABLE":
            continue
        r = path.get("route", "")
        if r.startswith("alias:"):
            return {"host": r[6:], "container": None}
        m = re.match(r"^docker:([\w.-]+)@([\w.-]+)$", r)
        if m and "redacted" not in r:
            return {"host": m.group(2), "container": m.group(1)}
    return None


def ssh_collect(box, ssh_bin, timeout):
    """One read-only SSH call, isolated: any failure on one box is that box's UNDETERMINED, never the batch's."""
    try:
        return _ssh_collect(box, ssh_bin, timeout)
    except Exception as e:  # noqa: BLE001 - per-box isolation
        return {"box": box.get("slug", "?"), "platform": box.get("platform", "?"), "status": "UNDETERMINED",
                "detail": "unexpected %s while collecting" % type(e).__name__}, []


def _ssh_collect(box, ssh_bin, timeout):
    slug = box["slug"]
    route = pick_route(box)
    st = {"box": slug, "platform": box.get("platform", "?")}
    if route is None:
        st.update(status="NOT_COLLECTED", detail="no usable route (REACHABLE alias or docker-on-alias path); "
                  "address is redacted by fleet-access, use --from-dir. UNDETERMINED, not empty")
        return st, []
    inner = REMOTE_SCRIPT
    if route["container"]:
        inner = "docker exec %s sh -c %s" % (shlex.quote(route["container"]), shlex.quote(REMOTE_SCRIPT))
    cmd = [ssh_bin, "-n", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", "-o", "ControlMaster=no",
           "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null", "-o", "LogLevel=ERROR",
           route["host"], "bash -lc " + shlex.quote(inner)]
    try:
        p = subprocess.run(cmd, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        st.update(status="UNDETERMINED", detail="ssh timed out after %ds" % timeout)
        return st, []
    except OSError as e:
        st.update(status="TOOLING_FAILURE", detail="cannot run ssh: %s" % type(e).__name__)
        return st, []
    out = p.stdout[:MAX_TAR_BYTES * 2].decode("utf-8", "replace")
    if "__SOPH_NODIR__" in out:
        st.update(status="NO_HARVEST_DIR", detail="box answered; no sop-harvest folder under ~/.openclaw or /data/.openclaw")
        return st, []
    m = re.search(r"__SOPH_DIR__\s*([A-Za-z0-9+/=\s]*?)\s*__SOPH_END__", out)
    if not m:
        st.update(status="UNDETERMINED", detail="ssh rc=%d, no marker in output (connection or shell failed)" % p.returncode)
        return st, []
    try:
        items, ignored = parse_tar(base64.b64decode(re.sub(r"\s", "", m.group(1))), slug)
    except (binascii.Error, tarfile.TarError, OSError) as e:
        st.update(status="UNDETERMINED", detail="could not parse the folder archive: %s" % type(e).__name__)
        return st, []
    st.update(status="COLLECTED", drafts=len(items), ignored_files=ignored, detail="read-only collect ok")
    return st, items


# ------------------------------------------------------------------------------ staging --
def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)


def role_type_of(slug, text):
    m = re.search(r"(?mi)^\*\*Role[ _]?type:\*\*\s*(.+?)\s*$", text)
    rt = (m.group(1).strip().lower() if m else "")
    if rt in ("director", "manager", "coordinator", "specialist"):
        return rt
    if slug.startswith(("director-", "head-of-")) or "chief-" in slug:
        return "director"
    return "manager" if "manager" in slug else "coordinator" if "coordinator" in slug else "specialist"


def stage(repo, lib, winners, branch, base, now):
    """Branch + files + index + library checks + one commit. Returns (code, info dict)."""
    repo = Path(repo)
    if git(repo, "status", "--porcelain").stdout.strip():
        return 3, {"error": "repo has uncommitted changes; use a clean checkout"}
    if git(repo, "rev-parse", "--verify", "--quiet", base).returncode != 0:
        return 3, {"error": "base ref not found: %s" % base}
    if git(repo, "rev-parse", "--verify", "--quiet", "refs/heads/" + branch).returncode == 0:
        return 3, {"error": "branch already exists: %s" % branch}
    hcm = lib.hcm
    trc = None
    tp = repo / SCRIPTS_REL / "tag_role_classes.py"
    if tp.is_file():
        try:
            trc = _load_mod(tp, "_trc_harvest")
            if not getattr(trc, "_SELECTOR_AVAILABLE", False):
                trc = None
        except Exception:  # noqa: BLE001 - class tag is optional metadata
            trc = None
    r = git(repo, "switch", "-c", branch, base)
    if r.returncode != 0:
        return 3, {"error": "git switch failed: " + r.stderr.strip()[:200]}
    index_path = repo / LIB_REL / "_index.json"
    raw_index = index_path.read_text(encoding="utf-8")
    index = json.loads(raw_index)
    iso = now.isoformat()
    written, touched = [], set()
    for w in winners:
        rel = "templates/role-library/%s/%s/how-to.md" % (w["dept"], w["role_slug"])
        dest = repo / "23-ai-workforce-blueprint" / rel
        if dest.exists() or (dest.parent.parent / (w["role_slug"] + ".md")).exists():  # folder or flat form
            w["verdict"], w["reasons"] = "SKIP", ["already-in-library"]
            continue
        text = w["_text"].rstrip("\n") + "\n"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8")
        rs = hcm.render_sha_of_text(text, w["title"], w["dept"].replace("-", " ").title(), False)
        rt = role_type_of(w["role_slug"], text)
        entry = {"slug": w["role_slug"], "dept": w["dept"], "title": w["title"], "role_type": rt,
                 "word_count": len(text.split()), "sop_count": hcm.count_embedded_sop_headings(text),
                 "sop_min": hcm.EMBEDDED_SOP_FLOOR, "path": rel}
        if trc is not None:
            ci = trc.infer_class(w["role_slug"], w["dept"], rt)
            entry.update(capability_class=ci["capability_class"], vision_flag=ci["vision_flag"])
        entry.update(content_sha=hcm.content_sha_of_text(text), render_sha=rs[0] if isinstance(rs, tuple) else rs,
                     content_version="1.0.0", content_hashed_at=iso)
        index.setdefault("roles", []).append(entry)
        d = index.setdefault("departments", {}).setdefault(w["dept"], {"count": 0, "roles": []})
        d.setdefault("roles", []).append(w["role_slug"])
        touched.add(w["dept"])
        written.append((rel, w))
    shas = {(r["dept"], r["slug"]): r.get("content_sha", "sha256:MISSING") for r in index["roles"]}
    for dn in touched:  # dept roll-up, same recipe as hash-content-manifest.py
        d = index["departments"][dn]
        d["roles"] = sorted(set(d["roles"]))
        d["count"] = len(d["roles"])
        payload = "\n".join("%s\t%s" % (m, shas.get((dn, m), "sha256:MISSING")) for m in d["roles"]).encode("utf-8")
        d["content_sha"] = "sha256:" + hashlib.sha256(payload).hexdigest()
        d["content_hashed_at"] = iso
    index["total_roles"] = len(index["roles"])
    index["total_departments"] = len(index["departments"])
    # keep the file's existing escaping style so the diff shows only the added roles
    index_path.write_text(json.dumps(index, indent=2, ensure_ascii=raw_index.isascii()) + "\n", encoding="utf-8")
    checks = []
    for script in ("register-library-additions.py", "hash-content-manifest.py"):
        sp = repo / SCRIPTS_REL / script
        if not sp.is_file():
            checks.append({"check": script, "status": "not-available"})
            continue
        p = subprocess.run([sys.executable, str(sp), "--check"], capture_output=True, text=True, timeout=600)
        checks.append({"check": script, "rc": p.returncode, "tail": (p.stdout.strip().splitlines() or [""])[-1][:200]})
    info = {"branch": branch, "base": base, "staged_roles": [w["role_slug"] for _, w in written], "checks": checks}
    if any(c.get("rc", 0) != 0 for c in checks):
        info["error"] = "library checks failed; changes left UNCOMMITTED on the branch for inspection"
        return 5, info
    if not written:
        info["note"] = "nothing to commit"
        return 0, info
    paths = ["23-ai-workforce-blueprint/" + rel for rel, _ in written] + [str(LIB_REL / "_index.json")]
    git(repo, "add", "--", *paths)
    msg = "feat(role-library): propose %d harvested role template(s) for review\n\nStaged by harvest-sop-drafts.py. Human review required before merge." % len(written)
    c = git(repo, "commit", "-q", "-m", msg)
    if c.returncode != 0:
        info["error"] = "git commit failed: " + c.stderr.strip()[:200]
        return 5, info
    info["commit"] = git(repo, "rev-parse", "HEAD").stdout.strip()
    return 0, info


# ------------------------------------------------------------------------------- report --
def write_report(out_dir, summary, box_status, results, winners, stage_info):
    out_dir.mkdir(parents=True, exist_ok=True)
    clean = [{k: v for k, v in r.items() if not k.startswith("_")} for r in results]
    (out_dir / "report.json").write_text(json.dumps(
        {"summary": summary, "boxes": box_status, "drafts": clean, "stage": stage_info}, indent=2) + "\n", encoding="utf-8")
    lines = ["# SOP draft harvest", "", "Generated: %s" % summary["generated_at"], "",
             "- Boxes asked: %d. Answered: %d. Not readable (UNDETERMINED): %d." % (
                 summary["boxes_total"], summary["boxes_answered"], summary["boxes_undetermined"]),
             "- Drafts found: %d. Passed the rubric: %d. Rejected: %d. Skipped: %d." % (
                 summary["drafts_found"], summary["passed"], summary["rejected"], summary["skipped"]),
             "- Roles proposed for the library: %d." % len(winners),
             "- Name scan: %s." % summary["name_scan"], "- Rubric: %s" % summary["rubric_sha"], ""]
    if summary.get("warnings"):
        lines += ["## Warnings"] + ["- " + w for w in summary["warnings"]] + [""]
    lines += ["## Boxes"] + ["- %s: %s%s" % (b["box"], b["status"], " (%s)" % b["detail"] if b.get("detail") else "") for b in box_status]
    lines += ["", "## Proposed roles (score, bytes)"] + ["- %s / %s: %.2f, %d bytes" % (w["dept"], w["role_slug"], w["score"], w["bytes"]) for w in winners]
    lines += ["", "## Rejected or skipped (reason classes only)"]
    lines += ["- %s / %s [%s]: %s" % (r["dept"], r["role_slug"], r["box"], ", ".join(r["reasons"])) for r in results if r["verdict"] != "PASS"]
    if stage_info:
        lines += ["", "## Branch", "- %s" % json.dumps({k: v for k, v in stage_info.items() if k != "checks"}),
                  "- Library checks: %s" % json.dumps(stage_info.get("checks", [])),
                  "", "Next, by hand: review the diff, `git push -u origin %s`, open the pull request. This tool never does."
                  % stage_info.get("branch", "<branch>")]
    (out_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Collect, check, de-duplicate and stage fleet SOP drafts (read-only on boxes).")
    ap.add_argument("--repo", default=str(REPO_DEFAULT), help="onboarding checkout (library + staging target)")
    ap.add_argument("--from-dir", help="read DIR/<box>/<dept>/<files> instead of the fleet")
    ap.add_argument("--box", action="append", default=[], help="only boxes whose slug contains this (repeatable)")
    ap.add_argument("--fleet-access", default=str(FLEET_ACCESS))
    ap.add_argument("--ssh", default="/usr/bin/ssh")
    ap.add_argument("--ssh-timeout", type=int, default=60)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--out-dir", help="report folder (default ~/Downloads/sop-harvest-<UTC stamp>)")
    ap.add_argument("--roster", help="client-name roster file (default $OPENCLAW_CLIENT_ROSTER or ~/.openclaw/client-roster.txt)")
    ap.add_argument("--allow-no-roster", action="store_true", help="stage even without a roster (structural scans still run)")
    ap.add_argument("--stage", action="store_true", help="create the branch + commit in --repo (default: report only)")
    ap.add_argument("--branch", help="staging branch (default sop-harvest-<UTC date>)")
    ap.add_argument("--base", default="origin/main", help="ref the branch starts from")
    a = ap.parse_args(argv)

    now = datetime.now(timezone.utc)
    out_dir = Path(a.out_dir).expanduser() if a.out_dir else Path.home() / "Downloads" / now.strftime("sop-harvest-%Y%m%dT%H%M%SZ")
    try:
        lib = Library(a.repo)
    except (OSError, ValueError) as e:
        log("REFUSED: %s" % e)
        return 3
    roster, name_scan = load_roster(a.roster)
    if roster is None and a.stage and not a.allow_no_roster:
        log("REFUSED: %s; client names cannot be scanned. Create the roster or pass --allow-no-roster." % name_scan)
        return 3
    warnings = [] if roster else ["name scan SKIPPED (%s); structural scans only. Human review must check for client names." % name_scan]

    if a.from_dir:
        box_status, items = collect_dir(a.from_dir)
        for b in box_status:
            b["detail"] = "read from --from-dir"
    else:
        try:
            boxes, w = fleet_boxes(a.fleet_access, a.box)
        except (RuntimeError, OSError, subprocess.TimeoutExpired) as e:
            log("TOOLING FAILURE: %s" % e)
            return 2
        warnings += w
        box_status, items = [], []
        with futures.ThreadPoolExecutor(max_workers=max(1, a.workers)) as ex:
            for st, its in ex.map(lambda b: ssh_collect(b, a.ssh, a.ssh_timeout), boxes):
                box_status.append(st)
                items += its
    answered = [b for b in box_status if b["status"] in ("COLLECTED", "NO_HARVEST_DIR", "NO_DRAFTS_IN_DIR")]
    if not answered:
        log("TOOLING FAILURE: zero boxes answered (%d asked). The instrument is suspect; no verdict is admissible." % len(box_status))
        write_report(out_dir, {"generated_at": now.isoformat(), "boxes_total": len(box_status), "boxes_answered": 0,
                               "boxes_undetermined": len(box_status), "drafts_found": 0, "passed": 0, "rejected": 0,
                               "skipped": 0, "name_scan": name_scan, "rubric_sha": lib.rubric_sha, "warnings": warnings},
                     box_status, [], [], None)
        return 2

    results = [evaluate(it, lib, roster) for it in items]
    winners = pick_winners(results, lib)
    stage_info = None
    code = 0
    if a.stage and not winners:
        stage_info = {"note": "nothing to stage; no branch was created"}
    elif a.stage:
        branch = a.branch or now.strftime("sop-harvest-%Y%m%d")
        code, stage_info = stage(a.repo, lib, winners, branch, a.base, now)
        if "error" in stage_info:
            log("STAGE: %s" % stage_info["error"])
    summary = {"generated_at": now.isoformat(), "boxes_total": len(box_status), "boxes_answered": len(answered),
               "boxes_undetermined": len(box_status) - len(answered), "drafts_found": len(results),
               "passed": len(winners), "rejected": sum(r["verdict"] == "REJECT" for r in results),
               "skipped": sum(r["verdict"] == "SKIP" for r in results), "name_scan": name_scan,
               "rubric_sha": lib.rubric_sha, "warnings": warnings}
    write_report(out_dir, summary, box_status, results, winners, stage_info)
    print("report: %s" % (out_dir / "report.md"))
    print("boxes answered %d/%d | drafts %d | proposed %d | rejected %d | skipped %d" % (
        len(answered), len(box_status), len(results), len(winners), summary["rejected"], summary["skipped"]))
    return code


if __name__ == "__main__":
    sys.exit(main())
