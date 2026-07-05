#!/usr/bin/env python3
"""
ad_build_check.py — Facebook & Instagram Ad Generator RECEIPT VALIDATORS + MONEY GATES.

================================================================================
This is the enforcement library for the Facebook & Instagram Ad Generator
(Skill 48). It is the analogue of the Movie Producer's video_build_check.py:
every PIPELINE autofail in AD-PIPELINE-MANIFEST.json whose enforced_by ==
"ad_director" names a py_symbol that is DEFINED here (and referenced on the
enforcement path in ad_director.py).

It validates RECEIPTS, not just their presence. Each stage's producing role
writes the human deliverable (s1-overlays.md, the images, ...) AND a small JSON
receipt that attests the machine-checkable facts (overlay_count, word_counts,
real kie_task_id, image size, the running spend tally, the QC scorecard
verdict). These checkers validate those receipts OFFLINE — no check makes a
live network call (the live calls happen in the integration helpers, which drop
the receipt the check reads). The ONE place that talks to the network is the
Phase-0 Kie balance preflight, run ONCE at start.

LOCKED DECISIONS honored here:
  * 10 ads (SELECTION_COUNT_LOCKED) from ~70 overlays (OVERLAY_COUNT_LOCKED).
  * 1500x1500 1:1 images (IMAGE_EDGE_PX) with the text BAKED IN by the model.
  * Image model auto-adopts any future gpt-image version: GPT_IMAGE_MODEL_PREFIX
    accepts gpt-image-2 AND gpt-image-3 / gpt-image-2-image-to-image / ... — the
    version is NEVER hardcoded in a way that blocks a bump.
  * Money = up-front estimate <= ceiling (AF-FBAD-COST-CEILING), a cheap LOCAL
    running tally that stops before crossing (AF-FBAD-TALLY-CROSS), and a single
    balance preflight at start (AF-FBAD-KIE-BALANCE). NOT a balance call per image.
  * Unique run-id namespaces every receipt so a retry never re-spends or
    double-uploads (AF-FBAD-RECEIPT-NAMESPACE + the ad_run_ledger).
  * Targeting fabrication auto-fails; "flagged-unverified" is the honest degrade
    (AF-FBAD-TARGETING-REAL).
  * Independent QC: a gate opens only with zero autofails AND an 8.5+ score from a
    DIFFERENT worker than the maker (AF-FBAD-*-QC + AF-FBAD-QC-INDEPENDENCE).

Each checker returns "" on PASS or a fatal "AF-FBAD-...: <reason>" string on FAIL.
Zero third-party deps (stdlib json / re / pathlib / urllib only).
"""

import json
import re
from pathlib import Path

# ---------------------------------------------------------------------------
# Module constants (the secondary_py_symbols the manifest autofails reference).
# ---------------------------------------------------------------------------
REQUIRED_BRIEF_FIELDS = [
    "job_id",
    "show_name",
    "audience_profile_ref",
    "money_ceiling_usd",
    "estimated_cost_usd",
    "owner",
]

# The locked creative quantities (LOCKED DECISIONS).
OVERLAY_COUNT_LOCKED = 70     # ~70 overlay lines written, the human picks the top 10
OVERLAY_WORD_MIN = 3          # an overlay line is a punchy fragment...
OVERLAY_WORD_MAX = 19         # ...that still bakes legibly into a 1:1 image
SELECTION_COUNT_LOCKED = 10   # the chosen ads -> 10 bodies / 10 headlines / 10 images

# Primary-text (body) discipline.
BODY_HOOK_MAX_CHARS = 125     # the above-the-fold hook before "See more"
BODY_CTA_COUNT = 3            # exactly three calls-to-action per body
BODY_EMOJI_MIN = 1
BODY_EMOJI_MAX = 12

# The locked headline shapes (only these four).
HEADLINE_SHAPES_LOCKED = ["how-to", "question", "number-list", "direct-promise"]

# The fixed image-prompt build order (every prompt declares these sections in order).
PROMPT_BUILD_ORDER = [
    "subject",
    "composition",
    "typography",
    "color-grading",
    "lighting",
    "quality",
    "facial-intelligence",
    "brand-style-block",
]
PROMPT_MIN_CHARS = 3500       # the richness floor (creativity/typography/grade/quality/face)
PROMPT_MAX_CHARS = 18000

# Image size (square feed ad) + the model family the generation must stay on.
IMAGE_EDGE_PX = 1500
# Auto-adopt any future gpt-image version: a model id must START WITH this prefix.
# gpt-image-2, gpt-image-3, gpt-image-2-image-to-image, gpt-image-2-text-to-image
# all pass; "dalle" / "flux" / "" fail. The version digit is NEVER hardcoded.
GPT_IMAGE_MODEL_PREFIX = "gpt-image-"

# Placeholder / fabricated tokens that are NOT a real Kie task id.
FABRICATED_TASK_ID_TOKENS = [
    "task_id", "taskid", "todo", "tbd", "xxxx", "xxx", "fake", "fabricated",
    "placeholder", "none", "null", "n/a", "na", "your_task_id", "example",
]
# Tokens that are NOT a real hosted-image URL.
FABRICATED_URL_TOKENS = [
    "placeholder", "example.com", "todo", "tbd", "xxxx", "fake", "your_url",
    "file://", "data:", "localhost",
]

# Every field PLAI's builder asks for (AF-FBAD-PLAI-FIELDS).
REQUIRED_PLAI_FIELDS = [
    "campaign_name",
    "objective",
    "image_links",
    "primary_texts",
    "headlines",
    "targeting_groups",
    "placements",
    "destination_url",
]

# Independent-QC pass line (mirrors the presentations >=8.5 / no-category-<7 model).
QC_MIN_AVERAGE = 8.5
QC_MIN_CATEGORY = 7.0
# gate -> scorecard filename under working/qc/ .
QC_SCORECARDS = {
    "copy": "copy-qc.json",
    "prompt": "prompt-qc.json",
    "image": "image-qc.json",
    "targeting": "targeting-qc.json",
    "package": "package-qc.json",
}

# The required-deliverable bundle (mirrors AD-PIPELINE-MANIFEST.deliverables_required).
# Lockstep (ad_sync_check.py D1/D2) requires this key set == the manifest key set.
DELIVERABLES_REQUIRED = [
    {"key": "job_manifest", "filename": "job-manifest.json", "min_bytes": 256,
     "label": "completed intake brief / job manifest"},
    {"key": "run_ledger", "filename": "ad_run_ledger.json", "min_bytes": 64,
     "label": "run-id no-double-charge ledger"},
    {"key": "image_receipt", "filename": "s5-image-receipt.json", "min_bytes": 256,
     "label": "Kie image generation receipt"},
    {"key": "plai_brief", "filename": "s7-plai-brief.json", "min_bytes": 256,
     "label": "PLAI-ready handoff package"},
]

# Phase-0 Kie balance preflight constants (AF-FBAD-KIE-BALANCE).
FBAD_KIE_CREDIT_URL = "https://api.kie.ai/api/v1/chat/credit"
FBAD_KIE_BALANCE_FLOOR_MULTIPLIER = 1.30  # headroom over the bare estimate (re-dos)
FBAD_CREDIT_PER_USD = 100                 # conservative USD->credit factor

# Tolerance between a scorecard's SELF-DECLARED average and the average COMPUTED from
# its own category scores. A declared number can NEVER override the computed one; a
# disagreement beyond this tolerance is an autofail (a fabricated/careless number).
QC_DECLARED_AVG_TOLERANCE = 0.05

_HERE = Path(__file__).resolve().parent


