#!/usr/bin/env python3
"""guard-prompt-pins.py -- the baked-prompt integrity gate for the Anthology Engine.

Unit W2.1. SPEC 3.4 row 22 / SPEC 6.1 (the complete pin inventory) / SPEC 14 item 5 /
CHECKLIST Part C items 1 and 10. Enforces autofail AF-AE-PROMPT-PIN (ENGINE-MANIFEST
autofails, py_symbol "evaluate").

It proves FOUR things over the engine's entire baked-prompt surface, at merge AND at
runtime, model-free and stdlib-only:

  1. PIN INTEGRITY  -- every baked prompt asset hashes byte-for-byte to its recorded
     sha256 pin. The pin maps live in three manifests that ship together in the fleet
     bundle (SPEC 6.1):
        * ENGINE  ae-01..04  -> 59-anthology-engine/ENGINE-MANIFEST.json
                                  engine_owned_prompt_pins            (MANDATORY)
        * SKILL54 aw-06..12  -> 54-anthology-writer/ANTHOLOGY-MANIFEST.json
                                  source_prompt_pins                  (sibling)
        * AVATAR  aa-01..03  -> 54 ANTHOLOGY-MANIFEST.json avatar_handoff.stages
                                  per-file pins over 52-avatar-alchemist/prompts
                                  (reference-by-path; NOT copied)     (sibling)
     tone-04..08 carry NO sha256 map in tone-core-manifest.json; their lockstep
     integrity is a DIFFERENT prover (verify_tone_core_sync.py). This guard reports
     tone as delegated and never claims to have pinned it.

  2. ZERO TRUNCATION -- no baked asset sits at the Airtable multilineText 32,767-char
     ceiling (SPEC 1.4: the eight truncated full-book records hit exactly that boundary).
     A pin that MATCHES a truncated body is still a truncated pin; the sha check alone
     cannot catch a body that was truncated at BAKE time and then pinned. The ceiling
     boundary is the deterministic signature. An operator may additionally feed the
     Wave-0 recorded verbatim sizes via --expected-lengths for a byte-exact proof.

  3. ZERO [UNCHANGED] -- no baked asset carries a surviving [UNCHANGED] placeholder
     (SPEC 1.4 repair law: the formatter's ten literal [UNCHANGED] markers are RESTORED
     from the CSV before pinning; a pin containing [UNCHANGED] is a hard failure).

  4. NO LEGACY PROMPT-BASE RUNTIME REFERENCE -- a static scan of the shipped runtime
     surface (scripts + config + manifests) proves zero references to either legacy
     Airtable prompt base (SPEC 1.2 LEGACY-PROMPT-BASE / LEGACY-SYSTEMS-BASE, both
     demoted to the operator's private editing workspace; SPEC 14 item 5; CHECKLIST
     item 10). The engine reaches its OWN state base by the ENV label
     ANTHOLOGY_STATE_BASE_ID only, so ANY hardcoded Airtable base-id literal, table-id
     literal, or api.airtable.com REST URL in a runtime file is a violation regardless
     of which base it names. An operator may supply the Wave-0-resolved legacy
     identifiers via --legacy-denylist (or $ANTHOLOGY_LEGACY_DENYLIST) for an
     exact-literal scan; those resolved identifiers are scrubbed and NEVER printed --
     matches are reported by label, file, and line only.

DOCTRINE (SPEC document control; MEMORY move-in-silence): this guard NEVER prints a
resolved legacy identifier, a credential, or the prose it inspects. Legacy hits are
redacted (kind + length). The guard EXCLUDES itself and the sibling guards from the
runtime scan, exactly as guard-no-anthropic treats its own deny-pattern DEFINITIONS as
allowed -- the shapes defined here are the enforcement tool, not a runtime reference.

Exit codes (SPEC 3.4 row 22 is the contract 0/4; house convention fills the edges):
  0  clean    -- every pin matches, zero truncation, zero [UNCHANGED], zero legacy refs
  4  violation -- any pin mismatch, truncation boundary, surviving [UNCHANGED], missing
                  pinned asset, or legacy prompt-base runtime reference (AF-AE-PROMPT-PIN)
  2  bad invocation -- skill dir / ENGINE-MANIFEST missing or unreadable, bad args
  3  dependency unavailable -- a REQUIRED sibling pin manifest is absent (operator
                  surface; NOT a silent pass). Use --engine-only to scope to ae-* pins.
  1  unexpected error
"""
import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path

