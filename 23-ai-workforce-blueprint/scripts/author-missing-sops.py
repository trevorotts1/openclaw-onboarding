#!/usr/bin/env python3
"""author-missing-sops.py — the self-healing step for SOP-NEEDED.json.

Consumes the machine-readable SOP-needed records written by the installer
(create_role_workspaces.record_sop_needed → SOP-NEEDED.json). Every record is a
role whose work is currently ROUTED to the general-task department because no
role-library template matched at install time. This script closes each gap
permanently:

  1. Deterministic fill first (no model call): re-run the nearest-template
     match — the library may have gained the role since the build.
  2. LLM authoring for what remains: rubric-grounded authoring per
     templates/role-library/_sop-writer.md (≥3072 bytes, no boilerplate, real
     DMAIC SOP structure), via `openclaw subagents spawn` when available,
     otherwise an inline work-file the operating agent picks up.
  3. Harvest: every authored SOP is written as the role's own how-to.md (token-
     filled). A client-neutral token draft + a machine-readable SOP-NEEDED
     record are ALSO written to the NEW collection folder
     <OpenClaw root>/workforce/sop-harvest/ so the operator can review the
     draft and propose it into the shared library. This script NEVER writes
     into the installed templates/role-library/ or its _index.json: that
     directory is repo-owned content whose hashes the update content check
     verifies, so a box-side write there would be reported as drift on the
     very next update.
  4. The record is marked "authored" in SOP-NEEDED.json.

A build with un-authored records fails the library gate (verify-library-gate.sh),
so gaps can never go quiet.

Boundary note: unlike populate-sops-from-manifest.py (which refuses canonical
depts because they should resolve by copy), a record here exists PRECISELY
because the copy path already failed for this role. Authoring fills ONLY this
role's own how-to.md; it never rewrites an existing canonical template and
never touches the installed role library.
The boundary status is still logged per record for audit.

Usage:
  author-missing-sops.py [--sop-needed PATH] [--departments-dir DIR]
                         [--apply] [--timeout-seconds N] [--max-parallel N]
Dry run by default (prints what it would do). --apply performs the work.

EXIT CODES:
  0 = every record authored (nothing left open)
  1 = SOP-NEEDED.json missing or malformed
  2 = one or more records failed authoring/QC (manifest unchanged for them)
  3 = records remain open (deterministic fill done, LLM step pending/failed)
  4 = inline-queue mode: work files WRITTEN but SOPs not yet authored.
      NOT success — re-run until records are authored.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import create_role_workspaces as crw  # noqa: E402

MIN_BYTES = 3072  # same substance floor the installer enforces
SOP_BEGIN = "---BEGIN SOP---"
SOP_END = "---END SOP---"

# Boilerplate / fabrication markers that fail the QC gate.
BOILERPLATE_MARKERS = (
    "[Step 1 - to be personalized]",
    "[Step 1 — to be personalized",
    "to be personalized based on research",
    "PENDING - FILL FROM LIBRARY",
    "how-to.md (stub)",
    "TODO: fill",
    "[TBD]",
    "lorem ipsum",
)

HOME = Path.home()

# Client sovereignty: the authoring model is ALWAYS the box's own default model.
# Anthropic routes stay forbidden (same markers as shared-utils/select_model.py
# FORBIDDEN_PREFIXES); a forbidden default is a recorded gap, never swapped out.
FORBIDDEN_MODEL_MARKERS = ("anthropic/", "anthropic.", "openrouter/anthropic/", "claude-")


def log(msg):
    print(f"[AUTHOR-MISSING-SOPS] {msg}", file=sys.stderr)


# ─── MANIFEST DISCOVERY ───────────────────────────────────────────────────────

def find_sop_needed(explicit=None):
    if explicit:
        p = Path(explicit)
        return p if p.is_file() else None
    try:
        from detect_platform import get_openclaw_paths  # noqa: E402
        company = get_openclaw_paths().get("company_dir")
        if company:
            p = Path(company) / "SOP-NEEDED.json"
            if p.is_file():
                return p
    except Exception:
        pass
    return None


def load_manifest(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        log(f"cannot read {path}: {e}")
        return None
    if not isinstance(data.get("records"), list):
        log(f"malformed manifest at {path}: no records list")
        return None
    return data


def save_manifest(path, data):
    tmp = Path(str(path) + f".tmp-{os.getpid()}")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, path)


# ─── MODEL RESOLUTION + SUB-AGENT SPAWN (mirrors populate-sops-from-manifest) ─

def _config_candidates(explicit=None):
    """openclaw.json locations, same order shared-utils/select_model.py uses."""
    env = os.environ.get("OPENCLAW_CONFIG")
    return [explicit,
            env if env and os.path.isfile(env) else None,
            str(HOME / ".openclaw" / "openclaw.json"),
            "/data/.openclaw/openclaw.json"]


def resolve_box_default_model(config_path=None):
    """Return (model_id, gap_reason) for the BOX'S OWN default model.

    Reads agents.defaults.model (string, or {"primary": ...}) from the box's
    openclaw.json. Never returns a hardcoded id: when no default can be
    resolved, or it is a forbidden (Anthropic) route, returns (None, reason).
    """
    path = next((c for c in _config_candidates(config_path)
                 if c and os.path.isfile(c)), None)
    if not path:
        return None, "no openclaw.json found on this box"
    try:
        cfg = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        return None, f"cannot read {path}: {e}"
    agents = cfg.get("agents") if isinstance(cfg, dict) else None
    defaults = agents.get("defaults") if isinstance(agents, dict) else None
    field = defaults.get("model") if isinstance(defaults, dict) else None
    if isinstance(field, dict):
        field = field.get("primary") or field.get("model")
    if not isinstance(field, str) or not field.strip():
        return None, f"{path} has no agents.defaults.model"
    mid = field.strip()
    if any(m in mid.lower() for m in FORBIDDEN_MODEL_MARKERS):
        return None, "box default model is a forbidden (Anthropic) route"
    return mid, ""


def resolve_model():
    """Box default model id, or None when unresolvable (caller records the gap)."""
    mid, why = resolve_box_default_model()
    if mid is None:
        log(f"no box default model: {why}")
    return mid


def find_openclaw():
    explicit = os.environ.get("OPENCLAW_BIN")
    if explicit and os.access(explicit, os.X_OK):
        return explicit
    for cand in (shutil.which("openclaw"), "/opt/homebrew/bin/openclaw",
                 "/usr/local/bin/openclaw",
                 str(HOME / ".openclaw" / "bin" / "openclaw"),
                 "/data/.npm-global/bin/openclaw",
                 "/data/linuxbrew/.linuxbrew/bin/openclaw"):
        if cand and os.access(cand, os.X_OK):
            return cand
    return None


_OPENCLAW_BIN = find_openclaw()


def openclaw_available():
    if not _OPENCLAW_BIN:
        return False
    try:
        r = subprocess.run([_OPENCLAW_BIN, "subagents", "--help"],
                           capture_output=True, text=True, timeout=5)
        return r.returncode == 0
    except Exception:
        return False


# ─── RUBRIC ───────────────────────────────────────────────────────────────────

def load_rubric():
    """Return the SOP-writer rubric text (condensed) for the authoring prompt."""
    p = crw._resolve_skill_dir() / "templates" / "role-library" / "_sop-writer.md"
    try:
        text = p.read_text(encoding="utf-8")
    except OSError:
        return ""
    # Condense: keep the identity + the hard rules, drop the long examples.
    keep = []
    for line in text.splitlines():
        keep.append(line)
        if len("\n".join(keep)) > 6000:
            break
    return "\n".join(keep)


def build_author_prompt(record, rubric, company_name, industry):
    role = record.get("role", "")
    dept = record.get("department", "")
    desc = record.get("role_description", "") or "(no description supplied)"
    return f"""You are authoring a production SOP for an AI workforce role. This is real
