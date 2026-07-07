#!/usr/bin/env python3
"""nudge_send.py -- the ONLY client-facing message path in the Anthology Engine
(SPEC 3.4 row 8, SPEC 10.5, ENGINE-MANIFEST inventory n=8; unit W1.15).

THE THREE SANCTIONED TEMPLATES, AND NOTHING ELSE:
  * gate-open.md      -- a gate has opened; here is your next step
  * completion.md     -- a deliverable is finished and saved for you
  * stuck-renudge.md  -- the single automatic re-nudge at 7 days stuck (deduped)
Any other template name is refused (exit 2). The engine sends the client NOTHING
else, ever -- the silence doctrine (SPEC 10.5). Operator surfaces are verbose;
client surfaces are silent and sanctioned.

RECIPIENTS ARE ALWAYS RESOLVED FROM THE LEDGER, NEVER A LITERAL ADDRESS: for a
participant-addressed message the recipient is the participant row's email for the
given contact_id; for a producer-addressed message it is the producer record's
email (via the anthology's producer_id). There is NO --to flag and no literal
recipient anywhere in the engine (the legacy hardcoded-test-inbox class is
structurally impossible). The resolved address is NEVER printed (client PII); it is
handed only to the configured delivery process, and human output redacts it.

THE 7-DAY STUCK RE-NUDGE: `renudge-sweep` finds every participant parked at an open
`*_gate` cursor for at least the configured window (default 7 days) and sends
EXACTLY ONE stuck-renudge per stuck episode, deduped through a nudge-owned sidecar
so a daily tick can run forever without a second automatic nudge. All other repeats
are manual (the board re-send button, rate-limited) -- not this script's job.

CLIENT-CLEAN SERIALIZER (SPEC 11.5, mirrored from Gate B Tier 1 checks 5/6): every
rendered message must fill every slot (an unresolved slot is fail-closed refused),
carry zero em dash characters and zero code fences, leak no internal tool / model /
provider identifier, and say Convert and Flow if it names the platform at all. Zero
Anthropic identifiers ship in this file.

Exit codes (SPEC 3.4 row 8; house convention: 1 unexpected error):
  0  sent (or, with --dry-run, rendered and validated without delivering)
  2  template, recipient, or slot refusal (unknown template; recipient not in the
     ledger; an unresolved slot / hygiene violation)
  3  delivery path unavailable (no configured delivery command, or delivery failed)
  1  unexpected error
"""
import argparse
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
SCRIPTS = SKILL_DIR / "scripts"
GATE_ENGINE = SCRIPTS / "gate_engine.py"                      # sibling W1.15 file
TEMPLATES_DIR = SKILL_DIR / "config" / "nudge-templates"
DEFAULT_CONFIG = SKILL_DIR / "config" / "engine-config.json"
TEMPLATE_CONFIG = SKILL_DIR / "config" / "engine-config.template.json"

EX_OK, EX_ERR, EX_REFUSE, EX_UNAVAIL = 0, 1, 2, 3

KEY_DELIM = "::"
DEFAULT_RENUDGE_DAYS = 7

# The ONLY three templates the engine may send (SPEC 3.4 row 8 / 10.5).
SANCTIONED = {
    "gate-open":     "gate-open.md",
    "completion":    "completion.md",
    "stuck-renudge": "stuck-renudge.md",
}

# gate id -> (recipient target, default deliverable label). The label is a
# human, client-clean phrase; never a stage code or an internal name.
GATE_META = {
    "s1_producer":   ("producer",    "author profile"),
    "s2_producer":   ("producer",    "tone profile"),
    "s3_selection":  ("participant", "title options"),
    "s4_producer":   ("producer",    "blurb and outline"),
    "s4_participant": ("participant", "outline"),
    "s5_participant": ("participant", "chapter draft"),
    "s9_ready":      ("producer",    "anthology readiness"),
    "s9_producer":   ("producer",    "manuscript"),
}