EX_OK, EX_ERR, EX_BAD, EX_DEP, EX_VIOLATION = 0, 1, 2, 3, 4

# The Airtable multilineText ceiling (SPEC 1.4). A baked body AT this boundary is the
# deterministic signature of platform truncation.
TRUNCATION_CEILING = 32767

# The one placeholder sentinel named by SPEC 1.4 / CHECKLIST item 1.
DEFAULT_UNCHANGED_TOKENS = ("[UNCHANGED]",)

# Airtable id shapes: a real id is a fixed prefix + 14 base62 chars. Real ids are random
# base62 and (essentially always) carry a digit or an uppercase letter; the trailing
# [A-Za-z0-9]{13} plus a mandatory digit-or-upper guards against English words like
# "applications"/"appropriate" ever matching. Anchored on non-word boundaries.
_AIRTABLE_ID_RE = re.compile(r"(?<![A-Za-z0-9])(app|tbl|rec|fld|viw)([A-Za-z0-9]{14})(?![A-Za-z0-9])")
# A literal Airtable REST call in a runtime file (the engine never uses literal URLs).
_AIRTABLE_URL_RE = re.compile(r"api\.airtable\.com/v0/[A-Za-z0-9]+")
# Recognised placeholders that are NOT real ids (installer templates, doc examples).
_PLACEHOLDER_ID_RE = re.compile(r"^(app|tbl|rec|fld|viw)[Xx]{14}$")

# The one ALLOWED way a runtime file names the state base (SPEC 7): by ENV label.
ALLOWED_BASE_LABEL = "ANTHOLOGY_STATE_BASE_ID"


class BadInvocation(Exception):
    """Maps to exit 2 (skill dir / manifest missing or malformed, bad args)."""


class DependencyUnavailable(Exception):
    """Maps to exit 3 (a required sibling pin manifest is absent)."""


# --------------------------------------------------------------------------- helpers
def _sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def _read_bytes(path):
    with open(path, "rb") as fh:
        return fh.read()


def _read_text(path):
    # errors='replace' so a stray byte never crashes the scan; we only match ASCII shapes.
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        return fh.read()


def _load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        raise
    except (ValueError, OSError) as exc:
        raise BadInvocation("unreadable/malformed JSON: %s (%s)" % (path, exc))


def _redact_id(match_text):
    """Never print a resolved/scrubbed identifier. Show prefix + length only."""
    head = match_text[:3]
    return "%s...(%d)" % (head, len(match_text))


# ------------------------------------------------------------------ pin-set discovery
def resolve_layout(skill_dir):
    """Resolve the skill dir and the onboarding root that holds the sibling skills."""
    skill_dir = Path(skill_dir).resolve()
    manifest = skill_dir / "ENGINE-MANIFEST.json"
    if not skill_dir.is_dir():
        raise BadInvocation("skill dir is not a directory: %s" % skill_dir)
    if not manifest.is_file():
        raise BadInvocation("ENGINE-MANIFEST.json not found under skill dir: %s" % skill_dir)
    root = os.environ.get("ANTHOLOGY_ONBOARDING_ROOT")
    onboarding_root = Path(root).resolve() if root else skill_dir.parent
    return skill_dir, onboarding_root, manifest


