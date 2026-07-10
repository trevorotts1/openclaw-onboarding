#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: anthology_book.py
# THE PRODUCER "START A BOOK" MINTER — the SINGLE authority for Book IDs.
# -----------------------------------------------------------------------------
# The engine is already a multi-book, multi-participant ledger: a participant is
# keyed contact_id::anthology_id, and every writer/router CONSUMES a supplied
# anthology_id but REFUSES an unknown one (the ledger's anthologies table is the
# authoritative allow-list; intake_router.py:798-802, anthology_state.py:854-856).
# What the engine never did was MINT a Book ID or emit an author-facing intake
# link. This tool closes exactly that gap and NOTHING else.
#
# WHY A SINGLE AUTHORITY: because the engine trusts a supplied id, GHL / Convert
# and Flow must never invent one at runtime. This minter is the one place a Book
# ID is born; the ledger then becomes its source of truth and the intake link
# carries it (as the form's hidden anthology_id field) so authors never type it.
#
# IT REUSES, IT DOES NOT RE-IMPLEMENT:
#   * the id shape       -> anthology_state.gen_id ("ANTH_<uuid4 hex[:20]>")
#   * the ledger row     -> `anthology_state.py upsert-anthology`  (SOLE writer)
#   * the CAF binding    -> `anthology_registry.py bind`           (per-box registry)
# The producer "start a book" flow orchestrates those three verbatim, then emits
# the link. It writes no state of its own and holds no credential.
#
# OPERATOR DECISION (multi-book design): bind to the ONE STANDARD SHARED pipeline
# (no per-book pipeline). `bind` with no --pipeline-id derives the resolved
# standard pipeline, so every book shares it. A same-author-in-two-concurrent-
# books card collision is possible-but-unlikely; the LEDGER stays correct either
# way (each book is its own row). `--pipeline-id` remains an explicit override.
#
# SUBCOMMANDS
#   mint          mint ONE Book ID and print it (the id generator, standalone)
#   start         B1-B4: mint -> upsert-anthology -> registry bind (shared) -> link
#   intake-link   build a book's shareable intake link from a Book ID + name
#   self-test     offline round-trip battery (temp state/registry/field-map)
#
# EXIT CODES  0 ok  1 error  2 refuse  5 validation. `start` PROPAGATES a failing
# sub-CLI's own exit code so the operator sees the real reason (e.g. exit 3 =
# unknown producer, exit 2/EX_STOP = pipeline unresolved on the bind step).
#
# Convert and Flow is the only platform name. The minted author-intake link is the
# GHL/LeadConnector hosted-form URL <base>/widget/form/<form_id>?anthology_id=<minted>.
# Its two knobs default to FLEET-WIDE, non-client values — the shared LeadConnector
# hosted-form domain and the ONE universal author-intake form id — and both stay
# overridable per box (config / --forms-base / --intake-form-id). No PER-CLIENT domain,
# no client identifier, and no credential is ever hardcoded here. Zero Anthropic
# identifiers ship in this file.
# =============================================================================
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote

# --------------------------------------------------------------------------- #
# Layout (mirrors every sibling script's resolution).
# --------------------------------------------------------------------------- #
SKILL_DIR = Path(__file__).resolve().parent.parent
SCRIPTS = SKILL_DIR / "scripts"
STATE_WRITER = SCRIPTS / "anthology_state.py"        # the SOLE ledger writer (SPEC 7.4)
REGISTRY = SCRIPTS / "anthology_registry.py"         # per-box CAF bindings
FIELD_MAP = SKILL_DIR / "config" / "field-map.json"
DEFAULT_CONFIG = SKILL_DIR / "config" / "engine-config.json"          # resolved per box
TEMPLATE_CONFIG = SKILL_DIR / "config" / "engine-config.template.json"

# Reuse the engine's ONE id generator — a NEW caller for anthology ids. gen_id is
# a pure function ("%s_%s" % (prefix, uuid4().hex[:20]), anthology_state.py:272);
# the sibling import mirrors anthology_registry.py's `from cover_render import ...`.
sys.path.insert(0, str(SCRIPTS))
from anthology_state import gen_id  # noqa: E402  (sibling import after path bootstrap)

