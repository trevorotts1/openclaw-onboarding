#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""front_door.py - the ONE front door for Skill 49 dispatch, shared by the shell entry and Skill 83.

signature-funnel-entry.sh and 83's routes/substrate.py (every load of a Skill 49 script) both call this
module, so the version, hash-pin and bypass-scan gates run on every path that can build a page. A tripped
gate raises FrontDoorError, a SystemExit subclass: it is not swallowed by `except Exception` and the
process ends non-zero with `ABORT [HASH-PIN|BYPASS-SCAN|VERSION|PIN-ROTATION]: ...` on stderr.

PIN. The digest covers every file the dispatch/launch path executes or reads for decisions (see
`pin_files`): all non-test Skill 49 scripts and data, the Skill 83 launcher tree, the shared launch contract
and the shared launch package. The list is GENERATED from the tree, so a new file changes the digest and
trips HASH-PIN until the pin is re-minted.

MINTING. Only two paths write scripts/SF-PROVER-PIN.sha256:
  * GitHub Actions (.github/workflows/sf-prover-pin-authority.yml) through `mint-pin --ci`; and
  * `write-pin --rotation-record FILE`, which refuses unless FILE is a `pin_rotation` approval signed with
    the operator-held key (SF_PIN_AUTHORITY_KEY_FILE, 0600, outside the checkout) for THIS tree's digest.
# ponytail: HMAC key + CI env check are the cheapest authority that works offline. A same-user AI session
# that can read the key or set GITHUB_* can still mint locally; the workflow recomputes the pin from the
# trusted base on every PR and tag, which is the check that cannot be talked around. Upgrade path:
# asymmetric signature (the verifier then holds no secret).

Usage: python3 front_door.py {check,hashpin,bypass-scan,pin-list,write-pin,mint-pin,sign-rotation} [...]
stdlib only.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import hmac
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

SKILL_DIR = Path(__file__).resolve().parents[1]
PIN_NAME = "SF-PROVER-PIN.sha256"
EXPECTED_MAJOR = "2"

# Pin set: (logical prefix, tree, [(subdir, glob)]). Test files are never pinned or scanned.
_PIN_SPEC = (
    ("49", "49", (("", "*.py"), ("", "signature-funnel-entry.sh"), ("", "FUNNEL-MANIFEST.json"),
                  ("scripts", "*.py"), ("scripts/vendor", "*.json"), ("structure", "*.json"),
                  ("schema", "*.json"), ("intake", "*.json"))),
    ("83", "83", (("launcher_core", "*.py"), ("launcher_core", "*.json"), ("routes", "*.py"),
                  ("", "entitlement-declaration.json"), ("", "receipt.schema.json"))),
    ("shared/contract", "contract", (("", "*.py"), ("", "*.json"))),
    ("shared/launch", "launch", (("", "*.py"), ("", "*.json"))),
)

# Hosts and senders a funnel must never hand-roll: GHL goes through Skill 6, mail through Skill 66/44,
# KIE through Skill 74 only.
BYPASS_PATTERNS = re.compile(
    r"services\.leadconnectorhq\.com|backend\.leadconnectorhq\.com|rest\.gohighlevel\.com|"
    r"api\.gohighlevel\.com|smtplib|sendgrid|mailgun|nodemailer|ses\.send_email|send_raw_email|"
    r"jobs/createtask|api\.kie\.ai|kie_generate\.py|kie_image\.py|api\.resend\.com|"
    r"postmarkapp\.com|api\.twilio\.com", re.IGNORECASE)
_RUN_DIR_EXTRA = re.compile(r"urllib\.request", re.IGNORECASE)

# Network-capable modules. Inside the skill tree only these files may import them (they are pinned);
# Skills 6 and 74 live outside this tree and are the approved adapters.
_NET_MODULES = ("urllib.request", "urllib3", "http.client", "http.server", "socket", "requests", "httpx",
                "aiohttp", "smtplib", "ftplib", "telnetlib", "imaplib", "poplib", "websocket", "websockets",
                "xmlrpc.client", "paramiko")
# The two Command Center clients (approval verification GET, launch-event POST) talk only to the client's own
# Command Center, never GHL, mail or KIE; both are pinned. Integration fix: U-enforcement-01's scan met
# U-approval-02 and U-cc-01 for the first time on integration/bfl-onboarding (see scratch/.../conflicts.md).
NET_ALLOWED = {"49/scripts/agnes_orchestrator.py", "49/scripts/mc_board.py",
               "shared/contract/approval_record.py", "shared/launch/launch_events.py"}