def collect_pin_entries(skill_dir, onboarding_root, engine_only):
    """Return (entries, missing_siblings).

    entries: list of {pin_id, set, base, rel, path, pin} for every sha256-pinned asset.
    missing_siblings: list of sibling manifest paths that were expected but absent.
    """
    entries = []
    missing = []

    # 1) ENGINE ae-01..04 (MANDATORY) -----------------------------------------------
    eng = _load_json(skill_dir / "ENGINE-MANIFEST.json")
    eng_pins = eng.get("engine_owned_prompt_pins", {})
    if not isinstance(eng_pins, dict):
        raise BadInvocation("engine_owned_prompt_pins is not an object")
    found_engine = 0
    for rel, pin in eng_pins.items():
        if rel.startswith("$"):  # $note keys are documentation, not pins
            continue
        entries.append({
            "pin_id": Path(rel).stem, "set": "ENGINE", "base": skill_dir,
            "rel": rel, "path": (skill_dir / rel), "pin": pin,
        })
        found_engine += 1
    if found_engine == 0:
        # The engine MUST own ae-01..04; an empty pin block is a malformed manifest.
        raise BadInvocation("ENGINE-MANIFEST.json declares zero engine_owned_prompt_pins")

    if engine_only:
        return entries, missing

    # 2) SKILL54 aw-06..12 + 3) AVATAR aa-01..03 (siblings) --------------------------
    s54_manifest = onboarding_root / "54-anthology-writer" / "ANTHOLOGY-MANIFEST.json"
    if not s54_manifest.is_file():
        missing.append(str(s54_manifest))
    else:
        m54 = _load_json(s54_manifest)
        s54_base = onboarding_root / "54-anthology-writer"
        for rel, pin in (m54.get("source_prompt_pins") or {}).items():
            entries.append({
                "pin_id": rel.split("/")[-1][:5], "set": "SKILL54", "base": s54_base,
                "rel": rel, "path": (s54_base / rel), "pin": pin,
            })
        # avatar_handoff per-file pins over Skill 52 (reference-by-path; base = root)
        for stage in ((m54.get("avatar_handoff") or {}).get("stages") or []):
            pdir = stage.get("prompt_dir", "")
            for fname, pin in (stage.get("files") or {}).items():
                rel = "%s/%s" % (pdir, fname)
                entries.append({
                    "pin_id": "%s/%s" % (stage.get("pin_id", "aa-??"), fname),
                    "set": "AVATAR", "base": onboarding_root,
                    "rel": rel, "path": (onboarding_root / rel), "pin": pin,
                })

    return entries, missing


# ------------------------------------------------------------------------- the checks
def check_pins(entries, ceiling, unchanged_tokens, expected_lengths):
    """Checks 1, 2, 3 over every pinned asset. Returns a list of violation dicts."""
    violations = []
    for e in entries:
        path = e["path"]
        label = "%s:%s" % (e["set"], e["pin_id"])
        if not path.is_file():
            violations.append({
                "kind": "missing-asset", "label": label, "asset": e["rel"],
                "detail": "pinned asset file is absent (broken pin inventory)",
            })
            continue
        raw = _read_bytes(path)
        got = _sha256_bytes(raw)

        # 1) PIN INTEGRITY
        if got != e["pin"]:
            violations.append({
                "kind": "pin-mismatch", "label": label, "asset": e["rel"],
                "detail": "sha256 %s != pinned %s" % (got[:12] + "…", e["pin"][:12] + "…"),
            })

        # decode once for the char-level checks
        text = raw.decode("utf-8", errors="replace")
        nchars, nbytes = len(text), len(raw)

        # 2) ZERO TRUNCATION -- ceiling boundary (chars or bytes at/over the ceiling)
        if nchars >= ceiling or nbytes >= ceiling:
            violations.append({
                "kind": "truncation-ceiling", "label": label, "asset": e["rel"],
                "detail": "body at/over the %d-char ceiling (%d chars, %d bytes)"
                          % (ceiling, nchars, nbytes),
            })
        # 2b) optional byte-exact truncation proof against recorded Wave-0 sizes
        exp = expected_lengths.get(e["rel"]) if expected_lengths else None
        if exp is not None:
            exp_chars = exp.get("chars") if isinstance(exp, dict) else None
            exp_bytes = exp.get("bytes") if isinstance(exp, dict) else (
                exp if isinstance(exp, int) else None)
            if exp_bytes is not None and nbytes != exp_bytes:
                violations.append({
                    "kind": "length-mismatch", "label": label, "asset": e["rel"],
                    "detail": "measured %d bytes != expected %d (truncation/tamper)"
                              % (nbytes, exp_bytes),
                })
            if exp_chars is not None and nchars != exp_chars:
                violations.append({
                    "kind": "length-mismatch", "label": label, "asset": e["rel"],
                    "detail": "measured %d chars != expected %d (truncation/tamper)"
                              % (nchars, exp_chars),
                })

        # 3) ZERO [UNCHANGED]
        for tok in unchanged_tokens:
            if tok in text:
                violations.append({
                    "kind": "unchanged-placeholder", "label": label, "asset": e["rel"],
                    "detail": "surviving %s placeholder (%d occurrence(s))"
                              % (tok, text.count(tok)),
                })
    return violations


