#!/usr/bin/env python3
"""podbean-publish-provision-manifest.py (S58-U18 companion)

Builds the OPERATOR-PRIVATE box manifest that
scripts/fleet-roll/podbean-publish-provision-roll.sh consumes (--boxes-file).
The roll script's header documents the exact shape this program emits:

    [
      {"name": "...", "role": "operator|client", "platform": "mac|vps",
       "ssh_target": "local" | "user@host",
       "container": "...",        # vps only, optional (roll defaults <name>-openclaw-1)
       "compose_dir": "...",      # vps only, REQUIRED for a vps --apply
       "home": "...",             # sandbox/test only
       "identity": {"last_name": "...", "email": "...", "first_name": "...",
                    "podcast_id": "...", "complete": true|false}}
    ]

It JOINS two operator-private inputs at runtime — never committed anywhere:

  --fleet-file  JSON array of box entries (name, role, platform, ssh_target,
                and for vps boxes container/compose_dir). This is the explicit
                target list; there is NO auto-discovery.
  --roster-file JSON array of podcast roster rows (the n8n roster export).
                A row is matched to a box by --join-key (default "box") equal
                to the box name. Identity fields are read from the row via
                --last-key/--email-key/--first-key/--podcast-id-key.

  --operator-self additionally emits an operator entry for THIS box whose
                identity is read BY NAME from ~/.openclaw/secrets/.env
                (PODCAST_CLIENT_LAST_NAME, PODCAST_CLIENT_EMAIL,
                PODCAST_CLIENT_FIRST_NAME, PODBEAN_PODCAST_ID). Values are
                never printed and never fabricated — absent means absent.

FAIL-CLOSED IDENTITY: identity.complete is true ONLY when last_name, email, and
podcast_id are non-empty. Anything less stays complete=false and the roll
BLOCKS that box; podbean_publish.sh requires the ID in every transport mode.

ZERO VALUES IN OUTPUT: stdout carries box names, roles, platforms and
complete/incomplete flags only. Identity values exist only inside the 0600
manifest file, which lives under ~/.openclaw/secrets/ by default.
"""

import argparse
import json
import os
import sys
import tempfile

DEFAULT_OUT = os.path.expanduser(
    "~/.openclaw/secrets/s58-u18-provision-manifest.json"
)
SECENV = os.path.expanduser("~/.openclaw/secrets/.env")


def eprint(*a):
    print(*a, file=sys.stderr)


def read_env_by_name(path, name):
    """First NAME=value line wins; value returned, never printed."""
    try:
        with open(path) as f:
            for line in f:
                if line.startswith(name + "="):
                    return line.rstrip("\n")[len(name) + 1:]
    except OSError:
        return ""
    return ""


def load_json_array(path, label):
    try:
        with open(path) as f:
            data = json.load(f)
    except Exception as e:
        eprint("manifest builder: cannot parse %s (%s): %s" % (label, path, e))
        sys.exit(1)
    if not isinstance(data, list):
        eprint("manifest builder: %s must be a JSON array" % label)
        sys.exit(1)
    return data


def build_identity(last, email, first, podcast_id):
    last = (last or "").strip()
    email = (email or "").strip()
    return {
        "last_name": last,
        "email": email,
        "first_name": (first or "").strip(),
        "podcast_id": (podcast_id or "").strip(),
        # The publisher requires the channel ID in proxy, broker, and local
        # modes, so a row without it is not provisionable.
        "complete": bool(last and email and (podcast_id or "").strip()),
    }


def ssh_host_key(target):
    """Normalize the textual SSH host; aliases/DNS resolution remain explicit."""
    target = (target or "").strip()
    if not target:
        return ""
    if target == "local":
        return "local"
    return target.rsplit("@", 1)[-1].lower()


def reject_duplicate_targets(entries):
    """Fail closed before writing a manifest that could target one box twice."""
    operators = [entry["name"] for entry in entries
                 if entry.get("role") == "operator"]
    if len(operators) > 1:
        eprint("manifest builder: duplicate operator entries (%s) — refusing"
               % ", ".join(operators))
        sys.exit(1)

    names = {}
    hosts = {}
    for entry in entries:
        name = entry["name"]
        name_key = name.casefold()
        if name_key in names:
            eprint("manifest builder: duplicate box name %r — refusing" % name)
            sys.exit(1)
        names[name_key] = name

        host_key = ssh_host_key(entry.get("ssh_target"))
        if host_key in hosts:
            eprint("manifest builder: duplicate SSH host %r targets both %s and %s — refusing"
                   % (host_key, hosts[host_key], name))
            sys.exit(1)
        if host_key:
            hosts[host_key] = name