# ---------------------------------------------------------------------------
# Registered-role registry (AD-PIPELINE-MANIFEST.json roles[].id) — used by the
# QC-independence check so a scorecard's maker/grader must be REAL registered role
# slugs, not free text. Own lightweight loader (no import of ad_director, which would
# be circular) mirroring ad_recovery's manifest resolution.
# ---------------------------------------------------------------------------
def _find_repo_root(start: Path):
    cur = start
    for _ in range(12):
        if (cur / "universal-sops").is_dir():
            return cur
        if cur.parent == cur:
            break
        cur = cur.parent
    return None


def _manifest_candidates():
    repo = _find_repo_root(_HERE)
    cands = []
    if repo:
        cands.append(repo / "universal-sops" / "fb-ad-craft" / "AD-PIPELINE-MANIFEST.json")
    cands += [
        _HERE.parent / "sops" / "AD-PIPELINE-MANIFEST.json",
        _HERE.parent / "AD-PIPELINE-MANIFEST.json",
        _HERE / "AD-PIPELINE-MANIFEST.json",
    ]
    return cands


def registered_role_slugs() -> set:
    """The set of REGISTERED role slugs (lowercased) from the manifest roles[].id.
    Returns an EMPTY set when the manifest cannot be resolved — the caller then skips
    ONLY the registered-slug leg (the ledger tie-back still applies) rather than crash
    in an environment without the manifest on disk."""
    slugs = set()
    for c in _manifest_candidates():
        try:
            if c.exists():
                m = json.loads(c.read_text())
                for r in (m.get("roles", []) or []):
                    rid = str((r or {}).get("id", "")).strip().lower()
                    if rid:
                        slugs.add(rid)
                break
        except Exception:  # noqa: BLE001 — a broken manifest degrades to "no registry"
            continue
    return slugs


# ---------------------------------------------------------------------------
# JSON helpers
# ---------------------------------------------------------------------------
def _read_json(path: Path):
    """Parsed object, or None when absent/unreadable, or {'__parse_error__': ...}
    on a JSON error so callers can distinguish a bad file from a missing one."""
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except Exception as exc:  # noqa: BLE001
        return {"__parse_error__": str(exc)}


def _working(run_dir: Path) -> Path:
    return run_dir / "working"


def _checkpoints(run_dir: Path) -> Path:
    return run_dir / "working" / "checkpoints"


def _qc_dir(run_dir: Path) -> Path:
    return run_dir / "working" / "qc"


def _load_job_manifest(run_dir: Path):
    return _read_json(_working(run_dir) / "job-manifest.json")


def _ledger(run_dir: Path):
    return _read_json(_checkpoints(run_dir) / "ad_run_ledger.json")


def _selection(run_dir: Path):
    return _read_json(_working(run_dir) / "s1-selection.json")


def _paid_in_scope(run_dir: Path) -> bool:
    """True when this job will dispatch at least one paid Kie image call. FB/IG ads
    are paid whenever estimated_cost_usd > 0 (10 images). A zero-cost dry run defers
    the paid-only gates (image task-id, balance preflight)."""
    jm = _load_job_manifest(run_dir)
    if isinstance(jm, dict) and "__parse_error__" not in jm:
        est = jm.get("estimated_cost_usd")
        if isinstance(est, (int, float)) and est > 0:
            return True
        if jm.get("paid_in_scope") is True:
            return True
    return False


def _ceiling(run_dir: Path):
    jm = _load_job_manifest(run_dir)
    if isinstance(jm, dict):
        cap = jm.get("money_ceiling_usd")
        if isinstance(cap, (int, float)):
            return float(cap)
    return None


# ===========================================================================
# S0-INTAKE — AF-FBAD-BRIEF-INCOMPLETE / AF-FBAD-COST-CEILING / AF-FBAD-RECEIPT-NAMESPACE
# ===========================================================================
def _chk_brief_complete(run_dir: Path) -> str:
    """AF-FBAD-BRIEF-INCOMPLETE. job-manifest.json sets brief_complete:true and
    carries every REQUIRED_BRIEF_FIELDS field with a non-empty value."""
    jm = _load_job_manifest(run_dir)
    if jm is None:
        return ("AF-FBAD-BRIEF-INCOMPLETE: working/job-manifest.json is absent — the "
                "intake brief is the precondition for every downstream stage.")
    if isinstance(jm, dict) and "__parse_error__" in jm:
        return (f"AF-FBAD-BRIEF-INCOMPLETE: job-manifest.json is not valid JSON "
                f"({jm['__parse_error__']}).")
    if jm.get("brief_complete") is not True:
        return ("AF-FBAD-BRIEF-INCOMPLETE: job-manifest.json does not set "
                "brief_complete:true. Return the gap list to the owner before "
                "proceeding — never guess at a missing brief input.")
    missing = [f for f in REQUIRED_BRIEF_FIELDS if jm.get(f) in (None, "", [], {})]
    if missing:
        return ("AF-FBAD-BRIEF-INCOMPLETE: job-manifest.json is missing required "
                f"field(s): {', '.join(missing)}. All of {REQUIRED_BRIEF_FIELDS} "
                "must be present.")
    return ""


def _chk_cost_ceiling(run_dir: Path) -> str:
    """AF-FBAD-COST-CEILING. The up-front estimate must be approved AND <= the
    per-job ceiling BEFORE any money is spent."""
    jm = _load_job_manifest(run_dir)
    if jm is None or (isinstance(jm, dict) and "__parse_error__" in jm):
        return ("AF-FBAD-COST-CEILING: job-manifest.json absent/invalid; the up-front "
                "cost estimate could not be confirmed.")
    if jm.get("cost_estimate_approved") is not True:
        return ("AF-FBAD-COST-CEILING: job-manifest.json does not set "
                "cost_estimate_approved:true. The estimate ('10 images = $X') must be "
                "announced and approved BEFORE the first paid image.")
    est = jm.get("estimated_cost_usd")
    cap = jm.get("money_ceiling_usd")
    if not isinstance(est, (int, float)) or not isinstance(cap, (int, float)):
        return ("AF-FBAD-COST-CEILING: estimated_cost_usd / money_ceiling_usd must "
                "both be numbers in job-manifest.json.")
    if est > cap:
        return ("AF-FBAD-COST-CEILING: estimated_cost_usd "
                f"({est}) exceeds the per-job ceiling ({cap}) BEFORE any spend. HARD "
                "STOP — raise the ceiling with the owner or cut the batch.")
    return ""


def _chk_run_ledger(run_dir: Path) -> str:
    """AF-FBAD-RECEIPT-NAMESPACE. The run-id ledger must exist, its run_id must equal
    the job_id, and it must carry an events[] log (the no-double-charge guarantee)."""
    led = _ledger(run_dir)
    if led is None:
        return ("AF-FBAD-RECEIPT-NAMESPACE: working/checkpoints/ad_run_ledger.json is "
                "absent. Every paid receipt must be namespaced by the unique run-id so a "
                "retry never re-spends or double-uploads.")
    if isinstance(led, dict) and "__parse_error__" in led:
        return (f"AF-FBAD-RECEIPT-NAMESPACE: ad_run_ledger.json is not valid JSON "
                f"({led['__parse_error__']}).")
    run_id = str(led.get("run_id", "")).strip()
    if not run_id:
        return ("AF-FBAD-RECEIPT-NAMESPACE: ad_run_ledger.json carries no run_id — the "
                "ledger must be namespaced by the unique run-id.")
    jm = _load_job_manifest(run_dir)
    job_id = str(jm.get("job_id", "")).strip() if isinstance(jm, dict) else ""
    if job_id and run_id != job_id:
        return ("AF-FBAD-RECEIPT-NAMESPACE: ledger run_id "
                f"({run_id!r}) != job_id ({job_id!r}). One run-id = one campaign = one "
                "ledger, forever.")
    if not isinstance(led.get("events"), list):
        return ("AF-FBAD-RECEIPT-NAMESPACE: ad_run_ledger.json carries no events[] log "
                "— the 'what already happened' log is what lets a retry skip done work.")
    return ""