# Files that must name the denylisted strings (they define or check them).
STRING_ALLOWED = {"49/scripts/kie74_receipt.py", "49/scripts/front_door.py"}
_SKIP_DIRS = {"__pycache__", "fixtures", "tests", "examples", "working"}
_CURL = re.compile(r"^\s*(curl|wget)(\s|$)")

_scan_cache: Dict[Tuple[str, str], Tuple[str, ...]] = {}


class FrontDoorError(SystemExit):
    """A tripped gate. SystemExit on purpose: a fail-closed door must not be catchable by `except Exception`."""

    def __init__(self, gate: str, detail: str) -> None:
        super().__init__(f"ABORT [{gate}]: {detail}")
        self.gate, self.detail = gate, detail


# ---------------------------------------------------------------- layout

def _skill_dirs(skill_dir: Path) -> Dict[str, Path]:
    """Resolve the 49, 83, contract and launch trees beside skill_dir (onboarding or deployed layout)."""
    root = skill_dir.parent
    bases = [root, root / ".claude" / "skills", root / "skills"]

    def skill(slug: str) -> Optional[Path]:
        for base in bases:
            for p in (sorted(base.iterdir()) if base.is_dir() else []):
                if p.is_dir() and (p.name == slug or p.name.endswith("-" + slug)) and (p / "SKILL.md").is_file():
                    return p
        return None

    shared = next((b / "shared-utils" for b in bases if (b / "shared-utils").is_dir()), None)
    out = {"49": skill_dir, "83": skill("black-friday-launcher")}
    out["contract"] = shared / "signature_launch_contract" if shared else None
    out["launch"] = shared / "signature_launch" if shared else None
    for key, path in out.items():
        if path is None or not path.is_dir():
            raise FrontDoorError("HASH-PIN", f"pinned tree missing: {key} (looked beside {skill_dir})")
    return out


def _is_test(name: str) -> bool:
    return name.startswith("test_") or name.endswith("_test.py")


def pin_files(skill_dir: Path = SKILL_DIR) -> List[Tuple[str, Path]]:
    """Every pinned file as (logical name, path), sorted by name. Generated, never hand-listed."""
    trees = _skill_dirs(Path(skill_dir))
    found: Dict[str, Path] = {}
    for prefix, key, rules in _PIN_SPEC:
        for sub, pattern in rules:
            d = trees[key] / sub if sub else trees[key]
            for p in sorted(d.glob(pattern)) if d.is_dir() else []:
                if p.is_file() and not _is_test(p.name):
                    found[f"{prefix}/{p.relative_to(trees[key]).as_posix()}"] = p
    return sorted(found.items())


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compute_pin(skill_dir: Path = SKILL_DIR) -> str:
    lines = sorted(f"{_sha(p)}  {name}\n" for name, p in pin_files(skill_dir))
    return hashlib.sha256("".join(lines).encode()).hexdigest()


# ---------------------------------------------------------------- gates

def step_version(skill_dir: Path = SKILL_DIR) -> None:
    vf = Path(skill_dir) / "skill-version.txt"
    if not vf.is_file() or not vf.read_text(encoding="utf-8").strip():
        raise FrontDoorError("VERSION", "skill-version.txt missing/empty")
    v = "".join(vf.read_text(encoding="utf-8").split())
    if not re.fullmatch(rf"v?{EXPECTED_MAJOR}\.[0-9]+\.[0-9]+", v):
        raise FrontDoorError("VERSION", f"skill-version.txt is '{v}', expected major {EXPECTED_MAJOR}.x.y")
    md = Path(skill_dir) / "SKILL.md"
    if not md.is_file():
        return
    lines = md.read_text(encoding="utf-8").splitlines()
    fm = ""
    if lines and lines[0] == "---":
        for ln in lines[1:]:
            if ln == "---":
                break
            if ln.startswith("version:"):
                fm = "".join(ln[len("version:"):].split()).strip("\"'")
                break
    if not fm:
        raise FrontDoorError("VERSION", "SKILL.md has no top-level frontmatter version: field")
    if fm != v:
        raise FrontDoorError("VERSION", f"SKILL.md frontmatter version ({fm}) != skill-version.txt ({v}) - drift")