def scan_unpinned_engine_assets(skill_dir, pinned_paths, unchanged_tokens, ceiling):
    """Defensive: catch a stray un-pinned prompt file under the engine's assets/prompts
    that carries [UNCHANGED] or sits at the truncation ceiling."""
    violations = []
    prompts_dir = skill_dir / "assets" / "prompts"
    if not prompts_dir.is_dir():
        return violations
    for p in sorted(prompts_dir.rglob("*")):
        if not p.is_file() or p.resolve() in pinned_paths:
            continue
        text = _read_text(p)
        rel = str(p.relative_to(skill_dir))
        for tok in unchanged_tokens:
            if tok in text:
                violations.append({
                    "kind": "unchanged-placeholder", "label": "ENGINE:unpinned",
                    "asset": rel, "detail": "surviving %s in an un-pinned engine asset" % tok,
                })
        if len(text) >= ceiling or len(text.encode("utf-8")) >= ceiling:
            violations.append({
                "kind": "truncation-ceiling", "label": "ENGINE:unpinned",
                "asset": rel, "detail": "un-pinned engine asset at/over the %d-char ceiling" % ceiling,
            })
    return violations


def _iter_runtime_files(skill_dir):
    """Yield the shipped RUNTIME surface: *.py and *.sh anywhere, everything under
    config/, and root-level *.json manifests. EXCLUDES tests, fixtures, __pycache__,
    prompt assets (data, checked separately), root-level docs (*.md prose that discusses
    the deprecation in LABEL form), and the guard scripts themselves (their deny-pattern
    DEFINITIONS are the enforcement tool, not a runtime reference)."""
    excluded_dirs = {"tests", "fixtures", "__pycache__", ".git"}
    for dirpath, dirnames, filenames in os.walk(skill_dir):
        dirnames[:] = [d for d in dirnames if d not in excluded_dirs]
        rel_dir = Path(dirpath).relative_to(skill_dir)
        parts = rel_dir.parts
        # skip the prompt-asset data tree (scanned by the [UNCHANGED] pass instead)
        if parts[:2] == ("assets", "prompts"):
            continue
        under_config = parts and parts[0] == "config"
        at_root = (dirpath == str(skill_dir))
        for fn in filenames:
            fp = Path(dirpath) / fn
            name = fn.lower()
            # never scan a guard's own body, nor test bodies
            if name.startswith("guard-") and name.endswith(".py"):
                continue
            if name.startswith("test_") or name.endswith("_test.py"):
                continue
            suffix = fp.suffix.lower()
            is_code = suffix in (".py", ".sh")
            is_root_json = at_root and suffix == ".json"
            if is_code or under_config or is_root_json:
                yield fp


def _load_legacy_denylist(explicit_path, onboarding_root):
    """Resolve the OPTIONAL Wave-0 legacy-identifier denylist. Never required; its absence
    leaves only the (comprehensive) structural checks. Returns (tokens, source) where
    tokens is a set of exact-literal strings to hunt in runtime files."""
    candidates = []
    if explicit_path:
        candidates.append(Path(explicit_path))
    env = os.environ.get("ANTHOLOGY_LEGACY_DENYLIST")
    if env:
        candidates.append(Path(env))
    # conventional operator-side location (build-state never ships in the repo)
    candidates.append(onboarding_root.parent / ".build-state" / "legacy-denylist.json")
    for c in candidates:
        try:
            if c and c.is_file():
                data = json.load(open(c, "r", encoding="utf-8"))
                tokens = set()
                for key in ("base_ids", "base_names", "table_names", "tokens"):
                    for v in (data.get(key) or []):
                        if isinstance(v, str) and v.strip():
                            tokens.add(v.strip())
                return tokens, str(c)
        except (ValueError, OSError):
            # a malformed operator denylist must not mask the structural checks
            continue
    return set(), None