# Exit codes (the sibling convention; validation == 5 as in anthology_state.py).
EX_OK, EX_ERR, EX_REFUSE, EX_VALIDATION = 0, 1, 2, 5
# anthology_state.py exit 4 = mirror write committed, base op QUEUED — a SUCCESS
# for our purposes (the book is registered locally and reconciles on the tick).
EX_STATE_BASE_DEFERRED = 4

ANTH_PREFIX = "ANTH"          # Book IDs are "ANTH_<20 hex>".
KEY_DELIM = "::"              # the composite-key delimiter a Book ID must never contain.
# The LIVE author-intake form is a Convert and Flow (LeadConnector) HOSTED form; its
# public URL shape is <base>/widget/form/<form_id>. The Book ID rides the ONE query
# param anthology_id onto the form's HIDDEN anthology_id field (SKILL.md:52; router
# accepts customData.anthology_id, intake_router.py:133-134), so authors never type it.
#
# G3 QUERY-KEY LAW: the query key is EXACTLY "anthology_id" (the form's hidden-field
# key) — NEVER "anthology_active_id" (that is the CONTACT custom field the delivery
# writer stamps with the ACTIVE anthology, a different thing; conflating the two is the
# G3 defect this constant pins shut).
#
# The GHL hosted-form domain and the UNIVERSAL intake form id are fleet-wide platform /
# universal values (ONE shared author-intake form for the whole engine), never a per-
# client domain or credential; both stay overridable per box (config intake.forms_base_url
# / intake.universal_intake_form_id, or --forms-base / --intake-form-id).
WIDGET_FORM_PATH = "/widget/form"                         # GHL/LeadConnector hosted-form path prefix
INTAKE_QUERY_KEY = "anthology_id"                         # G3: the hidden-field key (NOT anthology_active_id)
DEFAULT_FORMS_BASE = "https://link.msgsndr.com"           # GHL LeadConnector public hosted-form domain
DEFAULT_UNIVERSAL_INTAKE_FORM_ID = "U65pwoeMTy1niMqllKWG" # the LIVE universal author-intake form id

PY = sys.executable or "python3"


# --------------------------------------------------------------------------- #
# The minter (the single authority) + the link builder.
# --------------------------------------------------------------------------- #
def _bad_id_shape(v) -> bool:
    """Byte-identical to intake_router._bad_id_shape / the S0 gate (:645): empty,
    contains the composite-key delimiter, or > 256 chars is refused."""
    return (not v) or (KEY_DELIM in v) or (len(v) > 256)


def mint_book_id() -> str:
    """Mint ONE new Book ID. This module is the SINGLE authority for anthology ids;
    the engine trusts a supplied id but never invents one, so the minted id — never
    a GHL/Convert-and-Flow fabrication — is the source of truth."""
    aid = gen_id(ANTH_PREFIX)          # "ANTH_<uuid4 hex[:20]>"
    if _bad_id_shape(aid) or not aid.startswith(ANTH_PREFIX + "_"):
        raise RuntimeError("minted id failed the shape guard: %r" % aid)
    return aid


def _load_config(explicit=None) -> dict:
    """Best-effort read of the resolved per-box engine config, else the template,
    else {}. Only the NON-secret forms-base knob is read here. Mirrors
    gate_engine._load_config; the config file is owned by another unit and is never
    written from here."""
    for p in (Path(explicit) if explicit else None, DEFAULT_CONFIG, TEMPLATE_CONFIG):
        if p and p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                continue
    return {}


def resolve_forms_base(cfg, override="") -> str:
    """The PUBLIC GHL hosted-form base URL. Precedence: CLI override > config
    intake.forms_base_url > the fleet-wide GHL LeadConnector default. A per-CLIENT
    domain is never baked in; the default is the shared platform host only."""
    if override and override.strip():
        return override.strip()
    base = (((cfg.get("intake") or {}).get("forms_base_url")) or "").strip()
    return base or DEFAULT_FORMS_BASE