# ===========================================================================
# S1-OVERLAYS — count / wordcount / topline / on-mission / audience-wording
# ===========================================================================
def _s1_receipt(run_dir: Path):
    return _read_json(_checkpoints(run_dir) / "s1-receipt.json")


def measure_overlays(run_dir: Path):
    """MEASURE the real deliverable (working/s1-overlays.md): return the list of
    per-line word counts of the actual overlay lines, or None when the file is
    absent/unreadable. Only content lines count — a markdown header (``#...``), a
    blank line, or a horizontal rule is skipped; a leading list ordinal (``12.`` /
    ``12)``) or bullet (``- `` / ``* ``) is stripped before counting the overlay's
    own words. This is what lets the count/wordcount gates verify the SOURCE FILE
    against the maker's self-reported receipt numbers rather than trusting them."""
    p = _working(run_dir) / "s1-overlays.md"
    if not p.exists():
        return None
    try:
        text = p.read_text()
    except OSError:
        return None
    counts = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or set(line) <= {"-", "*", "_", "="}:
            continue  # blank / markdown header / horizontal rule
        m = re.match(r"^\d+[.)]\s+(.*)$", line)      # numbered list ordinal
        body = m.group(1) if m else line
        body = re.sub(r"^[-*]\s+", "", body).strip()  # leading bullet
        if not body:
            continue
        counts.append(len(body.split()))
    return counts


def _chk_overlay_count(run_dir: Path) -> str:
    """AF-FBAD-OVERLAY-COUNT. overlay_count must be exactly OVERLAY_COUNT_LOCKED — and
    the receipt count is verified against the MEASURED line count of s1-overlays.md."""
    r = _s1_receipt(run_dir)
    if r is None or (isinstance(r, dict) and "__parse_error__" in r):
        return ("AF-FBAD-OVERLAY-COUNT: working/checkpoints/s1-receipt.json is "
                "absent/invalid — the overlay set must attest its count.")
    n = r.get("overlay_count")
    if n != OVERLAY_COUNT_LOCKED:
        return ("AF-FBAD-OVERLAY-COUNT: overlay_count is "
                f"{n!r}, not the locked {OVERLAY_COUNT_LOCKED}. The human picks 10 from "
                "this fixed set; a short or padded set breaks the pick-10 contract.")
    measured = measure_overlays(run_dir)
    if measured is not None and len(measured) != n:
        return ("AF-FBAD-OVERLAY-COUNT: the receipt attests overlay_count "
                f"{n} but the MEASURED s1-overlays.md carries {len(measured)} overlay "
                "line(s). The receipt number must match the real deliverable, never a "
                "self-reported figure.")
    return ""


def _chk_overlay_wordcount(run_dir: Path) -> str:
    """AF-FBAD-OVERLAY-WORDCOUNT. Every overlay line is OVERLAY_WORD_MIN..MAX words —
    AND the receipt's per-line word_counts are verified against the MEASURED words of
    s1-overlays.md (a receipt that lies within-range is caught by the measurement)."""
    r = _s1_receipt(run_dir)
    if r is None or (isinstance(r, dict) and "__parse_error__" in r):
        return ("AF-FBAD-OVERLAY-WORDCOUNT: s1-receipt.json absent/invalid — per-line "
                "word counts must be attested.")
    wcs = r.get("word_counts")
    if not isinstance(wcs, list) or not wcs:
        return ("AF-FBAD-OVERLAY-WORDCOUNT: s1-receipt.json carries no word_counts[] "
                "list (one integer per overlay line).")
    bad = [i + 1 for i, w in enumerate(wcs)
           if not isinstance(w, int) or w < OVERLAY_WORD_MIN or w > OVERLAY_WORD_MAX]
    if bad:
        return ("AF-FBAD-OVERLAY-WORDCOUNT: overlay line(s) "
                f"{bad[:10]} fall outside {OVERLAY_WORD_MIN}..{OVERLAY_WORD_MAX} words. "
                "An over-long line does not bake legibly into a 1:1 image.")
    measured = measure_overlays(run_dir)
    if measured is not None:
        if len(measured) != len(wcs):
            return ("AF-FBAD-OVERLAY-WORDCOUNT: the receipt lists "
                    f"{len(wcs)} word_counts but s1-overlays.md carries "
                    f"{len(measured)} overlay line(s) — receipt and deliverable disagree.")
        mism = [i + 1 for i, (w, mw) in enumerate(zip(wcs, measured)) if w != mw]
        if mism:
            first = mism[0] - 1
            return ("AF-FBAD-OVERLAY-WORDCOUNT: receipt word_counts disagree with the "
                    f"MEASURED s1-overlays.md at line(s) {mism[:10]} (e.g. line "
                    f"{mism[0]}: receipt says {wcs[first]}, the file has "
                    f"{measured[first]} word(s)). MEASURE the artifact — never trust a "
                    "self-reported count.")
    return ""


def _chk_overlay_topline(run_dir: Path) -> str:
    """AF-FBAD-OVERLAY-TOPLINE. The fixed locked top line must be present."""
    r = _s1_receipt(run_dir)
    if r is None or (isinstance(r, dict) and "__parse_error__" in r):
        return ("AF-FBAD-OVERLAY-TOPLINE: s1-receipt.json absent/invalid.")
    if r.get("top_line_present") is not True:
        return ("AF-FBAD-OVERLAY-TOPLINE: s1-receipt.json does not record "
                "top_line_present:true — the fixed locked lead line is missing.")
    return ""


def _chk_on_mission(run_dir: Path) -> str:
    """AF-FBAD-ON-MISSION. Copy must feature the guest/show, never 'sell a product'."""
    r = _s1_receipt(run_dir)
    if r is None or (isinstance(r, dict) and "__parse_error__" in r):
        return ("AF-FBAD-ON-MISSION: s1-receipt.json absent/invalid.")
    if r.get("on_mission") is not True:
        return ("AF-FBAD-ON-MISSION: s1-receipt.json does not record on_mission:true — "
                "the copy must FEATURE the guest/show, never 'sell a product'.")
    return ""


def _chk_audience_wording(run_dir: Path) -> str:
    """AF-FBAD-AUDIENCE-WORDING. The client's exact audience wording is preserved."""
    r = _s1_receipt(run_dir)
    if r is None or (isinstance(r, dict) and "__parse_error__" in r):
        return ("AF-FBAD-AUDIENCE-WORDING: s1-receipt.json absent/invalid.")
    if r.get("audience_wording_preserved") is not True:
        return ("AF-FBAD-AUDIENCE-WORDING: s1-receipt.json does not record "
                "audience_wording_preserved:true — the client's exact audience wording "
                "must be carried verbatim, never paraphrased away.")
    return ""


# ===========================================================================
# PICK-10 — AF-FBAD-SELECTION-COUNT / AF-FBAD-SELECTION-SUBSET
# ===========================================================================
def _selection_list(run_dir: Path):
    sel = _selection(run_dir)
    if isinstance(sel, dict) and "__parse_error__" not in sel:
        picks = sel.get("selection")
        if isinstance(picks, list):
            return picks, sel
    return None, sel


def _chk_selection_count(run_dir: Path) -> str:
    """AF-FBAD-SELECTION-COUNT. Exactly SELECTION_COUNT_LOCKED distinct picks."""
    picks, sel = _selection_list(run_dir)
    if picks is None:
        return ("AF-FBAD-SELECTION-COUNT: working/s1-selection.json is absent/invalid or "
                "carries no selection[] list — the pick-10 reply has not been captured.")
    if len(set(picks)) != SELECTION_COUNT_LOCKED:
        return ("AF-FBAD-SELECTION-COUNT: the selection has "
                f"{len(set(picks))} distinct pick(s), not the locked "
                f"{SELECTION_COUNT_LOCKED}. De-duplicate and re-confirm; a second reply "
                "replaces the first (never adds).")
    return ""