def scan_legacy_references(skill_dir, legacy_tokens):
    """Check 4. Static scan of the runtime surface. Returns a list of violation dicts;
    every dict is redacted (no resolved identifier, no scrubbed name, no prose)."""
    violations = []
    for fp in _iter_runtime_files(skill_dir):
        try:
            text = _read_text(fp)
        except OSError:
            continue
        rel = str(fp.relative_to(skill_dir))
        for lineno, line in enumerate(text.splitlines(), 1):
            # 4a) hardcoded Airtable id shapes (base/table/rec/fld/view)
            for m in _AIRTABLE_ID_RE.finditer(line):
                token = m.group(0)
                if _PLACEHOLDER_ID_RE.match(token):
                    continue
                # require a digit or uppercase in the 14-char tail (real base62 ids do;
                # English words do not) -- kills 'applications'-style false positives
                tail = m.group(2)
                if not any(ch.isdigit() or ch.isupper() for ch in tail):
                    continue
                violations.append({
                    "kind": "hardcoded-airtable-id", "file": rel, "line": lineno,
                    "detail": "literal Airtable id %s in runtime; the state base is "
                              "referenced by the %s label only"
                              % (_redact_id(token), ALLOWED_BASE_LABEL),
                })
            # 4b) literal Airtable REST URL (engine uses the SDK/label, never a URL)
            for m in _AIRTABLE_URL_RE.finditer(line):
                violations.append({
                    "kind": "airtable-rest-literal", "file": rel, "line": lineno,
                    "detail": "literal api.airtable.com REST call in a runtime file",
                })
            # 4c) resolved legacy identifiers (operator denylist), exact-literal, redacted
            for tok in legacy_tokens:
                if tok in line:
                    violations.append({
                        "kind": "legacy-denylist-hit", "file": rel, "line": lineno,
                        "detail": "resolved legacy prompt-base identifier present "
                                  "(len %d; value withheld)" % len(tok),
                    })
    return violations


# ---------------------------------------------------------------------- orchestration
def run_battery(skill_dir=None, engine_only=False, ceiling=TRUNCATION_CEILING,
                unchanged_tokens=DEFAULT_UNCHANGED_TOKENS, expected_lengths=None,
                legacy_denylist_path=None, require_siblings=True):
    """Run all four checks. Returns a report dict. Raises BadInvocation (exit 2) or
    DependencyUnavailable (exit 3) for the non-violation edges."""
    if skill_dir is None:
        skill_dir = Path(__file__).resolve().parent.parent
    skill_dir, onboarding_root, _ = resolve_layout(skill_dir)

    entries, missing = collect_pin_entries(skill_dir, onboarding_root, engine_only)
    if missing and require_siblings and not engine_only:
        raise DependencyUnavailable(
            "required sibling pin manifest(s) absent: %s (use --engine-only to scope "
            "to the engine-owned ae-* pins)" % ", ".join(missing))

    legacy_tokens, denylist_source = _load_legacy_denylist(legacy_denylist_path, onboarding_root)

    pinned_paths = {e["path"].resolve() for e in entries}
    pin_viol = check_pins(entries, ceiling, unchanged_tokens, expected_lengths or {})
    pin_viol += scan_unpinned_engine_assets(skill_dir, pinned_paths, unchanged_tokens, ceiling)
    legacy_viol = scan_legacy_references(skill_dir, legacy_tokens)

    violations = pin_viol + legacy_viol
    return {
        "skill_dir": str(skill_dir),
        "engine_only": engine_only,
        "pins_checked": len(entries),
        "sets": sorted({e["set"] for e in entries}),
        "missing_siblings": missing,
        "tone_pins": "delegated to verify_tone_core_sync.py (no sha256 map in "
                     "tone-core-manifest.json)",
        "legacy_denylist_source": denylist_source or "(none; structural checks only)",
        "legacy_denylist_terms": len(legacy_tokens),
        "truncation_ceiling": ceiling,
        "violation_count": len(violations),
        "violations": violations,
        "ok": len(violations) == 0,
    }