# participant stage_cursor -> (gate id, target, default label) for the stuck sweep.
CURSOR_GATE = {
    "s1_gate":             ("s1_producer",   "producer",    "author profile"),
    "s2_gate":             ("s2_producer",   "producer",    "tone profile"),
    "s3_gate":             ("s3_selection",  "participant", "title options"),
    "s4_gate_producer":    ("s4_producer",   "producer",    "blurb and outline"),
    "s4_gate_participant": ("s4_participant", "participant", "outline"),
    "s5_gate":             ("s5_participant", "participant", "chapter draft"),
}

# Internal plumbing that must NEVER reach a client surface. Hyphenated / pathy /
# provider tokens chosen so a human first name can never false-trip (no bare common
# words). Case-insensitive substring match over the rendered body + subject.
INTERNAL_DENY = (
    "anthropic", "claude-", "ollama", "openrouter", "minimax", "gpt-image",
    "gpt-4", "weasyprint", "n8n", "gohighlevel", "go high level",
    "/api/tasks", "record-approval",
)
EM_DASH = "—"
CODE_FENCE = "```"
SLOT_RE = re.compile(r"\{\{\s*(\w+)\s*\}\}")
RESIDUAL_RE = re.compile(r"\{\{.*?\}\}", re.DOTALL)
COMMENT_RE = re.compile(r"^\s*<!--.*?-->\s*", re.DOTALL)


# --------------------------------------------------------------------------- #
# Shared utilities (the sibling conventions).
# --------------------------------------------------------------------------- #
def _env_first(names):
    for n in names:
        v = os.environ.get(n, "")
        if v and v.strip():
            return n, v.strip()
    return None, None


def resolve_state_dir(args):
    if getattr(args, "state_dir", None):
        return Path(args.state_dir).expanduser()
    env = os.environ.get("ANTHOLOGY_STATE_DIR", "").strip()
    if env:
        return Path(env).expanduser()
    data = os.environ.get("OPENCLAW_DATA_DIR", "").strip()
    if data:
        return Path(data).expanduser() / "anthology-engine" / "state"
    home = os.environ.get("HOME") or os.path.expanduser("~")
    return Path(home) / ".anthology-engine" / "state"


def _load_config(explicit=None):
    for p in (Path(explicit) if explicit else None, DEFAULT_CONFIG, TEMPLATE_CONFIG):
        if p and p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                continue
    return {}


def _renudge_days(cfg):
    days = ((cfg.get("nudge_policy") or {}).get("auto_renudge_days")) or DEFAULT_RENUDGE_DAYS
    try:
        return int(float(days))
    except (TypeError, ValueError):
        return DEFAULT_RENUDGE_DAYS


def _emit(obj, as_json):
    if as_json:
        sys.stdout.write(json.dumps(obj, ensure_ascii=False, sort_keys=True) + "\n")
    else:
        head = "OK" if obj.get("ok") else "REFUSED"
        sys.stdout.write("%s %s\n" % (head, obj.get("action", "")))
        for k in ("template", "subject_key", "gate", "recipient_redacted",
                  "delivered", "dry_run", "reason", "swept", "eligible",
                  "sent", "skipped_deduped", "note"):
            if k in obj and obj[k] is not None:
                sys.stdout.write("  %-18s %s\n" % (k, obj[k]))
    return obj


def _redact_email(addr):
    """A recipient is client PII; only a shape hint is ever surfaced."""
    if not addr or "@" not in addr:
        return "REDACTED"
    local, _, domain = addr.partition("@")
    dom = domain.split(".")
    dom_hint = (dom[-1] if dom else "")
    return "%s***@***.%s" % (local[:1] or "x", dom_hint or "***")


# --------------------------------------------------------------------------- #
# READ-ONLY ledger mirror access (SPEC 7.2 read path).
# --------------------------------------------------------------------------- #
class LedgerUnavailable(Exception):
    pass


def _mirror_ro(state_dir):
    db = Path(state_dir) / "anthology_state.db"
    if not db.exists():
        return None
    try:
        con = sqlite3.connect("file:%s?mode=ro" % db, uri=True, timeout=5)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA busy_timeout=5000")
        return con
    except sqlite3.Error as exc:
        raise LedgerUnavailable("mirror open failed: %s" % exc)