def _chk_selection_subset(run_dir: Path) -> str:
    """AF-FBAD-SELECTION-SUBSET. Every pick is a real in-range overlay index."""
    picks, sel = _selection_list(run_dir)
    if picks is None:
        return ("AF-FBAD-SELECTION-SUBSET: working/s1-selection.json absent/invalid.")
    n = None
    if isinstance(sel, dict):
        n = sel.get("overlay_count")
    if not isinstance(n, int) or n <= 0:
        r = _s1_receipt(run_dir)
        n = r.get("overlay_count") if isinstance(r, dict) else None
    if not isinstance(n, int) or n <= 0:
        n = OVERLAY_COUNT_LOCKED
    out_of_range = [p for p in picks if not isinstance(p, int) or p < 1 or p > n]
    if out_of_range:
        return ("AF-FBAD-SELECTION-SUBSET: pick(s) "
                f"{out_of_range[:10]} are not real in-range overlay indices (1..{n}). "
                "The selection must be a genuine subset of the overlays shown.")
    return ""


# ===========================================================================
# S2-PRIMARY-TEXT — AF-FBAD-BODY-HOOK / AF-FBAD-BODY-CTA / AF-FBAD-BODY-EMOJI
# ===========================================================================
def _s2_receipt(run_dir: Path):
    return _read_json(_checkpoints(run_dir) / "s2-receipt.json")


def _bodies(run_dir: Path):
    r = _s2_receipt(run_dir)
    if isinstance(r, dict) and "__parse_error__" not in r:
        b = r.get("bodies")
        if isinstance(b, list):
            return b
    return None


def _chk_body_hook(run_dir: Path) -> str:
    """AF-FBAD-BODY-HOOK. Every body opens with a hook <= BODY_HOOK_MAX_CHARS chars."""
    bodies = _bodies(run_dir)
    if bodies is None:
        return ("AF-FBAD-BODY-HOOK: working/checkpoints/s2-receipt.json absent/invalid or "
                "carries no bodies[] list.")
    bad = [i + 1 for i, b in enumerate(bodies)
           if not isinstance(b, dict) or not isinstance(b.get("hook_chars"), int)
           or b["hook_chars"] > BODY_HOOK_MAX_CHARS or b["hook_chars"] <= 0]
    if bad:
        return ("AF-FBAD-BODY-HOOK: body(s) "
                f"{bad[:10]} do not open with a hook within {BODY_HOOK_MAX_CHARS} "
                "characters (the above-the-fold line before 'See more').")
    return ""


def _chk_body_cta(run_dir: Path) -> str:
    """AF-FBAD-BODY-CTA. Every body carries exactly BODY_CTA_COUNT calls-to-action."""
    bodies = _bodies(run_dir)
    if bodies is None:
        return ("AF-FBAD-BODY-CTA: s2-receipt.json absent/invalid or no bodies[].")
    bad = [i + 1 for i, b in enumerate(bodies)
           if not isinstance(b, dict) or b.get("cta_count") != BODY_CTA_COUNT]
    if bad:
        return ("AF-FBAD-BODY-CTA: body(s) "
                f"{bad[:10]} do not carry exactly {BODY_CTA_COUNT} calls-to-action.")
    return ""


def _chk_body_emoji(run_dir: Path) -> str:
    """AF-FBAD-BODY-EMOJI. Every body's emoji count is BODY_EMOJI_MIN..MAX."""
    bodies = _bodies(run_dir)
    if bodies is None:
        return ("AF-FBAD-BODY-EMOJI: s2-receipt.json absent/invalid or no bodies[].")
    bad = [i + 1 for i, b in enumerate(bodies)
           if not isinstance(b, dict) or not isinstance(b.get("emoji_count"), int)
           or b["emoji_count"] < BODY_EMOJI_MIN or b["emoji_count"] > BODY_EMOJI_MAX]
    if bad:
        return ("AF-FBAD-BODY-EMOJI: body(s) "
                f"{bad[:10]} have an emoji count outside "
                f"{BODY_EMOJI_MIN}..{BODY_EMOJI_MAX} (emoji are a controlled "
                "scannability device, not decoration).")
    return ""


# ===========================================================================
# S3-HEADLINES — AF-FBAD-HEADLINE-SHAPE
# ===========================================================================
def _s3_receipt(run_dir: Path):
    return _read_json(_checkpoints(run_dir) / "s3-receipt.json")


def _chk_headline_shape(run_dir: Path) -> str:
    """AF-FBAD-HEADLINE-SHAPE. Every headline matches a locked shape."""
    r = _s3_receipt(run_dir)
    if r is None or (isinstance(r, dict) and "__parse_error__" in r):
        return ("AF-FBAD-HEADLINE-SHAPE: working/checkpoints/s3-receipt.json "
                "absent/invalid.")
    hs = r.get("headlines")
    if not isinstance(hs, list) or not hs:
        return ("AF-FBAD-HEADLINE-SHAPE: s3-receipt.json carries no headlines[] list.")
    locked = set(HEADLINE_SHAPES_LOCKED)
    bad = [i + 1 for i, h in enumerate(hs)
           if not isinstance(h, dict) or str(h.get("shape", "")).strip() not in locked]
    if bad:
        return ("AF-FBAD-HEADLINE-SHAPE: headline(s) "
                f"{bad[:10]} use a shape outside the locked {HEADLINE_SHAPES_LOCKED}.")
    return ""


# ===========================================================================
# S4-IMAGE-PROMPTS — order / richness / styleblock / QC
# ===========================================================================
def _s4_receipt(run_dir: Path):
    return _read_json(_checkpoints(run_dir) / "s4-receipt.json")


def _prompts(run_dir: Path):
    r = _s4_receipt(run_dir)
    if isinstance(r, dict) and "__parse_error__" not in r:
        p = r.get("prompts")
        if isinstance(p, list):
            return p
    return None


def _chk_prompt_order(run_dir: Path) -> str:
    """AF-FBAD-PROMPT-ORDER. Every prompt declares PROMPT_BUILD_ORDER sections in order."""
    prompts = _prompts(run_dir)
    if prompts is None:
        return ("AF-FBAD-PROMPT-ORDER: working/checkpoints/s4-receipt.json absent/invalid "
                "or no prompts[] list.")
    bad = []
    for i, p in enumerate(prompts):
        sections = p.get("sections") if isinstance(p, dict) else None
        if list(sections or []) != PROMPT_BUILD_ORDER:
            bad.append(i + 1)
    if bad:
        return ("AF-FBAD-PROMPT-ORDER: prompt(s) "
                f"{bad[:10]} do not declare the fixed build order {PROMPT_BUILD_ORDER}.")
    return ""


def _chk_prompt_richness(run_dir: Path) -> str:
    """AF-FBAD-PROMPT-RICHNESS. Every prompt is PROMPT_MIN_CHARS..MAX_CHARS chars."""
    prompts = _prompts(run_dir)
    if prompts is None:
        return ("AF-FBAD-PROMPT-RICHNESS: s4-receipt.json absent/invalid or no prompts[].")
    bad = [i + 1 for i, p in enumerate(prompts)
           if not isinstance(p, dict) or not isinstance(p.get("char_count"), int)
           or p["char_count"] < PROMPT_MIN_CHARS or p["char_count"] > PROMPT_MAX_CHARS]
    if bad:
        return ("AF-FBAD-PROMPT-RICHNESS: prompt(s) "
                f"{bad[:10]} fall outside {PROMPT_MIN_CHARS}..{PROMPT_MAX_CHARS} chars. "
                "A thin prompt yields generic art.")
    return ""


