#!/usr/bin/env python3
"""drive-tree-provision.py -- idempotent Drive folder tree (W1.11).

WHAT THIS IS (SPEC 3.4 row 10; SPEC 10.1; PRD 3.7; ENGINE-MANIFEST L10):
  Idempotent get-or-create of the delivery folder tree
        <PER-CLIENT ROOT> / Producer / Anthology / Participant
  under this client's OWN BlackCEO-hosted Shared-Drive root, resolved per box from
  GOOGLE_DRIVE_ROOT_FOLDER (config key delivery.drive_root_folder is a per-box slot;
  BlackCEO provisions ONE Shared Drive per client, never one shared operator root).
  Invoked by S0 intake "on first sight" of a participant, and by
  provision-anthology-client.sh for the producer root. It VERIFIES the configured
  per-client root at preflight (files.get, supportsAllDrives) and NEVER creates a NEW
  root -- if the root is unreachable it STOPS (exit 2), it does not invent one
  (BlackCEO provisions the per-client Shared Drive out of band).

  Idempotency: each level is get-or-created by exact name via drive_adapter's
  find_child_folder (deterministic earliest-createdTime pick), so a re-run of the
  same (producer, anthology, participant) returns the SAME ids and creates
  nothing. The four folder ids are printed so the caller caches them onto the
  ledger rows (producers.drive_root_folder_id, anthologies.drive_folder_id,
  participants.drive_folder_id) via anthology_state.py.

  Levels are optional and provisioned top-down as supplied: --producer alone
  provisions just the producer folder; add --anthology and --participant to drive
  deeper. A deeper level requires the ones above it.

DOCTRINE: no secret value is ever printed (credentials by label + SET/NOT-SET);
zero Anthropic identifiers; zero client PII; the root is REUSED, never created.

EXIT CODES (SPEC 3.4 row 10):
  0  tree verified or created (idempotent no-op included)
  1  unexpected error
  2  configured root unreachable / not a folder  OR  validation refusal
  3  Google API unreachable / credential unavailable (dependency/held)

USAGE:
  drive-tree-provision.py provision --producer NAME
      [--anthology NAME [--participant NAME]] [--root-folder-id ID] [--json]
  drive-tree-provision.py verify-root [--root-folder-id ID]   # preflight only
  drive-tree-provision.py --self-test                         # offline checks
"""
import argparse
import json
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import drive_adapter as da  # noqa: E402  (sibling module in scripts/)

EX_OK, EX_ERR, EX_ROOT, EX_DEP = 0, 1, 2, 3
MIME_FOLDER = da.MIME_FOLDER


class RootUnreachable(Exception):
    """The configured EXISTING root is missing or is not a folder (never create)."""
    exit_code = EX_ROOT


def verify_root(token, root_id):
    """Preflight: the configured PER-CLIENT root must exist and be a live folder.
    Returns its metadata dict. Raises RootUnreachable (exit 2) rather than ever
    creating one. Accepts the per-client root supplied via GOOGLE_DRIVE_ROOT_FOLDER
    (arg > env > config) -- a BlackCEO-hosted Shared-Drive root is fully supported
    (files_get sets supportsAllDrives and a Shared Drive resolves as a folder)."""
    try:
        meta = da.files_get(token, root_id,
                            fields="id,name,mimeType,trashed,capabilities")
    except da.DependencyError as exc:
        # 404 for the ROOT means the CONFIGURED root is wrong -> root-unreachable,
        # not a generic dependency outage. Distinguish on the message.
        if "not found" in str(exc).lower():
            raise RootUnreachable(
                "the configured delivery root %s is not reachable by the service "
                "account; refusing to create a new root (SPEC 10.1)." % root_id)
        raise
    if meta.get("trashed") or meta.get("mimeType") != MIME_FOLDER:
        raise RootUnreachable(
            "the configured delivery root %s is trashed or is not a folder; "
            "refusing to create a new root." % root_id)
    caps = meta.get("capabilities", {}) or {}
    if caps.get("canAddChildren") is False:
        raise RootUnreachable(
            "the service account cannot add children to the configured root %s "
            "(ACL/delegation issue); refusing to create a new root." % root_id)
    return meta


