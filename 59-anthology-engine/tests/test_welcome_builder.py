#!/usr/bin/env python3
"""test_welcome_builder.py -- unit tests for the U20 producer Welcome card
builder (scripts/u20_modules/welcome_builder.py, Skill 59).

THE WELCOME BUILDER LAW, pinned from the module and its doctrine
(u20_modules/__init__.py):

  * The card is BOARD COPY with a stable id: card_key 'welcome::producer',
    card_type 'welcome', title 'Welcome to the Anthology Engine', builder
    'welcome_builder.py'. The card body is rendered from HOW-TO-USE.md -- the
    engine's ONLY producer-language source of truth -- IN ITS EXACT SECTION
    ORDER: the guide's own '# ' title line, the intro paragraph (the guide's
    own opening words), then the six pinned '## ' sections verbatim. Nothing
    is invented, nothing is dropped (SOURCE_HEADINGS is a FULL set).
  * Producer-language law, ENFORCED not described: the body MUST mention
    'participant' / 'participants' (the producer's co-authors) and MUST carry
    the Convert and Flow naming (the client-facing platform name), matched on
    word boundaries. A guide edit that breaks either FAILS the build
    (exit 5), never ships.
  * The Trevor gate: the engine database is READ-ONLY in dry-run. The ONE
    INSERT is executed ONLY under --execute; WITHOUT --execute build STOPS
    (exit 2, AF-AE-WELCOME-NO-EXECUTE) after reporting exactly what it WOULD
    insert -- never a silent no-op, never a silent write. plan is OFFLINE:
    it never even opens the database.
  * Fail-closed on both sides of the gate: the READ-ONLY control
    (sqlite uri mode=ro) is the gate's own known-good control -- a missing or
    unreadable database is a STOP (exit 2, AF-AE-WELCOME-DB-UNREADABLE)
    BEFORE any write path; a schema-less or drifted meta table is a MISMATCH
    (exit 5, AF-AE-WELCOME-DB-MISMATCH); a foreign value already under the
    card's own key is NEVER overwritten; and a write is never trusted
    without read-back (AF-AE-WELCOME-READBACK-MISMATCH, exit 5).
  * SQL discipline: one INSERT, all columns named explicitly, one parameter
    per value (the driver escapes every value -- SQL is never
    string-interpolated). The meta schema law is whitespace-agnostic (the
    engine's own multi-line 'CREATE TABLE IF NOT EXISTS meta (...)' DDL
    normalizes to the pinned shape; a drifted column set does not).
  * Secrets doctrine: the module holds NO credential and resolves NONE -- the
    only env names it reads are ANTHOLOGY_STATE_DIR, OPENCLAW_DATA_DIR, and
    HOME (state-dir resolution, never credentials); no HTTP import, no
    subprocess, no browser UA of its own (the Cloudflare-edge UA is
    CAF_BROWSER_UA, owned by anthology_registry.py). Every machine surface
    reports the card body as a sha256 FINGERPRINT, never the body text.

OFFLINE BY DESIGN: no network, no secrets, no engine state -- every database
test runs against a temp dir that pytest cleans up, and every --execute run
happens ONLY against that temp database (never the engine's own state dir).

Run: python3 -m pytest 59-anthology-engine/tests/test_welcome_builder.py -q
 or: python3 59-anthology-engine/tests/test_welcome_builder.py
"""
import io
import json
import re
import sqlite3
import sys
from pathlib import Path

import pytest

SKILL_DIR = Path(__file__).resolve().parent.parent
SCRIPTS = SKILL_DIR / "scripts"
U20 = SCRIPTS / "u20_modules"
U20_INIT = U20 / "__init__.py"

for _p in (SCRIPTS, U20):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import welcome_builder as wb  # noqa: E402

# Anthropic-family id shapes assembled from fragments; no banned literal
# appears in this test file either.
_CLAUDE = "clau" + "de-"
_ANTH = "anthro" + "pic"
BANNED_IDS = re.compile(
    _CLAUDE + r"|us\." + _ANTH + r"\b|" + _ANTH + r"\.com", re.I)