def _one(con, sql, params):
    if con is None:
        return None
    try:
        r = con.execute(sql, params).fetchone()
        return dict(r) if r is not None else None
    except sqlite3.Error as exc:
        raise LedgerUnavailable("mirror read failed: %s" % exc)


def _resolve_context(con, subject_key, target):
    """Resolve the ledger context for a message. Returns a dict with the resolved
    (never-printed) recipient email plus the client-clean display values, or None
    when the subject is unknown / the recipient cannot be resolved from the ledger."""
    participant = anthology = producer = None
    if KEY_DELIM in subject_key:
        participant = _one(con, "SELECT * FROM participants WHERE participant_key=?",
                           (subject_key,))
        if not participant:
            return None
        anthology = _one(con, "SELECT * FROM anthologies WHERE anthology_id=?",
                         (participant.get("anthology_id"),))
    else:
        anthology = _one(con, "SELECT * FROM anthologies WHERE anthology_id=?",
                         (subject_key,))
        if not anthology:
            return None
    if anthology and anthology.get("producer_id"):
        producer = _one(con, "SELECT * FROM producers WHERE producer_id=?",
                        (anthology.get("producer_id"),))

    prod_name = (producer or {}).get("display_name") or "the editorial team"
    anth_name = (anthology or {}).get("name") or "the anthology"

    if target == "producer":
        recipient = (producer or {}).get("producer_email")
        greeting = (producer or {}).get("display_name") or "there"
    else:
        recipient = (participant or {}).get("email")
        greeting = (participant or {}).get("first_name") or "there"
    return {
        "recipient": (recipient or "").strip(),
        "first_name": greeting,
        "anthology_name": anth_name,
        "producer_display_name": prod_name,
        "anthology_id": (anthology or {}).get("anthology_id"),
    }


# --------------------------------------------------------------------------- #
# Template load + client-clean render/serialize.
# --------------------------------------------------------------------------- #
def _template_path(name):
    return TEMPLATES_DIR / SANCTIONED[name]


def _render(name, slots):
    """Load a sanctioned template, fill slots, and run the client-clean serializer.
    Returns (subject, body). Raises ValueError(reason) on any refusal so the caller
    maps it to exit 2 (fail-closed)."""
    path = _template_path(name)
    if not path.exists():
        raise ValueError("template_file_missing:%s" % path.name)
    raw = path.read_text(encoding="utf-8")
    raw = COMMENT_RE.sub("", raw, count=1)          # strip the authoring comment

    def repl(m):
        key = m.group(1)
        val = slots.get(key)
        return str(val) if val not in (None, "") else m.group(0)  # keep -> caught below
    filled = SLOT_RE.sub(repl, raw)

    residual = RESIDUAL_RE.search(filled)
    if residual:
        raise ValueError("unresolved_slot:%s" % residual.group(0))
    if EM_DASH in filled:
        raise ValueError("em_dash_present")
    if CODE_FENCE in filled:
        raise ValueError("code_fence_present")
    low = filled.lower()
    for bad in INTERNAL_DENY:
        if bad in low:
            raise ValueError("internal_identifier_leaked:%s" % bad)

    subject, _, body = filled.partition("\n")
    subject = subject.strip()
    if subject.lower().startswith("subject:"):
        subject = subject.split(":", 1)[1].strip()
    return subject, body.strip()


# --------------------------------------------------------------------------- #
# Gate-link resolution. Participant links MUST be opaque (a minted token via
# gate_engine), never a raw internal key. Producer links point at the board card.
# --------------------------------------------------------------------------- #
def _mint_participant_link(subject_key, state_dir, config_path):
    """Ask gate_engine to mint an opaque token link for the subject's open gate.
    Returns the gate_link or None (mint unavailable / no open gate)."""
    if not GATE_ENGINE.exists():
        return None
    argv = [sys.executable or "python3", str(GATE_ENGINE), "mint",
            "--subject-key", subject_key, "--state-dir", str(state_dir), "--json"]
    if config_path:
        argv += ["--config", config_path]
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=25)
    except (subprocess.SubprocessError, OSError):
        return None
    if proc.returncode != 0:
        return None
    try:
        return (json.loads(proc.stdout or "{}") or {}).get("gate_link")
    except ValueError:
        return None


