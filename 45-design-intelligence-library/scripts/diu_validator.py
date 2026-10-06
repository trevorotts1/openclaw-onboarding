#!/usr/bin/env python3
"""
diu_validator.py — DETERMINISTIC DESIGN-INTELLIGENCE-UNIT (DIU) ENFORCEMENT GATE.

================================================================================
Skill 45's binding gates were prose-only (prompt char tiers, the SOP-DIU-611
"coded hard stop" routing interlock, the >=4.0 fidelity gate + 3-strike loop).
Prose is not a gate. This is OUR stdlib-only code (no third-party deps) that turns
those three rules into MECHANICAL gates with receipts on disk and exit codes —
mirroring Skill 47's executive_producer.py pattern (deterministic, fail-soft
never; a violation is a hard non-zero exit an agent cannot narrate past).
================================================================================

WHAT IT ENFORCES (three sub-commands)

  prompt-caps  - MODEL MAX CEILING (KIE prompt rule 12).
      The prompt may never exceed the model's maxLength. The max comes from the shared
      enforcer shared-utils/kie_prompt_enforcer.py (Skill 74 prompt-budget: live schema,
      registry fallback), never from a table in this file. An assembled prompt over the max
      is a HARD FAIL (exit 3) and the message names the exact characters to cut.

  prompt-band  — GRAPHICS IMAGE PROTOCOL (GIP) PROMPT BANDS (_system/prompt-bands.json).
      A band is a QUALITY profile per asset class (density floor, text-bearing, endpoints).
      Prompt LENGTH is KIE prompt rule 12 and is checked through the shared enforcer against
      the model named by --model (default: the first endpoint of the band):
        * length below the 80 percent floor -> HARD FAIL (exit 3, AF-GIP-PROMPT-FLOOR):
          NOT submitted, NOT rendered, the message names the exact characters to ADD.
        * length above the model max (100 percent) -> HARD FAIL (exit 3, AF-DIU-PROMPT-CAP):
          the message names the exact characters to CUT.
        * 80 to 95 percent passes with a warning to expand (the writer targets 95 to 100).
        * a QUALITY defect (independent of length, exactly like AF-P13/P14/P-DENSITY)
          -> HARD FAIL (exit 6, AF-GIP-PROMPT-QUALITY): the negative block must name
          >= 6 of the 8 defect classes; a text-bearing band requires a per-string
          spelling-lock and the verbatim copy baked in; distinct-word density must
          clear the band floor (anti-padding); and when style reference images are
          attached (--style-ref) the STYLE-REFERENCE-ONLY directive is mandatory
          (MODEL-SPECS §4). Clearing the floor is NECESSARY, never SUFFICIENT.
          Text-bearing assets route to GPT Image 2.5 (`text_bearing_long`). There is no
          Ideogram text-bearing band: Ideogram V3 stays only on the non-social
          specialty `medium` band.

  route-check  — DIU ROUTING INTERLOCK (SOP-DIU-611 §D.1 "coded hard stop").
      An audience / webinar / funnel / sales / virtual-event deck CANNOT proceed on
      the DIU Style Rotation Engine (strategy-(b) pipeline). Any such deck routes to
      the Presentations department. Attempting to run one through the DIU is an
      architecture violation → HARD ABORT (exit 2). This is the code behind the
      prose "mechanical gate" the SOP claims.

  consent-check — CONSENT + MINOR + PII GATE (SOP-DIU-608 CONSENT.md, fail-closed).
      Real-person likeness generation requires an active, dated, unexpired consent
      record (personal-photo-shoot/{client-slug}/CONSENT.md front-matter), an
      attested-adult subject (Minors = HARD NO), and an at-rest protection
      attestation on the biometric IDENTITY store. Any missing/negative/ambiguous
      field, or an absent CONSENT.md, is a HARD FAIL (exit 4) — generation must
      not proceed. IDENTITY.md is only a pointer and is not read. Converts the
      prose consent rule into a coded hard stop.

  fidelity     — FIDELITY-SCORE RECEIPT + 3-STRIKE COUNTER (TEST-PROTOCOL.md §5).
      A card reaches `production` only when: average across all 12 dimensions
      >= 4.0 AND no single dimension < 3 AND ZERO hard-rule violations (one
      violation = automatic fail). Every test appends a RECEIPT to
      working/checkpoints/diu_fidelity_receipts.json (institutional memory —
      receipts are never deleted). The gate then reads the receipt history and
      counts CONSECUTIVE failures per (card, dimension): three consecutive
      failures on the same dimension = ESCALATE to the Chief Design Officer
      (exit 5) — "do not silently keep burning generations." A passing test on a
      dimension resets its streak.

EXIT CODES
    0 — pass (within cap / legal route / consent OK / fidelity pass, no 3rd strike;
        prompt-band: within [MIN, MAX] AND clears every quality tooth).
    2 — routing-interlock violation (AF-DIU-ROUTING-INTERLOCK) or usage error.
    3 — prompt over the model max (AF-DIU-PROMPT-CAP) OR under the band floor
        (AF-GIP-PROMPT-FLOOR) OR a fidelity FAIL that has not yet reached the 3rd
        consecutive strike.
    4 — consent/minor/PII gate failure (AF-DIU-CONSENT): consent unconfirmed, a
        minor, or the biometric IDENTITY store is unprotected — fail closed.
    5 — 3-strike escalation (AF-DIU-3-STRIKE): a dimension failed 3 consecutive
        times — escalate to CDO with the receipt evidence.
    6 — prompt-band QUALITY failure (AF-GIP-PROMPT-QUALITY): the length cleared the
        band but a quality tooth (8-class negative block / spelling-lock / verbatim
        copy / density / style-reference-only) did not — re-author, do not submit.

USAGE
    python3 diu_validator.py prompt-caps --model gpt-image-2-5-sunburst-text-to-image --prompt-file assembled.txt
    python3 diu_validator.py prompt-band --band text_bearing_long \
                --prompt-file assembled.txt --copy "Stop Guessing." [--style-ref] [--model MODEL_ID]
    python3 diu_validator.py prompt-band --band medium --prompt "…inline…" [--run-dir RUN]
    python3 diu_validator.py route-check --deck-kind webinar
    python3 diu_validator.py consent-check --consent-file personal-photo-shoot/<client-slug>/CONSENT.md
    python3 diu_validator.py fidelity --run-dir RUN --card-id FB-003 \
                --scores-file scores.json [--hard-rule-violation "text on face"]

This is a SCRIPT, not a manifest role/SOP. It has zero third-party imports so it
runs on any box with a stock Python 3.
"""