# The module's own golden guide -- the contract it pins in self-test. The
# tests reuse it (mirror-pinned, never re-authored) so a drift in the golden
# itself is caught by both the module's self-test and here.
GOLDEN = wb.GOLDEN_GUIDE

# Credential-shaped VALUE shapes that must never appear anywhere in the
# module's source (labels like CARD_KEY are fine; values are not).
CRED_VALUE_SHAPES = re.compile(
    r'=\s*["\'](sk-|eyJ|AIza|ghp_|xoxb-|AKIA)', re.M)


# ---------------------------------------------------------------------------
# Module source + package doctrine (fail-closed / secrets / stdlib-only).
# ---------------------------------------------------------------------------
def test_module_is_stdlib_only_no_http_no_subprocess():
    """The module's only surfaces are the local guide, the version file, and
    the local database -- no HTTP (no browser UA of its own; the CF-1010
    UA belongs to anthology_registry.py), no subprocess, no network."""
    src = Path(wb.__file__).read_text(encoding="utf-8")
    for line in src.splitlines():
        stripped = line.strip()
        if stripped.startswith(("import ", "from ")):
            assert "urllib" not in stripped
            assert "requests" not in stripped
            assert "subprocess" not in stripped
            assert "socket" not in stripped


def test_module_resolves_no_credential_from_env():
    """Secrets doctrine: the module reads env for STATE-DIR RESOLUTION ONLY.
    The complete set of env names it touches is the state-dir trio -- never a
    key/token/secret label, so a Welcome card (board copy) cannot leak a
    secret it never holds."""
    src = Path(wb.__file__).read_text(encoding="utf-8")
    env_names = re.findall(r'os\.environ\.get\("([^"]+)"', src)
    assert env_names == ["ANTHOLOGY_STATE_DIR", "OPENCLAW_DATA_DIR", "HOME"]


def test_module_has_no_credential_shaped_value_and_no_model_ids():
    """Never a secret-shaped literal, never an Anthropic runtime identifier
    in the runtime file (the doctrine sentence in the docstring is
    deliberately not matched by BANNED_IDS)."""
    src = Path(wb.__file__).read_text(encoding="utf-8")
    assert not CRED_VALUE_SHAPES.search(src)
    assert not BANNED_IDS.search(src)


def test_package_init_is_empty_and_carries_the_gate_doctrine():
    """u20_modules/__init__.py is a pure namespace container: zero imports,
    and its doctrine text pins the READ-ONLY dry-run / --execute gate and the
    HOW-TO-USE.md provenance law -- the same laws this module enforces."""
    text = U20_INIT.read_text(encoding="utf-8")
    assert text.count("import ") == text.count("# import") or "import" not in [
        ln.split()[0] for ln in text.splitlines() if ln.strip()]
    for line in text.splitlines():
        assert not line.lstrip().startswith(("import ", "from ")), \
            "package init must import nothing"
    assert "READ-ONLY" in text
    assert "--execute" in text
    assert "HOW-TO-USE.md" in text


# ---------------------------------------------------------------------------
# The card contract (stable ids and the law's constants).
# ---------------------------------------------------------------------------
def test_card_contract_constants_are_stable():
    assert wb.CARD_KEY == "welcome::producer"
    assert wb.CARD_TYPE == "welcome"
    assert wb.CARD_TITLE == "Welcome to the Anthology Engine"
    assert wb.CARD_SOURCE_FILE == "HOW-TO-USE.md"
    assert wb.CARD_BUILDER == "welcome_builder.py"
    assert wb.STATE_DB_NAME == "anthology_state.db"
    assert wb.META_TABLE == "meta"


def test_exit_code_convention():
    """House exit scheme 0/1/2/3/5 with 4 = enforced violation."""
    assert (wb.EX_OK, wb.EX_ERR, wb.EX_STOP, wb.EX_HELD,
            wb.EX_MISMATCH) == (0, 1, 2, 3, 5)
    assert wb.EX_VIOLATION == 4