def step_hashpin(skill_dir: Path = SKILL_DIR, must_cover=()) -> str:
    """Compare the recomputed pin to the committed one. must_cover: 49-relative paths the generated list
    has to include (the shell's PINNED_FILES floor), so a glob change can never silently drop a core file."""
    skill_dir = Path(skill_dir)
    missing = sorted(set(f"49/{r}" for r in must_cover) - {n for n, _ in pin_files(skill_dir)})
    if missing:
        raise FrontDoorError("HASH-PIN", f"the generated pin list no longer covers: {', '.join(missing)}")
    pin_file = skill_dir / "scripts" / PIN_NAME
    now = compute_pin(skill_dir)
    if not pin_file.is_file():
        raise FrontDoorError("HASH-PIN", f"pin file missing: {pin_file} (CI mints it; see sf-prover-pin-authority)")
    pinned = "".join(pin_file.read_text(encoding="utf-8").split())
    if not hmac.compare_digest(now, pinned):
        raise FrontDoorError("HASH-PIN", "launch-path hash mismatch (a pinned prover, validator, wrapper, route, "
                             f"page type or launcher file was modified). expected={pinned} got={now}")
    return now


def _text_hits(rel: str, data: bytes) -> Tuple[str, ...]:
    """Findings for one skill-tree file: denylisted strings, and (python) network imports/calls."""
    key = (hashlib.sha256(data).hexdigest(), rel)
    if key in _scan_cache:
        return _scan_cache[key]
    text, hits = data.decode("utf-8", "replace"), []
    if rel not in STRING_ALLOWED and BYPASS_PATTERNS.search(text):
        hits.append(f"{rel}: names a hand-rolled GHL/mail/KIE endpoint or sender")
    tree = None
    if rel.endswith(".py"):
        try:
            tree = ast.parse(text)
        except (SyntaxError, ValueError) as exc:
            hits.append(f"{rel}: unparseable ({type(exc).__name__}); cannot prove it makes no network call")
    if tree is not None:
        for node in ast.walk(tree):
            mods: List[str] = []
            if isinstance(node, ast.Import):
                mods = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                mods = [node.module] + [f"{node.module}.{a.name}" for a in node.names]
            elif isinstance(node, ast.Call) and node.args and isinstance(node.args[0], ast.Constant) \
                    and isinstance(node.args[0].value, str):
                fn = node.func
                name = fn.id if isinstance(fn, ast.Name) else fn.attr if isinstance(fn, ast.Attribute) else ""
                if name in ("__import__", "import_module"):
                    mods = [node.args[0].value]
            if rel not in NET_ALLOWED and any(m == n or m.startswith(n + ".") for m in mods for n in _NET_MODULES):
                hits.append(f"{rel}:{getattr(node, 'lineno', 0)}: network module outside the Skill 6/74 adapters")
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and _CURL.match(node.value):
                hits.append(f"{rel}:{getattr(node, 'lineno', 0)}: shells out to curl/wget")
    _scan_cache[key] = tuple(hits)
    return _scan_cache[key]


def scan_tree(skill_dir: Path = SKILL_DIR) -> List[str]:
    """Bypass scan over the skill tree itself (49, 83, shared contract/launch): strings plus an AST network check."""
    trees = _skill_dirs(Path(skill_dir))
    prefixes = {"49": "49", "83": "83", "contract": "shared/contract", "launch": "shared/launch"}
    hits: List[str] = []
    for key, base in trees.items():
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = sorted(d for d in dirnames if d not in _SKIP_DIRS)
            for fn in sorted(filenames):
                p = Path(dirpath) / fn
                if p.suffix in (".py", ".sh", ".json") and not _is_test(fn) and not p.is_symlink():
                    hits += _text_hits(f"{prefixes[key]}/{p.relative_to(base).as_posix()}", p.read_bytes())
    return hits