def _producer_link(cfg, subject_key):
    base = ((cfg.get("board") or {}).get("card_base_url")) or "/board"
    sep = "&" if "?" in base else "?"
    return "%s%scard=%s" % (base, sep, subject_key)


def _resolve_gate_link(cfg, target, subject_key, provided, state_dir, config_path):
    if provided:
        return provided
    if target == "participant":
        return _mint_participant_link(subject_key, state_dir, config_path)
    return _producer_link(cfg, subject_key)


# --------------------------------------------------------------------------- #
# Delivery. NO literal recipient in code; the resolved address goes ONLY to the
# configured delivery process (Skill 50 email-engine or the gateway notification
# path, wired per box). No configured path -> exit 3 (never a silent success).
# --------------------------------------------------------------------------- #
def _delivery_cmd(cfg):
    """Argv template (list) with {recipient} and {subject} placeholders; the body is
    delivered on stdin. From config nudge_delivery_cmd or env NUDGE_DELIVERY_CMD
    (space-split). Returns the list or None."""
    cmd = (cfg.get("nudge_delivery_cmd")
           or (cfg.get("nudge_policy") or {}).get("delivery_cmd"))
    if isinstance(cmd, list) and cmd:
        return cmd
    env = os.environ.get("NUDGE_DELIVERY_CMD", "").strip()
    if env:
        return env.split()
    return None


def _deliver(cfg, recipient, subject, body):
    """Deliver via the configured process. Returns (ok, detail). The recipient is
    never logged; only pass/fail is surfaced."""
    tmpl = _delivery_cmd(cfg)
    if not tmpl:
        return False, "no_delivery_path"
    try:
        argv = [str(tok).format(recipient=recipient, subject=subject) for tok in tmpl]
    except (KeyError, IndexError, ValueError):
        return False, "bad_delivery_template"
    try:
        proc = subprocess.run(argv, input=body, text=True,
                              capture_output=True, timeout=30)
    except (subprocess.SubprocessError, OSError) as exc:
        return False, "delivery_error:%s" % type(exc).__name__
    if proc.returncode != 0:
        return False, "delivery_rc:%d" % proc.returncode
    return True, "delivered"


# --------------------------------------------------------------------------- #
# Dedup sidecar for the automatic re-nudge (nudge-OWNED; NOT the domain ledger).
# --------------------------------------------------------------------------- #
class NudgeSentStore:
    def __init__(self, state_dir):
        self.available = False
        self.con = None
        try:
            Path(state_dir).mkdir(parents=True, exist_ok=True)
            self.con = sqlite3.connect(str(Path(state_dir) / "nudge_sent.db"), timeout=15)
            self.con.execute("PRAGMA journal_mode=WAL")
            self.con.execute("PRAGMA busy_timeout=15000")
            self.con.execute(
                "CREATE TABLE IF NOT EXISTS nudge_sent ("
                "  dedup_key TEXT PRIMARY KEY, template TEXT, participant_key TEXT,"
                "  gate TEXT, episode TEXT, sent_utc TEXT, status TEXT)")
            self.con.commit()
            self.available = True
        except sqlite3.Error:
            self.available = False

    @staticmethod
    def key(template, participant_key, gate, episode):
        return hashlib.sha256(
            ("%s|%s|%s|%s" % (template, participant_key, gate, episode)
             ).encode("utf-8")).hexdigest()

    def claim(self, dkey, template, participant_key, gate, episode):
        """Atomic 'this episode has not been auto-renudged yet' claim. True on a
        fresh claim, False if already sent (deduped). Fail-open store -> True."""
        if not self.available:
            return True
        try:
            cur = self.con.execute(
                "INSERT OR IGNORE INTO nudge_sent"
                "(dedup_key,template,participant_key,gate,episode,sent_utc,status)"
                " VALUES(?,?,?,?,?,?,?)",
                (dkey, template, participant_key, gate, episode,
                 datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
                 "claimed"))
            self.con.commit()
            return cur.rowcount == 1
        except sqlite3.Error:
            return True

    def finalize(self, dkey, status):
        if not self.available:
            return
        try:
            self.con.execute("UPDATE nudge_sent SET status=? WHERE dedup_key=?",
                             (status, dkey))
            self.con.commit()
        except sqlite3.Error:
            pass

    def release(self, dkey):
        if not self.available:
            return
        try:
            self.con.execute("DELETE FROM nudge_sent WHERE dedup_key=?", (dkey,))
            self.con.commit()
        except sqlite3.Error:
            pass

    def close(self):
        try:
            if self.con is not None:
                self.con.close()
        except sqlite3.Error:
            pass


