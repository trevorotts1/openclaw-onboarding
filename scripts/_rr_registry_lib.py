#!/usr/bin/env python3
"""_rr_registry_lib.py — RR-031 registry/table helpers for reconcile-rr-agent-map.sh.

Pure data + string work only: no network, no secrets, no writes outside the
caller's private run dir. Kept out of the shell so quoting, JSON, pagination
and the diff cannot drift, and so the box-descriptor argv is built in ONE
place that the tests can drive directly.

Subcommands
  hostname <url>                       -> bare host for reporting
  table-id <contract-manifest>         -> the rr_agent_map table id, or rc 1
  check <roster> <boxes>               -> key=value proof lines; rc 1 if any slug
                                          has no usable execution context
  argv <boxes> <slug> <ssh_timeout>    -> box probe argv, one element per line
  parse                                -> stdin: probe output -> runtime JSON
  page <page.json> <snapshot.jsonl>    -> append page rows; print nextCursor
  plan <roster> <boxes> <snap> <out> <table> <owner>
  merge <plan.json> <runtimes.jsonl> <out.json>
  jobs <final.json>                    -> "OP|chunkfile" lines, in order
  get <json> <key>                     -> scalar
  dupes <plan.json>
  announce <final.json>
  pending <final.json>
  verify <final.json> <snapshot.jsonl>
  emit <final.json> [k=v ...]
"""
import json
import os
import shlex
import sys

MARK_BEGIN = "__RR_AGENTS_BEGIN__"
MARK_END = "__RR_AGENTS_END__"

# The in-box probe. Runs INSIDE the box's own execution context (local shell,
# zsh -lc over the Mac's ssh alias, or `docker exec -u node <container> sh -c`
# on a VPS/Contabo Docker install) — never on the operator host, which is
# exactly the RCV-09 host-only discovery gap. python3 is NOT assumed on the
# far side: the raw output is framed with markers and parsed locally.
PROBE_SH = (
    'oc="$(command -v openclaw 2>/dev/null || true)"; '
    'if [ -z "$oc" ]; then for c in "$HOME/.openclaw/bin/openclaw" '
    '/usr/local/bin/openclaw /data/.openclaw/bin/openclaw; do '
    '[ -x "$c" ] && oc="$c" && break; done; fi; '
    'if [ -z "$oc" ]; then printf \'{"status":"unreachable","reason":"openclaw-not-found"}\\n\'; exit 0; fi; '
    'out="$("$oc" agents list --json 2>/dev/null)" || '
    '{ printf \'{"status":"unreachable","reason":"agents-list-failed"}\\n\'; exit 0; }; '
    'printf \'%s\\n\' "' + MARK_BEGIN + '"; printf \'%s\\n\' "$out"; printf \'%s\\n\' "' + MARK_END + '"'
)

BADKIND = {"status": "unreachable", "reason": "unsupported-box-kind"}


def out(obj):
    json.dump(obj, sys.stdout, sort_keys=True)
    sys.stdout.write("\n")


def die(msg, rc=2):
    sys.stderr.write("_rr_registry_lib: %s\n" % msg)
    sys.exit(rc)


def load(path, what):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception as e:
        die("%s unreadable (%s): %s" % (what, path, e))


# --- descriptor -> argv (THE reuse of the host descriptor) -------------------
def wrap(kind, entry, remote_cmd, ssh_timeout):
    """Mirror prove-zhe.py / prove-floor.py RemoteFS._wrap, plus the RR-031
    finite-SSH-deadline requirement (ConnectTimeout)."""
    if kind == "local":
        return ["sh", "-c", remote_cmd]
    if kind == "mac":
        target = entry.get("ssh_alias") or ""
        if not target:
            return None
        if entry.get("ssh_user"):
            target = "%s@%s" % (entry["ssh_user"], target)
        return ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=%s" % ssh_timeout,
                target, "zsh -lc %s" % shlex.quote(remote_cmd)]
    if kind in ("vps", "contabo"):
        container = entry.get("container") or ""
        if not container:
            return None
        inner = "docker exec -u node %s sh -c %s" % (shlex.quote(container), shlex.quote(remote_cmd))
        target = entry.get("ssh_target") or ""
        if not target:
            return None
        return ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=%s" % ssh_timeout,
                target, inner]
    return None


def exec_kind(entry):
    k = (entry.get("kind") or "").strip()
    if k:
        return k
    plat = (entry.get("platform") or "").strip()
    return plat