def scan_run_dir(run_dir: Path, skill_dir: Path = SKILL_DIR) -> List[str]:
    """Files in a run dir that hand-roll GHL/mail/KIE. Only Skill 74's own receipts are allow-listed."""
    rd, hits = Path(run_dir).resolve(), []
    kie_dir = rd / "receipts" / "kie74"
    for dirpath, _dirs, filenames in os.walk(rd):
        for fn in sorted(filenames):
            p = Path(dirpath) / fn
            if p.is_symlink():
                continue
            data = p.read_bytes()
            if b"\0" in data[:8192]:
                continue
            text = data.decode("utf-8", "replace")
            if not (BYPASS_PATTERNS.search(text) or _RUN_DIR_EXTRA.search(text)):
                continue
            if p.parent == kie_dir and p.suffix == ".json" and subprocess.run(
                    [sys.executable, str(Path(skill_dir) / "scripts" / "kie74_receipt.py"), "--check", str(p)],
                    capture_output=True).returncode == 0:
                continue
            hits.append(str(p))
    return hits


def step_bypass_scan(run_dir: Optional[Path] = None, skill_dir: Path = SKILL_DIR) -> None:
    run_hits = scan_run_dir(run_dir, skill_dir) if run_dir and Path(run_dir).is_dir() else []
    if run_hits:
        print("BYPASS-SCAN hits:\n" + "\n".join(run_hits), file=sys.stderr)
        raise FrontDoorError("BYPASS-SCAN", "run working files hand-roll GHL REST / a mail sender / a raw Kie "
                             "createTask or a KIE client script. All GHL build+media go through Skill 6; all image "
                             "and video generation goes through Skill 66 (policy) then Skill 74 (transport). "
                             "Delete the hand-rolled path.")
    tree_hits = scan_tree(skill_dir)
    if tree_hits:
        print("BYPASS-SCAN hits:\n" + "\n".join(tree_hits), file=sys.stderr)
        raise FrontDoorError("BYPASS-SCAN", "the skill tree itself hand-rolls a network call or sender. Only the "
                             "Skill 6 / Skill 74 adapters may reach GHL, mail or KIE.")


def check(run_dir: Optional[Path] = None, skill_dir: Path = SKILL_DIR) -> str:
    """version + hash-pin + bypass-scan. Returns the verified pin; raises FrontDoorError on any trip."""
    step_version(skill_dir)
    pin = step_hashpin(skill_dir)
    step_bypass_scan(run_dir, skill_dir)
    return pin


# ---------------------------------------------------------------- pin authority

def _key_bytes(skill_dir: Path, key_file: Optional[str] = None) -> bytes:
    path = Path(key_file or os.environ.get("SF_PIN_AUTHORITY_KEY_FILE")
                or Path.home() / ".sf-pin-authority" / "key")
    if not path.is_file():
        raise FrontDoorError("PIN-ROTATION", "operator key file not found (set SF_PIN_AUTHORITY_KEY_FILE)")
    real = path.resolve()
    if real == Path(skill_dir).parent.resolve() or Path(skill_dir).parent.resolve() in real.parents:
        raise FrontDoorError("PIN-ROTATION", "operator key must live outside the checkout")
    if real.stat().st_mode & 0o077:
        raise FrontDoorError("PIN-ROTATION", "operator key file must be mode 0600")
    key = real.read_bytes().strip()
    if len(key) < 16:
        raise FrontDoorError("PIN-ROTATION", "operator key is too short")
    return key


def _sign(record: dict, key: bytes) -> str:
    body = {k: v for k, v in record.items() if k != "signature"}
    return hmac.new(key, json.dumps(body, sort_keys=True, separators=(",", ":")).encode(), hashlib.sha256).hexdigest()


def sign_rotation(approver: str, skill_dir: Path = SKILL_DIR, key_file: Optional[str] = None,
                  hours: int = 24) -> dict:
    """The operator's pin_rotation approval for THIS tree's digest (needs the operator key)."""
    now = datetime.now(timezone.utc)
    record = {"kind": "pin_rotation", "pin": compute_pin(skill_dir), "approver": approver,
              "issued_at": now.isoformat(), "expires_at": (now + timedelta(hours=hours)).isoformat()}
    record["signature"] = _sign(record, _key_bytes(skill_dir, key_file))
    return record