def resolve_form_id(cfg, override="") -> str:
    """The intake FORM id the minted link targets. Precedence: CLI --intake-form-id >
    config intake.universal_intake_form_id > the fleet-wide UNIVERSAL author-intake
    form. One shared universal form serves the whole engine; it is not a per-client
    secret, and it stays overridable per box."""
    if override and override.strip():
        return override.strip()
    fid = (((cfg.get("intake") or {}).get("universal_intake_form_id")) or "").strip()
    return fid or DEFAULT_UNIVERSAL_INTAKE_FORM_ID


def build_intake_link(forms_base, form_id, anthology_id) -> str:
    """The minted author-intake link, EXACTLY:
        <forms_base>/widget/form/<form_id>?anthology_id=<minted>
    The SINGLE query key is anthology_id (G3: the form's hidden-field key, NEVER
    anthology_active_id) and its value is the minted Book ID. forms_base may be empty
    -> a RELATIVE link (path only), never a fabricated domain. The form id and the id
    value are url-encoded."""
    base = (forms_base or "").rstrip("/")
    fid = quote(form_id or "", safe="")
    return "%s%s/%s?%s=%s" % (
        base, WIDGET_FORM_PATH, fid, INTAKE_QUERY_KEY, quote(anthology_id or "", safe=""))


# --------------------------------------------------------------------------- #
# Sibling-CLI orchestration.
# --------------------------------------------------------------------------- #
def _run(argv):
    """Shell a sibling engine CLI. Returns (returncode, parsed_json_or_None). On a
    non-zero exit the sub-CLI's own operator surface is passed through to stderr."""
    proc = subprocess.run([PY] + [str(x) for x in argv],
                          capture_output=True, text=True)
    parsed = None
    out = proc.stdout or ""
    try:
        parsed = json.loads(out)
    except (ValueError, TypeError):
        parsed = None
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr or out)
    return proc.returncode, parsed


def _mask(v):
    v = str(v or "")
    return ("..." + v[-4:]) if len(v) > 4 else "..."


def run_start(*, producer_id, book_name, location_id, intake_form_id="",
              min_chapters=None, theme="", drive_folder="", pipeline_id="",
              forms_base="", config=None, state_dir="", db="", field_map="",
              registry=""):
    """B1-B4: mint -> upsert-anthology (ledger row) -> registry bind (SHARED
    pipeline) -> intake link. Returns (result_dict, exit_code). Reuses the sole-
    writer and registry CLIs verbatim; it never re-implements a write."""
    if not (producer_id and str(producer_id).strip()):
        return {"ok": False, "action": "start", "error": "missing --producer-id"}, EX_VALIDATION
    if not (book_name and str(book_name).strip()):
        return {"ok": False, "action": "start", "error": "missing --book-name"}, EX_VALIDATION
    if not (location_id and str(location_id).strip()):
        return {"ok": False, "action": "start", "error": "missing --location-id"}, EX_VALIDATION

    # ---- B1: mint the Book ID (the single authority).
    aid = mint_book_id()

    # Resolve the forms base + universal intake form id ONCE (per-box config / built-in
    # universal default); used by BOTH the registry binding and the emitted link so the
    # binding records the same form the author link points at.
    cfg = _load_config(config)
    resolved_form_id = resolve_form_id(cfg, intake_form_id)

    # ---- B2: register the book in the ledger (the authoritative Book ID registry).
    up = [STATE_WRITER, "upsert-anthology", "--anthology-id", aid,
          "--producer-id", producer_id, "--name", book_name,
          "--caf-location-binding", location_id, "--json"]
    if theme:
        up += ["--theme", theme]
    if min_chapters is not None:
        up += ["--min-chapters", str(min_chapters)]
    if drive_folder:
        up += ["--drive-folder-id", drive_folder]
    if db:
        up += ["--db", db]
    if state_dir:
        up += ["--state-dir", state_dir]
    rc, parsed = _run(up)
    if rc not in (EX_OK, EX_STATE_BASE_DEFERRED):
        return {"ok": False, "action": "start", "step": "upsert-anthology",
                "anthology_id": aid, "exit": rc,
                "error": "ledger upsert-anthology failed (exit %d)" % rc}, rc
    base_deferred = (rc == EX_STATE_BASE_DEFERRED)

    # ---- B3: bind CAF to the STANDARD SHARED pipeline. No --pipeline-id => `bind`
    #          derives the resolved standard pipeline (operator decision: one shared
    #          pipeline, no per-book pipeline).
    bind = [REGISTRY, "--location-id", location_id]
    if field_map:
        bind += ["--field-map", field_map]
    if registry:
        bind += ["--registry", registry]
    bind += ["bind", "--anthology-id", aid]
    if pipeline_id:                                   # explicit override only
        bind += ["--pipeline-id", pipeline_id]
    if resolved_form_id:
        bind += ["--form-ids", json.dumps({"intake": resolved_form_id})]
    if drive_folder:
        bind += ["--drive-folder", drive_folder]
    rc_b, _ = _run(bind)
    if rc_b != EX_OK:
        return {"ok": False, "action": "start", "step": "registry-bind",
                "anthology_id": aid, "exit": rc_b,
                "error": "registry bind failed (exit %d)" % rc_b,
                "hint": "the shared standard pipeline is unresolved on this box: run "
                        "`anthology_registry.py provision-pipeline` first, or pass "
                        "--pipeline-id for an explicit pre-existing pipeline"}, rc_b

    # ---- B4: emit the per-book author-intake link (GHL hosted form; ONE query key).
    fb = resolve_forms_base(cfg, forms_base)
    link = build_intake_link(fb, resolved_form_id, aid)

    result = {
        "ok": True, "action": "start", "anthology_id": aid,
        "producer_id": producer_id, "book_name": book_name,
        "location": _mask(location_id),
        "pipeline": ("override:%s" % pipeline_id) if pipeline_id else "shared-standard",
        "created": bool((parsed or {}).get("created", True)),
        "intake_form_id": resolved_form_id or None,
        "intake_link": link,
        "forms_base_configured": bool(fb),
    }
    if base_deferred:
        result["base_deferred"] = True
        result["note"] = ("ledger mirror write committed; base op queued (state exit "
                           "4) — reconcile-mirror flushes it")
    return result, EX_OK