def _chk_prompt_styleblock(run_dir: Path) -> str:
    """AF-FBAD-PROMPT-STYLEBLOCK. Brand style-block + exact baked-in words per prompt."""
    prompts = _prompts(run_dir)
    if prompts is None:
        return ("AF-FBAD-PROMPT-STYLEBLOCK: s4-receipt.json absent/invalid or no prompts[].")
    bad = [i + 1 for i, p in enumerate(prompts)
           if not isinstance(p, dict) or p.get("styleblock_ok") is not True
           or p.get("baked_text_present") is not True]
    if bad:
        return ("AF-FBAD-PROMPT-STYLEBLOCK: prompt(s) "
                f"{bad[:10]} do not spell out the brand style-block AND the exact words "
                "to bake into the image. The model bakes the text — the exact text must "
                "be in the prompt.")
    return ""


# ===========================================================================
# Generic independent-QC validator (Gate A/B/C/D/E) + independence
# ===========================================================================
def _qc_path(run_dir: Path, gate: str) -> Path:
    return _qc_dir(run_dir) / QC_SCORECARDS[gate]


def _validate_qc_score(run_dir: Path, gate: str, af_code: str) -> str:
    """Shared scorecard validator: present, pass:true, average >= QC_MIN_AVERAGE,
    no category < QC_MIN_CATEGORY. Returns "" or an af_code:... fatal string."""
    sc = _read_json(_qc_path(run_dir, gate))
    if sc is None:
        return (f"{af_code}: working/qc/{QC_SCORECARDS[gate]} is absent — the gate "
                "needs an independent scorecard, not just a 'looks good'.")
    if isinstance(sc, dict) and "__parse_error__" in sc:
        return (f"{af_code}: {QC_SCORECARDS[gate]} is not valid JSON "
                f"({sc['__parse_error__']}).")
    cats = sc.get("categories")
    if not isinstance(cats, dict) or not cats:
        return (f"{af_code}: {QC_SCORECARDS[gate]} carries no categories{{}} scores "
                "(a bare number with no per-category reasons is itself a fail).")
    try:
        scores = [float(v) for v in cats.values()]
    except (TypeError, ValueError):
        return (f"{af_code}: {QC_SCORECARDS[gate]} category scores must be numbers.")
    low = sorted(k for k, v in cats.items() if float(v) < QC_MIN_CATEGORY)
    if low:
        return (f"{af_code}: category(ies) {low} are below the floor "
                f"{QC_MIN_CATEGORY} — one 10 can't hide a 4. The maker redoes only the "
                "failing pieces.")
    # The COMPUTED average (from the maker's own category scores) is the ONLY number
    # the pass test may use — a self-declared `average` can never override it. If a
    # declared average is present and disagrees with the computed one beyond a tiny
    # tolerance, that is itself an autofail (a fabricated or careless top-line number,
    # e.g. all categories at 7.0 with a declared 9.9).
    computed = sum(scores) / len(scores)
    declared = sc.get("average")
    if isinstance(declared, (int, float)):
        if abs(float(declared) - computed) > QC_DECLARED_AVG_TOLERANCE:
            return (f"{af_code}: {QC_SCORECARDS[gate]} self-declares average "
                    f"{float(declared):.2f} but its own category scores compute to "
                    f"{computed:.2f} (disagreement > {QC_DECLARED_AVG_TOLERANCE}). A "
                    "declared number NEVER overrides the measured one — fix the "
                    "categories or the declared average so they agree.")
    if computed < QC_MIN_AVERAGE:
        return (f"{af_code}: computed average {computed:.2f} (from the category scores) "
                f"is below the {QC_MIN_AVERAGE} pass line.")
    if sc.get("pass") is not True:
        return (f"{af_code}: {QC_SCORECARDS[gate]} does not set pass:true.")
    return ""


def _chk_copy_qc(run_dir: Path) -> str:
    """AF-FBAD-COPY-QC. Gate A (The Words) independent scorecard."""
    return _validate_qc_score(run_dir, "copy", "AF-FBAD-COPY-QC")


def _chk_prompt_qc(run_dir: Path) -> str:
    """AF-FBAD-PROMPT-QC. Gate B (Image Prompts) independent scorecard."""
    return _validate_qc_score(run_dir, "prompt", "AF-FBAD-PROMPT-QC")


def _chk_image_qc(run_dir: Path) -> str:
    """AF-FBAD-IMAGE-QC. Gate C (Images) independent VISION scorecard — this is where
    baked-in text legibility is judged now that the OCR step is dropped."""
    return _validate_qc_score(run_dir, "image", "AF-FBAD-IMAGE-QC")


def _chk_targeting_qc(run_dir: Path) -> str:
    """AF-FBAD-TARGETING-QC. Gate D (Targeting) independent scorecard."""
    return _validate_qc_score(run_dir, "targeting", "AF-FBAD-TARGETING-QC")


def _chk_package_qc(run_dir: Path) -> str:
    """AF-FBAD-PACKAGE-QC. Gate E (Final Package) independent Devil's-Advocate scorecard."""
    return _validate_qc_score(run_dir, "package", "AF-FBAD-PACKAGE-QC")


def _ledger_qc_sessions(run_dir: Path) -> dict:
    """Map gate -> the run ledger's independently-recorded grading session
    {grader, session_id} for that gate. The ledger's qc_sessions[] is written by the
    CONDUCTOR when it dispatches an independent grader — NOT by the maker or grader —
    so it is the independent record a self-attested scorecard is cross-checked against.
    Returns {} when the ledger has no qc_sessions."""
    led = _ledger(run_dir)
    out = {}
    if isinstance(led, dict) and "__parse_error__" not in led:
        for s in (led.get("qc_sessions") or []):
            if isinstance(s, dict) and s.get("gate"):
                out[str(s["gate"])] = s
    return out