# --------------------------------------------------------------------------- #
# Slot assembly shared by send + sweep.
# --------------------------------------------------------------------------- #
def _build_slots(ctx, deliverable_label, gate_link, deliverable_link):
    return {
        "first_name": ctx["first_name"],
        "anthology_name": ctx["anthology_name"],
        "producer_display_name": ctx["producer_display_name"],
        "deliverable_label": deliverable_label,
        "gate_link": gate_link,
        "deliverable_link": deliverable_link,
    }


def _target_and_label(template, gate, subject_key, cfg_label):
    """Decide the recipient target and default deliverable label for a send."""
    if template == "completion":
        target = "participant"
        label = cfg_label or "deliverable"
    elif gate and gate in GATE_META:
        target, default_label = GATE_META[gate]
        label = cfg_label or default_label
    elif KEY_DELIM in subject_key:
        target, label = "participant", (cfg_label or "next step")
    else:
        target, label = "producer", (cfg_label or "next step")
    return target, label


# --------------------------------------------------------------------------- #
# COMMANDS
# --------------------------------------------------------------------------- #
def cmd_send(args):
    template = args.template
    if template not in SANCTIONED:
        return _emit({"ok": False, "action": "send", "template": template,
                      "reason": "unsanctioned_template",
                      "allowed": sorted(SANCTIONED)}, args.json), EX_REFUSE

    cfg = _load_config(args.config)
    state_dir = resolve_state_dir(args)
    target, label = _target_and_label(template, args.gate, args.subject_key,
                                       args.deliverable_label)

    con = None
    try:
        con = _mirror_ro(state_dir)
        ctx = _resolve_context(con, args.subject_key, target) if con else None
    except LedgerUnavailable as exc:
        return _emit({"ok": False, "action": "send", "template": template,
                      "reason": "ledger_unavailable", "detail": str(exc)},
                     args.json), EX_UNAVAIL
    finally:
        try:
            if con:
                con.close()
        except sqlite3.Error:
            pass
    if ctx is None:
        return _emit({"ok": False, "action": "send", "template": template,
                      "subject_key": args.subject_key,
                      "reason": "subject_not_in_ledger"}, args.json), EX_REFUSE
    if not ctx["recipient"]:
        return _emit({"ok": False, "action": "send", "template": template,
                      "subject_key": args.subject_key, "target": target,
                      "reason": "recipient_not_resolvable"}, args.json), EX_REFUSE

    gate_link = None
    if template in ("gate-open", "stuck-renudge"):
        gate_link = _resolve_gate_link(cfg, target, args.subject_key, args.gate_link,
                                       state_dir, args.config)

    slots = _build_slots(ctx, label, gate_link, args.deliverable_link)
    try:
        subject, body = _render(template, slots)
    except ValueError as exc:
        return _emit({"ok": False, "action": "send", "template": template,
                      "subject_key": args.subject_key,
                      "reason": "serializer_refusal", "detail": str(exc)},
                     args.json), EX_REFUSE

    if args.dry_run:
        return _emit({"ok": True, "action": "send", "template": template,
                      "subject_key": args.subject_key, "gate": args.gate,
                      "recipient_redacted": _redact_email(ctx["recipient"]),
                      "delivered": False, "dry_run": True,
                      "subject": subject, "body": body}, args.json), EX_OK

    ok, detail = _deliver(cfg, ctx["recipient"], subject, body)
    if not ok:
        return _emit({"ok": False, "action": "send", "template": template,
                      "subject_key": args.subject_key,
                      "recipient_redacted": _redact_email(ctx["recipient"]),
                      "delivered": False, "reason": detail}, args.json), EX_UNAVAIL
    return _emit({"ok": True, "action": "send", "template": template,
                  "subject_key": args.subject_key, "gate": args.gate,
                  "recipient_redacted": _redact_email(ctx["recipient"]),
                  "delivered": True}, args.json), EX_OK