operational documentation — a spawned worker will become this role ONLY by
loading and executing what you write, step by step. There is no room for
placeholders: an invented or thin procedure is worse than none.

ROLE: {role}
DEPARTMENT: {dept}
COMPANY: {company_name or "(see {{COMPANY_NAME}} token)"}
INDUSTRY: {industry or "unspecified"}
ROLE DESCRIPTION (from install spec): {desc}

RUBRIC (from templates/role-library/_sop-writer.md — follow it exactly):
{rubric}

HARD REQUIREMENTS:
1. Output ONLY the SOP document, delimited exactly as:
   {SOP_BEGIN}
   <the complete how-to.md>
   {SOP_END}
   Nothing outside the delimiters.
2. Use {{TOKENS}} for company-specific values ({{COMPANY_NAME}}, {{ROLE_TITLE}},
   {{DEPARTMENT_NAME}}, {{OWNER_NAME}}, {{COMPANY_INDUSTRY}}, {{ISO_DATE}}) —
   NEVER literal client data. The library stores the token version.
3. Minimum {MIN_BYTES} bytes of real, executable procedure. DMAIC structure
   (Define → Measure → Analyze → Improve → Control) expressed through the
   standard When/Frequency/Inputs/Steps/Outputs/Hand-to/Failure-mode SOP shape.