# --- subcommands -------------------------------------------------------------
def cmd_hostname(url):
    sys.stdout.write(url.split("://")[-1].split("/")[0] + "\n")


def cmd_table_id(manifest_path):
    """The rr_agent_map table id out of the FLEET rescue contract manifest.

    Accepted shapes: a list of entries, or a dict keyed by table name, or a
    dict of name -> entry / list-of-entries under any of the documented
    container keys (data_tables / tables / entries). An entry names the table
    by `name`/`slug`/`id` and carries its id in `id`/`table_id`.
    """
    d = load(manifest_path, "contract manifest")
    cands = []
    if isinstance(d, list):
        cands = d
    elif isinstance(d, dict):
        for key in ("data_tables", "tables", "entries"):
            v = d.get(key)
            if isinstance(v, list):
                cands.extend(v)
            elif isinstance(v, dict):
                for k, e in v.items():
                    if isinstance(e, dict):
                        e = dict(e)
                        e.setdefault("logical_name", k)
                        cands.append(e)
                    elif k == "tables" and isinstance(e, list):
                        cands.extend(e)
    for e in cands:
        if not isinstance(e, dict):
            continue
        nm = str(e.get("name") or e.get("slug") or e.get("logical_name") or e.get("id") or "")
        if nm == "rr_agent_map":
            tid = e.get("id") or e.get("table_id")
            if tid:
                sys.stdout.write(str(tid) + "\n")
                return 0
    return 1


def cmd_check(roster_path, boxes_path):
    roster = load(roster_path, "roster").get("boxes") or {}
    boxes = load(boxes_path, "box registry").get("boxes") or {}
    missing = 0
    kinds = {}
    for slug in sorted(roster):
        entry = boxes.get(slug) or {}
        kind = exec_kind(entry)
        argv = wrap(kind, entry, "true", "1") if kind else None
        usable = argv is not None
        if not usable:
            missing += 1
        kinds[kind or "none"] = kinds.get(kind or "none", 0) + 1
        print("slug=%s kind=%s exec=%s" % (slug, kind or "none", "mapped" if usable else "missing"))
    print("roster_slugs=%d registry_entries=%d unmapped=%d" % (len(roster), len(boxes), missing))
    for k in sorted(kinds):
        print("kind_count.%s=%d" % (k, kinds[k]))
    print("identity_proved=%d" % (1 if missing == 0 and roster else 0))
    return 1 if (missing or not roster) else 0


def cmd_argv(boxes_path, slug, ssh_timeout):
    boxes = load(boxes_path, "box registry").get("boxes") or {}
    entry = boxes.get(slug) or {}
    argv = wrap(exec_kind(entry), entry, PROBE_SH, ssh_timeout)
    if argv is None:
        return 1
    for a in argv:
        sys.stdout.write(a + "\n")
    return 0


def cmd_parse():
    raw = sys.stdin.read()
    if MARK_BEGIN not in raw or MARK_END not in raw:
        out({"status": "unreachable", "reason": "probe-output-unframed"})
        return 0
    body = raw.split(MARK_BEGIN, 1)[1].rsplit(MARK_END, 1)[0].strip()
    if not body:
        out({"status": "unreachable", "reason": "empty-probe-output"})
        return 0
    if body.startswith("{") and '"status"' in body and '"agents"' not in body:
        try:
            d = json.loads(body)
            if isinstance(d, dict) and d.get("status"):
                out(d)
                return 0
        except Exception:
            pass
    d = None
    try:
        d = json.loads(body)
    except Exception:
        i, j = body.find("["), body.rfind("]")
        if i >= 0 and j > i:
            try:
                d = json.loads(body[i:j + 1])
            except Exception:
                d = None
    if d is None:
        out({"status": "unreachable", "reason": "agents-json-unparseable"})
        return 0
    if isinstance(d, dict):
        d = d.get("agents") or d.get("data") or []
    if not isinstance(d, list):
        out({"status": "unreachable", "reason": "agents-json-not-a-list"})
        return 0
    ids = [str(a.get("id", "")) for a in d if isinstance(a, dict) and a.get("id")]
    default = ""
    for a in d:
        if isinstance(a, dict) and a.get("isDefault") and a.get("id"):
            default = str(a["id"])
            break
    if not default:
        out({"status": "no_default", "reason": "no-isDefault-agent", "agents": ids})
        return 0
    out({"status": "ok", "agent": default, "agents": ids})
    return 0