def _parse_iso(ts):
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


def cmd_renudge_sweep(args):
    """The ONE automatic re-nudge at the stuck window (default 7 days), deduped.
    Runs from the daily tick. Sends EXACTLY ONE stuck-renudge per stuck episode."""
    cfg = _load_config(args.config)
    state_dir = resolve_state_dir(args)
    days = args.days if args.days is not None else _renudge_days(cfg)
    threshold = days * 86400
    now = _parse_iso(args.now) or datetime.now(timezone.utc)

    try:
        con = _mirror_ro(state_dir)
    except LedgerUnavailable as exc:
        return _emit({"ok": False, "action": "renudge-sweep",
                      "reason": "ledger_unavailable", "detail": str(exc)},
                     args.json), EX_UNAVAIL
    if con is None:
        return _emit({"ok": True, "action": "renudge-sweep", "swept": 0,
                      "eligible": 0, "sent": 0, "skipped_deduped": 0,
                      "note": "no ledger yet (unprovisioned box)"}, args.json), EX_OK

    eligible = []
    swept = 0
    try:
        rows = con.execute(
            "SELECT participant_key, stage_cursor, stage_timestamps, anthology_id "
            "FROM participants WHERE stage_cursor IN (%s)"
            % ",".join("?" * len(CURSOR_GATE)),
            tuple(CURSOR_GATE)).fetchall()
    except sqlite3.Error as exc:
        con.close()
        return _emit({"ok": False, "action": "renudge-sweep",
                      "reason": "ledger_unavailable", "detail": str(exc)},
                     args.json), EX_UNAVAIL
    for r in rows:
        swept += 1
        cursor = r["stage_cursor"]
        gate_id, target, default_label = CURSOR_GATE[cursor]
        try:
            ts_map = json.loads(r["stage_timestamps"] or "{}")
        except (ValueError, TypeError):
            ts_map = {}
        entered = _parse_iso(ts_map.get(cursor))
        if entered is None:
            continue
        stuck = (now - entered).total_seconds()
        if stuck >= threshold:
            eligible.append({"participant_key": r["participant_key"], "gate": gate_id,
                             "target": target, "label": default_label,
                             "episode": ts_map.get(cursor),
                             "stuck_days": round(stuck / 86400, 1)})
    con.close()

    if args.dry_run:
        return _emit({"ok": True, "action": "renudge-sweep", "dry_run": True,
                      "days": days, "swept": swept, "eligible": len(eligible),
                      "candidates": eligible}, args.json), EX_OK

    store = NudgeSentStore(state_dir)
    sent = skipped = errors = 0
    try:
        for e in eligible:
            dkey = NudgeSentStore.key("stuck-renudge", e["participant_key"],
                                      e["gate"], e["episode"])
            if not store.claim(dkey, "stuck-renudge", e["participant_key"],
                               e["gate"], e["episode"]):
                skipped += 1                                  # already auto-renudged
                continue
            rc = _send_one(args, cfg, state_dir, "stuck-renudge",
                           e["participant_key"], e["gate"], e["target"], e["label"])
            if rc == EX_OK:
                store.finalize(dkey, "sent")
                sent += 1
            else:
                store.release(dkey)                          # let the next tick retry
                errors += 1
    finally:
        store.close()
    return _emit({"ok": True, "action": "renudge-sweep", "days": days,
                  "swept": swept, "eligible": len(eligible), "sent": sent,
                  "skipped_deduped": skipped, "errors": errors}, args.json), EX_OK