def evaluate(skill_dir=None, engine_only=False, **kwargs):
    """Manifest entry symbol (ENGINE-MANIFEST autofails AF-AE-PROMPT-PIN, py_symbol
    "evaluate"). Importable harness API. Returns True when the whole baked-prompt surface
    is clean, False when any pin/truncation/[UNCHANGED]/legacy violation exists. Raises
    BadInvocation (CLI exit 2) or DependencyUnavailable (CLI exit 3) for the edges."""
    return run_battery(skill_dir=skill_dir, engine_only=engine_only, **kwargs)["ok"]


def _print_report(report, as_json):
    if as_json:
        print(json.dumps(report, indent=2))
        return
    tag = "[guard-prompt-pins]"
    if report["ok"]:
        print("%s CLEAN  %d pin(s) across %s; zero truncation, zero [UNCHANGED], "
              "zero legacy runtime references" % (tag, report["pins_checked"],
              ", ".join(report["sets"])))
        if report["missing_siblings"]:
            print("%s note: sibling manifest(s) not present (engine-only scope): %s"
                  % (tag, ", ".join(report["missing_siblings"])))
    else:
        print("%s VIOLATION  %d finding(s) (AF-AE-PROMPT-PIN)"
              % (tag, report["violation_count"]))
        for v in report["violations"]:
            if "asset" in v:
                print("  [%s] %s :: %s -- %s"
                      % (v["kind"], v.get("label", "?"), v["asset"], v["detail"]))
            else:
                print("  [%s] %s:%s -- %s"
                      % (v["kind"], v.get("file", "?"), v.get("line", "?"), v["detail"]))