import argparse
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path


def _load_enforcer():
    """Find shared-utils/kie_prompt_enforcer.py (repo checkout or installed skills tree) and import it."""
    envd = os.environ.get("OPENCLAW_SKILLS_DIR")
    dirs = [p / "shared-utils" for p in Path(__file__).resolve().parents]
    dirs += ([Path(envd) / "shared-utils"] if envd else []) + [
        Path.home() / ".openclaw" / "skills" / "shared-utils", Path("/data/.openclaw/skills/shared-utils")]
    for d in dirs:
        if (d / "kie_prompt_enforcer.py").is_file():
            sys.path.insert(0, str(d))
            import kie_prompt_enforcer
            return kie_prompt_enforcer
    # No shared-utils beside this skill (a box may not ship it): the byte-identical embedded copy of the enforcer,
    # generated and hash-locked by scripts/embed-kie-prompt-enforcer.py. It enforces the same 80 percent floor and
    # 100 percent ceiling from its last-known limit table, and fails closed for a model it has no limit for.
    import importlib.util
    here = Path(__file__).resolve().parent / "_kie_prompt_enforcer_embedded.py"
    if here.is_file():
        spec = importlib.util.spec_from_file_location("kie_prompt_enforcer", here)
        mod = importlib.util.module_from_spec(spec)
        sys.modules["kie_prompt_enforcer"] = mod
        spec.loader.exec_module(mod)
        return mod
    raise ImportError("kie_prompt_enforcer not found (neither shared-utils nor the embedded copy beside this file)")


KPE = _load_enforcer()

# Model used when --model is not given and the band names no endpoint (drafts). Only the id is named here;
# its limit is read live by the enforcer.
DEFAULT_MODEL = "gpt-image-2-5-sunburst-text-to-image"

# ---------------------------------------------------------------------------
# 1) MODEL MAX CEILING: KIE prompt rule 12, through the shared enforcer.
# ---------------------------------------------------------------------------
def cmd_prompt_caps(args) -> int:
    if getattr(args, "tier", None):
        print(f"NOTE: --tier {args.tier} is retired and ignored; the ceiling is the model maxLength (rule 12).", file=sys.stderr)
    model = (getattr(args, "model", None) or DEFAULT_MODEL).strip()
    if args.prompt_file:
        p = Path(args.prompt_file)
        if not p.is_file():
            print(f"FATAL: --prompt-file not found: {p}", file=sys.stderr)
            return 2
        prompt = p.read_text(encoding="utf-8")
    elif args.prompt is not None:
        prompt = args.prompt
    else:
        print("FATAL: pass --prompt-file PATH or --prompt STR.", file=sys.stderr)
        return 2

    # ceiling only: this command never judges the floor (prompt-band does)
    v = KPE.check(model, prompt, kind="verbatim", fallback_max=KPE.last_known(model))
    if not v["ok"]:
        print("!" * 78, file=sys.stderr)
        print(f"FATAL AF-DIU-PROMPT-CAP: {v['message']}. Fall back to a model whose limit holds the "
              f"prompt or cut the stated characters; do NOT ship a prompt the endpoint will truncate.",
              file=sys.stderr)
        print("!" * 78, file=sys.stderr)
        return 3
    print(f"OK: prompt is {v['chars']}/{v['max']} chars for {model} (within the model max).")
    return 0


# ---------------------------------------------------------------------------
# 2) DIU ROUTING INTERLOCK — SOP-DIU-611 §D.1 (coded hard stop).
# ---------------------------------------------------------------------------
# Deck kinds that MUST route to the Presentations department and CANNOT run on
# the DIU Style Rotation Engine. Matched case-insensitively as whole words so
# "webinar-deck", "virtual event", "sales funnel", "audience deck" all trip it.
_INTERLOCK_TERMS = [
    "webinar",
    "funnel",
    "sales",          # SKILL.md §"NOT owned by Skill 45" names sales decks; a bare
                      # "sales deck" must trip the interlock, not only "sales funnel".
    "audience",
    "virtual event",
    "virtual-event",
]
# DIU-legal deck kinds (informational — the Rotation Engine's own domain).
_DIU_LEGAL = ["strategy", "brand", "campaign", "pitch", "portfolio", "internal"]


def cmd_route_check(args) -> int:
    kind = (args.deck_kind or "").strip().lower()
    if not kind:
        print("FATAL: --deck-kind is required (e.g. webinar, brand, campaign).",
              file=sys.stderr)
        return 2
    for term in _INTERLOCK_TERMS:
        if re.search(r"(?:^|[^a-z])" + re.escape(term) + r"(?:$|[^a-z])", kind):
            print("!" * 78, file=sys.stderr)
            print(f"FATAL AF-DIU-ROUTING-INTERLOCK: a {args.deck_kind!r} deck matches a "
                  f"CLIENT-WEBINAR-DECK-SOP archetype ({term!r}) and CANNOT proceed on the "
                  f"DIU Style Rotation Engine (strategy-(b) pipeline). Per SOP-DIU-611 §D.1 "
                  f"this is a mechanical gate, not a preference: HALT the DIU workflow and "
                  f"route to CDO for forwarding to the Presentations Director. Proceeding "
                  f"would assemble the deck from bare backgrounds + overlay text boxes — an "
                  f"AUTO-FAIL at final QC.", file=sys.stderr)
            print("!" * 78, file=sys.stderr)
            return 2
    print(f"OK: deck-kind {args.deck_kind!r} is DIU-routable "
          f"(no CLIENT-WEBINAR-DECK-SOP archetype match). Rotation Engine may proceed.")
    return 0


