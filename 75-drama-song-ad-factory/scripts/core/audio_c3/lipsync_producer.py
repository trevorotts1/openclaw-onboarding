"""Instrumented selected-song -> separated stem -> measured cut producer.

Usage: runner = skill74_runner(run_dir, uploader, dispatch_kwargs, isolation_reader);
produce(run_dir, run_id, shot_id, song_path, runner) returns a stem for upload_stem.
No operation occurs until produce is called.

The injected separation runner must use the existing Skill 74 approved dispatch
route. No default provider transport or retrospective receipt import is provided.
Generic vocal separation does not prove speaker isolation; its runner must return
speaker/isolation metadata from the existing audio preparation/QC process.
"""
from pathlib import Path
import json
import uuid

from lipsync_evidence import _approved, _binding, _need, _num, _path, _read, _sha
from lip_sync.narrator_rule import check_stems
from lip_sync.stem_offset.stem_offset import measure_offset_files, cut_plan

MODEL = "ai-music-api/separate-vocals"
SCHEMA = "blackceo.lipsync-production/v1"
VERSION = "1.0.0"


def _record(path, rec):
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(rec, sort_keys=True), encoding="utf-8")
    temp.replace(path)


def _selection(root, song):
    pick = root / "song-choices/pick.json"
    if pick.exists():
        pick = _path(root, str(pick))
        _need(_read(pick).get("sha256") == _sha(song), "LIPSYNC_SELECTED_SONG_MISMATCH", "source differs from selected pick")
        return {"mode": "picked", "path": str(pick), "sha256": _sha(pick)}
    state = root / "song-choices/state.json"
    state_hash = None
    if state.exists():
        state = _path(root, str(state))
        _need(not _read(state).get("required"), "LIPSYNC_SELECTED_SONG_MISMATCH", "required song choice has no pick")
        state_hash = _sha(state)
    from delivery_package.run_inputs import audio_sources
    mix = _path(root, str(audio_sources(str(root))["mix"]))
    _need(mix == song, "LIPSYNC_SELECTED_SONG_MISMATCH", "source differs from existing one-song mix")
    return {"mode": "single-mix", "path": str(mix), "sha256": _sha(mix), "choice_state_sha256": state_hash}


def produce(run_dir, run_id, shot_id, song_path, separation_runner,
            measure_offset=None, cut_runner=None):
    """Execute and record operations now; injected runners enable offline tests.

    separation_runner(request) returns the normal successful dispatch envelope,
    plus evidence.isolated_stem={path,speaker_id,kind,isolated}. It must preserve
    the approved Skill74 budget/retry policy, never submit uncertain jobs again.
    """
    root, required = _approved(run_dir)
    row = required.get(shot_id)
    _need(row is not None and callable(separation_runner), "LIPSYNC_PRODUCER_MISSING", "approved shot and separation runner required")
    song = _path(root, song_path)
    song_hash = _sha(song)
    _need(song.stat().st_size > 0, "LIPSYNC_SELECTED_SONG_MISMATCH", "selected song is empty")
    selection = _selection(root, song)
    directory = (root / "control/lipsync-production" / uuid.uuid4().hex).resolve()
    _need(directory.is_relative_to(root), "LIPSYNC_FOREIGN_ARTIFACT", "producer output leaves run")
    directory.mkdir(parents=True)
    path = directory / "lineage.json"
    request = {"model": MODEL, "run_id": run_id, "source_path": str(song),
               "source_sha256": song_hash, "output_dir": str(directory),
               "speaker_id": row["speaker"], "lipsync_binding": _binding(row)}
    record = {"schema": SCHEMA, "producer": "audio_c3.lipsync_producer", "producer_version": VERSION, "state": "separation_started",
              "run_id": run_id, "binding": _binding(row), "source_path": str(song),
              "source_sha256": song_hash, "selection": selection,
              "separation_request": request}
    _record(path, record)
    separation = separation_runner(request)
    _need(_sha(song) == song_hash and _selection(root, song) == selection,
          "LIPSYNC_SOURCE_CHANGED", "selected source changed during separation")
    ev = separation.get("evidence") or {}
    _need(separation.get("tool") == "kie_dispatch" and separation.get("outcome") == "ok"
          and separation.get("run_id") == run_id and ev.get("generated") is True and ev.get("task_id"),
          "LIPSYNC_SEPARATION_FAILED", "successful Skill74 separation task required")
    _source_binding(root, ev, song, song_hash)
    stem = ev.get("isolated_stem") or {}
    ok, code, errors = check_stems([stem], row["speaker"])
    _need(ok, code, str(errors))
    source = _path(root, stem.get("path"))
    saved = [_path(root, p) for p in ev.get("saved_paths", [])]
    _need(source in saved and source.stat().st_size > 0 and source != song,
          "LIPSYNC_SEPARATION_FAILED", "separation task did not save an isolated stem")
    source_hash = _sha(source)
    record.update(state="offset_started", separation=separation,
                  separated_path=str(source), separated_sha256=source_hash,
                  speaker_id=stem["speaker_id"], isolated=stem["isolated"], kind=stem.get("kind"))
    _record(path, record)
    offset = (measure_offset or measure_offset_files)(str(source), str(song))
    _need(_sha(source) == source_hash and _sha(song) == song_hash,
          "LIPSYNC_SOURCE_CHANGED", "source changed during offset measurement")
    _need(isinstance(offset, dict) and _num(offset.get("offset_s")) and _num(offset.get("corr")),
          "LIPSYNC_OFFSET_MISSING", "measured offset and correlation required")
    cut = cut_plan(row["start_s"], row["end_s"], offset["offset_s"], lead_s=0, tail_s=0)
    _need(cut["cut_start_stem"] >= 0, "LIPSYNC_CUT_INVALID", "offset places cut before source")
    output = directory / "cut.wav"
    argv = ["ffmpeg", "-v", "error", "-y", "-threads", "4", "-ss", str(cut["cut_start_stem"]),
            "-i", str(source), "-t", str(cut["cut_dur"]), "-vn", "-c:a", "pcm_s16le", str(output)]
    record.update(state="cut_started", offset=offset, cut=cut, cut_argv=argv)
    _record(path, record)
    if cut_runner is None:
        from load_governor import run_ffmpeg
        cut_runner = run_ffmpeg
    cut_runner(argv, "lipsync-line-cut", check=True, timeout=300)
    _need(_sha(source) == source_hash and _sha(song) == song_hash and _selection(root, song) == selection,
          "LIPSYNC_SOURCE_CHANGED", "source changed while cutting")
    output = _path(root, str(output))
    _need(output.stat().st_size > 0, "LIPSYNC_CUT_INVALID", "cut output empty")
    record.update(state="complete", output_path=str(output), output_sha256=_sha(output))
    _record(path, record)
    return {"path": str(output), "speaker_id": row["speaker"], "kind": stem.get("kind"),
            "isolated": True, "line_ids": row["lip_sync_line_ids"],
            "start_s": row["start_s"], "end_s": row["end_s"], "lineage_path": str(path)}