def test_section_law_is_the_full_six_heading_set():
    """The content law pins six headings, byte-exact, in the guide's own
    order -- a FULL set: a heading renamed, dropped, or reordered is a
    refusal, never a silent contradiction of the guide."""
    assert wb.SOURCE_HEADINGS == (
        "What the engine does for you",
        "Where you work: the Anthology board",
        "What your participants see",
        "Assembling the anthology",
        "The platform",
        "Good to know",
    )


def test_section_law_agrees_with_live_guide_structure():
    """The pinned law and the shipped HOW-TO-USE.md agree today: the guide's
    own title line, its intro paragraph, and all six headings in document
    order. The card body renders from this document, so a law-vs-document
    disagreement would be caught here first."""
    text = wb.HOW_TO_USE.read_text(encoding="utf-8")
    lines = text.splitlines()
    assert lines[0].startswith("# ")
    doc_heads = [ln[3:].strip() for ln in lines
                 if ln.strip().startswith("## ")]
    assert doc_heads == list(wb.SOURCE_HEADINGS)


# ---------------------------------------------------------------------------
# The pure build (offline: guide + version file are the only inputs).
# ---------------------------------------------------------------------------
def test_golden_build_passes_and_body_carries_guide_verbatim():
    card = wb.build_card(GOLDEN, "0.1.24-test",
                         built_at="2026-08-11T00:00:00Z")
    body = card["body"]
    assert card["card_key"] == wb.CARD_KEY
    assert card["title"] == wb.CARD_TITLE
    assert card["source_file"] == wb.CARD_SOURCE_FILE
    assert card["builder"] == wb.CARD_BUILDER
    assert card["engine_version"] == "0.1.24-test"
    assert body.startswith("# Anthology Engine -- Producer How-To\n")
    # the guide's intro paragraph is carried verbatim (never invented,
    # never dropped); the section-order law is pinned separately below
    assert "This is your guide to producing an anthology." in body
    # every section heading verbatim, in exact document order
    order = [body.index("## %s" % h) for h in wb.SOURCE_HEADINGS]
    assert order == sorted(order)


def test_golden_source_sha256_is_sha256_of_guide_bytes():
    card = wb.build_card(GOLDEN, "0.1.24-test",
                         built_at="2026-08-11T00:00:00Z")
    assert card["source_sha256"] == wb._sha256_bytes(
        GOLDEN.encode("utf-8"))


def test_live_guide_build_holds_the_law():
    """The live HOW-TO-USE.md (the doc the card is built FROM) builds today:
    producer language holds (participant(s) present, Convert and Flow naming
    present), the card body is deterministic across two builds, and the
    fingerprint is the sha256 of the guide itself."""
    text, version = wb._read_guide()
    assert version  # skill-version.txt is shipped and non-empty
    a = wb.build_card(text, version, built_at="2026-08-11T00:00:00Z")
    b = wb.build_card(text, version, built_at="2026-08-11T00:00:00Z")
    assert a == b
    assert a["source_sha256"] == wb._sha256_bytes(text.encode("utf-8"))
    body_lower = a["body"].lower()
    for req in wb.REQUIRED_WORDS:
        if req in body_lower:
            break
    else:
        pytest.fail("live card body must mention participant(s)")
    assert "convert and flow" in body_lower


def test_content_law_is_enforced_before_any_statement():
    """Producer-language law, enforced not described: the body MUST carry
    participant(s) and the Convert and Flow naming (word boundaries only --
    'converted'/'nonparticipant' never satisfy the law)."""
    wb._check_content_law("Everything is part of Convert and Flow. "
                          "Your participants decide.")
    wb._check_content_law("Convert and Flow. participant")
    for bad in (
        "Everything is part of Convert and Flow.",        # no participant
        "Your participants decide.",                      # no Convert/Flow
        "Everything is part of the platform here.",       # neither
        "Converted and Flowing participants decide.",  # phrase must be exact
        "Everything is part of Convert and Flow. "
        "Nonparticipants decide.",                        # boundary, not token
    ):
        with pytest.raises(ValueError):
            wb._check_content_law(bad)