def _chk_qc_independence(run_dir: Path) -> str:
    """AF-FBAD-QC-INDEPENDENCE. Every PRESENT scorecard must prove REAL independence,
    not merely self-assert it:
      * independent:true, a maker, a grader, and grader != maker;
      * BOTH maker and grader are REGISTERED role slugs (manifest roles[].id) — free
        text like 'some reviewer' is rejected;
      * the scorecard names a grader_session_id, and that session is cross-checked
        against the run ledger's independently-recorded qc_sessions[] (same gate, same
        session id, same grader). A grade the ledger never recorded is a self-attested
        grade and fails CLOSED."""
    roles = registered_role_slugs()   # empty set => manifest unresolved; slug leg skipped
    sessions = _ledger_qc_sessions(run_dir)
    for gate, fname in QC_SCORECARDS.items():
        sc = _read_json(_qc_path(run_dir, gate))
        if sc is None:
            continue  # absence is owned by that gate's own _chk_*_qc
        if isinstance(sc, dict) and "__parse_error__" in sc:
            return (f"AF-FBAD-QC-INDEPENDENCE: {fname} is not valid JSON.")
        if sc.get("independent") is not True:
            return (f"AF-FBAD-QC-INDEPENDENCE: {fname} does not set independent:true — "
                    "every grade must be written by a different worker than the maker.")
        maker = str(sc.get("maker", "")).strip().lower()
        grader = str(sc.get("grader", "")).strip().lower()
        if not maker or not grader:
            return (f"AF-FBAD-QC-INDEPENDENCE: {fname} is missing maker and/or grader — "
                    "the independence block must name both.")
        if maker == grader:
            return (f"AF-FBAD-QC-INDEPENDENCE: {fname} is self-graded (grader == maker "
                    f"== {maker!r}). The grader must NOT be the maker.")
        if roles:
            if maker not in roles:
                return (f"AF-FBAD-QC-INDEPENDENCE: {fname} maker {maker!r} is not a "
                        "registered role slug (AD-PIPELINE-MANIFEST roles[].id). A grade "
                        "must name real registered roles, never free text.")
            if grader not in roles:
                return (f"AF-FBAD-QC-INDEPENDENCE: {fname} grader {grader!r} is not a "
                        "registered role slug (AD-PIPELINE-MANIFEST roles[].id). The "
                        "grader must be a real registered QC/reviewer role.")
        session_id = str(sc.get("grader_session_id", "")).strip()
        if not session_id:
            return (f"AF-FBAD-QC-INDEPENDENCE: {fname} carries no grader_session_id — the "
                    "grading agent's session must be recorded so it can be tied back to "
                    "the run ledger, never a bare unverifiable claim.")
        entry = sessions.get(gate)
        if entry is None:
            return (f"AF-FBAD-QC-INDEPENDENCE: the run ledger records no qc_sessions "
                    f"entry for gate {gate!r} — a grade the ledger never saw is a "
                    "self-attested grade. The conductor must record every grading "
                    "session in ad_run_ledger.json.")
        if str(entry.get("session_id", "")).strip() != session_id:
            return (f"AF-FBAD-QC-INDEPENDENCE: {fname} grader_session_id "
                    f"{session_id!r} does not match the run ledger's recorded grading "
                    f"session for gate {gate!r} — the scorecard was not written by the "
                    "session the conductor dispatched.")
        if str(entry.get("grader", "")).strip().lower() != grader:
            return (f"AF-FBAD-QC-INDEPENDENCE: {fname} grader {grader!r} does not match "
                    f"the run ledger's recorded grader for gate {gate!r} "
                    f"({str(entry.get('grader', ''))!r}).")
    return ""


# ===========================================================================
# S5-IMAGE-GEN — task-id / size / model / running-tally / QC
# ===========================================================================
def _s5_receipt(run_dir: Path):
    return _read_json(_checkpoints(run_dir) / "s5-image-receipt.json")


def _images(run_dir: Path):
    r = _s5_receipt(run_dir)
    if isinstance(r, dict) and "__parse_error__" not in r:
        im = r.get("images")
        if isinstance(im, list):
            return im
    return None


def _chk_image_taskid(run_dir: Path) -> str:
    """AF-FBAD-IMAGE-TASKID. Every image carries a real (non-placeholder) kie_task_id.
    Defers for a free/dry run (no paid Kie call)."""
    if not _paid_in_scope(run_dir):
        return ""
    images = _images(run_dir)
    if images is None:
        return ("AF-FBAD-IMAGE-TASKID: working/checkpoints/s5-image-receipt.json "
                "absent/invalid or no images[] list — the task id is the "
                "anti-fabrication proof.")
    bad = []
    for i, im in enumerate(images):
        tid = str(im.get("kie_task_id", "") or "").strip() if isinstance(im, dict) else ""
        if not tid or tid.lower() in FABRICATED_TASK_ID_TOKENS:
            bad.append(i + 1)
    if bad:
        return ("AF-FBAD-IMAGE-TASKID: image(s) "
                f"{bad[:10]} carry no real kie_task_id (null/empty/placeholder). A "
                "missing task id means the image was not really generated.")
    return ""


def _chk_image_size(run_dir: Path) -> str:
    """AF-FBAD-IMAGE-SIZE. Every image is IMAGE_EDGE_PX x IMAGE_EDGE_PX (1:1 square)."""
    images = _images(run_dir)
    if images is None:
        return ("AF-FBAD-IMAGE-SIZE: s5-image-receipt.json absent/invalid or no images[].")
    bad = [i + 1 for i, im in enumerate(images)
           if not isinstance(im, dict) or im.get("width") != IMAGE_EDGE_PX
           or im.get("height") != IMAGE_EDGE_PX]
    if bad:
        return ("AF-FBAD-IMAGE-SIZE: image(s) "
                f"{bad[:10]} are not {IMAGE_EDGE_PX}x{IMAGE_EDGE_PX} (1:1). The "
                "Facebook/Instagram feed ad requires the locked square size.")
    return ""


def _chk_image_model(run_dir: Path) -> str:
    """AF-FBAD-IMAGE-MODEL. Every image model id starts with GPT_IMAGE_MODEL_PREFIX —
    so gpt-image-2 AND any future gpt-image-N are accepted with no code change."""
    images = _images(run_dir)
    if images is None:
        return ("AF-FBAD-IMAGE-MODEL: s5-image-receipt.json absent/invalid or no images[].")
    bad = []
    for i, im in enumerate(images):
        model = str(im.get("model", "") or "").strip().lower() if isinstance(im, dict) else ""
        if not model.startswith(GPT_IMAGE_MODEL_PREFIX):
            bad.append((i + 1, model or "<empty>"))
    if bad:
        return ("AF-FBAD-IMAGE-MODEL: image(s) "
                f"{[b[0] for b in bad[:10]]} use a model that does not start with "
                f"{GPT_IMAGE_MODEL_PREFIX!r} (got e.g. {bad[0][1]!r}). Generation must "
                "stay on the Kie gpt-image family (any version).")
    return ""


def _chk_tally_ceiling(run_dir: Path) -> str:
    """AF-FBAD-TALLY-CROSS. The cheap running tally never crossed the ceiling: ledger
    spent_usd <= ceiling AND no image recorded would_cross:true."""
    led = _ledger(run_dir)
    if led is None or (isinstance(led, dict) and "__parse_error__" in led):
        return ("AF-FBAD-TALLY-CROSS: ad_run_ledger.json absent/invalid — the running "
                "spend tally could not be confirmed.")
    cap = _ceiling(run_dir)
    spent = led.get("spent_usd")
    if isinstance(spent, (int, float)) and isinstance(cap, (int, float)) and spent > cap:
        return ("AF-FBAD-TALLY-CROSS: running spend tally "
                f"({spent}) crossed the ceiling ({cap}). Local arithmetic stops the run "
                "before the next paid image would cross — it must not have spent past it.")
    images = _images(run_dir) or []
    crossed = [i + 1 for i, im in enumerate(images)
               if isinstance(im, dict) and im.get("would_cross") is True]
    if crossed:
        return ("AF-FBAD-TALLY-CROSS: image entry(ies) "
                f"{crossed[:10]} recorded would_cross:true — the next paid image would "
                "have crossed the ceiling, so the run must STOP, not spend.")
    return ""


# ===========================================================================
# S6-TARGETING — shape / real-or-flagged / QC
# ===========================================================================
def _s6_targeting(run_dir: Path):
    return _read_json(_checkpoints(run_dir) / "s6-targeting.json")


def _chk_targeting_shape(run_dir: Path) -> str:
    """AF-FBAD-TARGETING-SHAPE. The brief is the PLAI 3-tier Group->Layer1/2/3 shape
    with a plain-English explanation per group."""
    t = _s6_targeting(run_dir)
    if t is None or (isinstance(t, dict) and "__parse_error__" in t):
        return ("AF-FBAD-TARGETING-SHAPE: working/checkpoints/s6-targeting.json "
                "absent/invalid.")
    groups = t.get("groups")
    if not isinstance(groups, list) or not groups:
        return ("AF-FBAD-TARGETING-SHAPE: s6-targeting.json carries no groups[] list.")
    for i, g in enumerate(groups):
        if not isinstance(g, dict):
            return (f"AF-FBAD-TARGETING-SHAPE: group {i + 1} is not an object.")
        if not str(g.get("explanation", "")).strip():
            return (f"AF-FBAD-TARGETING-SHAPE: group {i + 1} ({g.get('name')!r}) has no "
                    "plain-English explanation.")
        for layer in ("layer1", "layer2", "layer3"):
            if not isinstance(g.get(layer), list) or not g.get(layer):
                return (f"AF-FBAD-TARGETING-SHAPE: group {i + 1} ({g.get('name')!r}) is "
                        f"missing a non-empty {layer}. PLAI expects three interest layers "
                        "per group.")
    return ""