def main():
    ap = argparse.ArgumentParser(
        description="Build the operator-private S58-U18 provision manifest "
                    "(joins the fleet box list with the podcast roster)."
    )
    ap.add_argument("--fleet-file", help="operator-private fleet box list (JSON array)")
    ap.add_argument("--roster-file", help="podcast roster export (JSON array)")
    ap.add_argument("--join-key", default="box",
                    help="roster row key holding the box name (default: box)")
    ap.add_argument("--last-key", default="last_name")
    ap.add_argument("--email-key", default="email")
    ap.add_argument("--first-key", default="first_name")
    ap.add_argument("--podcast-id-key", default="podcast_id")
    ap.add_argument("--operator-self", action="store_true",
                    help="emit an operator entry for THIS box, identity read "
                         "by name from ~/.openclaw/secrets/.env")
    ap.add_argument("--operator-name", default="operator-mac")
    ap.add_argument("--out", default=DEFAULT_OUT)
    args = ap.parse_args()

    if not args.fleet_file and not args.operator_self:
        eprint("manifest builder: nothing to build — pass --fleet-file and/or --operator-self")
        sys.exit(1)

    entries = []

    if args.operator_self:
        ident = build_identity(
            read_env_by_name(SECENV, "PODCAST_CLIENT_LAST_NAME"),
            read_env_by_name(SECENV, "PODCAST_CLIENT_EMAIL"),
            read_env_by_name(SECENV, "PODCAST_CLIENT_FIRST_NAME"),
            read_env_by_name(SECENV, "PODBEAN_PODCAST_ID"),
        )
        entries.append({
            "name": args.operator_name,
            "role": "operator",
            "platform": "mac",
            "ssh_target": "local",
            "identity": ident,
        })

    if args.fleet_file:
        fleet = load_json_array(args.fleet_file, "fleet file")
        roster_by_box = {}
        if args.roster_file:
            for row in load_json_array(args.roster_file, "roster file"):
                if isinstance(row, dict):
                    key = str(row.get(args.join_key, "") or "").strip()
                    if key:
                        if key in roster_by_box:
                            eprint("manifest builder: duplicate roster join key %r — refusing"
                                   % key)
                            sys.exit(1)
                        roster_by_box[key] = row
        for box in fleet:
            if not isinstance(box, dict) or not str(box.get("name", "")).strip():
                eprint("manifest builder: fleet entry without a name — refusing "
                       "(explicit target list only, no guessing)")
                sys.exit(1)
            name = str(box["name"]).strip()
            row = roster_by_box.get(name, {})
            ident = build_identity(
                row.get(args.last_key), row.get(args.email_key),
                row.get(args.first_key), row.get(args.podcast_id_key),
            )
            role = str(box.get("role", "client")).strip()
            platform = str(box.get("platform", "")).strip()
            ssh_target = str(box.get("ssh_target", "")).strip()
            if platform not in {"mac", "vps"}:
                eprint("manifest builder: unsupported platform %r; expected mac or vps"
                       % platform)
                sys.exit(1)
            if role != "operator" and ssh_target == "local":
                eprint("manifest builder: non-operator rows may not set "
                       "ssh_target to local")
                sys.exit(1)
            entry = {
                "name": name,
                "role": role,
                "platform": platform,
                "ssh_target": ssh_target,
                "identity": ident,
            }
            for opt in ("container", "compose_dir", "home"):
                if box.get(opt):
                    entry[opt] = str(box[opt])
            if entry["role"] == "client" and entry["platform"] == "vps" \
                    and not entry.get("compose_dir"):
                eprint("  WARNING %s: vps entry without compose_dir — the roll "
                       "will BLOCK it in --apply" % name)
            entries.append(entry)

    if not entries:
        eprint("manifest builder: produced zero entries — refusing to write an empty manifest")
        sys.exit(1)

    reject_duplicate_targets(entries)

    out = os.path.expanduser(args.out)
    out_dir = os.path.dirname(out) or "."
    os.makedirs(out_dir, mode=0o700, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".s58u18-manifest.", dir=out_dir)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(entries, f, indent=2)
            f.write("\n")
        os.replace(tmp, out)  # atomic; never a half-written manifest
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise

    # Summary: names, roles, platforms, flags — NEVER identity values.
    complete = sum(1 for e in entries if e["identity"]["complete"])
    print("manifest: %s (0600)" % out)
    for e in entries:
        print("  box=%s role=%s platform=%s identity=%s" % (
            e["name"], e["role"], e["platform"] or "?",
            "complete" if e["identity"]["complete"] else "INCOMPLETE-will-block",
        ))
    print("total=%d identity_complete=%d" % (len(entries), complete))


if __name__ == "__main__":
    main()