def test_source_drift_is_refused_never_ships_a_card():
    """A heading renamed, dropped, or reordered in the guide NEVER ships a
    card -- each mutation raises ValueError out of the pure build."""
    mutations = (
        GOLDEN.replace("## The platform", "## The Platforms"),
        GOLDEN.replace("## Good to know\n", ""),
        GOLDEN.replace("## What your participants see",
                       "## What your co-authors see"),
        # headings swapped in place -> seen order drifts from the law
        GOLDEN.replace("## What your participants see",
                       "## Assembling the anthology").replace(
            "## Assembling the anthology",
            "## What your participants see"),
    )
    for mutated in mutations:
        with pytest.raises(ValueError):
            wb.build_card(mutated, "0.1.24-test",
                          built_at="2026-08-11T00:00:00Z")


def test_intro_paragraph_is_carried_verbatim_never_invented():
    """The guide's intro paragraph is the document's OWN opening words,
    carried into the card body verbatim -- never invented, never dropped
    (its position in the body is deliberately not pinned: the section-order
    law governs the six headings, and the intro renders as one block)."""
    body = wb._build_card_body(GOLDEN)
    intro = "This is your guide to producing an anthology. You are the " \
            "producer, the\nowner of this Command Center. Your co-authors " \
            "are your participants."
    assert intro in body
    # the body renders the intro as ONE contiguous verbatim block
    assert body.count("This is your guide to producing an anthology.") == 1


def test_build_insert_is_named_columns_one_parameter_per_value():
    """The ONE statement: all columns named explicitly, one parameter per
    value -- the driver escapes every value, SQL is never interpolated; the
    payload round-trips and the key rides the statement as a parameter,
    never as text."""
    card = wb.build_card(GOLDEN, "0.1.24-test",
                         built_at="2026-08-11T00:00:00Z")
    sql_stmt, params = wb.build_insert(card)
    assert sql_stmt.startswith("INSERT INTO meta(key, value)")
    assert "VALUES (?, ?)" in sql_stmt
    assert "ON CONFLICT(key) DO UPDATE SET value = excluded.value" in sql_stmt
    assert len(params) == 2 and params[0] == wb.CARD_KEY
    assert params[0] not in sql_stmt.replace("meta(key, value)", "")
    assert json.loads(params[1]) == card


def test_sha256_digest_utility_matches_hashlib():
    assert wb._sha256_bytes(b"hello") == (
        "2cf24dba5fb0a30e26e83b2ac5b9e29e"
        "1b161e5c1fa7425e73043362938b9824")


# ---------------------------------------------------------------------------
# The Trevor gate: READ-ONLY in dry-run, writes ONLY with --execute.
# ---------------------------------------------------------------------------
def test_plan_is_offline_and_never_opens_the_database(tmp_path):
    """plan reads nothing beyond the guide and the version file: the state
    database is never opened, never created -- the engine database is
    READ-ONLY in dry-run by construction because plan never touches it."""
    dev = io.StringIO()
    rc = wb.plan_action(str(tmp_path), out=dev, jsonout=dev)
    assert rc == wb.EX_OK
    assert not (tmp_path / wb.STATE_DB_NAME).exists()
    plan_json = json.loads(dev.getvalue().splitlines()[-1])
    assert plan_json["ok"] is True
    assert plan_json["dry_run"] is True
    assert plan_json["execute_required"] is True
    assert plan_json["card_key"] == wb.CARD_KEY
    assert plan_json["statement"].startswith("INSERT INTO meta(key, value)")
    # the database path rides as a MASKED file name, never a directory path
    assert plan_json["state_db"] == wb.STATE_DB_NAME
    assert str(tmp_path) not in dev.getvalue()