def _send_one(args, cfg, state_dir, template, subject_key, gate, target, label):
    """Resolve + render + deliver a single message (used by the sweep). Returns an
    exit code; never raises. Recipient never printed."""
    try:
        con = _mirror_ro(state_dir)
        ctx = _resolve_context(con, subject_key, target) if con else None
        if con:
            con.close()
    except LedgerUnavailable:
        return EX_UNAVAIL
    if ctx is None or not ctx["recipient"]:
        return EX_REFUSE
    gate_link = _resolve_gate_link(cfg, target, subject_key, None, state_dir, args.config)
    slots = _build_slots(ctx, label, gate_link, None)
    try:
        subject, body = _render(template, slots)
    except ValueError:
        return EX_REFUSE
    if args.dry_run:
        return EX_OK
    ok, _detail = _deliver(cfg, ctx["recipient"], subject, body)
    return EX_OK if ok else EX_UNAVAIL


# --------------------------------------------------------------------------- #
# SELF-TEST (pure: templates + serializer + dedup keying + tables; no ledger).
# --------------------------------------------------------------------------- #
def self_test():
    assert (EX_OK, EX_ERR, EX_REFUSE, EX_UNAVAIL) == (0, 1, 2, 3)

    # exactly the three sanctioned templates, and each file exists on disk.
    assert set(SANCTIONED) == {"gate-open", "completion", "stuck-renudge"}
    for name in SANCTIONED:
        assert _template_path(name).exists(), _template_path(name)

    ctx = {"first_name": "Sam", "anthology_name": "Voices of Dawn",
           "producer_display_name": "The Editorial Desk"}

    # gate-open renders cleanly with all slots filled.
    slots = _build_slots(ctx, "chapter draft", "/p/gate?t=OPAQUE", None)
    subject, body = _render("gate-open", slots)
    assert subject and "Voices of Dawn" in subject
    assert "Sam" in body and "chapter draft" in body and "/p/gate?t=OPAQUE" in body
    assert EM_DASH not in body and CODE_FENCE not in body
    assert "{{" not in body and "{{" not in subject

    # completion renders (needs deliverable_link).
    csub, cbody = _render("completion",
                          _build_slots(ctx, "chapter draft", None, "/d/xyz"))
    assert "/d/xyz" in cbody and csub

    # FAIL-CLOSED: an unresolved slot is refused (completion without its link).
    try:
        _render("completion", _build_slots(ctx, "chapter draft", None, None))
        raise AssertionError("expected unresolved_slot refusal")
    except ValueError as e:
        assert str(e).startswith("unresolved_slot"), e

    # HYGIENE: an em dash in a slot value is refused.
    try:
        _render("gate-open", _build_slots(
            {"first_name": "A" + EM_DASH + "B", "anthology_name": "X",
             "producer_display_name": "Y"}, "chapter", "/p?t=1", None))
        raise AssertionError("expected em_dash refusal")
    except ValueError as e:
        assert str(e) == "em_dash_present", e

    # HYGIENE: a leaked internal identifier is refused.
    try:
        _render("gate-open", _build_slots(
            {"first_name": "openrouter-relay", "anthology_name": "X",
             "producer_display_name": "Y"}, "chapter", "/p?t=1", None))
        raise AssertionError("expected internal-identifier refusal")
    except ValueError as e:
        assert str(e).startswith("internal_identifier_leaked"), e

    # recipient redaction never reveals the address.
    red = _redact_email("jane.doe@example.com")
    assert "jane.doe" not in red and red.endswith("com")

    # dedup keying is stable + episode-scoped (a new episode == a new single nudge).
    k1 = NudgeSentStore.key("stuck-renudge", "c::a", "s5_participant", "2026-07-01T00:00:00+00:00")
    k2 = NudgeSentStore.key("stuck-renudge", "c::a", "s5_participant", "2026-07-01T00:00:00+00:00")
    k3 = NudgeSentStore.key("stuck-renudge", "c::a", "s5_participant", "2026-07-20T00:00:00+00:00")
    assert k1 == k2 and k1 != k3

    # target routing: producer gates -> producer, participant gates -> participant.
    assert _target_and_label("gate-open", "s2_producer", "c::a", None)[0] == "producer"
    assert _target_and_label("gate-open", "s5_participant", "c::a", None)[0] == "participant"
    assert _target_and_label("completion", None, "c::a", None)[0] == "participant"

    # ISO parsing tolerates the ledger's offset timestamps.
    assert _parse_iso("2026-07-07T05:11:00+00:00") is not None
    assert _parse_iso("garbage") is None

    print("nudge_send self-test: OK "
          "(3 sanctioned templates, fail-closed serializer, hygiene refusals, "
          "PII redaction, episode-scoped dedup, target routing)")
    return EX_OK