def cmd_page(page_file, snap_file):
    try:
        with open(page_file) as f:
            d = json.load(f)
    except Exception as e:
        sys.stderr.write("page json invalid: %s\n" % e)
        return 1
    if not isinstance(d, dict) or "data" not in d or not isinstance(d["data"], list):
        sys.stderr.write("page schema invalid: expected an object with a data array\n")
        return 1
    with open(snap_file, "a") as f:
        for r in d["data"]:
            if isinstance(r, dict):
                f.write(json.dumps(r, sort_keys=True) + "\n")
    nxt = d.get("nextCursor")
    if nxt is None or nxt == "" or nxt == "null":
        return 0
    sys.stdout.write(str(nxt) + "\n")
    return 0


def read_snap(path):
    rows = []
    if not os.path.exists(path):
        return rows
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            if isinstance(r, dict):
                rows.append(r)
    return rows


def cmd_plan(roster_path, boxes_path, snap_path, out_path, table_id, owner):
    roster = load(roster_path, "roster").get("boxes") or {}
    boxes = load(boxes_path, "box registry").get("boxes") or {}
    rows = read_snap(snap_path)
    by_slug = {}
    for r in rows:
        slug = str(r.get("box_slug") or "").strip()
        if not slug:
            continue
        by_slug.setdefault(slug, []).append(r)
    dupes = {s: len(v) for s, v in by_slug.items() if len(v) > 1}
    plan = {
        "table_id": table_id,
        "pending_owner": owner,
        "roster_count": len(roster),
        "table_rows": len(rows),
        "slugs": sorted(roster),
        "rows_by_slug": {s: v for s, v in by_slug.items()},
        "duplicates": dupes,
        "duplicates_count": len(dupes),
        "unregistered": sorted(s for s in roster if s not in boxes),
    }
    with open(out_path, "w") as f:
        json.dump(plan, f, sort_keys=True)
    return 0


def cmd_merge(plan_path, runtimes_path, out_path):
    plan = load(plan_path, "plan")
    rts = {}
    if os.path.exists(runtimes_path):
        with open(runtimes_path) as f:
            for line in f:
                line = line.rstrip("\n")
                if not line or "\t" not in line:
                    continue
                slug, blob = line.split("\t", 1)
                try:
                    rts[slug] = json.loads(blob)
                except Exception:
                    rts[slug] = {"status": "unreachable", "reason": "runtime-json-unparseable"}
    owner = plan.get("pending_owner") or "operator"
    ops = []
    pending = []
    verified = 0
    for slug in plan["slugs"]:
        rt = rts.get(slug) or {"status": "unreachable", "reason": "runtime-not-probed"}
        existing = plan["rows_by_slug"].get(slug) or []
        if rt.get("status") != "ok" or not rt.get("agent"):
            pending.append({"box_slug": slug, "owner": owner,
                            "reason": rt.get("reason") or rt.get("status") or "unresolved"})
            continue
        agent = str(rt["agent"])
        if not existing:
            ops.append({"box_slug": slug, "op": "INSERT", "local_agent_id": agent, "before": None})
        elif str(existing[0].get("local_agent_id") or "") == agent:
            verified += 1
        else:
            ops.append({"box_slug": slug, "op": "PATCH", "local_agent_id": agent,
                        "before": str(existing[0].get("local_agent_id") or "")})
    final = {
        "table_id": plan["table_id"],
        "rows_by_slug": plan["rows_by_slug"],
        "duplicates": plan["duplicates"],
        "duplicates_count": plan["duplicates_count"],
        "table_rows": plan["table_rows"],
        "roster_count": plan["roster_count"],
        "unregistered": plan.get("unregistered") or [],
        "verified": verified,
        "changed": len(ops),
        "pending": len(pending),
        "pending_list": pending,
        "ops": ops,
        "runtimes": rts,
    }
    with open(out_path, "w") as f:
        json.dump(final, f, sort_keys=True)
    # payload chunks live beside the run dir, never in a shared temp path
    chunkdir = os.path.join(os.path.dirname(out_path), "chunks")
    os.makedirs(chunkdir, exist_ok=True)
    for o in ops:
        slug = o["box_slug"]
        if o["op"] == "PATCH":
            body = {"filter": {"type": "and", "filters": [
                {"columnName": "box_slug", "condition": "eq", "value": slug}]},
                "data": {"local_agent_id": o["local_agent_id"], "source": "reconcile_rr_agent_map"}}
            name = "%s.patch.json" % slug
        else:
            body = {"data": [{"box_slug": slug, "local_agent_id": o["local_agent_id"],
                              "source": "reconcile_rr_agent_map"}]}
            name = "%s.insert.json" % slug
        with open(os.path.join(chunkdir, name), "w") as f:
            json.dump(body, f, sort_keys=True)
    return 0