# --------------------------------------------------------------------------- #
# Emit + command handlers.
# --------------------------------------------------------------------------- #
def _emit(obj, as_json):
    if as_json:
        sys.stdout.write(json.dumps(obj, ensure_ascii=False, sort_keys=True) + "\n")
    else:
        head = "OK" if obj.get("ok") else "REFUSED"
        sys.stdout.write("%s [%s]\n" % (head, obj.get("action", "")))
        for k in ("anthology_id", "producer_id", "book_name", "pipeline",
                  "intake_form_id", "intake_link", "forms_base_configured",
                  "created", "base_deferred", "step", "exit", "error", "hint",
                  "note", "note_link"):
            if k in obj and obj[k] is not None:
                sys.stdout.write("  %-20s %s\n" % (k, obj[k]))
    return obj


def cmd_mint(args):
    aid = mint_book_id()
    return _emit({"ok": True, "action": "mint", "anthology_id": aid}, args.json), EX_OK


def cmd_intake_link(args):
    aid = args.anthology_id
    if _bad_id_shape(aid):
        return _emit({"ok": False, "action": "intake-link",
                      "error": "anthology_id fails the shape guard (empty / '::' / >256)"},
                     args.json), EX_VALIDATION
    cfg = _load_config(args.config)
    fb = resolve_forms_base(cfg, getattr(args, "forms_base", "") or "")
    fid = resolve_form_id(cfg, getattr(args, "intake_form_id", "") or "")
    link = build_intake_link(fb, fid, aid)
    out = {"ok": True, "action": "intake-link", "anthology_id": aid,
           "book_name": args.book_name or "", "intake_form_id": fid,
           "intake_link": link, "forms_base_configured": bool(fb)}
    return _emit(out, args.json), EX_OK