# ---------------------------------------------------------------------------
# 2b) CONSENT + MINOR + PII GATE — SOP-DIU-608 CONSENT.md (fail-closed).
# ---------------------------------------------------------------------------
# Generating a REAL person's likeness (personal-photo-shoot) is gated on documented
# consent, an ABSOLUTE minor prohibition (Minors = HARD NO), and protection of the
# biometric IDENTITY store. The ONE machine-read record is the per-client CONSENT.md
# (SOP-DIU-608): YAML front-matter with status / created / expiry_date / adult_attested /
# storage_protection. IDENTITY.md only carries a pointer to it and is never read here.
# FAILS CLOSED (exit 4, AF-DIU-CONSENT) on ANY missing / negative / ambiguous field, or if
# the file is absent. Consent that "cannot be confirmed" must block, never default open.
_PROTECT_OK = {"encrypted-at-rest", "encrypted_at_rest", "encrypted", "restricted",
               "redacted", "access-restricted", "access_restricted"}
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _consent_front_matter(text):
    """Flat {key: value} map from the leading `---` YAML front-matter block (stdlib only:
    one `key: value` per line, nested/list lines ignored, `# comments` and quotes stripped).
    Returns {} when there is no front-matter block, which fails closed downstream."""
    lines = text.splitlines()
    i = 0
    while i < len(lines) and not lines[i].strip():
        i += 1
    if i >= len(lines) or lines[i].strip() != "---":
        return {}
    out = {}
    for raw in lines[i + 1:]:
        if raw.strip() == "---":
            break
        if not raw or raw[0] in " \t#-":
            continue
        m = re.match(r"([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(.*)$", raw)
        if not m:
            continue
        val = m.group(2).strip()
        if val[:1] in "\"'":
            q = val[0]
            end = val.find(q, 1)
            val = val[1:end] if end > 0 else val[1:]
        else:
            val = val.split(" #", 1)[0].strip()
        out[m.group(1).lower()] = val.strip().lower()
    return out


def cmd_consent_check(args) -> int:
    # `identity_file` is the pre-CONSENT.md attribute name; kept so older callers and the
    # self-tests below still reach this gate (the path must now be a CONSENT.md).
    path = getattr(args, "consent_file", None) or getattr(args, "identity_file", None)
    p = Path(path)
    problems = []
    if not p.is_file():
        print("!" * 78, file=sys.stderr)
        print(f"FATAL AF-DIU-CONSENT: CONSENT.md not found: {p}. Consent CANNOT be "
              f"confirmed -> fail closed; do NOT generate this person's likeness. "
              f"(Create the record per SOP-DIU-608; an IDENTITY.md is not read.)",
              file=sys.stderr)
        print("!" * 78, file=sys.stderr)
        return 4
    fm = _consent_front_matter(p.read_text(encoding="utf-8"))

    # (1) Documented, dated, active, unexpired consent.
    status = fm.get("status", "")
    if status != "active":
        problems.append(f"consent status is {status or 'missing'!r}; SOP-DIU-608 requires "
                        f"'status: active'")
    if not _ISO_DATE.match(fm.get("created", "")):
        problems.append("no consent date present (need 'created: YYYY-MM-DD')")
    expiry = fm.get("expiry_date", "")
    if expiry and expiry not in ("null", "none", "~"):
        if not _ISO_DATE.match(expiry):
            problems.append(f"expiry_date {expiry!r} is not YYYY-MM-DD")
        elif expiry <= time.strftime("%Y-%m-%d"):
            problems.append(f"consent expired on {expiry}; renew per SOP-DIU-608")

    # (2) Minor gate — HARD NO. Fail closed unless the subject is EXPLICITLY attested adult.
    if fm.get("minors", "hard_block") != "hard_block":
        problems.append("'minors' must stay 'hard_block' (never overridden, SOP-DIU-608)")
    if fm.get("adult_attested", "") not in ("true", "yes"):
        problems.append("subject not attested adult (need 'adult_attested: true'); "
                        "minors are HARD NO -> fail closed")

    # (3) Biometric PII protection — the IDENTITY.md descriptors are biometric PII; require an
    # explicit at-rest protection attestation so they are never assumed plaintext-OK.
    protection = fm.get("storage_protection", "")
    if not (set(re.split(r"[^a-z0-9_-]+", protection)) & _PROTECT_OK):
        problems.append(f"IDENTITY biometric store protection not attested (got "
                        f"{protection!r}); need 'storage_protection: encrypted-at-rest' "
                        f"-- descriptors must not be stored plaintext")

    if problems:
        print("!" * 78, file=sys.stderr)
        print(f"FATAL AF-DIU-CONSENT: {p} FAILS the fail-closed consent/minor/PII gate "
              f"(SOP-DIU-608). Do NOT generate this person's likeness:", file=sys.stderr)
        for i, pr in enumerate(problems, 1):
            print(f"  {i}. {pr}", file=sys.stderr)
        print("!" * 78, file=sys.stderr)
        return 4
    print(f"OK: consent active + dated, subject attested adult, biometric store protection "
          f"declared -> likeness generation may proceed ({p}).")
    return 0


# ---------------------------------------------------------------------------
# 3) FIDELITY RECEIPT + 3-STRIKE — TEST-PROTOCOL.md §5.
# ---------------------------------------------------------------------------
# The 12 style dimensions the RAW PNG is graded on.
DIMENSIONS = [
    "render", "composition", "subject", "color", "grading", "lighting",
    "typography", "layering", "subject_background", "negative_space",
    "workflow", "unity",
]
FIDELITY_AVG_MIN = 4.0     # average across all 12 dimensions
FIDELITY_DIM_MIN = 3       # no single dimension may score below this
STRIKE_LIMIT = 3           # 3 consecutive fails on one dimension -> escalate


def _receipts_path(run_dir: Path) -> Path:
    return run_dir / "working" / "checkpoints" / "diu_fidelity_receipts.json"


def _load_receipts(run_dir: Path) -> list:
    p = _receipts_path(run_dir)
    if not p.exists():
        return []
    try:
        obj = json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return []
    if isinstance(obj, dict):
        obj = obj.get("receipts", [])
    return obj if isinstance(obj, list) else []