def cmd_jobs(final_path):
    d = load(final_path, "final")
    for o in d.get("ops", []):
        suffix = "patch.json" if o["op"] == "PATCH" else "insert.json"
        sys.stdout.write("%s|%s.%s\n" % (o["op"], o["box_slug"], suffix))
    return 0


def cmd_get(path, key):
    d = load(path, "json")
    v = d.get(key)
    if isinstance(v, bool):
        sys.stdout.write("1\n" if v else "0\n")
    elif v is None:
        sys.stdout.write("\n")
    elif isinstance(v, (int, float)):
        sys.stdout.write("%s\n" % v)
    elif isinstance(v, list):
        for item in v:
            sys.stdout.write("%s\n" % (item if isinstance(item, str) else json.dumps(item, sort_keys=True)))
    else:
        sys.stdout.write("%s\n" % v)
    return 0


def cmd_dupes(plan_path):
    d = load(plan_path, "plan")
    for slug in sorted(d.get("duplicates") or {}):
        print("  duplicate box_slug=%s rows=%s" % (slug, d["duplicates"][slug]))
    return 0


def cmd_announce(final_path):
    d = load(final_path, "final")
    print("  table=%s rows=%d roster=%d" % (d["table_id"], d["table_rows"], d["roster_count"]))
    for o in d.get("ops", []):
        if o["op"] == "PATCH":
            print("  plan REPAIR %s: %s -> %s" % (o["box_slug"], o["before"] or "?", o["local_agent_id"]))
        else:
            print("  plan INSERT %s: %s" % (o["box_slug"], o["local_agent_id"]))
    return 0


def cmd_pending(final_path):
    d = load(final_path, "final")
    for p in d.get("pending_list") or []:
        print("  pending %s owner=%s reason=%s" % (p["box_slug"], p["owner"], p["reason"]))
    return 0


def cmd_ledger(final_path, ledger_path, owner, identity_source, table_id, pages):
    """Write the DURABLE pending ledger: one entry per unresolved/inaccessible
    mapping, each carrying its owner, plus the run's actual counts. Written
    atomically (temp + rename) so a concurrent reader never sees a half file,
    and replaced wholesale so it always describes the run that just finished."""
    d = load(final_path, "final")
    doc = {
        "doc": "RR-031 rr_agent_map reconcile — unresolved/inaccessible mappings",
        "table_id": table_id,
        "identity_source": identity_source,
        "pending_owner_default": owner,
        "pages_read": pages,
        "counts": {
            "changed": d.get("changed", 0),
            "verified": d.get("verified", 0),
            "pending": d.get("pending", 0),
            "duplicates": d.get("duplicates_count", 0),
            "table_rows": d.get("table_rows", 0),
            "roster_count": d.get("roster_count", 0),
        },
        "complete": 1 if (d.get("pending", 0) == 0 and d.get("changed", 0) == 0) or d.get("pending", 0) == 0 else 0,
        "pending": [{"box_slug": p["box_slug"], "status": "pending",
                     "owner": p.get("owner") or owner,
                     "reason": p.get("reason") or "unresolved"}
                    for p in (d.get("pending_list") or [])],
    }
    tmp = ledger_path + ".tmp.%d" % os.getpid()
    with open(tmp, "w") as f:
        json.dump(doc, f, indent=1, sort_keys=True)
    os.replace(tmp, ledger_path)
    return 0