def cmd_start(args):
    result, rc = run_start(
        producer_id=args.producer_id, book_name=args.book_name,
        location_id=args.location_id, intake_form_id=args.intake_form_id or "",
        min_chapters=args.min_chapters, theme=args.theme or "",
        drive_folder=args.drive_folder or "", pipeline_id=args.pipeline_id or "",
        forms_base=getattr(args, "forms_base", "") or "", config=args.config,
        state_dir=args.state_dir or "", db=args.db or "",
        field_map=args.field_map or "", registry=args.registry or "")
    return _emit(result, args.json), rc


# --------------------------------------------------------------------------- #
# CLI.
# --------------------------------------------------------------------------- #
def build_parser():
    p = argparse.ArgumentParser(
        prog="anthology_book.py",
        description="Producer 'start a book' minter for the Anthology Engine "
                    "(Skill 59): the SINGLE authority for Book IDs + the intake-link "
                    "generator. Mints an anthology_id, registers it via the existing "
                    "sole writer, binds it to the shared pipeline via the existing "
                    "registry, and emits the author intake link.")
    p.add_argument("--json", action="store_true", help="emit the result as JSON")
    sub = p.add_subparsers(dest="cmd", required=True)

    def add(name, fn, help_):
        sp = sub.add_parser(name, help=help_)
        sp.set_defaults(_fn=fn, _name=name)
        # Accept --json AFTER the subcommand too (the natural call shape), with a
        # SUPPRESS default so an unset flag never clobbers a parent-set value — the
        # exact argparse subparser-default-clobber workaround the siblings use.
        sp.add_argument("--json", action="store_true",
                        default=argparse.SUPPRESS, help=argparse.SUPPRESS)
        return sp

    add("mint", cmd_mint, "mint ONE Book ID (ANTH_<hex>) and print it")

    s = add("intake-link", cmd_intake_link,
            "build a book's shareable author intake link from a Book ID + name")
    s.add_argument("--anthology-id", required=True)
    s.add_argument("--book-name", default="", help="display name (metadata only; NOT in the link)")
    s.add_argument("--forms-base", dest="forms_base", default="",
                   help="override the public forms base URL (else per-box config / built-in host)")
    s.add_argument("--intake-form-id", dest="intake_form_id", default="",
                   help="override the universal intake form id (else per-box config / built-in universal)")
    s.add_argument("--config", default=None, help="path to the resolved engine-config.json")

    s = add("start", cmd_start,
            "START A BOOK: mint -> upsert-anthology -> registry bind (shared pipeline) -> intake link")
    s.add_argument("--producer-id", required=True, help="the owning producer (must already exist)")
    s.add_argument("--book-name", required=True, help="the book's display name")
    s.add_argument("--location-id", required=True, help="the Convert and Flow location id")
    s.add_argument("--intake-form-id", dest="intake_form_id", default="",
                   help="the shared universal intake form id (stored in the binding's form_ids)")
    s.add_argument("--min-chapters", dest="min_chapters", type=int, default=None)
    s.add_argument("--theme", default="")
    s.add_argument("--drive-folder", dest="drive_folder", default="")
    s.add_argument("--pipeline-id", dest="pipeline_id", default="",
                   help="OVERRIDE only; omit to bind the standard SHARED pipeline (default)")
    s.add_argument("--forms-base", dest="forms_base", default="",
                   help="override the public forms base URL (else per-box config)")
    s.add_argument("--config", default=None, help="path to the resolved engine-config.json")
    s.add_argument("--state-dir", dest="state_dir", default="",
                   help="engine state dir passthrough to the ledger writer")
    s.add_argument("--db", default="", help="explicit ledger SQLite path passthrough")
    s.add_argument("--field-map", dest="field_map", default="",
                   help="field-map.json passthrough to the registry (default: config copy)")
    s.add_argument("--registry", default="",
                   help="registry.json passthrough (default: the per-box state dir)")

    add("self-test", None, "run the offline round-trip battery and exit")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args._name == "self-test":
        return self_test()
    if not hasattr(args, "json"):
        args.json = False
    _obj, rc = args._fn(args)
    return rc