def _normalize_scores(raw) -> dict:
    """Accept {dim: score} (extra/aliased keys tolerated) or an ordered list of
    12 numbers. Returns {dim: int} for the canonical 12 dimensions."""
    scores = {}
    if isinstance(raw, list):
        if len(raw) != len(DIMENSIONS):
            raise ValueError(
                f"score list has {len(raw)} entries; expected {len(DIMENSIONS)} "
                f"(one per dimension, in order: {DIMENSIONS}).")
        for dim, val in zip(DIMENSIONS, raw):
            scores[dim] = int(val)
        return scores
    if isinstance(raw, dict):
        def _key(k):
            return str(k).strip().lower().replace("-", "_").replace(" ", "_")
        by_norm = {_key(k): v for k, v in raw.items()}
        missing = [d for d in DIMENSIONS if d not in by_norm]
        if missing:
            raise ValueError(f"scores missing dimension(s): {missing}. "
                             f"All 12 required: {DIMENSIONS}.")
        for dim in DIMENSIONS:
            scores[dim] = int(by_norm[dim])
        return scores
    raise ValueError("scores must be a JSON object {dim: score} or a list of 12 numbers.")


def cmd_fidelity(args) -> int:
    run_dir = Path(args.run_dir).resolve()
    if not run_dir.is_dir():
        print(f"FATAL: --run-dir not found: {run_dir}", file=sys.stderr)
        return 2
    card_id = (args.card_id or "").strip()
    if not card_id:
        print("FATAL: --card-id is required.", file=sys.stderr)
        return 2

    if args.scores_file:
        sp = Path(args.scores_file)
        if not sp.is_file():
            print(f"FATAL: --scores-file not found: {sp}", file=sys.stderr)
            return 2
        raw = json.loads(sp.read_text(encoding="utf-8"))
    elif args.scores:
        raw = json.loads(args.scores)
    else:
        print("FATAL: pass --scores-file PATH or --scores JSON.", file=sys.stderr)
        return 2

    try:
        scores = _normalize_scores(raw)
    except ValueError as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        return 2
    for dim, val in scores.items():
        if val < 1 or val > 5:
            print(f"FATAL: dimension {dim!r} score {val} out of range 1-5.",
                  file=sys.stderr)
            return 2

    hard_violations = [v for v in (args.hard_rule_violation or []) if str(v).strip()]
    avg = round(sum(scores.values()) / len(scores), 3)
    below_min = sorted([d for d, v in scores.items() if v < FIDELITY_DIM_MIN])
    # A dimension "fails" this test if it is below the floor. Hard-rule violations
    # fail the WHOLE test regardless of scores (they are not per-dimension).
    failed_dims = below_min
    passed = (avg >= FIDELITY_AVG_MIN and not below_min and not hard_violations)

    receipt = {
        "card_id": card_id,
        "scores": scores,
        "avg": avg,
        "below_min_dimensions": below_min,
        "hard_rule_violations": hard_violations,
        "failed_dimensions": failed_dims,
        "passed": passed,
        "avg_min": FIDELITY_AVG_MIN,
        "dim_min": FIDELITY_DIM_MIN,
        "tested_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }

    # Append (never clobber) — receipts are the card's institutional memory.
    prior = _load_receipts(run_dir)
    ledger = prior + [receipt]
    rp = _receipts_path(run_dir)
    rp.parent.mkdir(parents=True, exist_ok=True)
    rp.write_text(json.dumps({"receipts": ledger}, indent=2) + "\n", encoding="utf-8")

    # 3-strike counter — consecutive fails per dimension for THIS card, across the
    # full receipt history (including this one). A pass on a dimension resets it.
    streaks = {d: 0 for d in DIMENSIONS}
    max_streak = 0
    escalate_dims = []
    for rec in ledger:
        if rec.get("card_id") != card_id:
            continue
        rec_failed = set(rec.get("failed_dimensions") or [])
        # A hard-rule violation fails EVERY graded dimension for streak purposes
        # (the whole PNG is rejected), so a repeated hard-rule miss also escalates.
        if rec.get("hard_rule_violations"):
            rec_failed = set(DIMENSIONS)
        for d in DIMENSIONS:
            if d in rec_failed:
                streaks[d] += 1
                if streaks[d] >= STRIKE_LIMIT and d not in escalate_dims:
                    escalate_dims.append(d)
            else:
                streaks[d] = 0
        max_streak = max(max_streak, max(streaks.values()))

    print(f"=== FIDELITY TEST — card {card_id} ===")
    print(f"  avg={avg} (min {FIDELITY_AVG_MIN})  below-floor dims={below_min or 'none'}  "
          f"hard-rule violations={hard_violations or 'none'}")
    print(f"  receipt appended -> {rp}")

    if escalate_dims:
        print("!" * 78, file=sys.stderr)
        print(f"ESCALATE AF-DIU-3-STRIKE: card {card_id} has {STRIKE_LIMIT} consecutive "
              f"failed fidelity tests on dimension(s) {sorted(escalate_dims)}. Per "
              f"TEST-PROTOCOL.md §5, STOP patching and escalate to the Chief Design "
              f"Officer with the receipt evidence at {rp} — do not silently keep burning "
              f"generations. CDO decides: retire the card, escalate to owner, or authorize "
              f"a different approach.", file=sys.stderr)
        print("!" * 78, file=sys.stderr)
        return 5

    if not passed:
        print(f"FAIL AF-DIU-FIDELITY: card {card_id} did not reach production "
              f"(need avg>={FIDELITY_AVG_MIN}, no dim<{FIDELITY_DIM_MIN}, zero hard-rule "
              f"violations). Patch the failed dimension(s) and re-run only the failed "
              f"test. Consecutive-fail streak so far: {max_streak}/{STRIKE_LIMIT}.",
              file=sys.stderr)
        return 3

    print(f"PASS: card {card_id} meets production fidelity (avg {avg}, no floor breach, "
          f"no hard-rule violation).")
    return 0


# ---------------------------------------------------------------------------
# 4) GRAPHICS IMAGE PROTOCOL (GIP) PROMPT BANDS — _system/prompt-bands.json.
# ---------------------------------------------------------------------------
# The MAX-only cap tiers (cmd_prompt_caps) let a one-line prompt reach the paid API
# unchallenged: there was NO minimum floor anywhere in graphics. This is the graphics
# analogue of the Presentations 9,000-char floor + quality gate (build_deck.py /
# prompt_gate.py), driven by the per-asset-class bands in prompt-bands.json. The gate
# is TWO independent halves, mirroring presentations exactly:
#   (1) LENGTH — a HARD MIN floor (AF-GIP-PROMPT-FLOOR) + the MAX cap (AF-DIU-PROMPT-CAP).
#   (2) QUALITY — length-independent teeth (AF-GIP-PROMPT-QUALITY): the 8-class negative
#       block, per-string spelling-lock + verbatim copy (text-bearing bands), distinct-word
#       density, and the mandatory style-reference-only directive when refs are attached.
# Clearing the floor is NECESSARY, never SUFFICIENT.

# The default location of the bands config, relative to this script (skill 45 layout:
# scripts/diu_validator.py + library/_system/prompt-bands.json). A --bands-file override
# exists for tests; the on-box runtime always uses the shipped default.
_BANDS_PATH = Path(__file__).resolve().parent.parent / "library" / "_system" / "prompt-bands.json"

# AF-GIP-QUALITY tokens — the EIGHT mandatory negative-block defect CLASSES. Adapted from
# the presentations 8-class negative block (build_deck.py / prompt_gate NEGATIVE_BLOCK_CLASS_
# TOKENS). A class is "named" when >=1 of its tolerant tokens is present in the prompt. The
# band gate requires the negative block to name at least GIP_MIN_NEGATIVE_CLASSES of the 8.
GIP_NEGATIVE_CLASS_TOKENS = {
    "garbled/misspelled text": [
        "misspell", "garble", "letter-for-letter", "letter for letter",
        "render every quoted", "exactly as written", "render every letter", "no invented text"],
    "logo mutation": [
        "logo", "monogram", "tagline lockup", "reference mark", "redraw",
        "redesign", "recolor", "restyle", "reinterpret", "invent a"],
    "anatomical artifacts": [
        "finger", "fused hand", "malformed", "anatom", "distorted facial",
        "mismatched eye", "asymmetric eye", "distorted teeth", "extra limb", "body proportion"],
    "contrast/legibility": [
        "busy", "cluttered", "high-detail background", "compete", "behind any text",
        "text zone", "scrim", "legib", "negative space", "contrast"],
    "placeholder/bracket tokens": [
        "bracketed token", "square bracket", "placeholder", "tbd", "build note",
        "to supply", "pending token", "insert token", "owner to confirm"],
    "demographic default / skin-tone fidelity": [
        "demographic", "skin tone", "skin-tone", "representation", "lighten",
        "ashen", "desaturate", "mono-cast", "mono cast", "deep skin"],
    "watermark / universal baseline": [
        "watermark", "emoji", "clipart", "default font", "calibri", "arial",
        "times new roman", "system default", "ui artifact", "user-interface"],
    "style-drift": [
        "style drift", "style-drift", "off-brand", "off brand", "off-palette",
        "off palette", "deviate from the style", "inconsistent style", "outside the style card",
        "outside the brand", "palette drift"],
}
GIP_MIN_NEGATIVE_CLASSES = 6  # per spec: the negative block must name >= 6 of the 8 classes.

# Per-string SPELLING-LOCK marker tokens (text-bearing bands). At least one must be present.
GIP_SPELLING_LOCK_TOKENS = [
    "spelling-lock", "spelling lock", "letter-for-letter", "letter for letter",
    "render this exact string", "reads exactly", "render every quoted text string exactly",
    "spelled exactly", "exact spelling", "render every letter", "correctly spelled",
]

# STYLE-REFERENCE-ONLY directive tokens (mandatory whenever refs are attached for style —
# MODEL-SPECS §4 "MANDATORY … applies equally to GPT-Image 2.5 I2I").
GIP_STYLE_REF_ONLY_TOKENS = [
    "style reference only", "style-reference only", "style-reference-only",
    "only as style reference", "as style reference", "only for style reference",
    "do not copy their subjects", "do not copy their faces", "do not copy their text",
    "reference for color grading",
]

# Forbidden hardcoded demographic-default landmines (AF-R3, ported from prompt_gate). A prompt
# must never bake in a default demographic split — representation comes from the client's
# captured audience/casting ledger.
GIP_FORBIDDEN_DEMOGRAPHIC_DEFAULTS = [
    "60/30/10", "60-30-10", "default demographic", "default ethnicity", "default race",
    "default skin tone", "default skin-tone", "standard demographic mix",
    "standard representation mix", "assume the audience is", "assumed demographic",
    "inferred demographic", "system default demographic",
]

_GIP_WORD_RE = re.compile(r"[a-z0-9][a-z0-9'\-]+")


def _gip_norm_ws(s: str) -> str:
    return re.sub(r"\s+", " ", str(s)).strip().lower()


def load_bands(bands_file=None) -> dict:
    """Load and validate prompt-bands.json. Returns the {band_id: band} mapping.
    Raises FileNotFoundError / ValueError (fail loud — a missing/broken bands config is a
    hard stop, never a silent default)."""
    p = Path(bands_file) if bands_file else _BANDS_PATH
    if not p.is_file():
        raise FileNotFoundError(
            f"prompt-bands.json not found at {p} — the GIP band config is required "
            "(ship 45-design-intelligence-library/library/_system/prompt-bands.json).")
    obj = json.loads(p.read_text(encoding="utf-8"))
    bands = obj.get("bands") if isinstance(obj, dict) else None
    if not isinstance(bands, dict) or not bands:
        raise ValueError(f"{p}: no 'bands' object — malformed prompt-bands config.")
    return bands


def _resolve_band(band_id: str, bands: dict) -> dict:
    key = (band_id or "").strip()
    if key not in bands:
        raise ValueError(
            f"unknown band {band_id!r} — valid bands: {sorted(bands)}. "
            "Declare 'ASSET: <class> | BAND: <band-id>' on the prompt's first line (SOP-GIP-01).")
    return bands[key]


def _is_text_bearing(band: dict) -> bool:
    return bool(band.get("text_bearing"))


def band_model(band: dict, model=None) -> str:
    """The KIE model whose maxLength sets the length band: --model, else the band's first endpoint."""
    return (model or (band.get("endpoints") or [DEFAULT_MODEL])[0]).strip()


def band_length_problems(prompt_text: str, band: dict, band_id: str, model=None) -> list:
    """LENGTH half = KIE prompt rule 12 through the shared enforcer. Returns a list of (af_code, message).
    AF-GIP-PROMPT-FLOOR when under the 80 percent floor (message names the chars to add); AF-DIU-PROMPT-CAP
    when over the model max (message names the chars to cut). Empty when inside the band."""
    stripped = prompt_text.strip()
    mdl = band_model(band, model)
    if not stripped:
        return [("AF-GIP-PROMPT-FLOOR",
                 f"prompt is empty / whitespace-only; it carries none of the mandatory per-asset {band_id} spec.")]
    v = KPE.check(mdl, prompt_text, fallback_max=KPE.last_known(mdl))
    if v["ok"]:
        return []
    code = "AF-DIU-PROMPT-CAP" if v["status"] == "ABOVE_MAX" else "AF-GIP-PROMPT-FLOOR"
    return [(code, v["message"] + (". NOT submitted, NOT rendered. Re-author (never truncate up to the floor)."
                                   if code == "AF-GIP-PROMPT-FLOOR" else
                                   ". Fall back to a model that holds the prompt; do not ship one the endpoint truncates."))]


def band_quality_problems(prompt_text: str, band: dict, band_id: str,
                          copy_val=None, style_ref: bool = False) -> list:
    """QUALITY half (length-independent, AF-GIP-PROMPT-QUALITY). Returns a list of fatal
    problem strings (empty = clears every quality tooth). Teeth:
      * the negative block must name >= GIP_MIN_NEGATIVE_CLASSES of the 8 defect classes;
      * a text-bearing band requires a per-string spelling-lock directive AND the verbatim
        copy baked into the body (when copy is supplied);
      * distinct-word density must clear the band's min_distinct_words floor (anti-padding);
      * when style refs are attached (style_ref), the style-reference-only directive is
        MANDATORY (MODEL-SPECS §4);
      * no forbidden hardcoded demographic-default landmine (AF-R3)."""
    prompt_lc = prompt_text.lower()
    problems = []

    # (a) 8-class negative block coverage.
    named = [cls for cls, toks in GIP_NEGATIVE_CLASS_TOKENS.items()
             if any(t in prompt_lc for t in toks)]
    if len(named) < GIP_MIN_NEGATIVE_CLASSES:
        missing = [c for c in GIP_NEGATIVE_CLASS_TOKENS if c not in named]
        problems.append(
            f"AF-GIP-PROMPT-QUALITY: negative block names only {len(named)}/8 defect classes "
            f"(floor {GIP_MIN_NEGATIVE_CLASSES}); a final-paragraph 'Do not…' block must cover "
            f"at least {GIP_MIN_NEGATIVE_CLASSES}. Not yet named: {', '.join(missing)}.")

    # (b) distinct-word density (anti paste-repetition padding).
    floor_words = int(band.get("min_distinct_words", 0))
    distinct = len(set(_GIP_WORD_RE.findall(prompt_lc)))
    if floor_words and distinct < floor_words:
        problems.append(
            f"AF-GIP-PROMPT-QUALITY: only {distinct} distinct words (band floor {floor_words}) "
            "— a long file with few distinct words is paste-repetition padding, not a rich spec.")

    # (c) text-bearing bands: spelling-lock + verbatim copy baked in.
    if _is_text_bearing(band):
        if not any(t in prompt_lc for t in GIP_SPELLING_LOCK_TOKENS):
            problems.append(
                "AF-GIP-PROMPT-QUALITY: text-bearing band but NO per-string spelling-lock "
                "directive (e.g. 'render this exact string, letter-for-letter, correctly "
                "spelled') — every verbatim on-image string must be spelling-locked (SOP-GIP-01 "
                "element 5). A verbatim string without its lock is an AUTO-FAIL.")
        if copy_val is not None:
            strings = copy_val if isinstance(copy_val, list) else [copy_val]
            prompt_norm = _gip_norm_ws(prompt_text)
            missing_copy = []
            for c in strings:
                cn = _gip_norm_ws(c)
                if len(cn) < 3:
                    continue
                if cn not in prompt_norm:
                    missing_copy.append(str(c) if len(str(c)) <= 60 else str(c)[:57] + "...")
            if missing_copy:
                problems.append(
                    "AF-GIP-PROMPT-QUALITY: the asset's exact copy is NOT baked into the prompt "
                    "body verbatim (kie.ai must bake the words, never overlaid): "
                    + " | ".join(missing_copy))

    # (d) style-reference-only directive when refs attached for style.
    if style_ref and not any(t in prompt_lc for t in GIP_STYLE_REF_ONLY_TOKENS):
        problems.append(
            "AF-GIP-PROMPT-QUALITY: style reference image(s) attached (--style-ref) but the "
            "STYLE-REFERENCE-ONLY directive is absent (MODEL-SPECS §4, MANDATORY for GPT-Image 2.5 "
            "I2I / Nano Banana 2): add 'Use the attached images only as style reference for color "
            "grading, lighting, and composition — do not copy their subjects, faces, or text.'")

    # (e) forbidden hardcoded demographic-default landmine (AF-R3).
    for landmine in GIP_FORBIDDEN_DEMOGRAPHIC_DEFAULTS:
        if landmine.lower() in prompt_lc:
            problems.append(
                f"AF-GIP-PROMPT-QUALITY: forbidden hardcoded demographic default {landmine!r} "
                "(AF-R3) — representation must come from the client's captured audience / casting "
                "ledger, never a baked-in default split.")
            break

    return problems


def band_problems(prompt_text: str, band: dict, band_id: str,
                  copy_val=None, style_ref: bool = False, model=None) -> dict:
    """Accumulating (non-raising) form used by the prover and the CLI. Returns
    {'length': [(code, msg), ...], 'quality': [msg, ...]} — empty lists = clears the whole
    band gate."""
    return {
        "length": band_length_problems(prompt_text, band, band_id, model),
        "quality": band_quality_problems(prompt_text, band, band_id, copy_val, style_ref),
    }


def _band_receipts_path(run_dir: Path) -> Path:
    return run_dir / "working" / "checkpoints" / "diu_prompt_band_receipts.json"


def cmd_prompt_band(args) -> int:
    band_id = (args.band or "").strip()
    if not band_id:
        print("FATAL: --band is required (e.g. text_bearing_long | visual_long | medium | "
              "short_draft).", file=sys.stderr)
        return 2
    try:
        bands = load_bands(args.bands_file)
        band = _resolve_band(band_id, bands)
    except (FileNotFoundError, ValueError) as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        return 2

    if args.prompt_file:
        p = Path(args.prompt_file)
        if not p.is_file():
            print(f"FATAL: --prompt-file not found: {p}", file=sys.stderr)
            return 2
        prompt = p.read_text(encoding="utf-8")
    elif args.prompt is not None:
        prompt = args.prompt
    else:
        print("FATAL: pass --prompt-file PATH or --prompt STR.", file=sys.stderr)
        return 2

    copy_val = args.copy or None
    mdl = band_model(band, getattr(args, "model", None))
    res = band_problems(prompt, band, band_id, copy_val=copy_val, style_ref=bool(args.style_ref), model=mdl)
    length_probs = res["length"]
    quality_probs = res["quality"]
    n = len(prompt.strip())

    # Receipt on disk (institutional memory) — mirrors the fidelity/prompt-caps receipt pattern.
    if args.run_dir:
        run_dir = Path(args.run_dir).resolve()
        if run_dir.is_dir():
            receipt = {
                "band": band_id,
                "chars": n,
                "model": mdl,
                "length_rule": "KIE prompt rule 12 (shared enforcer)",
                "distinct_words": len(set(_GIP_WORD_RE.findall(prompt.lower()))),
                "text_bearing": _is_text_bearing(band),
                "style_ref": bool(args.style_ref),
                "length_problems": [f"{c}: {m}" for c, m in length_probs],
                "quality_problems": quality_probs,
                "passed": not length_probs and not quality_probs,
                "tested_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            }
            rp = _band_receipts_path(run_dir)
            prior = []
            if rp.exists():
                try:
                    obj = json.loads(rp.read_text(encoding="utf-8"))
                    prior = obj.get("receipts", []) if isinstance(obj, dict) else (obj or [])
                except Exception:  # noqa: BLE001
                    prior = []
            rp.parent.mkdir(parents=True, exist_ok=True)
            rp.write_text(json.dumps({"receipts": prior + [receipt]}, indent=2) + "\n",
                          encoding="utf-8")

    if not length_probs and not quality_probs:
        print(f"OK: {band_id} prompt is {n} chars for {mdl} (rule 12 band), "
              f"clears the GIP band + quality gate.")
        return 0

    print("!" * 78, file=sys.stderr)
    # LENGTH failures take precedence for the exit code (a floor/cap breach is not run at all).
    if length_probs:
        codes = sorted({c for c, _ in length_probs})
        print(f"FATAL {'/'.join(codes)}: {band_id} prompt FAILS the GIP band length gate — it is "
              f"NOT submitted, NOT rendered. Re-author.", file=sys.stderr)
        for code, msg in length_probs:
            print(f"  - {code}: {msg}", file=sys.stderr)
    if quality_probs:
        print(f"FATAL AF-GIP-PROMPT-QUALITY: {band_id} prompt cleared/failed length but has "
              f"{len(quality_probs)} quality defect(s) (independent of length):", file=sys.stderr)
        for msg in quality_probs:
            print(f"  - {msg}", file=sys.stderr)
    print("!" * 78, file=sys.stderr)
    # Exit 3 when a floor/cap breach is present (fold under AF-GIP-PROMPT-FLOOR / AF-DIU-PROMPT-CAP);
    # otherwise exit 6 for a pure quality failure (AF-GIP-PROMPT-QUALITY).
    return 3 if length_probs else 6


# ---------------------------------------------------------------------------
# 5) SELF-TEST — smoke-test every gate in one command.
# ---------------------------------------------------------------------------
def cmd_self_test(_args) -> int:
    """Run a self-contained smoke test of every enforcement gate.
    Returns 0 when all tests pass, non-zero on the first failure."""
    failures = []

    # (a) The band file holds no length numbers: length is rule 12 through the shared enforcer.
    try:
        bands = load_bands()
        for bid, band in bands.items():
            for key in ("min", "max"):
                if key in band:
                    failures.append(f"{bid}: hard-coded {key} reintroduced in prompt-bands.json")
        if "text_bearing_medium" in bands:
            failures.append("text_bearing_medium (the Ideogram social band) must not exist")
        print("SELF-TEST OK: prompt-bands.json carries no length numbers; no Ideogram social band.")
    except Exception as exc:  # noqa: BLE001
        failures.append(f"prompt-bands load failed: {exc}")
        bands = {}

    # (b) Text-bearing bands never route to nano-banana-2.
    for bid, band in bands.items():
        if _is_text_bearing(band) and "nano-banana-2" in band.get("endpoints", []):
            failures.append(f"{bid}: nano-banana-2 in endpoints on text-bearing band (GK-20).")
    print("SELF-TEST OK: no text-bearing band routes to nano-banana-2 (GK-20 reconciled).")

    # (c) Rule 12 on GPT Image 2.5 (max 20,000): 79 percent rejected (add), 101 percent rejected (cut), 95 percent passes.
    for n, want in ((15800, 3), (20200, 3), (19000, 0), (20000, 0)):
        pb = cmd_prompt_band(_FakeArgs(band="text_bearing_long", prompt="x" * n))
        # length passes -> the filler has no negative block, so the exit is 6 (quality), never 3
        got = 3 if pb == 3 else 0
        if got != want:
            failures.append(f"prompt-band: {n}-char text_bearing_long prompt length verdict {got} != {want} (exit {pb})")
    print("SELF-TEST OK: prompt-band enforces rule 12 (79 percent and 101 percent rejected, 95 and 100 percent length-clear).")

    # (d) prompt-caps: over the model max exits 3; at the max exits 0.
    if cmd_prompt_caps(_FakeArgs(prompt="x" * 20001, model=DEFAULT_MODEL)) != 3:
        failures.append("prompt-caps: 20,001 chars on GPT Image 2.5 should exit 3")
    if cmd_prompt_caps(_FakeArgs(prompt="x" * 20000, model=DEFAULT_MODEL)) != 0:
        failures.append("prompt-caps: 20,000 chars on GPT Image 2.5 should exit 0")
    print("SELF-TEST OK: prompt-caps enforces the model max (exit 3 above, exit 0 at the max).")

    # (f) route-check: a webinar deck must be rejected.
    rc_rc = cmd_route_check(_FakeArgs(deck_kind="webinar deck"))
    if rc_rc != 2:
        failures.append(f"route-check: 'webinar deck' should exit 2, got {rc_rc}")
    else:
        print("SELF-TEST OK: route-check rejects webinar deck (exit 2).")

    # (g) route-check: a brand deck must pass.
    rc_rc2 = cmd_route_check(_FakeArgs(deck_kind="brand deck"))
    if rc_rc2 != 0:
        failures.append(f"route-check: 'brand deck' should exit 0, got {rc_rc2}")
    else:
        print("SELF-TEST OK: route-check passes brand deck (exit 0).")

    # (h) prompt-band: a 1,000-char text_bearing_long prompt must fail the floor.
    pb_rc = cmd_prompt_band(_FakeArgs(
        band="text_bearing_long", prompt="x" * 1000))
    if pb_rc != 3:
        failures.append(f"prompt-band: 1,000-char text_bearing_long prompt should exit 3 (floor), got {pb_rc}")
    else:
        print("SELF-TEST OK: prompt-band floor rejects a 1,000-char text_bearing_long prompt.")

    # (i) consent-check: a missing identity file must fail closed.
    import tempfile as _tf
    import os as _os
    with _tf.NamedTemporaryFile(suffix=".md", delete=False) as tf:
        tf.write(b"")
        tmpf = tf.name
    try:
        _os.unlink(tmpf)
        cc_rc = cmd_consent_check(_FakeArgs(identity_file=tmpf))
        if cc_rc != 4:
            failures.append(f"consent-check: missing CONSENT file should exit 4, got {cc_rc}")
        else:
            print("SELF-TEST OK: consent-check fails closed on missing CONSENT file (exit 4).")
    finally:
        pass

    if failures:
        print("\nSELF-TEST FAILURES:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print("\nSELF-TEST ALL PASSED.")
    return 0


class _FakeArgs:
    """Lightweight namespace for self-test argument simulation."""
    def __init__(self, **kw):
        self.__dict__.update(kw)
        self.__dict__.setdefault("prompt_file", None)
        self.__dict__.setdefault("bands_file", None)
        self.__dict__.setdefault("copy", [])
        self.__dict__.setdefault("style_ref", False)
        self.__dict__.setdefault("run_dir", None)
        self.__dict__.setdefault("model", None)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Deterministic DIU enforcement gate (prompt caps, GIP prompt "
                    "bands, routing interlock, consent/minor/PII, fidelity + 3-strike).")
    sub = ap.add_subparsers(dest="cmd", required=True)

    pc = sub.add_parser("prompt-caps", help="enforce the model max (KIE rule 12 ceiling, shared enforcer)")
    pc.add_argument("--model", default=DEFAULT_MODEL, help="KIE model id whose maxLength is the ceiling (default: %(default)s)")
    pc.add_argument("--tier", help="DEPRECATED and ignored: the SHORT/MEDIUM/LONG tier table is retired; the ceiling is the model maxLength")
    pc.add_argument("--prompt-file", help="path to the assembled prompt")
    pc.add_argument("--prompt", help="inline prompt string")
    pc.set_defaults(func=cmd_prompt_caps)

    pb = sub.add_parser("prompt-band",
                        help="enforce the GIP per-asset-class prompt band (rule 12 length through "
                             "the shared enforcer + quality teeth)")
    pb.add_argument("--band", required=True,
                    help="text_bearing_long | visual_long | medium | short_draft")
    pb.add_argument("--model", help="KIE model id whose maxLength sets the length band "
                                    "(default: the band's first endpoint)")
    pb.add_argument("--prompt-file", help="path to the assembled prompt")
    pb.add_argument("--prompt", help="inline prompt string")
    pb.add_argument("--copy", action="append", default=[],
                    help="a verbatim on-image copy string that must be baked into the prompt "
                         "body (repeatable; enforced on text-bearing bands)")
    pb.add_argument("--style-ref", action="store_true",
                    help="style reference image(s) are attached -> require the mandatory "
                         "style-reference-only directive (MODEL-SPECS §4)")
    pb.add_argument("--run-dir", help="optional run dir for the band receipt "
                                      "(working/checkpoints/diu_prompt_band_receipts.json)")
    pb.add_argument("--bands-file", help="override path to prompt-bands.json (tests only)")
    pb.set_defaults(func=cmd_prompt_band)

    rc = sub.add_parser("route-check", help="DIU routing interlock (SOP-DIU-611 D.1)")
    rc.add_argument("--deck-kind", required=True,
                    help="deck kind, e.g. webinar | funnel | brand | campaign")
    rc.set_defaults(func=cmd_route_check)

    cc = sub.add_parser("consent-check",
                        help="fail-closed consent + minor + PII gate (SOP-DIU-608 CONSENT.md)")
    cc.add_argument("--consent-file", "--identity-file", dest="consent_file", required=True,
                    help="path to the client's personal-photo-shoot CONSENT.md "
                         "(--identity-file is the old spelling; it must still point at CONSENT.md)")
    cc.set_defaults(func=cmd_consent_check)

    fd = sub.add_parser("fidelity", help="fidelity receipt + 3-strike counter")
    fd.add_argument("--run-dir", required=True)
    fd.add_argument("--card-id", required=True)
    fd.add_argument("--scores-file", help="JSON: {dim: score} or [12 numbers]")
    fd.add_argument("--scores", help="inline JSON scores")
    fd.add_argument("--hard-rule-violation", action="append", default=[],
                    help="a hard-rule violation description (repeatable); any one "
                         "fails the whole test")
    fd.set_defaults(func=cmd_fidelity)

    st = sub.add_parser("self-test", help="smoke-test every enforcement gate")
    st.set_defaults(func=cmd_self_test)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