def cmd_verify(final_path, snap_path):
    d = load(final_path, "final")
    rows = read_snap(snap_path)
    by_slug = {}
    for r in rows:
        slug = str(r.get("box_slug") or "").strip()
        if slug:
            by_slug.setdefault(slug, []).append(r)
    want = {}
    for slug, ex in d["rows_by_slug"].items():
        if ex:
            want[slug] = str(ex[0].get("local_agent_id") or "")
    for o in d.get("ops", []):
        want[o["box_slug"]] = o["local_agent_id"]
    dupes = sorted(s for s, v in by_slug.items() if len(v) > 1)
    wrong, missing = [], []
    for slug, agent in sorted(want.items()):
        got = by_slug.get(slug)
        if not got:
            missing.append(slug)
        elif str(got[0].get("local_agent_id") or "") != agent:
            wrong.append("%s (expected %s, got %s)" % (slug, agent, got[0].get("local_agent_id")))
    print("  verify: table rows=%d unique_slugs=%d checked=%d missing=%d mismatched=%d duplicates=%d"
          % (len(rows), len(by_slug), len(want), len(missing), len(wrong), len(dupes)))
    if missing:
        print("    missing: %s" % ", ".join(missing))
    if wrong:
        print("    mismatched: %s" % "; ".join(wrong))
    if dupes:
        print("    duplicate slugs: %s" % ", ".join(dupes))
    return 0 if (not missing and not wrong and not dupes) else 1


def parse_extras(extras):
    """The shell passes the k=v list as ONE quoted argument
    ("aborted=0 duplicates=0 complete=0 ..."), so each element must be split on
    whitespace first — otherwise the whole string lands in one base key and the
    machine-readable line carries every key TWICE (once from the override
    string, once from base). QC RR-W4-REGISTRY: emit each key exactly once."""
    pairs = []
    for e in extras:
        pairs.extend(e.split())
    return pairs

def cmd_emit_empty(extras):
    base = {"aborted": 1, "changed": 0, "verified": 0, "pending": 0, "failed": 0,
            "duplicates": 0, "rows_inserted": 0, "rows_updated": 0, "pages": 0,
            "complete": 0, "identity_source": "unknown"}
    for e in parse_extras(extras):
        if "=" in e:
            k, v = e.split("=", 1)
            base[k] = v
    sys.stdout.write("reconcile-rr-agent-map: " + " ".join("%s=%s" % (k, base[k]) for k in sorted(base)) + "\n")
    return 0


def cmd_emit(final_path, extras):
    """The machine-readable count line. `extras` OVERRIDE the planned counts
    with the ACTUAL ones the run observed (rows inserted/updated, failures,
    pages read, completeness), so the line states what happened, not what was
    intended, and every key appears exactly once."""
    d = load(final_path, "final")
    base = {
        "changed": d.get("changed", 0),
        "verified": d.get("verified", 0),
        "pending": d.get("pending", 0),
        "failed": 0,
        "aborted": 0,
        "duplicates": d.get("duplicates_count", 0),
        "rows_inserted": 0,
        "rows_updated": 0,
        "complete": 1,
    }
    for e in parse_extras(extras):
        if "=" in e:
            k, v = e.split("=", 1)
            base[k] = v
    sys.stdout.write("reconcile-rr-agent-map: " + " ".join("%s=%s" % (k, base[k]) for k in sorted(base)) + "\n")
    return 0


def main(argv):
    if len(argv) < 2:
        die("usage: _rr_registry_lib.py <subcommand> ...")
    c = argv[1]
    a = argv[2:]
    if c == "hostname":
        return cmd_hostname(a[0])
    if c == "table-id":
        return cmd_table_id(a[0])
    if c == "check":
        return cmd_check(a[0], a[1])
    if c == "argv":
        return cmd_argv(a[0], a[1], a[2])
    if c == "parse":
        return cmd_parse()
    if c == "page":
        return cmd_page(a[0], a[1])
    if c == "plan":
        return cmd_plan(a[0], a[1], a[2], a[3], a[4], a[5])
    if c == "merge":
        return cmd_merge(a[0], a[1], a[2])
    if c == "jobs":
        return cmd_jobs(a[0])
    if c == "get":
        return cmd_get(a[0], a[1])
    if c == "dupes":
        return cmd_dupes(a[0])
    if c == "announce":
        return cmd_announce(a[0])
    if c == "pending":
        return cmd_pending(a[0])
    if c == "ledger":
        return cmd_ledger(a[0], a[1], a[2], a[3], a[4], a[5])
    if c == "verify":
        return cmd_verify(a[0], a[1])
    if c == "emit":
        return cmd_emit(a[0], a[1:])
    if c == "emit-empty":
        return cmd_emit_empty(a[0:])
    die("unknown subcommand: %s" % c)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