# ===========================================================================
# SELF-TEST — offline round-trip (temp state / registry / field-map / config).
# Proves: mint -> upsert -> bind -> link; a second mint is distinct; an author
# intake with the MINTED id is ACCEPTED while an UNKNOWN id is still REFUSED;
# the link is well-formed and round-trips. No base, no network.
# ===========================================================================
def self_test():
    import shutil
    import tempfile
    from urllib.parse import urlsplit, parse_qs

    checks = []

    def ok(label, cond):
        checks.append((label, bool(cond)))

    tmp = Path(tempfile.mkdtemp(prefix="anthology_book_selftest_"))
    try:
        db = tmp / "state.db"
        reg = tmp / "registry.json"
        fmp = tmp / "field-map.json"
        cfgp = tmp / "engine-config.json"

        # ensure the child processes run MIRROR-ONLY (no base id in this env).
        for k in ("ANTHOLOGY_STATE_BASE_ID", "AIRTABLE_API_KEY", "AIRTABLE_TOKEN",
                  "AIRTABLE_PAT", "ANTHOLOGY_STATE_AIRTABLE_KEY"):
            os.environ.pop(k, None)

        # (1) the minter: distinct, well-shaped ids.
        id1, id2 = mint_book_id(), mint_book_id()
        ok("mint id1 well-formed", id1.startswith("ANTH_") and not _bad_id_shape(id1))
        ok("mint id2 well-formed", id2.startswith("ANTH_") and not _bad_id_shape(id2))
        ok("two mints are distinct", id1 != id2)
        ok("minted id is ANTH_ + 20 hex", len(id1) == len("ANTH_") + 20)

        # A resolved field-map: simulate a provisioned box's SHARED standard pipeline
        # (the committed template ships resolved.pipeline_id null, so bind would STOP).
        base_fm = json.loads((SKILL_DIR / "config" / "field-map.json").read_text(encoding="utf-8"))
        stages = base_fm["pipeline"]["standard_stages"]
        base_fm["pipeline"]["resolved"] = {
            "pipeline_id": "pl_selftest_shared",
            "stage_ids": {s["name"]: "stg_%s" % s["name"].lower() for s in stages},
            "provisioned_at": "2026-01-01T00:00:00+00:00",
            "location_masked": "...test",
        }
        fmp.write_text(json.dumps(base_fm), encoding="utf-8")

        # A per-box config carrying the forms base (SOURCED, never hardcoded).
        cfgp.write_text(json.dumps(
            {"intake": {"forms_base_url": "https://forms.example.test"}}), encoding="utf-8")

        # Ledger bootstrap + producer (start assumes the producer already exists).
        rc, _ = _run([STATE_WRITER, "--db", db, "bootstrap"])
        ok("ledger bootstrap exit 0", rc == 0)
        rc, _ = _run([STATE_WRITER, "--db", db, "upsert-producer",
                      "--producer-id", "prodSELFTEST",
                      "--producer-email", "owner@example.test",
                      "--display-name", "Owner"])
        ok("producer upsert exit 0", rc == 0)

        # (2) the full START flow: mint -> upsert -> bind(shared) -> link.
        book = "Voices & Vision: Book One"
        result, rc = run_start(
            producer_id="prodSELFTEST", book_name=book,
            location_id="LOC_SELFTEST_AAA", intake_form_id="form_self",
            min_chapters=3, config=str(cfgp), db=str(db),
            field_map=str(fmp), registry=str(reg))
        ok("start flow exit 0", rc == 0 and result.get("ok") is True)
        minted = result.get("anthology_id", "")
        ok("start minted a Book ID", minted.startswith("ANTH_") and not _bad_id_shape(minted))
        ok("start bound the SHARED pipeline", result.get("pipeline") == "shared-standard")

        # registered in the ledger (the authoritative Book-ID allow-list).
        rc, _ = _run([STATE_WRITER, "--db", db, "get-anthology", "--anthology-id", minted])
        ok("minted book registered in ledger (get-anthology exit 0)", rc == 0)

        # bound in the per-box registry, to the shared pipeline + intake form.
        rc, parsed = _run([REGISTRY, "--registry", reg, "--json",
                           "resolve", "--anthology-id", minted])
        ok("minted book bound in registry (resolve exit 0)", rc == 0)
        ok("binding uses the shared standard pipeline",
           (parsed or {}).get("pipeline_id") == "pl_selftest_shared")
        ok("binding carries the intake form id",
           ((parsed or {}).get("form_ids") or {}).get("intake") == "form_self")
        # _default_stage_map keys the map by ENGINE stage (s0..s9), so its size is
        # the engine-stage map count (10; s5 and s6 both resolve to "Chapter"), not
        # the 9 pipeline stages.
        engine_stage_n = len(base_fm["pipeline"]["engine_stage_to_pipeline_stage"])
        ok("binding has a full engine-stage map",
           len((parsed or {}).get("caf_stage_map") or {}) == engine_stage_n)

        # (3) a second start yields a DISTINCT id.
        result2, rc2 = run_start(
            producer_id="prodSELFTEST", book_name="Second Book",
            location_id="LOC_SELFTEST_AAA", config=str(cfgp), db=str(db),
            field_map=str(fmp), registry=str(reg))
        ok("second start exit 0", rc2 == 0)
        ok("second start distinct id", result2.get("anthology_id") != minted)

        # (4) author intake: MINTED id ACCEPTED, UNKNOWN id REFUSED. The engine
        #     trusts a supplied id but validates it against the ledger.
        rc, _ = _run([STATE_WRITER, "--db", db, "upsert-participant",
                      "--contact-id", "cSELF", "--anthology-id", minted,
                      "--first-name", "Ada"])
        ok("intake with MINTED id accepted (exit 0)", rc == 0)
        rc, _ = _run([STATE_WRITER, "--db", db, "upsert-participant",
                      "--contact-id", "cSELF", "--anthology-id", "ANTH_neverminted00000"])
        ok("intake with UNKNOWN id refused (exit 3)", rc == 3)

        # (5) the intake link is the GHL hosted-form URL, ONE query key, round-trips.
        link = result.get("intake_link", "")
        parts = urlsplit(link)
        q = parse_qs(parts.query)
        ok("link uses the configured forms base",
           link.startswith("https://forms.example.test/widget/form/"))
        ok("link path is /widget/form/<form_id>", parts.path == "/widget/form/form_self")
        ok("link carries the minted anthology_id", q.get("anthology_id", [""])[0] == minted)
        # G3: the ONE query key is anthology_id, NEVER anthology_active_id.
        ok("link query key is anthology_id (G3)", "anthology_id" in q)
        ok("link has NO anthology_active_id key (G3)", "anthology_active_id" not in q)
        ok("link has EXACTLY one query key", list(q.keys()) == ["anthology_id"])
        ok("start records the resolved intake form id", result.get("intake_form_id") == "form_self")
        ok("start keeps the book name as metadata", result.get("book_name") == book)

        # CANONICAL live link: GHL host + the LIVE universal intake form id -> EXACT shape.
        canon = build_intake_link(DEFAULT_FORMS_BASE, DEFAULT_UNIVERSAL_INTAKE_FORM_ID, minted)
        ok("canonical live link is the exact GHL widget-form URL",
           canon == "https://link.msgsndr.com/widget/form/%s?anthology_id=%s"
                    % (DEFAULT_UNIVERSAL_INTAKE_FORM_ID, minted))

        # Defaults (no config, no override) -> the built-in universal form + GHL host.
        ok("default forms base resolves to the GHL host", resolve_forms_base({}) == DEFAULT_FORMS_BASE)
        ok("default form id resolves to the universal intake form",
           resolve_form_id({}) == DEFAULT_UNIVERSAL_INTAKE_FORM_ID)

        # relative fallback when forms base is explicitly empty (never fabricates a domain).
        rel = build_intake_link("", "form_self", minted)
        ok("relative link when forms base empty", rel.startswith("/widget/form/"))
        ok("relative link still carries the minted id", ("anthology_id=%s" % minted) in rel)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    passed = sum(1 for _, c in checks if c)
    for label, c in checks:
        sys.stdout.write("  [%s] %s\n" % ("PASS" if c else "FAIL", label))
    sys.stdout.write("anthology_book self-test: %d/%d passed\n" % (passed, len(checks)))
    return EX_OK if passed == len(checks) else EX_ERR


if __name__ == "__main__":
    sys.exit(main())