def test_build_without_execute_stops_and_writes_nothing(tmp_path):
    """Without --execute build STOPS (exit 2, AF-AE-WELCOME-NO-EXECUTE),
    reports exactly what it WOULD insert, and NEVER creates or touches the
    engine database -- the fail-closed dry-run contract."""
    dev = io.StringIO()
    rc = wb.build_action(str(tmp_path), execute=False, out=dev, jsonout=dev)
    assert rc == wb.EX_STOP
    out_text = dev.getvalue()
    assert "AF-AE-WELCOME-NO-EXECUTE" in out_text
    assert "WOULD-INSERT" in out_text
    assert "NOT executed" in out_text
    assert not (tmp_path / wb.STATE_DB_NAME).exists()
    j = json.loads(out_text.splitlines()[-1])
    assert j["ok"] is False and j["exit"] == wb.EX_STOP
    assert j["execute"] is False and j["reason"] == "no-execute"
    assert j["card_key"] == wb.CARD_KEY


def test_missing_database_stops_before_any_write_path(tmp_path):
    """The READ-ONLY control is the gate's own known-good control: a missing
    state database is a STOP (exit 2, AF-AE-WELCOME-DB-UNREADABLE) even
    under --execute, and the control open NEVER creates the file."""
    dev = io.StringIO()
    rc = wb.build_action(str(tmp_path), execute=True, out=dev, jsonout=dev)
    assert rc == wb.EX_STOP
    assert "AF-AE-WELCOME-DB-UNREADABLE" in dev.getvalue()
    assert not (tmp_path / wb.STATE_DB_NAME).exists()


def test_readonly_control_handle_cannot_mutate(tmp_path):
    """The sqlite uri mode=ro handle is the fail-closed control: a bug in
    this module can NEVER mutate the ledger through it, and opening a
    missing database read-only raises WITHOUT creating the file."""
    db = tmp_path / wb.STATE_DB_NAME
    with pytest.raises(sqlite3.Error):
        wb._open_readonly(db)
    assert not db.exists()
    con = sqlite3.connect(str(db))
    con.executescript(wb.META_SCHEMA_SQL)
    con.close()
    ro = wb._open_readonly(db)
    try:
        with pytest.raises(sqlite3.OperationalError) as excinfo:
            ro.execute("INSERT INTO meta(key, value) VALUES('x', 'y')")
        assert "readonly" in str(excinfo.value)
    finally:
        ro.close()


def test_schema_less_database_is_a_mismatch_never_a_blind_insert(tmp_path):
    """A database with no meta table is a REFUSAL (exit 5,
    AF-AE-WELCOME-DB-MISMATCH): the card's home does not exist, so the card
    is never inserted into an unknown schema."""
    db = tmp_path / wb.STATE_DB_NAME
    sqlite3.connect(str(db)).close()  # empty file: valid db, no tables
    dev = io.StringIO()
    rc = wb.build_action(str(tmp_path), execute=True, out=dev, jsonout=dev)
    assert rc == wb.EX_MISMATCH
    assert "AF-AE-WELCOME-DB-MISMATCH" in dev.getvalue()
    con = sqlite3.connect(str(db))
    n = con.execute("SELECT COUNT(*) FROM sqlite_master").fetchone()[0]
    con.close()
    assert n == 0, "the refusal must leave the database untouched"


def test_drifted_meta_schema_is_a_mismatch_never_an_insert(tmp_path):
    """The schema law is the engine's own column contract: a drifted meta
    DDL (an extra column) is a MISMATCH (exit 5) and nothing is written."""
    db = tmp_path / wb.STATE_DB_NAME
    con = sqlite3.connect(str(db))
    con.executescript("CREATE TABLE meta (key TEXT PRIMARY KEY, "
                      "value TEXT, extra TEXT)")
    con.close()
    dev = io.StringIO()
    rc = wb.build_action(str(tmp_path), execute=True, out=dev, jsonout=dev)
    assert rc == wb.EX_MISMATCH
    assert "AF-AE-WELCOME-DB-MISMATCH" in dev.getvalue()
    con = sqlite3.connect(str(db))
    n = con.execute("SELECT COUNT(*) FROM meta").fetchone()[0]
    con.close()
    assert n == 0


