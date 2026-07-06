#!/usr/bin/env python3
# =============================================================================
# 58-PODCAST-PRODUCTION-ENGINE :: GUARD-CRON-INVENTORY (furnace Guardrail 6)
# -----------------------------------------------------------------------------
# DETERMINISTIC, NO-AI, FAIL-CLOSED. The one-cron inventory audit. Rides the
# repo QC merge gate (same G-gate family), runs at provisioning, and doubles as
# the fleet churn sweep. The furnace law it enforces: this skill ships with
# EXACTLY ONE recurring job per client (the daily smoke test), no heartbeat
# entry ever, no queue poller, no per-job watcher, once-daily cadence, silent
# delivery (never announce into the client chat), and a departed client leaves
# ZERO recurring jobs behind (an orphaned cron on a dead client is the purest
# furnace there is).
#
# TWO INPUT SURFACES (either or both):
#
#   INVENTORY MODE (authoritative; provisioning + fleet sweep). A cron inventory
#     as JSON (an array of entries, or an object with a crons/jobs/entries
#     array) via --inventory FILE or stdin (-), or captured live with --live
#     ($OPENCLAW_BIN cron list). Asserts, over the podcast-namespace entries:
#       * per client exactly one recurring job (a second cron FAILS),
#       * cadence is not sub-daily (hourly / */n / multi-hour FAILS),
#       * no heartbeat entry references the skill,
#       * no queue poller / per-job watcher,
#       * delivery never announces (when the listing exposes the mode),
#       * --sweep: any podcast cron whose client is not in --roster is an
#         ORPHAN and FAILS (the churn proof).
#
#   STATIC MODE (repo QC gate over the shipped skill). Scans shipped .sh/.py
#     registration surfaces and FAILS on: any heartbeat registration, any queue
#     poller registration, any sub-daily `cron add`, any `cron add` missing
#     --no-deliver (the known CLI drift defaults delivery to announce and spams
#     the chat), or MORE THAN ONE distinct scheduled podcast cron name. Zero
#     registrations is not a static failure (the registrar is a sibling slice);
#     the per-client exactly-one count is proven authoritatively in INVENTORY
#     mode at provisioning. Pass --min-one to require at least one.
#
# No secret is ever printed: a finding names the cron by name/class only.
#
# EXIT: 0 PASS / 2 AUTOFAIL / 3 USAGE-IO / 6 DEPS-MISSING (live mode, no CLI).
# USAGE:
#   python3 guard-cron-inventory.py [--scan DIR] [--skill-root DIR] [--min-one]
#   python3 guard-cron-inventory.py --inventory crons.json [--client SLUG]
#                 [--sweep --roster roster.txt] [--heartbeat-config hb.json]
#   python3 guard-cron-inventory.py --live [--sweep --roster roster.txt]
#   cat crons.json | python3 guard-cron-inventory.py --inventory -
#   python3 guard-cron-inventory.py --self-test
# Test seam: $OPENCLAW_BIN overrides the CLI binary for --live.
# =============================================================================
"""Fail-closed one-cron / no-heartbeat / no-poller / clean-churn guard for the Podcast Production Engine."""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

EXIT_PASS = 0
EXIT_AUTOFAIL = 2
EXIT_USAGE = 3
EXIT_DEPS = 6

AF_SECOND_CRON = "AF-PPE-SECOND-CRON"
AF_SUBDAILY = "AF-PPE-SUBDAILY"
AF_HEARTBEAT = "AF-PPE-HEARTBEAT"
AF_POLLER = "AF-PPE-POLLER"
AF_ANNOUNCE = "AF-PPE-ANNOUNCE"
AF_ORPHAN = "AF-PPE-ORPHAN-CRON"
AF_MISSING = "AF-PPE-MISSING-CRON"
AF_IO = "AF-PPE-IO"

_SELF = Path(__file__).resolve()

# A cron belongs to this skill's namespace when its name/command carries the
# podcast token. Configurable via --namespace-regex.
_DEFAULT_NAMESPACE = r"(?i)podcast"
_HEARTBEAT_RE = re.compile(r"(?i)heart[\s_-]?beat")
_POLLER_RE = re.compile(
    r"(?i)(poller|polling|\bpoll\b|drain(?:er|[-_ ]?loop)?|watcher|per[-_ ]?job|queue[-_ ]?(?:poll|watch))")