def _chk_targeting_real(run_dir: Path) -> str:
    """AF-FBAD-TARGETING-REAL. Every interest resolves to a real Meta entity OR is
    marked flagged_unverified. Inventing a Meta interest is forbidden."""
    t = _s6_targeting(run_dir)
    if t is None or (isinstance(t, dict) and "__parse_error__" in t):
        return ("AF-FBAD-TARGETING-REAL: s6-targeting.json absent/invalid.")
    interests = []
    groups = t.get("groups") or []
    for g in groups if isinstance(groups, list) else []:
        if not isinstance(g, dict):
            continue
        for layer in ("layer1", "layer2", "layer3"):
            for it in g.get(layer) or []:
                interests.append(it)
    if isinstance(t.get("interests"), list):
        interests += t["interests"]
    if not interests:
        return ("AF-FBAD-TARGETING-REAL: no interest entries found to verify.")
    for it in interests:
        if not isinstance(it, dict):
            return ("AF-FBAD-TARGETING-REAL: an interest entry is not an object "
                    "{name, resolved/meta_id | flagged_unverified}.")
        resolved = it.get("resolved") is True and str(it.get("meta_id", "")).strip()
        flagged = it.get("flagged_unverified") is True
        if not resolved and not flagged:
            return ("AF-FBAD-TARGETING-REAL: interest "
                    f"{it.get('name')!r} is neither resolved to a real Meta entity (a "
                    "real meta_id) NOR marked flagged_unverified. Never invent a Meta "
                    "interest — degrade to flagged_unverified instead.")
    return ""


# ===========================================================================
# S7-DELIVER — fanout / ghl-url / adtext-doc / plai-fields / board / QC
# ===========================================================================
def _s7_receipt(run_dir: Path):
    return _read_json(_checkpoints(run_dir) / "s7-deliver-receipt.json")


def _plai_brief(run_dir: Path):
    return _read_json(_working(run_dir) / "s7-plai-brief.json")


def _chk_fanout(run_dir: Path) -> str:
    """AF-FBAD-FANOUT. selection == bodies == headlines == prompts == images, all 1:1
    and all == SELECTION_COUNT_LOCKED."""
    r = _s7_receipt(run_dir)
    if r is None or (isinstance(r, dict) and "__parse_error__" in r):
        return ("AF-FBAD-FANOUT: working/checkpoints/s7-deliver-receipt.json "
                "absent/invalid.")
    counts = r.get("counts")
    if not isinstance(counts, dict):
        return ("AF-FBAD-FANOUT: s7-deliver-receipt.json carries no counts{} object "
                "(selection/bodies/headlines/prompts/images).")
    keys = ["selection", "bodies", "headlines", "prompts", "images"]
    vals = [counts.get(k) for k in keys]
    if any(not isinstance(v, int) for v in vals):
        return ("AF-FBAD-FANOUT: counts{} must carry integer "
                f"{keys}; got {counts!r}.")
    if len(set(vals)) != 1 or vals[0] != SELECTION_COUNT_LOCKED:
        return ("AF-FBAD-FANOUT: the 1:1 fan-out is broken — "
                f"{dict(zip(keys, vals))} are not all equal to "
                f"{SELECTION_COUNT_LOCKED}. Every chosen overlay maps to exactly one "
                "body, headline, prompt, and image.")
    return ""


def _chk_ghl_url(run_dir: Path) -> str:
    """AF-FBAD-GHL-URL. Every image hosted in GoHighLevel with a real public https URL
    + an HTTP-200 verification recorded."""
    r = _s7_receipt(run_dir)
    if r is None or (isinstance(r, dict) and "__parse_error__" in r):
        return ("AF-FBAD-GHL-URL: s7-deliver-receipt.json absent/invalid.")
    delivered = r.get("delivered")
    if not isinstance(delivered, list) or not delivered:
        return ("AF-FBAD-GHL-URL: s7-deliver-receipt.json carries no delivered[] list of "
                "hosted images.")
    for i, d in enumerate(delivered):
        if not isinstance(d, dict):
            return (f"AF-FBAD-GHL-URL: delivered[{i}] is not an object.")
        url = str(d.get("image_url", "") or "").strip()
        low = url.lower()
        if not low.startswith("https://"):
            return (f"AF-FBAD-GHL-URL: delivered image {i + 1} has no https GoHighLevel "
                    f"URL (got {url!r}).")
        if any(tok in low for tok in FABRICATED_URL_TOKENS):
            return (f"AF-FBAD-GHL-URL: delivered image {i + 1} URL looks fabricated "
                    f"({url!r}) — a placeholder link is never accepted.")
        if d.get("http_status") != 200:
            return (f"AF-FBAD-GHL-URL: delivered image {i + 1} has no recorded HTTP-200 "
                    f"verification (got http_status={d.get('http_status')!r}).")
    return ""


def _chk_adtext_doc(run_dir: Path) -> str:
    """AF-FBAD-ADTEXT-DOC. The copy-paste ad-text doc has SELECTION_COUNT_LOCKED
    Headline+Body block pairs matching the approved copy."""
    r = _s7_receipt(run_dir)
    if r is None or (isinstance(r, dict) and "__parse_error__" in r):
        return ("AF-FBAD-ADTEXT-DOC: s7-deliver-receipt.json absent/invalid.")
    pairs = r.get("adtext_block_pairs")
    if pairs != SELECTION_COUNT_LOCKED:
        return ("AF-FBAD-ADTEXT-DOC: the ad-text doc has "
                f"{pairs!r} Headline+Body block pairs, not the locked "
                f"{SELECTION_COUNT_LOCKED}. Each ad is two separate copy-paste blocks.")
    if r.get("adtext_matches_copy") is not True:
        return ("AF-FBAD-ADTEXT-DOC: s7-deliver-receipt.json does not record "
                "adtext_matches_copy:true — the doc must carry the approved copy "
                "verbatim, not a paraphrase.")
    return ""


def _chk_plai_fields(run_dir: Path) -> str:
    """AF-FBAD-PLAI-FIELDS. Every REQUIRED_PLAI_FIELDS field is present in the brief."""
    pb = _plai_brief(run_dir)
    if pb is None:
        return ("AF-FBAD-PLAI-FIELDS: working/s7-plai-brief.json is absent — PLAI's "
                "builder asks for every field.")
    if isinstance(pb, dict) and "__parse_error__" in pb:
        return (f"AF-FBAD-PLAI-FIELDS: s7-plai-brief.json is not valid JSON "
                f"({pb['__parse_error__']}).")
    missing = [f for f in REQUIRED_PLAI_FIELDS if pb.get(f) in (None, "", [], {})]
    if missing:
        return ("AF-FBAD-PLAI-FIELDS: PLAI brief is missing required field(s): "
                f"{', '.join(missing)}. All of {REQUIRED_PLAI_FIELDS} must be present.")
    return ""


def _chk_board(run_dir: Path) -> str:
    """AF-FBAD-BOARD. The job is on the Command Center board (campaign_id recorded)."""
    r = _s7_receipt(run_dir)
    if r is None or (isinstance(r, dict) and "__parse_error__" in r):
        return ("AF-FBAD-BOARD: s7-deliver-receipt.json absent/invalid.")
    cid = str(r.get("campaign_id", "") or "").strip()
    if not cid:
        return ("AF-FBAD-BOARD: s7-deliver-receipt.json carries no campaign_id — the "
                "campaign must be visible as one grouped campaign on the board (the "
                "campaign_id IS the receipt-number). Degrade-to-ungrouped is logged, not "
                "silent.")
    return ""