def plan():
    print("nudge_send.py -- the three sanctioned client templates only")
    print("templates    : %s" % ", ".join(sorted(SANCTIONED)))
    print("recipients   : ALWAYS resolved from the ledger (participant email or")
    print("               producer email); NO literal recipient exists; never printed")
    print("re-nudge      : ONE deduped automatic stuck-renudge at %d days (renudge-sweep)"
          % DEFAULT_RENUDGE_DAYS)
    print("serializer    : fill every slot (fail-closed), zero em dash, zero code")
    print("               fence, no internal identifier; Convert and Flow only")
    print("delivery      : configured process (Skill 50 / gateway); none -> exit 3")
    print("exit codes    : 0 sent ; 2 template/recipient/slot refusal ; 3 unavailable ; 1 error")
    return EX_OK


def _build_parser():
    ap = argparse.ArgumentParser(
        prog="nudge_send.py",
        description="Send one of the three sanctioned Anthology client nudges, or run "
                    "the deduped 7-day stuck re-nudge sweep.")
    ap.add_argument("--self-test", action="store_true",
                    help="run the pure self-test (no ledger / network) and exit")
    ap.add_argument("--plan", action="store_true", help="print the contract and exit")
    sub = ap.add_subparsers(dest="cmd")

    def common(sp):
        sp.add_argument("--state-dir", dest="state_dir")
        sp.add_argument("--config", help="path to the resolved engine-config.json")
        sp.add_argument("--dry-run", action="store_true",
                        help="render + validate without delivering")
        sp.add_argument("--json", action="store_true")

    sp = sub.add_parser("send", help="send ONE sanctioned nudge")
    sp.add_argument("--template", required=True, choices=sorted(SANCTIONED))
    sp.add_argument("--subject-key", dest="subject_key", required=True,
                    help="participant_key (contact_id::anthology_id) or anthology_id")
    sp.add_argument("--gate", help="the open gate id (routes recipient + label)")
    sp.add_argument("--gate-link", dest="gate_link",
                    help="opaque deep link; if omitted, minted via gate_engine (participant)")
    sp.add_argument("--deliverable-label", dest="deliverable_label",
                    help="client-clean label override (e.g. 'chapter draft')")
    sp.add_argument("--deliverable-link", dest="deliverable_link",
                    help="the finished deliverable link (completion template)")
    common(sp)

    sp = sub.add_parser("renudge-sweep",
                        help="ONE deduped automatic re-nudge for gates stuck >= N days")
    sp.add_argument("--days", type=int, default=None,
                    help="stuck window in days (default: config or 7)")
    sp.add_argument("--now", help="ISO-8601 'now' override (testing)")
    common(sp)
    return ap


HANDLERS = {"send": cmd_send, "renudge-sweep": cmd_renudge_sweep}


def main(argv=None):
    ap = _build_parser()
    args = ap.parse_args(argv)
    try:
        if args.self_test:
            return self_test()
        if args.plan:
            return plan()
        if not args.cmd:
            ap.print_help()
            return EX_ERR
        _out, rc = HANDLERS[args.cmd](args)
        return rc
    except BrokenPipeError:
        return EX_OK
    except Exception as exc:  # noqa: BLE001 -- last-resort guard; house exit 1
        sys.stderr.write("[nudge_send] unexpected error: %s\n" % exc)
        return EX_ERR


if __name__ == "__main__":
    sys.exit(main())
