#!/usr/bin/env python3
"""repair-placeholder-sops.py -- remove installer placeholder how-to.md files from an EXISTING box.

Before v25.4.0 the Skill 23 installer silently wrote "[PENDING -- FILL FROM LIBRARY]"
stub how-to.md files (and, since v25.4.0, a ROUTED notice when no library template
matched). A role with a placeholder has no executable playbook. This script walks the
box's departments tree and, for every role how-to.md that is pure installer
boilerplate:

  1. FILL from the role library when a template exists (same matcher, token fill and
     3072-byte substance floor as fill-pending-howtos.py). If the role has an open
     SOP-NEEDED.json record it is marked "authored".
  2. Otherwise HAND OFF to authoring: the stub becomes the standard ROUTED notice and
     the role gets an open record in <company>/SOP-NEEDED.json. Then run
     author-missing-sops.py --apply, which authors the SOP with the BOX'S OWN default
     model. This script never calls a model and never picks one.
  3. DELETE aggregate department-level stubs: a stub how-to.md sitting directly in a
     department folder or in a non-role container folder (sops/, scripts/, ...). Those
     belong to no role and nothing reads them.

  4. FILL the other file classes the health gate judges to the SAME standard, so one
     repair pass clears the gate instead of it failing after every clean update:
       - an EMPTY or thin (< 3072 B) role how-to.md, from the same library ladder;
       - an EMPTY or placeholder SOP .md anywhere under a sops/ container, from the
         shipped SOP libraries (role-library/<dept>/sops/, then universal-sops/);
       - an EMPTY or placeholder flat role file under <dept>/roles/, from the library.
  5. A dept-level ROUTED notice for a department the library does not cover is filled
     from the single shipped department-guide renderer (how_to_use_department.py), so it
     is never left gate-fatal with no deterministic writer.

Safety: a file is touched only when the HEALTH GATE would fail it (same signatures,
same 600-byte head, same 3072-byte role floor) or when it is empty. A file that merely
mentions a signature, or has real content under a stub header, is reported as "needs
manual review" and left alone. A THIN file that is not empty may hold real owner words:
every original byte is kept as a prefix and the shipped library body is appended after
it -- never replaced, never truncated. No client content is ever authored: a file with
no shipped source is reported as a named CLIENT ACTION, not silently rewritten.
Symlinked files are never touched. Nothing but the judged .md files and
<company>/SOP-NEEDED.json is ever written; openclaw.json is never read or written.
Idempotent: a second run changes nothing.

Usage:
  repair-placeholder-sops.py [--departments-dir DIR] [--dept SLUG ...]
                             [--sop-needed PATH] [--dry-run] [--json]
Default applies the repair; --dry-run reports what would change and writes nothing
(--apply is accepted as the explicit form of the default).

EXIT CODES: 0 = no placeholder left; 3 = roles still need authoring (run
author-missing-sops.py --apply) or need manual review; 2 = departments dir not found.
"""
import argparse
import difflib
import importlib.util
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

S23 = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(S23))
import create_role_workspaces as crw  # noqa: E402

_spec = importlib.util.spec_from_file_location("fill_pending_howtos", S23 / "fill-pending-howtos.py")
fpm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fpm)

TAG = "[repair-placeholder-sops]"
CUTOFF, LIBRARY_CUTOFF = 0.6, 0.85  # same matcher floors fill-pending-howtos.py ships
# The stub signature is read from fill-pending-howtos.SIG (the gate's own set).
# Folders that hold no role: a stub how-to.md directly inside one is an aggregate stub.
CONTAINERS = {"_archive", "_index", "_compliance_audit", "_pending_rewrite", "_stage1_drafts",
              "sops", "scripts", "roles", "_drafts", "artifacts", "templates", "assets", "intake",
              "runs", "fish-audio", "release-matrix", "contract"}
NOT_ROLES = {"memory", "devils-advocate"}  # never roles; their how-to.md is library content
CEO_DEPTS = {"ai-ceo", "master-orchestrator"}
# Stub sections / lines that are boilerplate by construction (see the four legacy writers).
BOILER_SECTIONS = ("persona governance override", "sops (read-first)", "what this role does")
BOILER_LINE = re.compile(r"^(#|>|\(|\*\*(Department|Company|Industry|Status|Generated|Staffing|"
                         r"Owner request):\*\*|\d+\.\s+(Read|Check|Consult)\b)")