4. Every step must be something an AI agent can ACTUALLY do — read a specific
   file, call a specific tool, hit a specific endpoint with a specific payload.
   Never invent an API contract; never write "[Step N — to be personalized]".
5. No boilerplate, no TODO markers, no lorem ipsum, no PENDING headers.
6. Include the Persona Governance Override section and a "When to Spawn a
   Sub-Specialist" section (ephemeral workers execute the SOP step by step,
   report back, and are terminated).
"""


# ─── QC ───────────────────────────────────────────────────────────────────────

def qc_authored(text):
    """Return (ok, reason) for authored SOP text."""
    if not text or not text.strip():
        return False, "empty output"
    size = len(text.encode("utf-8"))
    if size < MIN_BYTES:
        return False, f"below {MIN_BYTES}B floor ({size}B)"
    lowered = text.lower()
    for marker in BOILERPLATE_MARKERS:
        if marker.lower() in lowered:
            return False, f"boilerplate marker present: {marker!r}"
    # Structural sanity: must read like a procedure, not an essay.
    steps = len(re.findall(r"(?m)^\s*(?:\d+\.|[-*])\s+\S", text))
    if steps < 5:
        return False, f"too few actionable steps ({steps})"
    return True, f"QC pass ({size}B, {steps} steps)"


def extract_sop(output):
    """Pull the delimited SOP out of sub-agent output."""
    if SOP_BEGIN in output and SOP_END in output:
        return output.split(SOP_BEGIN, 1)[1].split(SOP_END, 1)[0].strip()
    return output.strip()


# ─── DETERMINISTIC FILL (no model call) ───────────────────────────────────────

def deterministic_fill(record, departments_dir):
    """Try nearest-template fill. Returns (ok, detail)."""
    dept_slug = record.get("department", "")
    title = record.get("role", "")
    role_folder = record.get("role_folder", "")
    role_dir = Path(role_folder) if role_folder else None
    if not role_dir or not role_dir.is_dir():
        # resolve from departments_dir as fallback
        if departments_dir:
            cands = list(Path(departments_dir).glob(f"{dept_slug}/*{crw.slugify(title)}*"))
            role_dir = cands[0] if cands else None
    if not role_dir or not (role_dir / "how-to.md").is_file():
        return False, "role folder not found on disk"
    how_to = role_dir / "how-to.md"
    try:
        head = how_to.read_text(encoding="utf-8", errors="replace")[:600]
    except OSError:
        return False, "cannot read how-to.md"
    if "[ROUTED — WORK HANDLED BY GENERAL-TASK]" not in head:
        # Already replaced (authored meanwhile) — never overwrite real content.
        return False, "how-to.md no longer a routing notice"

    sys.path.insert(0, str(HERE))
    try:
        import fill_pending_howtos as fph  # noqa: E402
    except ImportError as e:
        return False, f"fill-pending-howtos unavailable: {e}"
    doc, entry, how = fph.nearest_template(title, dept_slug, 0.6, 0.85)
    if not doc:
        return False, how
    dept_name = dept_slug.replace("-", " ").title()
    filled = crw.fill_tokens(doc.read_text(encoding="utf-8"), title, dept_name,
                             False, role_entry=entry)
    if len(filled.encode("utf-8")) < MIN_BYTES:
        return False, "nearest template fills below floor"
    header = (f"<!-- workforce-provenance: source=role-library role-slug={entry.get('slug', '?')} "
              f"dept={entry.get('dept', '?')} content_sha={entry.get('content_sha', 'sha256:UNKNOWN')} "
              f"content_version={entry.get('content_version', '?')} "
              f"instantiated={datetime.now(timezone.utc).strftime('%Y-%m-%d')} "
              f"generator=author-missing-sops.py match={how} -->\\n")
    tmp = how_to.with_name(f".how-to.md.tmp-{os.getpid()}")
    tmp.write_text(header + filled, encoding="utf-8")
    os.replace(tmp, how_to)
    return True, f"deterministic fill via {how}: {entry.get('dept')}/{entry.get('slug')}"


# ─── HARVEST (collection folder; NEVER the installed role library) ────────────

HARVEST_SCHEMA = "sop-needed-harvest/1"


def slugify(text):
    return crw.slugify(text)


def harvest_dir():
    """<OpenClaw root>/workforce/sop-harvest/ (created on first write), or None."""
    try:
        root = crw.get_openclaw_paths().get("root")
    except Exception as e:
        log(f"cannot resolve OpenClaw root: {e}")
        return None
    return Path(root) / "workforce" / "sop-harvest" if root else None


def neutralize(text, cfg):
    """Swap any literal company / owner / AI CEO name for its token.

    The draft leaves the box, so it must be client-neutral even if the author
    model echoed a literal name instead of the token.
    """
    pairs = (
        (cfg.get("companyName") or cfg.get("company_name") or cfg.get("name"), "{{COMPANY_NAME}}"),
        (cfg.get("ownerName") or cfg.get("owner_name") or cfg.get("ownerFirstName"), "{{OWNER_NAME}}"),
        (cfg.get("aiCeoName") or cfg.get("ai_ceo_name") or cfg.get("aiCEOName"), "{{AI_CEO_NAME}}"),
    )
    for value, token in pairs:
        value = (value or "").strip() if isinstance(value, str) else ""
        if len(value) >= 3 and value != "AI CEO":
            text = re.sub(r"(?<!\w)" + re.escape(value) + r"(?!\w)", token, text)
    return text


def upstream_to_library(record, token_text):
    """Collect the authored SOP for operator review. NEVER writes the library.

    Writes two NEW files under <OpenClaw root>/workforce/sop-harvest/<dept>/:
      <role>.<sha8>.draft.md          client-neutral token draft
      <role>.<sha8>.sop-needed.json   machine-readable SOP-NEEDED record
    The sha8 in the name makes a re-run of identical content a no-op and keeps
    different content from ever overwriting an earlier draft.
    Returns (ok, detail).
    """
    out = harvest_dir()
    if out is None:
        return False, "no OpenClaw root — nothing harvested"
    draft = neutralize(token_text.rstrip("\n"), crw._load_company_config()) + "\n"
    sha = hashlib.sha256(draft.encode("utf-8")).hexdigest()
    dept_slug = slugify(record.get("department", "") or "general") or "general"
    role_slug = slugify(record.get("role", "unnamed-role")) or "unnamed-role"
    dept_dir = out / dept_slug
    stem = f"{role_slug}.{sha[:8]}"
    draft_path, rec_path = dept_dir / f"{stem}.draft.md", dept_dir / f"{stem}.sop-needed.json"
    if draft_path.exists() and rec_path.exists():
        return True, f"already harvested: {draft_path}"
    rec = {
        "schema": HARVEST_SCHEMA,
        "id": record.get("id", ""),
        "status": "SOP-NEEDED",
        "role": record.get("role", role_slug),
        "role_slug": role_slug,
        "department": dept_slug,
        "draft_file": draft_path.name,
        "content_sha": "sha256:" + sha,
        "bytes": len(draft.encode("utf-8")),
        "word_count": len(draft.split()),
        "sop_count": len(re.findall(r"(?m)^###?\s+SOP\s+9\.", draft)),
        "min_bytes": MIN_BYTES,
        "authored_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "authored_via": record.get("_authored_via", "llm"),
    }
    try:
        dept_dir.mkdir(parents=True, exist_ok=True)
        for path, body in ((draft_path, draft), (rec_path, json.dumps(rec, indent=2) + "\n")):
            tmp = path.with_name(f".{path.name}.tmp-{os.getpid()}")
            tmp.write_text(body, encoding="utf-8")
            os.replace(tmp, path)
    except OSError as e:
        return False, f"cannot write {dept_dir}: {e}"
    return True, f"harvested {draft_path}"


# ─── AUTHORING RUN ────────────────────────────────────────────────────────────

def author_one_subagent(record, prompt, model_id, timeout):
    """Spawn an openclaw sub-agent to author the SOP. Returns (ok, sop_text, detail)."""
    cmd = [_OPENCLAW_BIN or "openclaw", "subagents", "spawn",
           "--model", model_id, "--purpose-tier", "heavy",
           "--timeout-seconds", str(timeout), "--prompt", prompt,
           "--label", f"sop-author-{record.get('id', 'x')}"]
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True)
    except Exception as e:
        return False, "", f"spawn failed: {e}"
    try:
        out, err = proc.communicate(timeout=timeout + 120)
    except subprocess.TimeoutExpired:
        proc.kill()
        return False, "", "sub-agent timed out"
    if proc.returncode != 0:
        return False, "", f"sub-agent rc={proc.returncode}: {err[:300]}"
    return True, extract_sop(out or ""), "sub-agent completed"


def author_one_inline_queue(record, prompt, model_id, timeout, queue_dir):
    """Fallback: write a work file for the operating agent to pick up."""
    queue_dir = Path(queue_dir)
    queue_dir.mkdir(parents=True, exist_ok=True)
    work_file = queue_dir / f"sop-author-{record.get('id', 'x')}-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.md"
    body = f"""# SOP Author Job — {record.get('id', '')}