def provision(producer, anthology=None, participant=None, root_folder_id=None):
    """Idempotently ensure Root/Producer[/Anthology[/Participant]] exists.

    Returns a machine-readable dict with each level's id and a created flag."""
    if not producer or not str(producer).strip():
        raise da.ValidationError("--producer is required (a display name).")
    if participant and not anthology:
        raise da.ValidationError("--participant requires --anthology (tree is top-down).")

    root_id = da.load_root_folder_id(root_folder_id)
    token = da.mint_token()

    root_meta = verify_root(token, root_id)  # NEVER creates a root

    result = {
        "ok": True, "action": "provision",
        "root": {"id": root_meta["id"], "name": root_meta.get("name"),
                 "existing": True, "created": False},
        "credentials": da._credential_status(),
    }

    prod_folder, prod_created = da.get_or_create_folder(token, root_id, producer)
    result["producer"] = {"id": prod_folder["id"], "name": producer,
                          "created": prod_created}
    parent_id = prod_folder["id"]

    if anthology:
        anth_folder, anth_created = da.get_or_create_folder(token, parent_id, anthology)
        result["anthology"] = {"id": anth_folder["id"], "name": anthology,
                               "created": anth_created}
        parent_id = anth_folder["id"]

        if participant:
            part_folder, part_created = da.get_or_create_folder(
                token, parent_id, participant)
            result["participant"] = {"id": part_folder["id"], "name": participant,
                                     "created": part_created}
            result["participant_folder_id"] = part_folder["id"]

    # A convenience: the deepest provisioned folder id (what S0 caches per row).
    deepest = (result.get("participant") or result.get("anthology")
               or result["producer"])
    result["deepest_folder_id"] = deepest["id"]
    return result


def cmd_verify_root(args):
    root_id = da.load_root_folder_id(args.root_folder_id)
    token = da.mint_token()
    meta = verify_root(token, root_id)
    _out({"ok": True, "action": "verify-root", "root_id": meta["id"],
          "name": meta.get("name"), "is_folder": True,
          "credentials": da._credential_status()})
    return EX_OK


def cmd_provision(args):
    _out(provision(args.producer, args.anthology, args.participant,
                   args.root_folder_id))
    return EX_OK


# ---------------------------------------------------------------------------
# Offline self-test (no network)
# ---------------------------------------------------------------------------
def self_test():
    assert (EX_OK, EX_ERR, EX_ROOT, EX_DEP) == (0, 1, 2, 3)
    assert RootUnreachable.exit_code == 2
    # participant without anthology is a top-down violation (no network reached)
    for kwargs in ({"producer": "P", "participant": "X"},
                   {"producer": "   "}):
        raised = False
        try:
            provision(**kwargs)
        except da.ValidationError:
            raised = True
        assert raised, "expected ValidationError for %r" % kwargs
    # the module reuses drive_adapter's config resolver and never invents a root
    assert da.load_root_folder_id("EXPLICIT") == "EXPLICIT"
    # confirm the adapter's own self-test wiring is importable and coherent
    assert callable(da.get_or_create_folder)
    assert callable(da.files_get)
    print("drive-tree-provision self-test: OK (top-down guard, root reuse, "
          "exit-code contract)")
    return EX_OK


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _out(obj):
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")


def build_parser():
    p = argparse.ArgumentParser(
        prog="drive-tree-provision.py",
        description="Idempotent Producer/Anthology/Participant Drive tree under "
                    "the EXISTING root (never creates a new root).")
    p.add_argument("--self-test", action="store_true",
                   help="run offline coherence checks and exit")
    sub = p.add_subparsers(dest="cmd")

    pr = sub.add_parser("provision", help="get-or-create the folder tree")
    pr.add_argument("--producer", required=True, help="producer display name (level 1)")
    pr.add_argument("--anthology", help="anthology name (level 2)")
    pr.add_argument("--participant", help="participant name (level 3; needs --anthology)")
    pr.add_argument("--root-folder-id", help="override the configured EXISTING root id")
    pr.add_argument("--json", action="store_true", help="(default) JSON output")

    vr = sub.add_parser("verify-root", help="preflight: verify the configured root only")
    vr.add_argument("--root-folder-id", help="override the configured EXISTING root id")

    return p


def dispatch(args):
    if args.self_test:
        return self_test()
    if args.cmd == "provision":
        return cmd_provision(args)
    if args.cmd == "verify-root":
        return cmd_verify_root(args)
    raise da.ValidationError("no subcommand given; run with -h for usage.")


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        return dispatch(args)
    except SystemExit:
        raise
    except RootUnreachable as exc:
        sys.stderr.write("[drive-tree-provision] RootUnreachable: %s\n" % exc)
        return EX_ROOT
    except da.AdapterError as exc:
        # ValidationError -> 2 (matches "configured root unreachable / validation")
        code = EX_ROOT if exc.exit_code == 2 else exc.exit_code
        sys.stderr.write("[drive-tree-provision] %s: %s\n" % (type(exc).__name__, exc))
        return code
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write("[drive-tree-provision] unexpected error: %s: %s\n"
                         % (type(exc).__name__, exc))
        return EX_ERR


if __name__ == "__main__":
    sys.exit(main())