def verify(run_dir, run_id, row, stem, song_path=None):
    """Replay immutable operation facts against files; never reconstruct a receipt."""
    root = Path(run_dir).resolve()
    path = _path(root, stem.get("lineage_path"))
    rec = _read(path)
    _need(rec.get("schema") == SCHEMA and rec.get("producer") == "audio_c3.lipsync_producer"
          and rec.get("producer_version") == VERSION and rec.get("state") == "complete" and rec.get("run_id") == run_id
          and rec.get("binding") == _binding(row), "LIPSYNC_LINEAGE_MISMATCH", "current producer lineage required")
    source = _path(root, rec.get("source_path"))
    _need(_selection(root, source) == rec.get("selection") and _sha(source) == rec.get("source_sha256"),
          "LIPSYNC_SELECTED_SONG_MISMATCH", "selected song changed")
    if song_path is not None:
        _need(source == _path(root, song_path), "LIPSYNC_SELECTED_SONG_MISMATCH", "export uses a different soundtrack")
    separated = _path(root, rec.get("separated_path"))
    output = _path(root, rec.get("output_path"))
    _need(_sha(separated) == rec.get("separated_sha256") and output == _path(root, stem.get("path"))
          and _sha(output) == rec.get("output_sha256"), "LIPSYNC_LINEAGE_MISMATCH", "separated/cut bytes changed")
    offset = rec.get("offset") or {}
    _need(_num(offset.get("offset_s")) and _num(offset.get("corr")), "LIPSYNC_OFFSET_MISSING", "measured offset missing")
    expected = cut_plan(row["start_s"], row["end_s"], offset["offset_s"], lead_s=0, tail_s=0)
    _need(rec.get("cut") == expected and expected["cut_start_stem"] >= 0,
          "LIPSYNC_LINEAGE_MISMATCH", "cut window/placement differs from approved timeline")
    expected_argv = ["ffmpeg", "-v", "error", "-y", "-threads", "4", "-ss", str(expected["cut_start_stem"]),
                     "-i", str(separated), "-t", str(expected["cut_dur"]), "-vn", "-c:a", "pcm_s16le", str(output)]
    _need(rec.get("cut_argv") == expected_argv and rec.get("speaker_id") == stem.get("speaker_id")
          and rec.get("isolated") is True, "LIPSYNC_LINEAGE_MISMATCH", "executed cut or speaker differs")
    separation = rec.get("separation") or {}
    ev = separation.get("evidence") or {}
    _need(separation.get("run_id") == run_id and separation.get("outcome") == "ok"
          and ev.get("task_id") and ev.get("generated") is True
          and separated in [_path(root, p) for p in ev.get("saved_paths", [])],
          "LIPSYNC_SEPARATION_FAILED", "separation task evidence missing")
    isolated = ev.get("isolated_stem") or {}
    req = rec.get("separation_request") or {}
    _need(separation.get("tool") == "kie_dispatch" and req.get("model") == MODEL
          and req.get("source_path") == str(source) and req.get("source_sha256") == _sha(source)
          and req.get("lipsync_binding") == _binding(row)
          and isolated.get("speaker_id") == rec.get("speaker_id") and isolated.get("isolated") is True
          and _path(root, isolated.get("path")) == separated,
          "LIPSYNC_SEPARATION_SOURCE_MISMATCH", "separation operation identity differs")
    _source_binding(root, ev, source, rec["source_sha256"])
    return {"path": str(path), "sha256": _sha(path), "source_sha256": _sha(source),
            "separation_task_id": ev["task_id"], "cut": expected}