_ANNOUNCE_VALUES = {"announce", "channel", "chat", "deliver", "channel-deliver"}

_TEXT_EXT_STATIC = {".sh", ".bash", ".zsh", ".py"}
_SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv", ".next", "dist", "build"}


# --------------------------------------------------------------------------- #
# Cadence: bound on fires-per-day for a schedule string
# --------------------------------------------------------------------------- #
def _field_count(field, lo, hi):
    """Upper bound on the number of distinct values a cron field fires on."""
    total = 0
    for part in str(field).split(","):
        part = part.strip()
        if not part:
            continue
        step = 1
        base = part
        if "/" in part:
            base, s = part.split("/", 1)
            try:
                step = max(1, int(s))
            except ValueError:
                return hi - lo + 1
        if base == "*" or base == "":
            a, b = lo, hi
        elif "-" in base:
            x, y = base.split("-", 1)
            try:
                a, b = int(x), int(y)
            except ValueError:
                return hi - lo + 1
        else:
            try:
                a = b = int(base)
            except ValueError:
                return hi - lo + 1
        if b < a:
            a, b = b, a
        cnt, v = 0, a
        while v <= b:
            cnt += 1
            v += step
        total += cnt
    return total if total > 0 else 1


_INTERVAL_UNITS = {"s": 1, "sec": 1, "second": 1, "seconds": 1,
                   "m": 60, "min": 60, "minute": 60, "minutes": 60,
                   "h": 3600, "hr": 3600, "hour": 3600, "hours": 3600,
                   "d": 86400, "day": 86400, "days": 86400,
                   "w": 604800, "week": 604800, "weeks": 604800}

_AT_SHORTCUTS = {
    "@yearly": 1.0 / 365, "@annually": 1.0 / 365, "@monthly": 1.0 / 30,
    "@weekly": 1.0 / 7, "@daily": 1.0, "@midnight": 1.0, "@hourly": 24.0,
}


def fires_per_day_bound(schedule):
    """Return an upper bound on fires per day, or None if unparseable.

    <= 1.0 means at most once daily (not a furnace). > 1.0 means sub-daily."""
    if schedule is None:
        return None
    s = str(schedule).strip().lower()
    if not s:
        return None

    if s in _AT_SHORTCUTS:
        return _AT_SHORTCUTS[s]
    if s == "@reboot":
        return None  # not a recurring daily schedule; caller fails closed

    # interval forms: "@every 15m", "every 15 minutes", "15m", "1h", "1d"
    m = re.match(r"^(?:@every\s+|every\s+)?(\d+)\s*([a-z]+)$", s)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        sec = _INTERVAL_UNITS.get(unit)
        if sec:
            secs = n * sec
            return None if secs <= 0 else 86400.0 / secs
        return None

    # cron expression: 5 fields (min hour dom mon dow) or 6 (sec + those)
    fields = s.split()
    if len(fields) in (5, 6):
        if len(fields) == 6:
            sec_c = _field_count(fields[0], 0, 59)
            minute, hour = fields[1], fields[2]
        else:
            sec_c = 1
            minute, hour = fields[0], fields[1]
        min_c = _field_count(minute, 0, 59)
        hr_c = _field_count(hour, 0, 23)
        return float(sec_c * min_c * hr_c)

    return None


# --------------------------------------------------------------------------- #
# Inventory normalization and entry accessors
# --------------------------------------------------------------------------- #
def normalize_inventory(raw):
    """Accept a list, or an object wrapping crons/jobs/entries; return a list of dicts."""
    if isinstance(raw, list):
        items = raw
    elif isinstance(raw, dict):
        items = None
        for key in ("crons", "jobs", "entries", "items", "schedules"):
            if isinstance(raw.get(key), list):
                items = raw[key]
                break
        if items is None:
            items = [raw]
    else:
        items = []
    out = []
    for it in items:
        if isinstance(it, dict):
            out.append(it)
    return out


def _text_of(entry):
    parts = []
    for k in ("name", "id", "command", "cmd", "prompt", "session", "sessionTarget", "tag"):
        v = entry.get(k)
        if isinstance(v, str):
            parts.append(v)
    sk = entry.get("skills")
    if isinstance(sk, list):
        parts.extend(str(x) for x in sk)
    return " ".join(parts)