def verify_rotation(record_path: Optional[str], pin: str, skill_dir: Path = SKILL_DIR,
                    key_file: Optional[str] = None) -> dict:
    if not record_path:
        raise FrontDoorError("PIN-ROTATION", "--write-pin needs a signed pin_rotation approval record "
                             "(--rotation-record FILE); none was given. CI mints the pin on merge.")
    try:
        rec = json.loads(Path(record_path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise FrontDoorError("PIN-ROTATION", f"rotation record unreadable ({type(exc).__name__})") from exc
    if not isinstance(rec, dict) or rec.get("kind") != "pin_rotation":
        raise FrontDoorError("PIN-ROTATION", "record is not a pin_rotation approval")
    sig = rec.get("signature")
    if not isinstance(sig, str) or not hmac.compare_digest(sig, _sign(rec, _key_bytes(skill_dir, key_file))):
        raise FrontDoorError("PIN-ROTATION", "rotation record signature does not verify against the operator key")
    if rec.get("pin") != pin:
        raise FrontDoorError("PIN-ROTATION", "rotation record approves a different pin than this tree computes")
    if not isinstance(rec.get("approver"), str) or not rec["approver"].strip():
        raise FrontDoorError("PIN-ROTATION", "rotation record names no approver")
    try:
        issued, expires = (datetime.fromisoformat(rec[k]) for k in ("issued_at", "expires_at"))
        now = datetime.now(timezone.utc)
        ok = issued <= now + timedelta(minutes=1) and now < expires
    except (KeyError, TypeError, ValueError):
        ok = False
    if not ok:
        raise FrontDoorError("PIN-ROTATION", "rotation record is expired or not yet valid")
    return rec


def _write_pin_file(skill_dir: Path, pin: str) -> Path:
    target = Path(skill_dir) / "scripts" / PIN_NAME
    fd, tmp = tempfile.mkstemp(dir=str(target.parent), prefix=".pin-")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(pin + "\n")
    os.replace(tmp, target)
    return target


def write_pin(skill_dir: Path = SKILL_DIR, record_path: Optional[str] = None, key_file: Optional[str] = None) -> str:
    """Local re-mint: refuses (pin file untouched) unless a verified pin_rotation approval covers the new digest."""
    pin = compute_pin(skill_dir)
    verify_rotation(record_path, pin, skill_dir, key_file)
    _write_pin_file(skill_dir, pin)
    return pin


def mint_pin_ci(skill_dir: Path = SKILL_DIR, env=None) -> str:
    """The workflow's mint. Refuses outside GitHub Actions on a push or manual dispatch."""
    env = os.environ if env is None else env
    if env.get("GITHUB_ACTIONS") != "true" or env.get("GITHUB_EVENT_NAME") not in ("push", "workflow_dispatch") \
            or not env.get("GITHUB_REPOSITORY") or not env.get("GITHUB_RUN_ID"):
        raise FrontDoorError("PIN-ROTATION", "mint-pin --ci runs only inside the sf-prover-pin-authority workflow")
    pin = compute_pin(skill_dir)
    _write_pin_file(skill_dir, pin)
    return pin


# ---------------------------------------------------------------- command line

def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="front_door.py", description=__doc__.split("\n\n")[0])
    ap.add_argument("--skill-dir", default=str(SKILL_DIR), help="the Skill 49 directory to check (default: this one)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("check", "bypass-scan"):
        sub.add_parser(name).add_argument("--run-dir")
    sub.add_parser("pin-list")
    sub.add_parser("hashpin").add_argument("--must-cover", nargs="*", default=[])
    wp = sub.add_parser("write-pin")
    wp.add_argument("--rotation-record")
    sub.add_parser("mint-pin").add_argument("--ci", action="store_true", required=True)
    sub.add_parser("sign-rotation").add_argument("--approver", required=True)
    a = ap.parse_args(argv)
    sd = Path(a.skill_dir).resolve()
    if a.cmd == "check":
        print(f"front door cleared (version/hash-pin/bypass): pin {check(a.run_dir, sd)}")
    elif a.cmd == "hashpin":
        print(f"hash-pin verified: {step_hashpin(sd, a.must_cover)}")
    elif a.cmd == "bypass-scan":
        step_bypass_scan(a.run_dir, sd)
        print(f"BYPASS-SCAN clean: {a.run_dir or sd}")
    elif a.cmd == "pin-list":
        print("\n".join(name for name, _ in pin_files(sd)))
    elif a.cmd == "write-pin":
        print(f"wrote pin: {write_pin(sd, a.rotation_record)}")
    elif a.cmd == "mint-pin":
        print(f"minted pin: {mint_pin_ci(sd)}")
    else:
        print(json.dumps(sign_rotation(a.approver, sd), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