def test_schema_law_is_whitespace_agnostic_like_the_engine_ddl(tmp_path):
    """sqlite stores DDL as the engine wrote it -- the real engine schema is
    'CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)'
    with the engine's own multi-line whitespace (anthology_state.py). The
    pinned comparison normalizes ALL whitespace, so both the module's own
    single-line form and the engine's multi-line form pass -- a drifted
    column set is what the law refuses."""
    assert wb._normalize_ddl("CREATE TABLE meta (key TEXT PRIMARY KEY, "
                             "value TEXT)") == \
        wb._normalize_ddl("CREATE TABLE meta\n(\n key TEXT PRIMARY KEY,\n "
                          "value TEXT\n)")
    assert wb._normalize_ddl("CREATE TABLE meta (key TEXT PRIMARY KEY, "
                             "value TEXT, extra TEXT)") != \
        wb._normalize_ddl(wb.META_SCHEMA_NORMALIZED)
    # the engine's OWN DDL shape, executed through sqlite, passes the law
    db = tmp_path / wb.STATE_DB_NAME
    con = sqlite3.connect(str(db))
    con.executescript("CREATE TABLE IF NOT EXISTS meta (\n"
                      "    key                 TEXT PRIMARY KEY,\n"
                      "    value               TEXT\n"
                      ");")
    con.close()
    con = wb._open_readonly(db)
    try:
        assert wb._prove_schema(con) is True
    finally:
        con.close()


# ---------------------------------------------------------------------------
# The --execute path (TEMP database only -- never engine state).
# ---------------------------------------------------------------------------
def _make_state_db(tmp_path, schema=wb.META_SCHEMA_SQL, rows=None):
    """Bootstrap a temp engine state database with the meta table (and any
    seed rows), exactly as the module's own self-test does."""
    db = tmp_path / wb.STATE_DB_NAME
    con = sqlite3.connect(str(db))
    con.executescript(schema)
    for key, value in (rows or []):
        con.execute("INSERT INTO meta(key, value) VALUES(?, ?)",
                    (key, value))
    con.commit()
    con.close()
    return db


def test_execute_inserts_once_and_reads_back(tmp_path):
    """Golden full path under --execute: the schema is proven READ-ONLY
    first, the ONE INSERT executes, the READ-ONLY read-back confirms, exit
    0, exactly one row, and the stored payload round-trips the card."""
    db = _make_state_db(tmp_path)
    dev = io.StringIO()
    rc = wb.build_action(str(tmp_path), execute=True, out=dev, jsonout=dev)
    assert rc == wb.EX_OK
    out_text = dev.getvalue()
    assert "INSERTED" in out_text
    assert "confirmed it by read-back" in out_text
    j = json.loads(out_text.splitlines()[-1])
    assert j["ok"] is True and j["inserted"] is True
    assert j["card_key"] == wb.CARD_KEY
    con = wb._open_readonly(db)
    try:
        stored = wb._card_present(con)
        n = con.execute("SELECT COUNT(*) AS c FROM meta WHERE key=?",
                        (wb.CARD_KEY,)).fetchone()["c"]
    finally:
        con.close()
    assert n == 1, "the card key must exist exactly once"
    assert stored is not None
    assert json.loads(stored)["card_key"] == wb.CARD_KEY
    assert json.loads(stored)["title"] == wb.CARD_TITLE


def test_execute_is_idempotent_never_a_second_row(tmp_path):
    """A re-run sees the card present with identical content and is a clean
    NO-OP (exit 0, 'IDEMPOTENT NO-OP') -- never a duplicate row, never a
    foreign overwrite."""
    db = _make_state_db(tmp_path)
    assert wb.build_action(str(tmp_path), execute=True,
                           out=io.StringIO()) == wb.EX_OK
    dev = io.StringIO()
    rc = wb.build_action(str(tmp_path), execute=True, out=dev, jsonout=dev)
    assert rc == wb.EX_OK
    assert "IDEMPOTENT NO-OP" in dev.getvalue()
    j = json.loads(dev.getvalue().splitlines()[-1])
    assert j["ok"] is True and j["inserted"] is False
    assert j["idempotent"] is True
    con = wb._open_readonly(db)
    try:
        n = con.execute("SELECT COUNT(*) AS c FROM meta WHERE key=?",
                        (wb.CARD_KEY,)).fetchone()["c"]
    finally:
        con.close()
    assert n == 1


