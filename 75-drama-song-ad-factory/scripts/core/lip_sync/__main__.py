#!/usr/bin/env python3
"""``python3 -m lip_sync run --run-dir <run>`` -- the lip-sync chain (S75-038).

Run it from ``scripts/core`` (the skill root's package folder) so ``lip_sync``
imports as a package. The chain itself is ``lip_sync/chain.py``; this module is
the command line only.

Exit 0 every planned clip has its receipt; 5 a gate refused (nothing was
spent past the refusal); 1 an input or environment error.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)


def _isolation_reader(path):
    """The run's recorded isolation metadata, read as the stem reader.

    A dict (or its ``isolated_stem`` member) naming the task's saved stem
    path, speaker, kind and isolated flag. The existing audio preparation/QC
    process writes it; this command never invents one.
    """
    from lip_sync import chain
    doc = chain._read(Path(path))
    stem = doc.get("isolated_stem") if isinstance(doc, dict) else None
    stem = stem if isinstance(stem, dict) else doc
    chain._need(isinstance(stem, dict) and isinstance(stem.get("path"), str)
                and stem.get("path").strip()
                and isinstance(stem.get("speaker_id"), str)
                and stem.get("isolated") is True,
                "LIPSYNC_PROVIDER_MAPPING_MISSING",
                "the isolation metadata must name path, speaker_id and "
                "isolated=true for the separated stem")
    return lambda result: dict(stem)


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="python3 -m lip_sync",
        description="Wire the lip-sync chain as one command: gate the picture, "
                    "cut the line from the one vocal stem, upload the stem, "
                    "dispatch the locked lip-sync model and run the sync gate, "
                    "for every planned lip-sync clip.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    x = sub.add_parser("run", help="run the chain for every planned clip")
    x.add_argument("--run-dir", required=True)
    x.add_argument("--run-id", default=None)
    x.add_argument("--ledger", default=None,
                   help="this run's spend ledger (default: <run>/spend.sqlite3)")
    x.add_argument("--state-store", default=None,
                   help="the run's control/state.sqlite3, when it differs")
    x.add_argument("--stage", default="video-generation",
                   choices=("video-generation", "qc-retakes"))
    x.add_argument("--adapter", default=None,
                   help="Skill 74 kie_live_adapter.py (default: the standard search)")
    x.add_argument("--usd-per-s", type=float, default=None,
                   help="Skill 74's price for kling/ai-avatar-standard, per second")
    x.add_argument("--isolation-metadata", default=None,
                   help="JSON the audio preparation/QC wrote: the separated "
                        "stem's path, speaker_id, kind and isolated flag")
    x.add_argument("--shot", action="append", default=None,
                   help="only this approved shot id (repeatable)")
    x.add_argument("--spoken", action="store_true",
                   help="the lines are spoken, not sung (default: sung)")
    x.add_argument("--look", default=None,
                   help="the run's look, for the cartoon correlation floor")
    x.add_argument("--person-verdicts", default=None,
                   help="JSON {shot_id: 'DEFECT'} from a person's review")
    a = ap.parse_args(argv)
    from lip_sync import chain
    run_dir = Path(a.run_dir).expanduser().resolve()
    ledger = a.ledger or str(run_dir / "spend.sqlite3")
    providers = {"ledger_db": ledger, "stage": a.stage, "adapter_path": a.adapter,
                 "usd_per_s": a.usd_per_s, "shots": a.shot,
                 "sung": not a.spoken, "look": a.look,
                 "state_store": a.state_store}
    if a.isolation_metadata:
        try:
            providers["isolated_stem_reader"] = _isolation_reader(a.isolation_metadata)
        except chain.ChainError as exc:
            print(json.dumps({"outcome": "refused", "reason_code": exc.code,
                              "detail": str(exc)}, indent=2, sort_keys=True))
            return chain.EXIT["refused"]
    if a.person_verdicts:
        held = chain._read(Path(a.person_verdicts))
        providers["person_verdicts"] = held if isinstance(held, dict) else {}
    # The real Skill 74 upload transport for the picture and the own-line stem;
    # picture_gate.adapter_uploader() resolves the adapter lazily, so building
    # it here costs nothing and fails only when an upload is actually asked for.
    from lip_sync.lip_gate import picture_gate as PG
    upload = PG.adapter_uploader(a.adapter)
    providers.update({"picture_uploader": upload, "stem_uploader": upload,
                      "source_uploader": upload})
    result = chain.run(str(run_dir), a.run_id, providers=providers)
    print(json.dumps(result, indent=2, sort_keys=True))
    return chain.EXIT.get(result.get("outcome"), 1)


if __name__ == "__main__":
    sys.exit(main())