# ===========================================================================
# PUBLISH — AF-FBAD-APPROVE
# ===========================================================================
def _chk_approve(run_dir: Path) -> str:
    """AF-FBAD-APPROVE. The approve-to-publish receipt carries who + when + confirmed."""
    ar = _read_json(_checkpoints(run_dir) / "approval-receipt.json")
    if ar is None:
        return ("AF-FBAD-APPROVE: working/checkpoints/approval-receipt.json is absent — "
                "the second human pause cannot be skipped; publish only happens after an "
                "explicit owner approval.")
    if isinstance(ar, dict) and "__parse_error__" in ar:
        return (f"AF-FBAD-APPROVE: approval-receipt.json is not valid JSON "
                f"({ar['__parse_error__']}).")
    if not str(ar.get("approved_by", "")).strip():
        return ("AF-FBAD-APPROVE: approval-receipt.json lacks approved_by (the named "
                "approver).")
    if not str(ar.get("approval_received_at", "")).strip():
        return ("AF-FBAD-APPROVE: approval-receipt.json lacks approval_received_at (when "
                "the approval was given).")
    if ar.get("owner_confirmed") is not True:
        return ("AF-FBAD-APPROVE: approval-receipt.json does not set "
                "owner_confirmed:true — the owner must explicitly confirm before the "
                "PLAI handoff.")
    return ""


# ===========================================================================
# Phase-0 Kie balance preflight — AF-FBAD-KIE-BALANCE (shared with the driver)
# ===========================================================================
def _fetch_kie_balance(api_key: str, url: str = FBAD_KIE_CREDIT_URL,
                       timeout: int = 30) -> float:
    """GET the live Kie credit balance. Returns the numeric balance. Raises
    RuntimeError on a network/parse error so the caller fails LOUD rather than
    treating an unknown balance as 'enough'."""
    import urllib.request
    import urllib.error
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, urllib.error.HTTPError, OSError) as exc:
        raise RuntimeError(f"Kie credit endpoint unreachable ({url}): {exc}")
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Kie credit response is not JSON: {exc}; body={raw[:200]!r}")
    candidates = []
    if isinstance(obj, (int, float)):
        candidates.append(obj)
    if isinstance(obj, dict):
        data_val = obj.get("data")
        if isinstance(data_val, (int, float)):
            candidates.append(data_val)
        for container in (data_val if isinstance(data_val, dict) else None, obj):
            if not isinstance(container, dict):
                continue
            for k in ("credit", "credits", "balance", "remaining", "available"):
                v = container.get(k)
                if isinstance(v, (int, float)):
                    candidates.append(v)
    if not candidates:
        raise RuntimeError(f"Kie credit response carried no numeric balance: {raw[:200]!r}")
    return float(candidates[0])


def kie_balance_preflight(run_dir: Path, estimated_cost_usd: float,
                          api_key=None) -> str:
    """AF-FBAD-KIE-BALANCE. Phase-0 balance gate for a PAID job, run ONCE at start.
    Computes the estimated credit floor (estimated_cost_usd x FBAD_CREDIT_PER_USD x
    FBAD_KIE_BALANCE_FLOOR_MULTIPLIER), fetches the live Kie balance, and returns a
    fatal AF-FBAD-KIE-BALANCE string when balance < floor OR the balance cannot be
    verified. Defers (passes) for a free job (estimated_cost<=0) or when no API key is
    available on this box. An UNVERIFIABLE balance is a HARD ABORT."""
    if not estimated_cost_usd or estimated_cost_usd <= 0:
        return ""
    if not api_key:
        return ""  # no key to query on this box; deferred to the generation subprocess.
    estimated_floor = (float(estimated_cost_usd) * FBAD_CREDIT_PER_USD
                       * FBAD_KIE_BALANCE_FLOOR_MULTIPLIER)
    try:
        balance = _fetch_kie_balance(api_key)
    except RuntimeError as exc:
        return ("AF-FBAD-KIE-BALANCE: could not verify the Kie.ai credit balance before "
                f"generation ({exc}). An unverifiable balance is a HARD ABORT — never "
                "generate on an unknown balance. Fix the key/endpoint, or top up and "
                "retry.")
    if balance < estimated_floor:
        return ("AF-FBAD-KIE-BALANCE: Kie.ai credit balance is below the estimated floor "
                f"for this batch. balance={balance:g} credits, "
                f"estimated_floor={estimated_floor:g} (estimated_cost "
                f"${estimated_cost_usd:g} x {FBAD_CREDIT_PER_USD} credits/USD x "
                f"{FBAD_KIE_BALANCE_FLOOR_MULTIPLIER} headroom). HARD ABORT before any "
                "paid dispatch so the batch does not die mid-run. Top up and retry.")
    return ""


# ===========================================================================
# The checker registry (used by tests / the driver dispatch table).
# ===========================================================================
CHECKERS = {
    "_chk_brief_complete": _chk_brief_complete,
    "_chk_cost_ceiling": _chk_cost_ceiling,
    "_chk_run_ledger": _chk_run_ledger,
    "_chk_overlay_count": _chk_overlay_count,
    "_chk_overlay_wordcount": _chk_overlay_wordcount,
    "_chk_overlay_topline": _chk_overlay_topline,
    "_chk_on_mission": _chk_on_mission,
    "_chk_audience_wording": _chk_audience_wording,
    "_chk_copy_qc": _chk_copy_qc,
    "_chk_selection_count": _chk_selection_count,
    "_chk_selection_subset": _chk_selection_subset,
    "_chk_body_hook": _chk_body_hook,
    "_chk_body_cta": _chk_body_cta,
    "_chk_body_emoji": _chk_body_emoji,
    "_chk_headline_shape": _chk_headline_shape,
    "_chk_prompt_order": _chk_prompt_order,
    "_chk_prompt_richness": _chk_prompt_richness,
    "_chk_prompt_styleblock": _chk_prompt_styleblock,
    "_chk_prompt_qc": _chk_prompt_qc,
    "_chk_image_taskid": _chk_image_taskid,
    "_chk_image_size": _chk_image_size,
    "_chk_image_model": _chk_image_model,
    "_chk_tally_ceiling": _chk_tally_ceiling,
    "_chk_image_qc": _chk_image_qc,
    "_chk_targeting_shape": _chk_targeting_shape,
    "_chk_targeting_real": _chk_targeting_real,
    "_chk_targeting_qc": _chk_targeting_qc,
    "_chk_fanout": _chk_fanout,
    "_chk_ghl_url": _chk_ghl_url,
    "_chk_adtext_doc": _chk_adtext_doc,
    "_chk_plai_fields": _chk_plai_fields,
    "_chk_board": _chk_board,
    "_chk_package_qc": _chk_package_qc,
    "_chk_qc_independence": _chk_qc_independence,
    "_chk_approve": _chk_approve,
}


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("usage: ad_build_check.py RUN_DIR [checker_name]", file=sys.stderr)
        sys.exit(2)
    rd = Path(sys.argv[1]).resolve()
    if len(sys.argv) >= 3:
        fn = CHECKERS.get(sys.argv[2])
        if not fn:
            print(f"unknown checker {sys.argv[2]!r}; known: {sorted(CHECKERS)}",
                  file=sys.stderr)
            sys.exit(2)
        reason = fn(rd)
        print(reason or f"PASS — {sys.argv[2]}")
        sys.exit(3 if reason else 0)
    for name, fn in CHECKERS.items():
        reason = fn(rd)
        status = "FAIL" if reason else "pass"
        print(f"[{status}] {name}: {reason or 'ok'}")