DEFAULT_DESC = re.compile(r"^\(.*\)$|^Owner-requested specialist in the .*Materialized as a build decision",
                          re.S)
# The gate's routing signature accepts any dash form; fpm.ROUTED_MARKER is em-dash only.
GATE_ROUTED = re.compile(r"\[ROUTED\W{1,6}WORK HANDLED BY GENERAL-TASK\]", re.IGNORECASE)
# Gate parity (scripts/health/library-gate-check.sh): SOP dirs, inherited core files,
# the flat-role folder, and the whole-file SOP check.
SOP_DIRS = {"sops", "_sops", "sop"}
CORE_FILES = {"AGENTS.md", "TOOLS.md", "USER.md", "IDENTITY.md", "SOUL.md", "MEMORY.md",
              "HEARTBEAT.md", "DREAMS.md", "ROSTER.md"}
SOP_CUTOFF = 0.6  # filename similarity floor for a nearest shipped SOP
# Shipped generic operating SOP: the last deterministic rung for an EMPTY SOP file the
# libraries do not name. Real repo doctrine, never client-authored.
GENERIC_SOP = Path("universal-sops") / "interdepartmental-communication-guidelines.md"


def log(msg):
    print(f"{TAG} {msg}")


def read(path):
    return path.read_text(encoding="utf-8", errors="replace")


def write_atomic(path, text):
    tmp = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def write_bytes_atomic(path, data):
    tmp = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def apply_fill(how_to, raw, fill_text, append):
    """Write the library body. A thin non-empty original keeps EVERY original byte as
    the prefix (`append`): no client word is ever replaced or truncated."""
    if append and raw.strip():
        write_bytes_atomic(how_to, raw + b"\n\n" + fill_text.encode("utf-8"))
    else:
        write_bytes_atomic(how_to, fill_text.encode("utf-8"))


# --- classification ----------------------------------------------------------

def residual_lines(text):
    """Count body lines that are NOT known installer boilerplate."""
    skip, n = False, 0
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("#"):
            skip = any(k in s.lower() for k in BOILER_SECTIONS)
            continue
        if skip or not s or BOILER_LINE.match(s):
            continue
        n += 1
    return n


def classify(text):
    """'stub' | 'routed' | 'empty' | 'review' | None (real content, not ours to touch).

    Signatures are read from the first 600 bytes with the GATE's own pattern set
    (fill-pending-howtos.SIG), not from the title line alone: the gate reads the
    head, so a stub whose marker sits in the body is fatal to the gate and used to
    be invisible here -- the repair could never clear a file it could not see.

    An EMPTY file is a gate failure in every class ("empty") and used to classify as
    None, so no repair path could ever clear the 0-byte files the gate reports.
    """
    if not text.strip():
        return "empty"
    head = text[:600]
    if fpm.ROUTED_MARKER in head or GATE_ROUTED.search(head):
        return "routed"
    if fpm.is_placeholder_text(head):
        # ponytail: content verify = signature in the head + under the substance floor +
        # <=3 non-boilerplate body lines. Upgrade to a full line diff against the four
        # legacy templates if hand-edited stubs show up in the field.
        pure = len(text.encode("utf-8")) < fpm.MIN_BYTES and residual_lines(text) <= 3
        return "stub" if pure else "review"
    return None  # no installer signature: real content


def gate_reason(text, floor):
    """What scripts/health/library-gate-check.sh would say about this file, or None.

    Mirrors bad_reason(): empty head -> "empty"; a signature (or a routing notice, in
    any dash form) in the first 600 bytes -> "placeholder text"; a ROLE playbook under
    the 3072-byte floor -> "thin (N bytes)". Repair and gate must never disagree about
    which file is fatal -- that disagreement is the defect this repair exists to close.
    """
    if not text.strip():
        return "empty"
    head = text[:600]
    if fpm.is_placeholder_text(head) or GATE_ROUTED.search(head):
        return "placeholder text"
    if floor and len(text.encode("utf-8")) < fpm.MIN_BYTES:
        return "thin (%d bytes)" % len(text.encode("utf-8"))
    return None