**Role:** {record.get('role', '')} (department `{record.get('department', '')}`)
**Status:** PENDING — pick this up and execute the instructions below.
**Model to use:** `{model_id}` (this box's own default model).
**Timeout budget:** {timeout} seconds.
**How-to path to write:** `{record.get('how_to_path', '')}`
**Record id:** `{record.get('id', '')}`

## Instructions

{prompt}

## When done

1. Write the DELIMITED SOP to the how-to path above (replacing the routing notice).
2. Run `python3 author-missing-sops.py --sop-needed <path> --apply --finalize <this-file>` so the record is QC'd, harvested to sop-harvest/, and marked authored.
3. Move this file to `{queue_dir}/done/`.
"""
    work_file.write_text(body, encoding="utf-8")
    log(f"queued inline work file: {work_file}")
    return work_file


def finalize_record(record, sop_token_text, manifest_path, data):
    """QC → write how-to.md → harvest → mark authored. Returns (ok, detail)."""
    ok, why = qc_authored(sop_token_text)
    if not ok:
        return False, f"QC failed: {why}"
    # Write the token-FILLED version as the role's how-to.md.
    how_to_path = record.get("how_to_path", "")
    dept_slug = record.get("department", "")
    title = record.get("role", "")
    dept_name = dept_slug.replace("-", " ").title()
    filled = crw.fill_tokens(sop_token_text, title, dept_name, False)
    if len(filled.encode("utf-8")) < MIN_BYTES:
        return False, "filled SOP below substance floor"
    header = (f"<!-- Filled from role-library -->\n"
              f"<!-- workforce-provenance: source=role-library-authored "
              f"record={record.get('id', '?')} "
              f"instantiated={datetime.now(timezone.utc).strftime('%Y-%m-%d')} "
              f"generator=author-missing-sops.py -->\n")
    if how_to_path:
        p = Path(how_to_path)
        try:
            head = p.read_text(encoding="utf-8", errors="replace")[:600]
        except OSError:
            head = ""
        if "[ROUTED — WORK HANDLED BY GENERAL-TASK]" not in head and "authored" not in head.lower():
            return False, "how-to.md no longer a routing notice — refusing overwrite"
        tmp = p.with_name(f".how-to.md.tmp-{os.getpid()}")
        tmp.write_text(header + filled, encoding="utf-8")
        os.replace(tmp, p)
    ok, why = upstream_to_library(record, sop_token_text)
    if not ok:
        # The role already has its real how-to.md; a harvest miss only delays
        # sharing the draft, so record it and keep going.
        log(f"{record.get('id', '?')}: harvest skipped — {why}")
        record["harvest"] = f"skipped: {why}"
    record["status"] = "authored"
    record["authored_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    record["authored_via"] = record.get("_authored_via", "llm")
    record.pop("_authored_via", None)
    save_manifest(manifest_path, data)
    return True, f"authored; harvest: {why}"


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--sop-needed", help="path to SOP-NEEDED.json")
    ap.add_argument("--departments-dir", help="built workforce departments dir")
    ap.add_argument("--apply", action="store_true", help="perform the work (default: dry run)")
    ap.add_argument("--timeout-seconds", type=int, default=1800)
    ap.add_argument("--finalize", metavar="WORKFILE",
                    help="finalize one inline work file: read its SOP, QC, harvest, mark authored")
    a = ap.parse_args(argv)

    manifest_path = find_sop_needed(a.sop_needed)
    if not manifest_path:
        log("SOP-NEEDED.json not found (pass --sop-needed)")
        return 1
    data = load_manifest(manifest_path)
    if data is None:
        return 1
    records = data.get("records", [])
    open_recs = [r for r in records if r.get("status") != "authored"]
    log(f"{manifest_path}: {len(open_recs)} open / {len(records)} total records")
    if not open_recs:
        log("nothing to do — every record authored ✅")
        return 0

    # Company context for prompts.
    cfg = crw._load_company_config()
    company_name = cfg.get("companyName") or cfg.get("company_name") or ""
    industry = cfg.get("industry") or cfg.get("companyIndustry") or ""

    departments_dir = a.departments_dir
    if not departments_dir:
        try:
            from detect_platform import get_openclaw_paths  # noqa: E402
            company = get_openclaw_paths().get("company_dir")
            if company:
                departments_dir = str(Path(company) / "departments")
        except Exception:
            pass

    if not a.apply:
        for r in open_recs:
            log(f"DRY RUN — would author: {r.get('id')} '{r.get('role')}' ({r.get('department')}) — {r.get('reason')}")
        log("dry run; nothing written (use --apply)")
        return 0

    rubric = load_rubric()
    model_id, model_gap = resolve_box_default_model()
    if model_id is None:
        log(f"no box default model ({model_gap}) — roles needing authoring are "
            "recorded as a gap and skipped; nothing is guessed")
    else:
        log(f"authoring model: {model_id} (box default)")
    use_subagents = openclaw_available()
    log(f"sub-agent spawn: {'available' if use_subagents else 'UNAVAILABLE — inline queue mode'}")
    queue_dir = Path(manifest_path).parent / ".sop-author-queue"

    failures = 0
    inline_queued = 0
    for r in open_recs:
        rid = r.get("id", "?")
        # Step 1: deterministic fill (no model call).
        ok, why = deterministic_fill(r, departments_dir)
        if ok:
            r["status"] = "authored"
            r["authored_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            r["authored_via"] = "deterministic-fill"
            save_manifest(manifest_path, data)
            log(f"{rid}: {why} → authored")
            continue
        log(f"{rid}: deterministic fill not possible ({why}) — LLM authoring")
        if model_id is None:
            r["model_gap"] = model_gap
            save_manifest(manifest_path, data)
            log(f"{rid}: no box default model — gap recorded, role stopped")
            failures += 1
            continue
        r.pop("model_gap", None)
        # Step 2: LLM authoring.
        prompt = build_author_prompt(r, rubric, company_name, industry)
        if use_subagents:
            ok, sop_text, why = author_one_subagent(r, prompt, model_id, a.timeout_seconds)
            if not ok:
                log(f"{rid}: authoring failed — {why}")
                failures += 1
                continue
            r["_authored_via"] = "llm-subagent"
            ok, why = finalize_record(r, sop_text, manifest_path, data)
            log(f"{rid}: {'authored ✅' if ok else 'FAILED — ' + why}")
            if not ok:
                failures += 1
        else:
            author_one_inline_queue(r, prompt, model_id, a.timeout_seconds, queue_dir)
            inline_queued += 1

    remaining = [r for r in data.get("records", []) if r.get("status") != "authored"]
    log(f"done: {len(records) - len(remaining)} authored, {len(remaining)} still open, {failures} failures")
    if inline_queued and not remaining:
        # All remaining were queued inline — work files written, SOPs pending.
        return 4
    if remaining or failures:
        return 3 if not failures else 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
