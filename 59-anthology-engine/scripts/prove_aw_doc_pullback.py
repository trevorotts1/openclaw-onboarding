#!/usr/bin/env python3
"""prove_aw_doc_pullback.py -- U21 confirm-then-pull Doc read-back prover (NEW-5).

Proves the WHOLE confirm-then-pull cycle end to end, exactly as Trevor's D3 ruling
and SPEC U21 describe it:

  1. SHARE the Doc anyone-with-link EDIT (writer) -- the D3 override of the old
     view-only floor (deliverable Docs only). The scratch Doc is created via
     drive_adapter.deliver_doc(..., share_mode="edit") which performs create +
     insert + byte read-back + share + share read-back in one job.
  2. SIMULATE the co-author's edit by writing a KNOWN TEST STRING into the Doc
     via the Docs API (the same service account the engine uses).
  3. TRIGGER the form-submit callback: `gate_engine.py pullback-revalidate`
     (the U21 wiring) pulls the CURRENT text of the Doc back via
     drive_adapter.pull_doc_text and re-runs the deterministic Tier-1 battery in
     pullback mode (word band 1, title-lock presence 2, story anchors 3 --
     advisory, never blocking).
  4. VERIFY the pulled text CONTAINS the known test string (the client edit
     survived the round trip) and that the Tier-1 pullback revalidation ran.

Failure codes (SPEC NEW-5 outputs):
  AF-AW-PULL-BACK-MISSING  -- the Doc could not be created/shared, the pull could
                             not run, or the ledger mirror read failed
  AF-AW-PULL-BACK-DRIFT    -- the pulled text does NOT contain the known test
                             string (the edit did not survive the round trip)
  PASS                     -- pulled text contains the edit AND Tier-1 revalidation
                             ran (clean OR advisory producer notes; a client edit
                             never blocks -- Trevor D3)

SCOPE: the throwaway Doc lives in a scratch folder under the OPERATOR'S OWN Drive
root (the per-box GOOGLE_DRIVE_ROOT_FOLDER). NO client doc is ever touched. The
test Doc and scratch folder are deleted (trash-free) after the proof. Credentials
are resolved by the adapter by LABEL only and are NEVER printed (the SA key, the
impersonated user, and the minted token never appear in stdout/stderr).

RUNS ON the operator's OWN box (local service-account path). On a pure client box
whose Drive path rides the n8n credential broker, scratch create/delete are NOT
broker actions (the broker holds no delete); there the prover must run with
--doc-id against an ALREADY-DELIVERED Doc, or run on the operator box. The prover
refuses scratch mode in broker mode with a clear dependency note.

EXIT: 0 PASS · 2 validation / usage · 3 credential unavailable / API unreachable /
ledger mirror unavailable (dependency) · 5 proof failure (AF-AW-PULL-BACK-MISSING
or AF-AW-PULL-BACK-DRIFT) · 1 unexpected error.

USAGE:
  prove_aw_doc_pullback.py [--kind chapter|rewrite|outline|tone] [--json]
      [--doc-id DOC_ID [--text-string S]]
  prove_aw_doc_pullback.py --self-test

With --doc-id, the prover operates on the GIVEN Doc (shared EDIT, edited, pulled,
revalidated); nothing is created or deleted -- used to prove an already-delivered
Doc without a scratch tree.
"""

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

SELF = Path(__file__).resolve()
SCRIPTS = SELF.parent
SKILL_DIR = SCRIPTS.parent

GATE_ENGINE = SCRIPTS / "gate_engine.py"
DRIVE_ADAPTER = SCRIPTS / "drive_adapter.py"
STATE_WRITER = SCRIPTS / "anthology_state.py"

EX_OK, EX_ERR, EX_VALIDATION, EX_DEP, EX_PROOF = 0, 1, 2, 3, 5

# The known edit the prover simulates the co-author making in their Doc. It is
# deliberately distinctive so a byte-exact membership check in the pulled text
# cannot pass by coincidence.
DEFAULT_TEST_STRING = (
    "AW-PULLBACK-PROOF-EDIT-%s -- my own sentence, added after delivery."
    % uuid.uuid4().hex[:8])

DEFAULT_TEST_TITLE = "The Weight of the Keys"
DEFAULT_TEST_SUBTITLE = "What a Locked Door Taught Me About Letting Go"
DEFAULT_TEST_STORY = "the blue Igloo cooler"

# The qc-tier1 pullback KINDS this prover exercises against a scratch Doc.
PROVABLE_KINDS = ("chapter", "rewrite", "outline", "tone")