def entry_name(entry):
    for k in ("name", "id", "cmd", "command"):
        v = entry.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return "<unnamed>"


def in_namespace(entry, ns_re):
    return bool(ns_re.search(_text_of(entry)))


def entry_client(entry, client_re):
    for k in ("client", "slug", "tenant", "tag"):
        v = entry.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip().lower()
    name = entry_name(entry)
    m = client_re.search(name) if client_re else None
    if m:
        return (m.group(1) if m.groups() else m.group(0)).lower()
    if "-" in name:
        return name.rsplit("-", 1)[-1].lower()
    return name.lower()


def entry_schedule(entry):
    for k in ("schedule", "cron", "cronExpression", "expr", "interval", "when"):
        v = entry.get(k)
        if isinstance(v, (str, int)) and str(v).strip():
            return str(v).strip()
    return None


def entry_is_heartbeat(entry):
    kind = str(entry.get("kind") or entry.get("type") or "").lower()
    if kind in ("heartbeat", "hb"):
        return True
    if entry.get("heartbeat") is True:
        return True
    return bool(_HEARTBEAT_RE.search(_text_of(entry)))


def entry_is_poller(entry):
    kind = str(entry.get("kind") or entry.get("type") or "").lower()
    if kind in ("poller", "watcher"):
        return True
    return bool(_POLLER_RE.search(_text_of(entry)))


def entry_announces(entry):
    """Return True only when the entry EXPOSES an announce/channel delivery mode.
    Absent delivery info means 'cannot assert' (not a failure) - the static gate
    proves --no-deliver at registration time."""
    for k in ("delivery", "deliveryMode", "delivery_mode", "mode"):
        v = entry.get(k)
        if isinstance(v, str) and v.strip().lower() in _ANNOUNCE_VALUES:
            return True
    if entry.get("announce") is True:
        return True
    if entry.get("deliver") is True and not entry.get("silent") and "no-deliver" not in _text_of(entry).lower():
        return True
    return False


# --------------------------------------------------------------------------- #
# INVENTORY MODE assertions
# --------------------------------------------------------------------------- #
def audit_inventory(entries, ns_re, client_re, sweep=False, roster=None,
                    only_client=None, heartbeat_skills=None):
    findings = []
    roster_set = {r.strip().lower() for r in (roster or []) if r.strip()}

    # Heartbeat: any heartbeat entry that references the skill is forbidden.
    for e in entries:
        if entry_is_heartbeat(e) and in_namespace(e, ns_re):
            findings.append((AF_HEARTBEAT, "heartbeat-entry-references-podcast:%s" % entry_name(e)))
    if heartbeat_skills:
        for hb in heartbeat_skills:
            skills = hb.get("skills") if isinstance(hb, dict) else None
            agents = hb.get("agents") if isinstance(hb, dict) else None
            blob = " ".join(str(x) for x in ((skills or []) + (agents or [])))
            if ns_re.search(blob) or ns_re.search(json.dumps(hb)):
                nm = hb.get("name", "<heartbeat>") if isinstance(hb, dict) else "<heartbeat>"
                findings.append((AF_HEARTBEAT, "heartbeat-config-lists-podcast:%s" % nm))

    pod = [e for e in entries if in_namespace(e, ns_re) and not entry_is_heartbeat(e)]

    # Poller / per-job watcher.
    for e in pod:
        if entry_is_poller(e):
            findings.append((AF_POLLER, "queue-poller-or-watcher:%s" % entry_name(e)))

    # Cadence + announce, per podcast cron.
    for e in pod:
        sch = entry_schedule(e)
        bound = fires_per_day_bound(sch)
        if bound is None:
            findings.append((AF_SUBDAILY, "schedule-unparseable-cannot-prove-once-daily:%s" % entry_name(e)))
        elif bound > 1.0 + 1e-9:
            findings.append((AF_SUBDAILY, "sub-daily-schedule:%s(~%.0f/day)" % (entry_name(e), bound)))
        if entry_announces(e):
            findings.append((AF_ANNOUNCE, "delivery-announces-into-chat:%s" % entry_name(e)))

    # Per-client exactly one (recurring, non-poller) podcast cron.
    by_client = {}
    for e in pod:
        if entry_is_poller(e):
            continue
        by_client.setdefault(entry_client(e, client_re), []).append(entry_name(e))

    if only_client:
        c = only_client.strip().lower()
        n = len(by_client.get(c, []))
        if n == 0:
            findings.append((AF_MISSING, "client-has-no-recurring-podcast-cron:%s" % c))
        elif n > 1:
            findings.append((AF_SECOND_CRON, "client-has-%d-podcast-crons:%s%s" % (n, c, by_client[c])))
    else:
        for c, names in by_client.items():
            if len(names) > 1:
                findings.append((AF_SECOND_CRON, "client-has-%d-podcast-crons:%s%s" % (len(names), c, names)))

    # Churn sweep: any podcast cron for a client outside the active roster.
    if sweep:
        if roster is None:
            findings.append((AF_IO, "sweep-requested-without-roster"))
        else:
            for c, names in by_client.items():
                if c not in roster_set:
                    findings.append((AF_ORPHAN, "orphan-cron-client-not-in-roster:%s%s" % (c, names)))

    return findings


