"""beat_sheet.singer: the right singer and the sung hook (N-65).

Plan 3F.2. Two checks on the joined story script against the Voice Map:

  * **The right singer.** On a lip-sync line, the character on camera is the
    character the lyric sheet says sings those words. The Voice Map says, for
    each stretch of the song, who is singing, and so who may be shown singing
    it. A row whose singer is not the voice the map names for that stretch
    fails ``WRONG_SINGER`` (3J MAJOR item 8). Where the map is absent the check
    fails closed with ``VOICE_MAP_MISSING`` (item 15).
  * **The hook is sung.** Every line of the hook has an open-mouthed singing
    shot or a lip-sync row of the people singing it. ``HOOK_NOT_SUNG`` (item 9).

Nothing is inferred from a name's resemblance: a voice is matched by id only.

Stdlib only; data in, verdicts out; no model call, no write.
"""
from __future__ import annotations

from ._util import finding, norm, num, rows

#: where a hook line list may live in the song record
HOOK_FIELDS = ("hook_lines", "hook")


def _map_stretches(voice_map):
    """Voice Map entries: [{"start_s", "end_s", "voice_id"/"singer"}]."""
    if not isinstance(voice_map, dict):
        return None
    data = voice_map.get("stretches") or voice_map.get("segments")
    if not isinstance(data, list):
        return None
    out = []
    for entry in data:
        if not isinstance(entry, dict):
            return None
        start, end = num(entry.get("start_s")), num(entry.get("end_s"))
        voice = entry.get("voice_id") or entry.get("singer") or entry.get("who_sings")
        if start is None or end is None or not voice:
            return None
        out.append({"start_s": start, "end_s": end, "voice_id": voice})
    return out


def _voice_at(stretches, start, end):
    """The voices the map names across [start, end); None when no stretch holds."""
    mid = (start + end) / 2.0
    hits = [s["voice_id"] for s in stretches if s["start_s"] <= mid < s["end_s"]]
    if not hits:
        hits = [s["voice_id"] for s in stretches
                if s["end_s"] > start and s["start_s"] < end]
    return hits


def _is_lip_sync(row):
    if row.get("lip_sync") is True:
        return True
    return norm(row.get("lip_sync")) in ("yes", "true", "lip-sync", "lipsync")


def singer_defects(script, voice_map=None, lyric_sheet=None):
    """Every lip-sync row sings the words its own voice sings (N-65)."""
    stretches = _map_stretches(voice_map)
    if stretches is None:
        return [finding("VOICE_MAP_MISSING", "/voice-map",
                        "no Voice Map: every lip-sync row needs one to prove the singer")]
    voices = {}
    if isinstance(lyric_sheet, dict):
        for line in lyric_sheet.get("lines") or []:
            if isinstance(line, dict) and line.get("line_id"):
                voices[line["line_id"]] = line.get("voice_id")

    out = []
    for index, row in enumerate(rows(script)):
        if not _is_lip_sync(row):
            continue
        start, end = num(row.get("start_s")), num(row.get("end_s"))
        if start is None or end is None or end <= start:
            continue
        expected = _voice_at(stretches, start, end)
        if not expected:
            out.append(finding("VOICE_MAP_INCOMPLETE", "/voice-map",
                               "no stretch covers %.3f to %.3f s" % (start, end),
                               row=index))
            continue
        on_camera = norm(row.get("who_sings") or row.get("singer"))
        named = voices.get(row.get("line_id")) if voices else None
        if named and norm(named) != on_camera:
            out.append(finding("WRONG_SINGER", "/rows/%d/who_sings" % index,
                               "the lyric sheet says %r sings this line, not %r"
                               % (named, row.get("who_sings")), row=index))
            continue
        if on_camera and on_camera not in [norm(v) for v in expected]:
            out.append(finding("WRONG_SINGER", "/rows/%d/who_sings" % index,
                               "the Voice Map names %s on this stretch, not %r"
                               % (sorted(expected), row.get("who_sings")), row=index))
    return out


def hook_defects(script, hook_lines):
    """Every hook line is shown being sung (N-65)."""
    out = []
    rows_all = rows(script)
    for hook in hook_lines or []:
        text = hook.get("text") if isinstance(hook, dict) else hook
        line_id = hook.get("line_id") if isinstance(hook, dict) else None
        if not (isinstance(text, str) and text.strip()) and not line_id:
            continue
        shown = False
        for row in rows_all:
            if line_id:
                matches = row.get("line_id") == line_id
            else:
                matches = isinstance(text, str) and \
                    (row.get("text") or "").strip() == text.strip()
            if not matches:
                continue
            if _is_lip_sync(row) and (row.get("singing") or row.get("who_sings")):
                shown = True
                break
        if not shown:
            out.append(finding("HOOK_NOT_SUNG", "/rows",
                               "the hook line %r has no lip-sync row of the people "
                               "singing it" % (text or line_id), line_id=line_id))
    return out


def check_singer(script, voice_map=None, lyric_sheet=None, hook_lines=None):
    """Result envelope for the singer and hook checks (N-65)."""
    defects = singer_defects(script, voice_map=voice_map, lyric_sheet=lyric_sheet)
    defects.extend(hook_defects(script, hook_lines))
    return {"ok": not any(d.get("level") == "MAJOR" for d in defects),
            "defects": defects}


def _selfcheck():
    script = {"rows": [
        {"row_id": "r1", "line_id": "l1", "beat_number": 1, "start_s": 0.0,
         "end_s": 4.0, "who_sings": "lead", "singing": ["lead"], "lip_sync": True},
        {"row_id": "r2", "line_id": "l2", "beat_number": 1, "start_s": 4.0,
         "end_s": 8.0, "who_sings": "lead", "singing": ["lead"], "lip_sync": True},
    ]}
    voice_map = {"stretches": [
        {"start_s": 0.0, "end_s": 4.0, "voice_id": "lead"},
        {"start_s": 4.0, "end_s": 8.0, "voice_id": "choir"}]}
    assert check_singer(script, voice_map=voice_map)["ok"] is False
    codes = [d["code"] for d in check_singer(script, voice_map=voice_map)["defects"]]
    assert codes == ["WRONG_SINGER"], codes
    assert [d["code"] for d in check_singer(script)["defects"]] == ["VOICE_MAP_MISSING"]
    only_first = {"rows": [script["rows"][0]]}
    assert check_singer(only_first, voice_map=voice_map, hook_lines=["l2"])["ok"] is False


if __name__ == "__main__":
    _selfcheck()
    print("beat_sheet.singer selfcheck: OK")