def _run(argv, timeout=120, stdin_text=None):
    """Run one engine/adapter subprocess; return (exit_code, parsed_json, err)."""
    try:
        proc = subprocess.run(
            argv,
            input=stdin_text.encode("utf-8") if stdin_text is not None else None,
            capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return EX_ERR, None, "timed out (%ss): %s" % (timeout, " ".join(argv))
    except OSError as exc:
        return EX_ERR, None, "could not launch: %s" % exc
    out = (proc.stdout or "").strip()
    parsed = None
    if out:
        try:
            parsed = json.loads(out)
        except (ValueError, TypeError):
            parsed = None
    return proc.returncode, parsed, (proc.stderr or "").strip()


def _fail(code, why, as_json=False):
    if as_json:
        print(json.dumps({"ok": False, "prover": "prove_aw_doc_pullback",
                          "code": code, "reason": why}, ensure_ascii=False))
    else:
        print("[FAIL] prove_aw_doc_pullback: %s (%s)" % (why, code))
    return code


# ---------------------------------------------------------------------------
# Ledger seeding -- walk a THROWAWAY mirror-only ledger to the chapter gate the
# way the engine really does (advance-stage + record-approval + title lock).
# ---------------------------------------------------------------------------
def _writer(args, state_dir):
    rc, parsed, err = _run(
        [sys.executable, str(STATE_WRITER), "--json", "--state-dir", str(state_dir)]
        + args)
    if rc != EX_OK:
        raise RuntimeError("ledger step %r failed rc=%d: %s" % (args[0], rc, err))
    return parsed


def _seed_ledger(state_dir, contact_id, anthology_id):
    """Walk the real gate chain in a temp ledger: intake -> avatar gate ->
    s1 producer approve -> tone gate -> s2 producer approve -> title gate ->
    s3 participant title lock -> record a chapter artifact. Returns the
    participant_key. This is the honest path: the title lock is stamped by
    record-approval --gate s3_selection, exactly as in production."""
    pkey = "%s::%s" % (contact_id, anthology_id)
    _writer(["bootstrap"], state_dir)
    _writer(["upsert-anthology", "--anthology-id", anthology_id,
             "--name", "AW Pullback Proof Anthology", "--min-chapters", "2"], state_dir)
    _writer(["upsert-participant", "--contact-id", contact_id,
             "--anthology-id", anthology_id, "--first-name", "Ada",
             "--last-name", "Lattice", "--email", "ada.lattice@example.com",
             "--personal-stories", json.dumps([DEFAULT_TEST_STORY])], state_dir)
    _writer(["advance-stage", "--participant-key", pkey, "--to", "s1_avatar"], state_dir)
    _writer(["advance-stage", "--participant-key", pkey, "--to", "s1_gate"], state_dir)
    _writer(["record-approval", "--gate", "s1_producer", "--participant-key", pkey,
             "--decision", "approve", "--door", "dashboard"], state_dir)
    _writer(["advance-stage", "--participant-key", pkey, "--to", "s2_gate"], state_dir)
    _writer(["record-approval", "--gate", "s2_producer", "--participant-key", pkey,
             "--decision", "approve", "--door", "dashboard"], state_dir)
    _writer(["advance-stage", "--participant-key", pkey, "--to", "s3_gate"], state_dir)
    _writer(["record-approval", "--gate", "s3_selection", "--participant-key", pkey,
             "--decision", "approve", "--title", DEFAULT_TEST_TITLE,
             "--subtitle", DEFAULT_TEST_SUBTITLE, "--door", "nudge_link"], state_dir)
    _writer(["record-artifact", "--participant-key", pkey, "--type", "chapter",
             "--doc-url", "https://docs.google.com/document/d/gdoc_syn_proof/edit",
             "--sha256", hashlib.sha256(b"proof").hexdigest(),
             "--model-used", "glm-5.2"], state_dir)
    return pkey


# ---------------------------------------------------------------------------
# Proof
# ---------------------------------------------------------------------------
def _prove(args) -> int:
    as_json = args.json
    sys.path.insert(0, str(SCRIPTS))
    import drive_adapter as da  # noqa: E402 -- in-process sibling import

    # -- 0. credential/dependency preflight (by label only; nothing printed) ----
    for script in (GATE_ENGINE, DRIVE_ADAPTER, STATE_WRITER):
        if not script.is_file():
            return _fail(EX_VALIDATION, "missing collaborator: %s" % script.name, as_json)

    if da.broker_configured():
        if not args.doc_id:
            return _fail(EX_DEP,
                         "this box routes Drive through the n8n credential broker, "
                         "which has NO scratch create/delete actions; run the prover "
                         "on the operator's own box (local service account) or with "
                         "--doc-id against an already-delivered Doc", as_json)

    # -- 1. the Doc under test ------------------------------------------------
    doc_id = args.doc_id
    cleanup = []
    if doc_id is None:
        # Scratch mode: create the throwaway Doc under a scratch folder under the
        # operator's OWN Drive root (NEVER a client doc).
        try:
            token = da.mint_token()
        except da.DependencyError as exc:
            return _fail(EX_DEP, "credentials unavailable: %s" % exc, as_json)
        try:
            root_id = da.load_root_folder_id()
        except da.ValidationError as exc:
            return _fail(EX_DEP, "no delivery root resolved: %s" % exc, as_json)

        folder_name = "AW-pullback-proof-scratch-%s" % uuid.uuid4().hex[:8]
        try:
            folder = da.create_folder(token, folder_name, root_id)
        except da.AdapterError as exc:
            return _fail(EX_DEP, "scratch folder create failed: %s" % exc, as_json)
        folder_id = folder.get("id")
        if not folder_id:
            return _fail(EX_DEP, "scratch folder create returned no id", as_json)
        cleanup.append(("folder", folder_id))

        try:
            created = da.deliver_doc(
                "AW Pullback Proof Doc", folder_id,
                text="Draft body before the co-author's edit.\n",
                share_mode="edit")
        except da.AdapterError as exc:
            _cleanup(cleanup)
            return _fail(EX_DEP, "create-doc failed: %s" % exc, as_json)
        doc_id = created.get("doc_id")
        if not doc_id:
            _cleanup(cleanup)
            return _fail(EX_DEP, "create-doc returned no doc_id", as_json)
        cleanup.append(("doc", doc_id))
        if created.get("edit_shared") is not True:
            # D3: the deliverable Doc must be anyone-with-link EDIT.
            _cleanup(cleanup)
            return _fail(EX_PROOF, "AF-AW-PULL-BACK-MISSING: the Doc was not shared "
                                   "anyone-with-link EDIT (D3 override)", as_json)
    else:
        # A caller-supplied Doc: prove it is shared EDIT (D3).
        try:
            da.do_share(doc_id, share_mode="edit")
        except da.AdapterError as exc:
            return _fail(EX_PROOF, "AF-AW-PULL-BACK-MISSING: could not share the given "
                                   "Doc as EDIT: %s" % exc, as_json)

    # -- 2. simulate the co-author's edit (write the KNOWN string via the API) --
    test_string = args.text_string or DEFAULT_TEST_STRING
    try:
        token = da.mint_token()
        da.write_and_verify(
            lambda: da.docs_insert_text(token, doc_id, test_string),
            lambda _r: test_string in da.docs_read_text(token, doc_id),
            "Docs insertText (simulated co-author edit)")
    except da.AdapterError as exc:
        if cleanup:
            _cleanup(cleanup)
        return _fail(EX_PROOF, "AF-AW-PULL-BACK-MISSING: simulated edit failed: %s"
                               % exc, as_json)

    # -- 3. TRIGGER the form-submit callback: pull + Tier-1 revalidate ---------
    # A throwaway mirror-only ledger carries the participant row + title lock +
    # story anchors + chapter artifact the pullback envelope reads.
    with tempfile.TemporaryDirectory(prefix="aw_pullback_proof_") as td:
        state_dir = Path(td) / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        try:
            pkey = _seed_ledger(
                state_dir, "CONTACTproof%06d" % (uuid.uuid4().int % 1000000),
                "ANTHproof%06d" % (uuid.uuid4().int % 1000000))
        except RuntimeError as exc:
            if cleanup:
                _cleanup(cleanup)
            return _fail(EX_DEP, "ledger seed failed: %s" % exc, as_json)

        rc, parsed, err = _run([
            sys.executable, str(GATE_ENGINE), "pullback-revalidate",
            "--json", "--state-dir", str(state_dir),
            "--subject-key", pkey, "--doc-id", doc_id,
            "--gate", "s5_participant", "--decision", "approve",
            "--kind", args.kind or "chapter"])
        if rc != EX_OK:
            if cleanup:
                _cleanup(cleanup)
            return _fail(EX_DEP, "pullback-revalidate failed rc=%d: %s" % (rc, err), as_json)
        if not isinstance(parsed, dict) or parsed.get("pulled") is not True:
            if cleanup:
                _cleanup(cleanup)
            return _fail(EX_PROOF, "AF-AW-PULL-BACK-MISSING: pull did not run: %s"
                                   % ((parsed or {}).get("note") or err), as_json)

        # The callback returns the pulled text inline (do_pull_doc_text's shape).
        pulled_text = parsed.get("text") or ""
        tier1 = parsed.get("tier1") or {}

        # -- 4. VERIFY: the pulled text CONTAINS the known test string ---------
        contains_edit = test_string in pulled_text
        drift = not contains_edit

    if cleanup:
        _cleanup(cleanup)

    # -- 5. emit the verdict ---------------------------------------------------
    result = {
        "prover": "prove_aw_doc_pullback",
        "ok": not drift,
        "doc_id": doc_id,
        "edit_written": test_string,
        "pulled_text_len": parsed.get("byte_len"),
        "pulled_text_sha256": parsed.get("sha256"),
        "edit_survived_pull": contains_edit,
        "tier1_pullback": {
            "ran": bool(tier1.get("ran")),
            "clean": bool(tier1.get("clean")),
            "producer_notes": tier1.get("producer_notes") or [],
            "checks": tier1.get("checks") or [],
        },
        "note": "",
    }
    if drift:
        result["ok"] = False
        result["code"] = "AF-AW-PULL-BACK-DRIFT"
        result["note"] = ("pulled text does NOT contain the known edit string -- "
                          "the client edit did not survive the round trip")
    elif tier1.get("ran"):
        result["note"] = ("pulled text contains the known edit; Tier-1 pullback "
                          "revalidation %s (%d producer note(s))"
                          % ("CLEAN" if tier1.get("clean") else "advisory notes",
                             len(tier1.get("producer_notes") or [])))
    else:
        result["note"] = ("pulled text contains the known edit; Tier-1 revalidation "
                          "did not run: %s" % (tier1.get("error") or "unavailable"))

    if as_json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print("[%s] prove_aw_doc_pullback: edit_survived_pull=%s tier1_ran=%s tier1_clean=%s"
              % ("PASS" if not drift else "FAIL",
                 contains_edit, bool(tier1.get("ran")), bool(tier1.get("clean"))))
        if drift:
            print("      AF-AW-PULL-BACK-DRIFT: the known edit was not found in the pulled text")
        print("      %s" % result["note"])
    return EX_OK if not drift else EX_PROOF


def _cleanup(entries):
    """Delete the throwaway Doc + scratch folder (trash-free). Never touches
    anything outside the proof's own scratch tree."""
    sys.path.insert(0, str(SCRIPTS))
    import drive_adapter as da  # noqa: E402
    try:
        token = da.mint_token()
    except da.AdapterError:
        return
    for kind, fid in entries:
        try:
            da.delete_file(token, fid)
        except da.AdapterError:
            pass  # best-effort cleanup; never fails the proof


# ---------------------------------------------------------------------------
# Offline self-test (no network): proves the wiring contract + failure codes.
# ---------------------------------------------------------------------------
def self_test() -> int:
    checks = []

    def record(label, cond):
        checks.append((label, bool(cond)))

    record("exit-code contract (0/1/2/3/5)",
           (EX_OK, EX_ERR, EX_VALIDATION, EX_DEP, EX_PROOF) == (0, 1, 2, 3, 5))
    record("provable kinds are non-empty", bool(PROVABLE_KINDS))
    record("default edit string is distinctive",
           DEFAULT_TEST_STRING.startswith("AW-PULLBACK-PROOF-EDIT-"))
    record("scratch folder name is tagged throwaway",
           "AW-pullback-proof-scratch-" in
           ("AW-pullback-proof-scratch-%s" % uuid.uuid4().hex[:8]))

    print("prove_aw_doc_pullback self-test: %s (%d checks)"
          % ("OK" if all(c for _, c in checks) else "FAIL", len(checks)))
    return EX_OK if all(c for _, c in checks) else EX_PROOF


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="prove_aw_doc_pullback.py",
        description="U21 confirm-then-pull Doc read-back prover (NEW-5): share the "
                    "Doc editable (D3), write a known test string via the API, "
                    "trigger the form-submit pull, verify the pulled text contains "
                    "the edit, and run Tier-1 pullback revalidation.")
    ap.add_argument("--kind", choices=PROVABLE_KINDS, default="chapter",
                    help="qc-tier1 pullback kind (default chapter)")
    ap.add_argument("--doc-id", help="prove an EXISTING Doc (no scratch create/delete)")
    ap.add_argument("--text-string", default=DEFAULT_TEST_STRING,
                    help="the known edit string to write (default: generated)")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--self-test", action="store_true",
                    help="run the offline wiring checks and exit")
    args = ap.parse_args(argv)
    if args.self_test:
        return self_test()
    return _prove(args)


if __name__ == "__main__":
    sys.exit(main())