# --------------------------------------------------------------------------- #
# STATIC MODE: scan shipped registration surfaces
# --------------------------------------------------------------------------- #
_CRON_ADD_RE = re.compile(r"\bcron\s+add\b", re.I)
# Capture the schedule value, preserving spaces inside a quoted cron expression.
_SCHED_FLAG_RE = re.compile(r"""--(?:schedule|cron|when)(?:[=\s]+)(?:"([^"]+)"|'([^']+)'|([^\s"']+))""")
_NAME_FLAG_RE = re.compile(r"""--(?:name|id)[=\s]+["']?([A-Za-z0-9_.\-]+)""")
_NODELIVER_RE = re.compile(r"--no-deliver\b")
_HEARTBEAT_REG_RE = re.compile(r"(?i)heart[\s_-]?beat[\s_-]*(?:add|register|enable|append|set)|--heartbeat\b|cron\s+add[^\n]*heart[\s_-]?beat")


def _static_scan_file(path):
    findings = []
    reg_names = []
    try:
        lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        return [(AF_IO, "unreadable:%s" % type(exc).__name__)], reg_names
    for lineno, raw in enumerate(lines, 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if _HEARTBEAT_REG_RE.search(line):
            findings.append((AF_HEARTBEAT, "heartbeat-registration:%s:%d" % (path.name, lineno)))
        if not _CRON_ADD_RE.search(line):
            continue
        # This is a cron registration line.
        low = line.lower()
        if _POLLER_RE.search(low):
            findings.append((AF_POLLER, "poller-cron-registration:%s:%d" % (path.name, lineno)))
        sm = _SCHED_FLAG_RE.search(line)
        if sm:
            sched_val = sm.group(1) or sm.group(2) or sm.group(3)
            bound = fires_per_day_bound(sched_val)
            if bound is not None and bound > 1.0 + 1e-9:
                findings.append((AF_SUBDAILY, "sub-daily-cron-add:%s:%d(~%.0f/day)" % (path.name, lineno, bound)))
        if not _NODELIVER_RE.search(line):
            findings.append((AF_ANNOUNCE, "cron-add-missing---no-deliver:%s:%d" % (path.name, lineno)))
        nm = _NAME_FLAG_RE.search(line)
        reg_names.append(nm.group(1) if nm else "cron@%s:%d" % (path.name, lineno))
    return findings, reg_names


def _iter_static_files(target):
    p = Path(target)
    if p.is_file():
        if p.suffix.lower() in _TEXT_EXT_STATIC:
            yield p
        return
    for root, dirs, files in os.walk(p):
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
        for fn in files:
            fp = Path(root) / fn
            if fp.resolve() == _SELF:
                continue
            if fp.suffix.lower() in _TEXT_EXT_STATIC:
                yield fp


def audit_static(targets, min_one=False):
    findings = []
    reg_names = []
    for t in targets:
        if not Path(t).exists():
            findings.append((AF_IO, "missing-target:%s" % t))
            continue
        for fp in _iter_static_files(t):
            f, names = _static_scan_file(fp)
            findings.extend(f)
            reg_names.extend(names)
    distinct = sorted(set(reg_names))
    if len(distinct) > 1:
        findings.append((AF_SECOND_CRON, "more-than-one-distinct-scheduled-cron-name:%s" % distinct))
    if min_one and len(distinct) == 0:
        findings.append((AF_MISSING, "no-cron-registration-found-in-shipped-skill"))
    return findings, distinct


# --------------------------------------------------------------------------- #
# Live capture
# --------------------------------------------------------------------------- #
def _live_inventory():
    binname = os.environ.get("OPENCLAW_BIN", "openclaw")
    for args in ([binname, "cron", "list", "--json"], [binname, "cron", "list"]):
        try:
            out = subprocess.run(args, capture_output=True, text=True, timeout=30)
        except (OSError, subprocess.SubprocessError):
            continue
        text = (out.stdout or "").strip()
        if not text:
            continue
        try:
            return normalize_inventory(json.loads(text))
        except ValueError:
            entries = _parse_cron_text(text)
            if entries:
                return entries
    return None


def _parse_cron_text(text):
    """Best-effort parse of `openclaw cron list` plain text: one entry per line,
    extract a name token and a cron expression if present."""
    cron_re = re.compile(r"((?:[\*\d,\-/]+\s+){4}[\*\d,\-/]+|@\w+)")
    entries = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.lower().startswith(("name", "id", "===", "---")):
            continue
        name = line.split()[0]
        cm = cron_re.search(line)
        entries.append({"name": name, "schedule": cm.group(1) if cm else None, "_raw": line})
    return entries


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def _emit(findings, as_json, mode, extra=None):
    passed = not findings
    if as_json:
        print(json.dumps({
            "gate": "podcast-guard-cron-inventory",
            "mode": mode,
            "pass": passed,
            "extra": extra or {},
            "findings": [{"code": c, "class": cl} for c, cl in findings],
        }, indent=2))
    else:
        print("== Podcast Production Engine :: guard-cron-inventory (%s) ==" % mode)
        if extra:
            for k, v in extra.items():
                print("  %s: %s" % (k, v))
        if passed:
            print("RESULT: PASS - one-cron inventory law holds (or nothing forbidden found).")
        else:
            print("RESULT: FAIL (fail-closed) - %d finding(s):" % len(findings))
            for c, cl in findings:
                print("  [%s] %s" % (c, cl))
    return EXIT_PASS if passed else EXIT_AUTOFAIL


def _read_roster(path, inline):
    names = []
    if path:
        try:
            names += [ln.strip() for ln in Path(path).read_text(encoding="utf-8").splitlines()
                      if ln.strip() and not ln.strip().startswith("#")]
        except OSError:
            return None
    if inline:
        names += [t.strip() for t in inline.split(",") if t.strip()]
    return names


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Fail-closed one-cron / no-heartbeat / no-poller / clean-churn guard (Podcast Production Engine).")
    ap.add_argument("--inventory", help="cron inventory JSON file, or - for stdin")
    ap.add_argument("--live", action="store_true", help="capture the inventory from $OPENCLAW_BIN cron list")
    ap.add_argument("--scan", action="append", default=[], help="shipped dir/file to static-scan (repeatable)")
    ap.add_argument("--skill-root", default=str(_SELF.parent.parent),
                    help="skill root (default: parent of scripts/)")
    ap.add_argument("--min-one", action="store_true", help="static mode: require at least one cron registration")
    ap.add_argument("--client", help="scope the per-client exactly-one check to this slug")
    ap.add_argument("--sweep", action="store_true", help="churn sweep: flag crons for clients not in --roster")
    ap.add_argument("--roster", help="active-client roster file (one slug per line)")
    ap.add_argument("--roster-inline", help="active-client roster as a comma list")
    ap.add_argument("--heartbeat-config", help="heartbeat config JSON (list of {name,skills,agents})")
    ap.add_argument("--namespace-regex", default=_DEFAULT_NAMESPACE, help="regex identifying podcast crons")
    ap.add_argument("--client-regex", default=r"[-_]([a-z0-9]+)$", help="regex to extract the client slug from a cron name")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-test", dest="self_test", action="store_true")
    args = ap.parse_args(argv)

    if args.self_test:
        return self_test()

    try:
        ns_re = re.compile(args.namespace_regex)
        client_re = re.compile(args.client_regex, re.I)
    except re.error as exc:
        print("FATAL: bad regex: %s" % exc, file=sys.stderr)
        return EXIT_USAGE

    # INVENTORY / LIVE mode
    if args.inventory or args.live:
        if args.live:
            entries = _live_inventory()
            if entries is None:
                print("FATAL: could not capture cron inventory from the OpenClaw CLI (set $OPENCLAW_BIN or use --inventory).",
                      file=sys.stderr)
                return EXIT_DEPS
        else:
            try:
                raw_text = sys.stdin.read() if args.inventory == "-" else Path(args.inventory).read_text(encoding="utf-8")
                entries = normalize_inventory(json.loads(raw_text))
            except (OSError, ValueError) as exc:
                print("FATAL: cannot read/parse inventory: %s" % type(exc).__name__, file=sys.stderr)
                return EXIT_USAGE

        roster = None
        if args.roster or args.roster_inline:
            roster = _read_roster(args.roster, args.roster_inline)
            if roster is None:
                print("FATAL: cannot read roster file.", file=sys.stderr)
                return EXIT_USAGE

        hb_skills = None
        if args.heartbeat_config:
            try:
                hb_skills = json.loads(Path(args.heartbeat_config).read_text(encoding="utf-8"))
                if isinstance(hb_skills, dict):
                    hb_skills = hb_skills.get("heartbeats") or hb_skills.get("entries") or [hb_skills]
            except (OSError, ValueError) as exc:
                print("FATAL: cannot read/parse heartbeat config: %s" % type(exc).__name__, file=sys.stderr)
                return EXIT_USAGE

        findings = audit_inventory(entries, ns_re, client_re, sweep=args.sweep, roster=roster,
                                   only_client=args.client, heartbeat_skills=hb_skills)
        pod_n = len([e for e in entries if in_namespace(e, ns_re)])
        return _emit(findings, args.json, "inventory",
                     extra={"entries_total": len(entries), "podcast_entries": pod_n,
                            "sweep": args.sweep, "roster_size": len(roster) if roster else 0})

    # STATIC mode (default)
    targets = args.scan or [args.skill_root]
    findings, distinct = audit_static(targets, min_one=args.min_one)
    return _emit(findings, args.json, "static",
                 extra={"distinct_cron_names": distinct, "targets": targets})


# --------------------------------------------------------------------------- #
# Self-test
# --------------------------------------------------------------------------- #
def self_test():
    ok = True

    def check(label, cond):
        nonlocal ok
        ok = ok and cond
        print("  [%s] %s" % ("PASS" if cond else "MISS", label))

    print("== self-test: cadence bound ==")
    check("once-daily-6am", fires_per_day_bound("12 6 * * *") == 1.0)
    check("daily-shortcut", fires_per_day_bound("@daily") == 1.0)
    check("weekly-not-furnace", fires_per_day_bound("0 6 * * 1") == 1.0)  # one min/hour -> 1 on active days
    check("weekly-shortcut-le1", fires_per_day_bound("@weekly") <= 1.0)
    check("hourly-is-subdaily", fires_per_day_bound("0 * * * *") == 24.0)
    check("step15-is-subdaily", fires_per_day_bound("*/15 * * * *") == 96.0)
    check("twice-daily", fires_per_day_bound("0 6,18 * * *") == 2.0)
    check("hourly-shortcut", fires_per_day_bound("@hourly") == 24.0)
    check("interval-15m", fires_per_day_bound("15m") == 96.0)
    check("interval-1d", fires_per_day_bound("1d") == 1.0)
    check("reboot-unparseable", fires_per_day_bound("@reboot") is None)
    check("garbage-unparseable", fires_per_day_bound("not a schedule") is None)
    check("six-field-sub-minute", fires_per_day_bound("*/30 * * * * *") > 1)

    ns = re.compile(_DEFAULT_NAMESPACE)
    cre = re.compile(r"[-_]([a-z0-9]+)$", re.I)

    print("== self-test: inventory - clean single cron per client ==")
    clean = [
        {"name": "podcast-smoke-test-acme", "schedule": "12 6 * * *", "delivery": "silent", "client": "acme"},
        {"name": "podcast-smoke-test-boba", "schedule": "18 6 * * *", "delivery": "silent", "client": "boba"},
        {"name": "social-media-weekly-theme", "schedule": "0 8 * * 6", "client": "acme"},
    ]
    check("clean-passes", audit_inventory(clean, ns, cre) == [])

    def has(f, needle):
        return any(needle in cl for _, cl in f)

    print("== self-test: inventory - forbidden shapes caught ==")
    two = clean + [{"name": "podcast-extra-acme", "schedule": "0 12 * * *", "delivery": "silent", "client": "acme"}]
    check("second-cron", has(audit_inventory(two, ns, cre), "podcast-crons:acme"))
    subd = [{"name": "podcast-smoke-test-acme", "schedule": "*/10 * * * *", "delivery": "silent", "client": "acme"}]
    check("sub-daily", has(audit_inventory(subd, ns, cre), "sub-daily-schedule"))
    hb = [{"name": "agent-heartbeat", "kind": "heartbeat", "skills": ["podcast", "email"], "schedule": "0 * * * *"}]
    check("heartbeat-ref", has(audit_inventory(hb, ns, cre), "heartbeat-entry-references-podcast"))
    poll = [{"name": "podcast-queue-poller-acme", "schedule": "*/5 * * * *", "client": "acme"}]
    check("poller", has(audit_inventory(poll, ns, cre), "queue-poller-or-watcher"))
    ann = [{"name": "podcast-smoke-test-acme", "schedule": "12 6 * * *", "delivery": "announce", "client": "acme"}]
    check("announce", has(audit_inventory(ann, ns, cre), "delivery-announces-into-chat"))

    print("== self-test: inventory - churn sweep ==")
    sweep_in = [
        {"name": "podcast-smoke-test-acme", "schedule": "12 6 * * *", "delivery": "silent", "client": "acme"},
        {"name": "podcast-smoke-test-gone", "schedule": "12 6 * * *", "delivery": "silent", "client": "gone"},
    ]
    check("orphan-flagged", has(audit_inventory(sweep_in, ns, cre, sweep=True, roster=["acme", "boba"]), "orphan-cron-client-not-in-roster:gone"))
    check("no-orphan-when-all-in-roster",
          not has(audit_inventory(sweep_in, ns, cre, sweep=True, roster=["acme", "gone"]), "orphan-cron"))

    print("== self-test: inventory - heartbeat config ==")
    hbcfg = [{"name": "main-heartbeat", "skills": ["podcast-production-engine"], "agents": []}]
    check("heartbeat-config-listed", has(audit_inventory([], ns, cre, heartbeat_skills=hbcfg), "heartbeat-config-lists-podcast"))

    print("== self-test: inventory - --client scoping ==")
    check("missing-client", has(audit_inventory(clean, ns, cre, only_client="ghost"), "client-has-no-recurring-podcast-cron:ghost"))
    check("present-client-ok", not has(audit_inventory(clean, ns, cre, only_client="acme"), "client-has"))

    print("== self-test: static registration scan ==")
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        good = Path(td) / "provision-podcast-client.sh"
        good.write_text(
            '#!/usr/bin/env bash\n'
            'openclaw cron add --name "podcast-smoke-test-${SLUG}" --schedule "12 6 * * *" --no-deliver --command "$ENTRY"\n',
            encoding="utf-8")
        # A clean single registrar (one --no-deliver once-daily cron add) yields no findings.
        check("static-good-nofindings", audit_static([str(td)])[0] == [])

        bad = Path(td) / "bad-provision.sh"
        bad.write_text(
            '#!/usr/bin/env bash\n'
            'openclaw cron add --name "podcast-poller-${SLUG}" --schedule "*/5 * * * *" --command "$X"\n'
            'openclaw cron add --name "podcast-heartbeat" --schedule "0 * * * *"\n',
            encoding="utf-8")
        f2, distinct2 = audit_static([str(td)])
        check("static-missing-nodeliver", has(f2, "cron-add-missing---no-deliver"))
        check("static-sub-daily", has(f2, "sub-daily-cron-add"))
        check("static-poller", has(f2, "poller-cron-registration"))
        check("static-second-cron", has(f2, "more-than-one-distinct-scheduled-cron-name"))

    print("== self-test: inventory normalization ==")
    check("wrap-crons-key", len(normalize_inventory({"crons": [{"name": "a"}]})) == 1)
    check("bare-list", len(normalize_inventory([{"name": "a"}, {"name": "b"}])) == 2)
    check("text-parse", len(_parse_cron_text("podcast-x  12 6 * * *  silent\npodcast-y  @daily")) == 2)

    print("== self-test: %s ==" % ("ALL ASSERTIONS PASSED" if ok else "FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