def test_foreign_value_under_card_key_is_never_overwritten(tmp_path):
    """A foreign value already sitting under 'welcome::producer' is a
    MISMATCH (exit 5) and stays untouched -- the card is never blindly
    overwritten, and the foreign row is never duplicated."""
    db = _make_state_db(tmp_path, rows=[(wb.CARD_KEY, "not-the-card")])
    dev = io.StringIO()
    rc = wb.build_action(str(tmp_path), execute=True, out=dev, jsonout=dev)
    assert rc == wb.EX_MISMATCH
    assert "AF-AE-WELCOME-DB-MISMATCH" in dev.getvalue()
    con = wb._open_readonly(db)
    try:
        still = wb._card_present(con)
    finally:
        con.close()
    assert still == "not-the-card"


def test_readback_disagreement_is_never_reported_inserted(tmp_path,
                                                          monkeypatch):
    """READ-BACK LAW: if the read-only re-open returns anything other than
    the exact card payload, the run is a MISMATCH (exit 5,
    AF-AE-WELCOME-READBACK-MISMATCH) -- a write is never trusted without
    read-back, and a tampered read-back is never reported as inserted."""
    _make_state_db(tmp_path)
    calls = {"n": 0}

    def tampered_card_present(con):
        # first call = the control phase (absent -> proceeds); second call
        # = the read-back phase (disagrees with the written payload)
        calls["n"] += 1
        if calls["n"] == 1:
            return None
        return "tampered"

    monkeypatch.setattr(wb, "_card_present", tampered_card_present)
    dev = io.StringIO()
    rc = wb.build_action(str(tmp_path), execute=True, out=dev, jsonout=dev)
    assert rc == wb.EX_MISMATCH
    assert "AF-AE-WELCOME-READBACK-MISMATCH" in dev.getvalue()
    assert calls["n"] == 2


def test_refused_insert_is_never_reported_inserted(tmp_path, monkeypatch):
    """A refused INSERT (read-only filesystem, locked database) is NEVER
    reported inserted: 'locked'/'busy' conditions are HELD (exit 3), any
    other refusal is a STOP (exit 2, AF-AE-WELCOME-INSERT-REFUSED) -- and
    the refusal happens after the READ-ONLY control, with no row written."""
    _make_state_db(tmp_path)
    real_connect = wb.sqlite3.connect

    def refused_connect(*args, **kwargs):
        # the read-only control opens with uri=True; the write path is the
        # plain open -- only the write path is refused
        if kwargs.get("uri"):
            return real_connect(*args, **kwargs)
        raise sqlite3.OperationalError("attempt to write a readonly database")

    monkeypatch.setattr(wb.sqlite3, "connect", refused_connect)
    dev = io.StringIO()
    rc = wb.build_action(str(tmp_path), execute=True, out=dev, jsonout=dev)
    assert rc == wb.EX_STOP
    assert "AF-AE-WELCOME-INSERT-REFUSED" in dev.getvalue()
    con = wb._open_readonly(tmp_path / wb.STATE_DB_NAME)
    try:
        assert wb._card_present(con) is None, "the refused write left no row"
    finally:
        con.close()


def test_locked_database_is_held_never_stopped_as_inserted(tmp_path,
                                                           monkeypatch):
    """A locked/busy write is a HELD (exit 3) -- retryable by the operator,
    but the module NEVER retries it and never reports it inserted."""
    _make_state_db(tmp_path)
    real_connect = wb.sqlite3.connect

    def locked_connect(*args, **kwargs):
        if kwargs.get("uri"):
            return real_connect(*args, **kwargs)
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(wb.sqlite3, "connect", locked_connect)
    dev = io.StringIO()
    rc = wb.build_action(str(tmp_path), execute=True, out=dev, jsonout=dev)
    assert rc == wb.EX_HELD
    assert "AF-AE-WELCOME-INSERT-REFUSED" in dev.getvalue()
    assert "database is locked" in dev.getvalue()