def _source_binding(root, evidence, source, digest):
    binding = evidence.get("separation_source") or {}
    receipt = _read(_path(root, binding.get("upload_receipt_path")))
    _need(binding.get("path") == str(source) and binding.get("sha256") == digest
          and receipt == {"path": str(source), "sha256": digest, "url": binding.get("url")}
          and evidence.get("separation_input", {}).get("audio_url") == binding.get("url"),
          "LIPSYNC_SEPARATION_SOURCE_MISMATCH", "submitted separation audio is not selected song upload")


def skill74_runner(run_dir, source_uploader, dispatch_kwargs, isolated_stem_reader,
                   dispatch_fn=None):
    """Configured real dispatcher adapter; no operation occurs until called.

    source_uploader and isolated_stem_reader are existing runtime capabilities,
    never synthesized defaults. dispatch_kwargs supplies normal ledger, budget,
    attempt and adapter credentials through the dispatch API. Its menu/approval
    refusal is returned unchanged; this wrapper never bypasses those gates.
    """
    import shutil
    import tempfile
    root = Path(run_dir).resolve()
    _need(callable(source_uploader) and callable(isolated_stem_reader),
          "LIPSYNC_PROVIDER_MAPPING_MISSING", "source uploader and isolated-stem QC reader required")
    _need(not ({"model", "request", "save_dir", "run_id"} & set(dispatch_kwargs)),
          "LIPSYNC_PROVIDER_MAPPING_MISSING", "dispatcher identity cannot be overridden")
    def run(request):
        source = _path(root, request["source_path"])
        digest = _sha(source)
        _need(digest == request["source_sha256"], "LIPSYNC_SOURCE_CHANGED", "selected source changed")
        output_dir = Path(request["output_dir"]).resolve()
        _need(output_dir.is_relative_to(root), "LIPSYNC_FOREIGN_ARTIFACT", "output leaves run")
        with tempfile.TemporaryDirectory(dir=output_dir, prefix="source-upload-") as temp:
            copy = Path(temp) / source.name
            shutil.copyfile(source, copy)
            _need(_sha(copy) == digest, "LIPSYNC_SOURCE_CHANGED", "upload copy differs")
            url = source_uploader(str(copy))
            _need(_sha(copy) == digest and _sha(source) == digest,
                  "LIPSYNC_SOURCE_CHANGED", "upload changed selected bytes")
        _need(isinstance(url, str) and url.startswith("https://"),
              "LIPSYNC_PROVIDER_MAPPING_MISSING", "selected source upload needs HTTPS URL")
        upload = output_dir / "source-upload.json"
        with upload.open("x", encoding="utf-8") as f:
            json.dump({"path": str(source), "sha256": digest, "url": url}, f)
        inp = {"audio_url": url, "type": "separate_vocal", "stem_name": "Lead Vocal"}
        dispatch = dispatch_fn
        if dispatch is None:
            from kie_dispatch.kie_dispatch import dispatch
        result = dispatch(model=MODEL, request={"model": MODEL, "input": inp, "run_dir": str(root)},
                          save_dir=str(output_dir), run_id=request["run_id"], **dispatch_kwargs)
        if result.get("outcome") != "ok":
            return result
        evidence = result.setdefault("evidence", {})
        evidence["separation_input"] = inp
        evidence["separation_source"] = {"path": str(source), "sha256": digest,
                                          "url": url, "upload_receipt_path": str(upload)}
        evidence["isolated_stem"] = isolated_stem_reader(result)
        return result
    return run