def owner_description(text):
    """Owner-supplied role description inside a stub -- real content we must not lose."""
    parts = []
    m = re.search(r"^\*\*Owner request:\*\*\s*(.+)$", text, re.M)
    if m:
        parts.append(m.group(1).strip())
    m = re.search(r"^## What This Role Does\s*\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    if m:
        parts.append(m.group(1).strip())
    return "\n\n".join(dict.fromkeys(p for p in parts if p and not DEFAULT_DESC.match(p)))


# --- SOP-NEEDED.json ---------------------------------------------------------

class Manifest:
    def __init__(self, path):
        self.path, self.dirty = Path(path), False
        try:
            self.data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(self.data.get("records"), list):
                raise ValueError("no records list")
        except (OSError, ValueError):
            self.data = {"records": []}
        self.records = self.data["records"]

    def find(self, role_dir, title, dept):
        for r in self.records:
            if r.get("role_folder") == str(role_dir) or (
                    r.get("role", "").lower() == title.lower() and r.get("department") == dept):
                return r
        return None

    def next_id(self):
        nums = [int(m.group(1)) for r in self.records
                if (m := re.fullmatch(r"sop-needed-(\d+)", str(r.get("id", ""))))]
        return f"sop-needed-{max(nums, default=0) + 1:04d}"

    def open_record(self, role_dir, how_to, title, dept, desc):
        """Existing record reopened, or a new open one; returns the record."""
        rec = self.find(role_dir, title, dept)
        if rec is None:
            rec = {"id": self.next_id(), "role": title, "department": dept,
                   "role_folder": str(role_dir), "how_to_path": str(how_to),
                   "reason": "placeholder how-to.md found on an existing box; no role-library template",
                   "routed_to": crw.GENERAL_TASK_DEPT_SLUG, "status": crw.SOP_NEEDED_ROUTED,
                   "recorded_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                   "role_description": desc}
            self.records.append(rec)
            self.dirty = True
        elif rec.get("status") == crw.SOP_NEEDED_AUTHORED:  # claimed authored, file says otherwise
            rec["status"] = crw.SOP_NEEDED_ROUTED
            rec.pop("authored_at", None)
            self.dirty = True
        return rec

    def mark_authored(self, role_dir, title, dept):
        rec = self.find(role_dir, title, dept)
        if rec and rec.get("status") != crw.SOP_NEEDED_AUTHORED:
            rec.update(status=crw.SOP_NEEDED_AUTHORED, authored_via="repair-placeholder-sops",
                       authored_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
            self.dirty = True

    def save(self):
        if not self.dirty:
            return
        self.data["open_count"] = sum(1 for r in self.records if r.get("status") != crw.SOP_NEEDED_AUTHORED)
        self.data["record_count"] = len(self.records)
        self.data.setdefault("generator", "repair-placeholder-sops.py")
        self.data["generated"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        write_atomic(self.path, json.dumps(self.data, indent=2))


# --- the repair --------------------------------------------------------------

def library_fill(dept_dir, title, desc):
    """(text, why) from the nearest library template, or from the shared scaffold."""
    doc, entry, how = fpm.nearest_template(title, dept_dir.name, CUTOFF, LIBRARY_CUTOFF)
    if not doc:
        # Last deterministic rung: the shared role scaffold (see
        # fill-pending-howtos.generic_template). A department the library does not
        # cover can never match a role template, so without this the role stays on
        # the routing notice forever and the gate fails it by construction.
        doc, entry = fpm.generic_template()
        how = fpm.GENERIC_HOW if doc else None
    if not doc:
        return None, how or "no comparable template"
    dept_name = dept_dir.name.replace("-", " ").title()
    is_ceo = dept_dir.name.lower() in CEO_DEPTS
    filled = crw.fill_tokens(doc.read_text(encoding="utf-8"), title, dept_name, is_ceo, role_entry=entry)
    if len(filled.encode("utf-8")) < fpm.MIN_BYTES:
        return None, f"template {entry['dept']}/{entry['slug']} fills below {fpm.MIN_BYTES}B"
    header = (f"<!-- workforce-provenance: source=role-library role-slug={entry.get('slug', '?')} "
              f"dept={entry.get('dept', '?')} content_sha={entry.get('content_sha', 'sha256:UNKNOWN')} "
              f"content_version={entry.get('content_version', '?')} "
              f"instantiated={datetime.now(timezone.utc).strftime('%Y-%m-%d')} "
              f"generator=repair-placeholder-sops.py match={how} -->\n")
    keep = f"\n## Role description (kept from the original placeholder)\n\n{desc}\n" if desc else ""
    return header + filled + keep, f"{how}: {entry['dept']}/{entry['slug']}"


def iter_candidates(ddir, depts):
    """(dept_dir, kind, how_to_path); kind is 'role' or 'aggregate'."""
    for dept in sorted(p for p in ddir.iterdir() if p.is_dir() and not p.name.startswith(".")
                       and ".bak" not in p.name):
        if depts and dept.name not in depts:
            continue
        yield dept, "aggregate", dept / "how-to.md"
        for sub in sorted(p for p in dept.iterdir() if p.is_dir() and not p.name.startswith(".")
                          and ".bak" not in p.name and p.name.lower() not in NOT_ROLES):
            yield dept, ("aggregate" if sub.name.lower() in CONTAINERS else "role"), sub / "how-to.md"


_HUD = None


def _dept_guide_renderer():
    """The repo's ONE department-guide renderer (loaded by path: the module name has
    underscores but lives beside hyphen-named siblings, so no plain import)."""
    global _HUD
    if _HUD is None:
        spec = importlib.util.spec_from_file_location("how_to_use_department",
                                                      S23 / "how_to_use_department.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _HUD = mod
    return _HUD


def dept_guide_fill(dept_dir, allow_generic=False):
    """(text, why) from the library's own guide for this department, or (None, reason).

    A DEPT-LEVEL how-to.md has no library owner: the library ships
    how-to-use-this-department.md and never how-to.md, so a legacy dept stub or
    dept-level routing notice was never replaceable -- the gate failed it and the
    repair filed it as REVIEW. The dept guide is real library content, so it is
    the honest replacement.

    `allow_generic` adds the shipped generic department-guide renderer as the last
    rung. It is used ONLY for a ROUTED notice: a dept the library does not cover has
    no guide file, so without this rung the notice classified REVIEW and stayed
    gate-fatal forever. A legacy dept STUB keeps its existing behavior (deleted as an
    aggregate stub) so nothing about today's stub handling changes.
    """
    lib = crw._resolve_dept_library_dir(dept_dir.name)
    src = (lib / "how-to-use-this-department.md") if lib else None
    if src and src.is_file():
        dept_name = dept_dir.name.replace("-", " ").title()
        text = crw.fill_tokens(src.read_text(encoding="utf-8"), dept_name, dept_name, False,
                               role_entry=None)
        if text.strip() and not fpm.is_placeholder_text(text[:600]):
            return text, "dept guide from role-library/how-to-use-this-department.md"
    if not allow_generic:
        return None, "library has no how-to-use-this-department.md for this department"
    try:
        cfg = crw._load_company_config()
        tokens = {"COMPANY_NAME": cfg.get("companyName") or cfg.get("name") or "",
                  "GENERATION_DATE": datetime.now(timezone.utc).strftime("%Y-%m-%d")}
        text = _dept_guide_renderer().render_how_to_use(dept_dir.name, tokens=tokens)
    except (OSError, ValueError, KeyError, ImportError) as e:
        return None, "generic dept guide unavailable (%s)" % type(e).__name__
    if not text.strip() or fpm.is_placeholder_text(text[:600]):
        return None, "generic dept guide renders as a placeholder"
    header = (f"<!-- workforce-provenance: source=dept-guide-renderer "
              f"dept={dept_dir.name} generator=repair-placeholder-sops.py "
              f"instantiated={datetime.now(timezone.utc).strftime('%Y-%m-%d')} -->\n")
    return header + text, "generic dept guide from templates/how-to-use-this-department.template.md"


# --- SOP files and flat role files (gate parity) -----------------------------

def present_depts(ddir, depts):
    for dept in sorted(p for p in ddir.iterdir() if p.is_dir() and not p.name.startswith(".")
                       and ".bak" not in p.name):
        if not depts or dept.name in depts:
            yield dept


def iter_sop_files(dept):
    """Every *.md the gate judges as an SOP: a file under a sops/ container, minus the
    inherited core files, symlinks and the container's own how-to.md (an aggregate
    candidate handled by the how-to.md walk)."""
    for root, dirs, files in os.walk(str(dept)):
        dirs[:] = sorted(d for d in dirs if not d.startswith(".") and d.lower() != "memory")
        parts = Path(root).relative_to(dept).parts
        if not any(p.lower() in SOP_DIRS for p in parts):
            continue
        for n in sorted(files):
            p = Path(root) / n
            if (n.endswith(".md") and n not in CORE_FILES and n != "how-to.md"
                    and p.is_file() and not p.is_symlink()):
                yield p


def iter_flat_roles(dept):
    """The gate judges <dept>/roles/*.md as role files (no size floor).

    how-to.md is skipped: the how-to.md walk already owns that path.
    """
    roles = dept / "roles"
    if not roles.is_dir():
        return
    for p in sorted(roles.glob("*.md")):
        if p.name != "how-to.md" and p.is_file() and not p.is_symlink():
            yield p


_SOP_INDEX = None


def _sop_index():
    """{dept_slug: {name: path}}, {name: path} and the shipped generic SOP.

    Sources, all shipped: role-library/<dept>/sops/*.md and universal-sops/**/*.md.
    Exact names win; the first file seen for a name is kept, so the department's own
    library file beats a same-named file from anywhere else.
    """
    global _SOP_INDEX
    if _SOP_INDEX is None:
        skill = crw._resolve_skill_dir()
        by_dept, every = {}, {}
        for p in sorted((skill / "templates" / "role-library").glob("*/sops/*.md")):
            by_dept.setdefault(p.parent.parent.name, {}).setdefault(p.name.lower(), p)
            every.setdefault(p.name.lower(), p)
        for p in sorted((skill.parent / "universal-sops").rglob("*.md")):
            every.setdefault(p.name.lower(), p)
        generic = skill.parent / GENERIC_SOP
        _SOP_INDEX = {"dept": by_dept, "all": every,
                      "generic": generic if generic.is_file() else None}
    return _SOP_INDEX


def sop_fill(dept_dir, sop_path):
    """(text, why) for an empty/placeholder SOP from the shipped SOP libraries."""
    idx = _sop_index()
    name = sop_path.name.lower()
    src = idx["dept"].get(dept_dir.name, {}).get(name) or idx["all"].get(name)
    how = "exact-name"
    if src is None:
        pool = dict(idx["all"])
        pool.update(idx["dept"].get(dept_dir.name, {}))
        hit = difflib.get_close_matches(name, list(pool), n=1, cutoff=SOP_CUTOFF)
        src = pool[hit[0]] if hit else None
        how = "nearest-name"
    if src is None:
        src, how = idx["generic"], "generic-sop"
    if src is None:
        return None, "no shipped SOP source"
    body = src.read_text(encoding="utf-8", errors="replace")
    if not body.strip() or fpm.is_placeholder_text(body[:600]):
        return None, "shipped SOP %s is itself a placeholder" % src.name
    header = (f"<!-- workforce-provenance: source=sop-library role-slug={sop_path.stem} "
              f"template={src.name} generator=repair-placeholder-sops.py match={how} "
              f"instantiated={datetime.now(timezone.utc).strftime('%Y-%m-%d')} -->\n")
    return header + body, f"{how}: {src.name}"


def replaceable(how_to, kinds):
    """Re-check immediately before a write: still absent, or still one of `kinds`."""
    if not how_to.is_file():
        return True
    return classify(read(how_to)) in kinds


def repair(ddir, manifest, depts, apply):
    c = dict(scanned=0, placeholders=0, filled_from_library=0, handed_to_authoring=0,
             already_awaiting_authoring=0, aggregate_stubs_deleted=0, needs_manual_review=0,
             skipped_symlink=0, errors=0, thin_appended=0, sop_files_filled=0,
             flat_roles_filled=0, client_action=0)
    for dept, kind, how_to in iter_candidates(ddir, depts):
        present = how_to.is_file() or how_to.is_symlink()
        # The gate counts a role folder holding IDENTITY.md but no how-to.md as
        # "missing how-to.md". Skipping absent paths meant the repair never saw
        # that file, so the gate could never be cleared.
        missing_role = (not present and kind == "role"
                        and (how_to.parent / "IDENTITY.md").is_file())
        if not present and not missing_role:
            continue
        c["scanned"] += 1
        rel = f"{dept.name}/{how_to.parent.name if how_to.parent != dept else ''}".rstrip("/")
        try:
            if how_to.is_symlink():
                if classify(read(how_to)):
                    c["skipped_symlink"] += 1
                    log(f"SKIP symlinked how-to.md {rel}")
                continue
            raw = how_to.read_bytes() if present else b""
            text = raw.decode("utf-8", "replace")
            found = classify(text) if present else "empty"
            # The gate's own verdict decides whether this file is ours to fix.
            reason = gate_reason(text, floor=(kind == "role")) if present else "empty"
            if reason is None:
                continue
            c["placeholders"] += 1
            if found == "review":
                c["needs_manual_review"] += 1
                log(f"REVIEW {rel}: signature present but not pure boilerplate -- "
                    f"CLIENT ACTION: an owner must resolve it; left untouched")
                continue
            # A thin file that is NOT a stub may hold real owner words: keep its every
            # byte as the prefix and append the shipped body after it.
            append = reason.startswith("thin")
            if kind == "aggregate":
                if how_to.parent == dept or found == "routed":
                    # Dept-level file (or a container routing notice): the library owns
                    # it through its department guide. `allow_generic` covers a dept the
                    # library does not list, so a routed notice is never left gate-fatal.
                    new, why = dept_guide_fill(dept, allow_generic=(found == "routed"))
                    if new is not None:
                        c["filled_from_library"] += 1
                        log(f"{'FILLED' if apply else 'WOULD FILL'} {rel} ({why})")
                        if apply and replaceable(how_to, ("stub", "routed", "empty")):
                            apply_fill(how_to, raw, new, append=False)
                        continue
                if found != "stub":
                    c["needs_manual_review"] += 1
                    log(f"REVIEW {rel}: signature present but not pure boilerplate -- "
                        f"CLIENT ACTION: an owner must resolve it; left untouched")
                    continue
                c["aggregate_stubs_deleted"] += 1
                log(f"{'DELETE' if apply else 'WOULD DELETE'} aggregate stub {rel}/how-to.md")
                if apply and how_to.is_file() and classify(read(how_to)) == "stub":
                    how_to.unlink()
                continue
            role_dir = how_to.parent
            title = fpm.role_title(role_dir)
            desc = owner_description(text) if found == "stub" else ""
            new, why = library_fill(dept, title, desc)
            if new is not None:
                c["filled_from_library"] += 1
                if append:
                    c["thin_appended"] += 1
                log(f"{'FILLED' if apply else 'WOULD FILL'} {rel} ({why})")
                kinds = (None,) if append else ("stub", "routed", "empty")
                if apply and replaceable(how_to, kinds):
                    apply_fill(how_to, raw, new, append=append)
                    if not append and not why.startswith(fpm.GENERIC_HOW):
                        # The shared scaffold is not an authored playbook: leave the
                        # record open so the role-specific SOP is still owed.
                        manifest.mark_authored(role_dir, title, dept.name)
                continue
            if found == "routed" and manifest.find(role_dir, title, dept.name):
                c["already_awaiting_authoring"] += 1
                log(f"AWAITING authoring {rel} ({why})")
                continue
            c["handed_to_authoring"] += 1
            log(f"{'HAND OFF' if apply else 'WOULD HAND OFF'} {rel} to authoring ({why})")
            if apply and replaceable(how_to, ("stub", "routed", "empty")):
                rec = manifest.open_record(role_dir, how_to, title, dept.name, desc)
                cfg = crw._load_company_config()
                write_atomic(how_to, crw.routing_how_to(
                    title, dept.name.replace("-", " ").title(), dept.name,
                    cfg.get("companyName", ""), cfg.get("industry", ""), rec["id"], desc))
        except (OSError, ValueError, KeyError) as e:
            c["errors"] += 1
            log(f"ERROR {rel}: {e}")

    # The gate's other two file classes, walked exactly as it walks them. Neither
    # carries a size floor, so only EMPTY and placeholder-text files are fatal there.
    for dept in present_depts(ddir, depts):
        for sop in iter_sop_files(dept):
            rel = str(sop.relative_to(ddir))
            try:
                raw = sop.read_bytes()
                text = raw.decode("utf-8", "replace")
                reason = gate_reason(text, floor=False)
                if reason is None:
                    continue
                c["scanned"] += 1
                c["placeholders"] += 1
                if classify(text) == "review":
                    c["needs_manual_review"] += 1
                    log(f"REVIEW {rel}: placeholder signature beside real SOP text -- "
                        f"CLIENT ACTION: an owner must resolve it; left untouched")
                    continue
                new, why = sop_fill(dept, sop)
                if new is None:
                    c["client_action"] += 1
                    log(f"CLIENT ACTION {rel}: {why} -- left untouched")
                    continue
                c["sop_files_filled"] += 1
                log(f"{'FILLED' if apply else 'WOULD FILL'} {rel} ({why})")
                if apply and gate_reason(read(sop), floor=False):
                    apply_fill(sop, raw, new, append=False)
            except (OSError, ValueError, KeyError) as e:
                c["errors"] += 1
                log(f"ERROR {rel}: {e}")
        for flat in iter_flat_roles(dept):
            rel = str(flat.relative_to(ddir))
            try:
                raw = flat.read_bytes()
                text = raw.decode("utf-8", "replace")
                reason = gate_reason(text, floor=False)
                if reason is None:
                    continue
                c["scanned"] += 1
                c["placeholders"] += 1
                if classify(text) == "review":
                    c["needs_manual_review"] += 1
                    log(f"REVIEW {rel}: placeholder signature beside real role text -- "
                        f"CLIENT ACTION: an owner must resolve it; left untouched")
                    continue
                title = re.sub(r"^\d+[-_]", "", flat.stem).replace("-", " ").title()
                new, why = library_fill(dept, title, "")
                if new is None:
                    c["client_action"] += 1
                    log(f"CLIENT ACTION {rel}: {why} -- left untouched")
                    continue
                c["flat_roles_filled"] += 1
                log(f"{'FILLED' if apply else 'WOULD FILL'} {rel} ({why})")
                if apply and gate_reason(read(flat), floor=False):
                    apply_fill(flat, raw, new, append=False)
            except (OSError, ValueError, KeyError) as e:
                c["errors"] += 1
                log(f"ERROR {rel}: {e}")
    return c


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--departments-dir")
    ap.add_argument("--dept", action="append", help="only these department folders (repeatable)")
    ap.add_argument("--sop-needed", help="SOP-NEEDED.json path (default: <company>/SOP-NEEDED.json)")
    ap.add_argument("--dry-run", action="store_true", help="report only; write nothing")
    ap.add_argument("--apply", action="store_true", help="explicit form of the default")
    ap.add_argument("--json", action="store_true", help="print the counts as one JSON line")
    a = ap.parse_args(argv)
    if a.dry_run and a.apply:
        ap.error("--dry-run and --apply contradict each other")
    ddir = Path(a.departments_dir) if a.departments_dir else fpm.default_departments_dir()
    if not ddir or not ddir.is_dir():
        print(f"{TAG} ERROR: departments dir not found (pass --departments-dir)", file=sys.stderr)
        return 2
    apply = not a.dry_run
    manifest = Manifest(a.sop_needed or ddir.parent / "SOP-NEEDED.json")
    counts = repair(ddir, manifest, set(a.dept or []), apply)
    if apply:
        manifest.save()
    left = (counts["handed_to_authoring"] + counts["already_awaiting_authoring"]
            + counts["needs_manual_review"] + counts["client_action"])
    log(" ".join(f"{k}={v}" for k, v in counts.items()) + ("" if apply else " -- DRY RUN, nothing written"))
    if counts["handed_to_authoring"] + counts["already_awaiting_authoring"]:
        log("next: author-missing-sops.py --apply  (authors the rest with the box's own default model)")
    if a.json:
        print(json.dumps(dict(counts, dry_run=not apply)))
    return 3 if left else 0


if __name__ == "__main__":
    sys.exit(main())