# --------------------------------------------------------------------------- self-test
def self_test():
    """Force AND observe every failure mode in an isolated temp tree, then prove the
    clean case passes. Returns EX_OK iff every mode fired exactly as contracted."""
    import tempfile
    tag = "[guard-prompt-pins] self-test:"
    print("%s building an isolated skill tree and forcing each failure mode" % tag)

    def write(p, data):
        p.parent.mkdir(parents=True, exist_ok=True)
        mode = "wb" if isinstance(data, (bytes, bytearray)) else "w"
        with open(p, mode) as fh:
            fh.write(data)

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        skill = root / "59-anthology-engine"
        (skill / "scripts").mkdir(parents=True)
        (skill / "config").mkdir(parents=True)
        ap = skill / "assets" / "prompts"
        ap.mkdir(parents=True)

        # a good engine asset + its correct pin
        good_body = "# ae-01 order curation\nCurate the chapter order.\n"
        write(ap / "ae-01-order-curation.md", good_body)
        good_pin = _sha256_bytes(good_body.encode("utf-8"))

        def manifest_with(pins):
            write(skill / "ENGINE-MANIFEST.json",
                  json.dumps({"engine_owned_prompt_pins": pins}))

        # ---- CLEAN baseline (engine-only; no siblings in the temp tree) ----
        manifest_with({"assets/prompts/ae-01-order-curation.md": good_pin})
        rep = run_battery(skill_dir=skill, engine_only=True)
        assert rep["ok"], "clean baseline wrongly flagged: %r" % rep["violations"]
        print("%s clean baseline PASS (%d pin ok)" % (tag, rep["pins_checked"]))

        # ---- MODE 1: pin mismatch (tamper the body, pin unchanged) ----
        write(ap / "ae-01-order-curation.md", good_body + "TAMPERED\n")
        rep = run_battery(skill_dir=skill, engine_only=True)
        assert not rep["ok"] and any(v["kind"] == "pin-mismatch" for v in rep["violations"]), \
            "pin mismatch not caught: %r" % rep["violations"]
        assert evaluate(skill_dir=skill, engine_only=True) is False
        print("%s MODE 1 pin-mismatch: FIRED" % tag)
        write(ap / "ae-01-order-curation.md", good_body)  # restore

        # ---- MODE 2: truncation ceiling (body pinned AT 32,767 chars) ----
        trunc_body = "A" * TRUNCATION_CEILING
        write(ap / "ae-01-order-curation.md", trunc_body)
        manifest_with({"assets/prompts/ae-01-order-curation.md":
                       _sha256_bytes(trunc_body.encode("utf-8"))})
        rep = run_battery(skill_dir=skill, engine_only=True)
        assert not rep["ok"] and any(v["kind"] == "truncation-ceiling" for v in rep["violations"]), \
            "truncation ceiling not caught: %r" % rep["violations"]
        print("%s MODE 2 truncation-ceiling: FIRED (pin matched a truncated body)" % tag)

        # ---- MODE 2b: expected-length mismatch (byte-exact truncation proof) ----
        write(ap / "ae-01-order-curation.md", good_body)
        manifest_with({"assets/prompts/ae-01-order-curation.md": good_pin})
        rep = run_battery(skill_dir=skill, engine_only=True,
                          expected_lengths={"assets/prompts/ae-01-order-curation.md":
                                            {"bytes": len(good_body.encode()) + 999}})
        assert not rep["ok"] and any(v["kind"] == "length-mismatch" for v in rep["violations"]), \
            "expected-length mismatch not caught: %r" % rep["violations"]
        print("%s MODE 2b length-mismatch: FIRED" % tag)

        # ---- MODE 3: surviving [UNCHANGED] placeholder ----
        unchanged_body = good_body + "Formatter rule: keep the [UNCHANGED] section.\n"
        write(ap / "ae-01-order-curation.md", unchanged_body)
        manifest_with({"assets/prompts/ae-01-order-curation.md":
                       _sha256_bytes(unchanged_body.encode("utf-8"))})
        rep = run_battery(skill_dir=skill, engine_only=True)
        assert not rep["ok"] and any(v["kind"] == "unchanged-placeholder" for v in rep["violations"]), \
            "[UNCHANGED] not caught: %r" % rep["violations"]
        print("%s MODE 3 unchanged-placeholder: FIRED" % tag)
        write(ap / "ae-01-order-curation.md", good_body)
        manifest_with({"assets/prompts/ae-01-order-curation.md": good_pin})

        # ---- MODE 4a: hardcoded Airtable base-id literal in a runtime script ----
        fake_base = "appAB12cd34EF56gh"  # app + 14 base62 (fake; contains digits/upper)
        write(skill / "scripts" / "leaky_adapter.py",
              "BASE = '%s'  # forbidden literal\n" % fake_base)
        rep = run_battery(skill_dir=skill, engine_only=True)
        assert not rep["ok"] and any(v["kind"] == "hardcoded-airtable-id" for v in rep["violations"]), \
            "hardcoded base-id not caught: %r" % rep["violations"]
        # the raw id must NOT appear in the emitted report (redaction proof)
        assert fake_base not in json.dumps(rep), "raw base id leaked into the report"
        print("%s MODE 4a hardcoded-airtable-id: FIRED (and redacted)" % tag)
        (skill / "scripts" / "leaky_adapter.py").unlink()

        # ---- MODE 4b: literal api.airtable.com REST URL ----
        write(skill / "config" / "bad.json",
              json.dumps({"url": "https://api.airtable.com/v0/appXXXXXXXXXXXXXX/Prompts"}))
        rep = run_battery(skill_dir=skill, engine_only=True)
        assert not rep["ok"] and any(v["kind"] == "airtable-rest-literal" for v in rep["violations"]), \
            "airtable REST literal not caught: %r" % rep["violations"]
        print("%s MODE 4b airtable-rest-literal: FIRED" % tag)
        (skill / "config" / "bad.json").unlink()

        # ---- MODE 4c: resolved legacy identifier via the operator denylist (redacted) ----
        secret_legacy = "appLEGACYpromptXX"  # stand-in resolved legacy base id
        write(skill / "scripts" / "harvester.py",
              "LEGACY = '%s'\n" % secret_legacy)
        denylist = root / "denylist.json"
        write(denylist, json.dumps({"base_ids": [secret_legacy]}))
        rep = run_battery(skill_dir=skill, engine_only=True,
                          legacy_denylist_path=str(denylist))
        assert not rep["ok"] and any(v["kind"] == "legacy-denylist-hit" for v in rep["violations"]), \
            "legacy denylist hit not caught: %r" % rep["violations"]
        assert secret_legacy not in json.dumps(rep), "resolved legacy id leaked into the report"
        print("%s MODE 4c legacy-denylist-hit: FIRED (and value withheld)" % tag)
        (skill / "scripts" / "harvester.py").unlink()

        # ---- EDGE: missing pinned asset -> violation ----
        (ap / "ae-01-order-curation.md").unlink()
        rep = run_battery(skill_dir=skill, engine_only=True)
        assert not rep["ok"] and any(v["kind"] == "missing-asset" for v in rep["violations"]), \
            "missing asset not caught: %r" % rep["violations"]
        print("%s EDGE missing-asset: FIRED" % tag)
        write(ap / "ae-01-order-curation.md", good_body)

        # ---- EDGE: required sibling manifest absent -> DependencyUnavailable (exit 3) ----
        try:
            run_battery(skill_dir=skill, engine_only=False, require_siblings=True)
            raise AssertionError("absent sibling manifest did not raise DependencyUnavailable")
        except DependencyUnavailable:
            print("%s EDGE dependency-unavailable (exit 3): FIRED" % tag)

        # ---- EDGE: bad invocation (no ENGINE-MANIFEST) -> BadInvocation (exit 2) ----
        try:
            run_battery(skill_dir=root, engine_only=True)
            raise AssertionError("missing ENGINE-MANIFEST did not raise BadInvocation")
        except BadInvocation:
            print("%s EDGE bad-invocation (exit 2): FIRED" % tag)

        # ---- FINAL: clean again ----
        rep = run_battery(skill_dir=skill, engine_only=True)
        assert rep["ok"], "final clean case wrongly flagged: %r" % rep["violations"]
        print("%s FINAL clean case PASS" % tag)

    print("%s PASS -- every failure mode forced and observed" % tag)
    return EX_OK