# ---------------------------------------------------------------------------
# The machine surfaces: card body rides as a fingerprint, never verbatim.
# ---------------------------------------------------------------------------
def test_machine_surfaces_report_body_fingerprint_never_body_text(tmp_path,
                                                                  capsys):
    """Never-print law: the plan and no-execute JSON surfaces carry the body
    as a sha256 FINGERPRINT and a character count -- the body text never
    echoes onto a machine surface."""
    for argv in (
        ["plan", "--state-dir", str(tmp_path), "--json"],
        ["build", "--state-dir", str(tmp_path), "--json"],
    ):
        out, _err = capsys.readouterr()
        rc = wb.main(argv)
        out, _err = capsys.readouterr()
        j = json.loads(out.strip().splitlines()[-1])
        assert rc in (wb.EX_OK, wb.EX_STOP)
        assert re.fullmatch(r"[0-9a-f]{64}", j["body_sha256"])
        assert j["body_chars"] > 0
        assert "This is your guide to producing" not in out
        assert "Your participants have no login" not in out


def test_state_dir_resolution_follows_the_sibling_convention(monkeypatch):
    """--state-dir > $ANTHOLOGY_STATE_DIR > $OPENCLAW_DATA_DIR/
    anthology-engine/state > ~/.anthology-engine/state -- the convention
    agreed with anthology_state / gate_engine / mc_board."""
    monkeypatch.setenv("ANTHOLOGY_STATE_DIR", "/tmp/from-env")
    assert wb._default_state_dir() == "/tmp/from-env"
    monkeypatch.delenv("ANTHOLOGY_STATE_DIR")
    monkeypatch.setenv("OPENCLAW_DATA_DIR", "/tmp/data")
    assert wb._default_state_dir() == "/tmp/data/anthology-engine/state"
    monkeypatch.delenv("OPENCLAW_DATA_DIR")
    monkeypatch.setenv("HOME", "/tmp/fakehome")
    assert wb._default_state_dir() == "/tmp/fakehome/.anthology-engine/state"


# ---------------------------------------------------------------------------
# CLI surface (house style: argparse + subcommands + flag aliases).
# ---------------------------------------------------------------------------
def test_cli_plan_exits_zero_and_build_without_execute_stops(tmp_path,
                                                             capsys):
    assert wb.main(["plan", "--state-dir", str(tmp_path)]) == wb.EX_OK
    assert wb.main(["build", "--state-dir", str(tmp_path)]) == wb.EX_STOP
    assert not (tmp_path / wb.STATE_DB_NAME).exists()
    out, _err = capsys.readouterr()
    assert out == ""


def test_cli_build_execute_against_missing_db_stops(tmp_path, capsys):
    rc = wb.main(["build", "--execute", "--state-dir", str(tmp_path)])
    assert rc == wb.EX_STOP
    assert not (tmp_path / wb.STATE_DB_NAME).exists()


def test_cli_dry_run_flag_is_the_offline_plan_surface(tmp_path, capsys):
    rc = wb.main(["build", "--dry-run", "--state-dir", str(tmp_path)])
    assert rc == wb.EX_OK
    assert "PLAN" in capsys.readouterr().err
    assert not (tmp_path / wb.STATE_DB_NAME).exists()


def test_cli_selftest_flag_aliases_and_selftest_exit_zero(capsys):
    """self-test is the module's own golden + attack battery; it exits 0
    today (the live guide still holds the pinned law), and both flag forms
    normalize to the subcommand."""
    assert wb.main(["self-test"]) == wb.EX_OK
    assert wb.main(["--self-test"]) == wb.EX_OK
    assert wb.main(["--selftest"]) == wb.EX_OK
    assert "welcome_builder self-test: OK" in capsys.readouterr().err


def test_cli_unknown_command_is_a_usage_error():
    with pytest.raises(SystemExit):
        wb.main(["frobnicate"])


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