# --------------------------------------------------------------------------------- CLI
def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Baked-prompt integrity gate for the Anthology Engine (W2.1): pins "
                    "match sha256, zero truncation, zero [UNCHANGED], zero legacy "
                    "prompt-base runtime references.")
    ap.add_argument("--skill-dir", default=None,
                    help="the 59-anthology-engine skill directory (default: this "
                         "script's parent skill dir)")
    ap.add_argument("--engine-only", action="store_true",
                    help="scope to the engine-owned ae-* pins (skip the sibling "
                         "aw-*/aa-* manifests)")
    ap.add_argument("--legacy-denylist", default=None,
                    help="optional JSON of Wave-0-resolved legacy identifiers "
                         "{base_ids,base_names,table_names}; matched exact-literal, "
                         "reported by label only (never printed)")
    ap.add_argument("--expected-lengths", default=None,
                    help="optional JSON map {asset_rel: {bytes|chars}} of recorded "
                         "verbatim sizes for a byte-exact truncation proof")
    ap.add_argument("--truncation-ceiling", type=int, default=TRUNCATION_CEILING,
                    help="the platform ceiling that signals truncation (default 32767)")
    ap.add_argument("--json", action="store_true", help="emit a machine-readable report")
    ap.add_argument("--self-test", action="store_true",
                    help="force and observe every failure mode, then exit")
    args = ap.parse_args(argv)

    try:
        if args.self_test:
            return self_test()

        expected_lengths = None
        if args.expected_lengths:
            expected_lengths = _load_json(Path(args.expected_lengths))

        report = run_battery(
            skill_dir=args.skill_dir,
            engine_only=args.engine_only,
            ceiling=args.truncation_ceiling,
            expected_lengths=expected_lengths,
            legacy_denylist_path=args.legacy_denylist,
        )
        _print_report(report, args.json)
        return EX_VIOLATION if not report["ok"] else EX_OK

    except BadInvocation as exc:
        sys.stderr.write("[guard-prompt-pins] bad invocation: %s\n" % exc)
        return EX_BAD
    except DependencyUnavailable as exc:
        sys.stderr.write("[guard-prompt-pins] dependency unavailable: %s\n" % exc)
        return EX_DEP
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write("[guard-prompt-pins] unexpected error: %s\n" % exc)
        return EX_ERR


if __name__ == "__main__":
    sys.exit(main())
