#!/usr/bin/env python3
"""Skill 72 audio policy (MG-023): mode resolution, mix policy, and
measured audio verification for the assembly layer.

MG-022 built the assembly plumbing and deliberately left policy here.
This module owns:

- Audio modes. The compiled timeline declares who owns the audio
  (`audio_owner`: none / parent / self in the canonical contract);
  the policy names for those owners are `none`, `inherited`, and
  `own`. Resolution happens ONCE, here, from the compiled plan plus
  the media registry, and produces the resolved audio plan the
  assembler consumes. Nothing downstream re-reads a manifest or a
  media registry to second-guess it (the D-ASSEMBLE-MUSIC-RESET
  defect was exactly such a re-read discarding a resolved score).

- Mode rules:
  * none: the deliverable is silent. Any placed narration or SFX, or
    a declared music bed, contradicts the mode and fails by name.
  * inherited: a parent program owns narration and music (VSL
    inserts). The insert itself must stay silent, so placed narration
    or SFX fails by name. A music bed carried in the job package is
    NOT mixed (that would add a second bed under the parent's); it is
    excluded and the exclusion is recorded in the resolved plan.
  * own: the job produces its own final mix. Narration comes from the
    compiled plan (MG-025's narration.json is its package source,
    placed by the MG-021 compiler), music is a supplied track or,
    optionally, a synthesized score (synthesis is an option, never
    the definition of quality), and SFX cues come from the plan. A
    declared loudness target applies because this mode, and only
    this mode, makes an independent final mix.

- Mix policy defaults: music volume 1.0 unless declared; ducking,
  when narration and music coexist and no ducking value is declared,
  defaults to the parameters the legacy bridge preserved
  (threshold 0.02, ratio 8, attack 20 ms, release 400 ms), keyed on
  the narration stem only (the signal-path rule MG-022 fixed). An
  explicit null declares no ducking.

- Loudness: own-mode mixes are finished with MEASURED loudnorm
  (measure the mix, apply with the measured values, then measure the
  encoded output and verify it). The default target is -14 LUFS
  integrated, -1 dBTP true peak, the values the legacy finish
  declared; verification tolerance is 1.0 LU / 0.5 dB.

- Verification measurements on the ENCODED output (not on requested
  filter settings): loudness within tolerance, no clipping, the
  final narration segment's tail actually present (missing final
  words), and the chosen score audible in narration-free sections.
  Source files are also clipping-checked when the plan is loaded: a
  clipped source fails by name instead of being laundered through
  loudness normalization.

Failure vocabulary (consumed by MG-034's QC rebuild; assemble.py
findings carry the Section 16.9 category alongside the local code):

  ASSEMBLE_AUDIO_MODE_VIOLATION     exit 4   MG_MODE_MISMATCH
  ASSEMBLE_AUDIO_CLIPPING           exit 6   MG_QC_FAILED
  ASSEMBLE_AUDIO_LOUDNESS_OFF_TARGET exit 6  MG_QC_FAILED
  ASSEMBLE_AUDIO_FINAL_WORDS_MISSING exit 6  MG_QC_FAILED
  ASSEMBLE_AUDIO_NARRATION_MISSING  exit 6   MG_QC_FAILED
  ASSEMBLE_AUDIO_SCORE_NOT_AUDIBLE  exit 6   MG_QC_FAILED

Exit codes keep assemble.py's established local mapping (4 plan,
6 output verification); the mg_category field carries the Section
16.9 class for the orchestrator, per Section 16.9's rule that
wrappers translate deliberately.

Measurement scale note: outputs of this skill are short-form
(seconds to a few minutes). Decoded-PCM checks load the decoded
program into memory as an int16 array; that is deliberate and
bounded by the skill's output shapes.
"""

import array
import json
import math
import os
import struct
import subprocess
import tempfile
import wave

SAMPLE_RATE = 48000

POLICY_VERSION = "mg023-1"

MODE_NONE = "none"
MODE_INHERITED = "inherited"
MODE_OWN = "own"
OWNER_TO_MODE = {"none": MODE_NONE, "parent": MODE_INHERITED, "self": MODE_OWN}

DEFAULT_MUSIC_VOLUME = 1.0
DEFAULT_DUCKING = {"threshold": 0.02, "ratio": 8, "attack": 20, "release": 400}
DEFAULT_LOUDNESS_TARGET = {"integratedLufs": -14.0, "truePeakDb": -1.0}
LOUDNORM_LRA = 11.0
LOUDNESS_TOLERANCE_LU = 1.0
TRUE_PEAK_TOLERANCE_DB = 0.5

# A sample at or above 99.9% of full scale counts as full-scale; a
# stream with more than 0.1% such samples is clipped, not just hot.
CLIP_PEAK_FRACTION = 0.999
CLIP_MAX_RATIO = 0.001
# The encoded output must never sit above this sample peak, however
# it got there.
OUTPUT_CLIP_CEILING_DBFS = -0.3
# Window energy at or below this is silence for QC purposes.
SILENCE_DBFS = -55.0
# A narration source tail above this counts as speech present.
PRESENCE_DBFS = -45.0
# The score check allows this much level slack under the expected
# (source level x declared volume) in a narration-free window.
SCORE_AUDIBLE_SLACK_DB = 18.0

EXIT_PLAN = 4
EXIT_VERIFY = 6


class AudioPolicyError(Exception):
    """A named audio-policy failure: stable code, Section 16.9
    category, and the local assemble.py exit code."""

    def __init__(self, code, message, exit_code, mg_category, **details):
        super().__init__(message)
        self.code = code
        self.message = message
        self.exit_code = exit_code
        self.mg_category = mg_category
        self.details = details

    def finding(self):
        out = {"status": "error", "code": self.code,
               "mg_category": self.mg_category, "message": self.message}
        if self.details:
            out["details"] = self.details
        return out


def mode_violation(message, **details):
    return AudioPolicyError("ASSEMBLE_AUDIO_MODE_VIOLATION", message,
                            EXIT_PLAN, "MG_MODE_MISMATCH", **details)


def qc_failure(code, message, **details):
    return AudioPolicyError(code, message, EXIT_VERIFY, "MG_QC_FAILED",
                            **details)


# --------------------------------------------------------------------
# Resolution: the compiled plan plus media registry in, one resolved
# audio plan out. Pure: no filesystem access, no synthesis. The
# assembler executes a "synthesized" music decision exactly once and
# records the produced path back into this plan before graph
# building; it never re-resolves.
# --------------------------------------------------------------------

def _declared(media, key):
    """A policy declaration may live in the media registry's `audio`
    record (the MG-023 policy record) or in its legacy `mix` record.
    The `audio` record wins. Returns (found, value)."""
    audio = media.get("audio") or {}
    if key in audio:
        return True, audio[key]
    mix = media.get("mix") or {}
    if key in mix:
        return True, mix[key]
    return False, None


def resolve_audio_plan(audio_owner, narration_ids, sfx_ids, media):
    if audio_owner not in OWNER_TO_MODE:
        raise mode_violation(
            "timeline declares audio_owner %r; expected one of %s"
            % (audio_owner, sorted(OWNER_TO_MODE)),
            audio_owner=audio_owner)
    mode = OWNER_TO_MODE[audio_owner]

    audio_rec = media.get("audio") or {}
    declared_mode = audio_rec.get("mode")
    if declared_mode is not None and declared_mode != mode:
        raise mode_violation(
            "media registry declares audio mode %r but the compiled "
            "timeline's audio_owner %r resolves to %r; the compiled "
            "plan is authoritative" % (declared_mode, audio_owner, mode),
            declared_mode=declared_mode, resolved_mode=mode)

    narration_ids = list(narration_ids)
    sfx_ids = list(sfx_ids)
    music_entry = media.get("music") or None

    plan = {
        "policyVersion": POLICY_VERSION,
        "mode": mode,
        "audioOwner": audio_owner,
        "narration": narration_ids,
        "sfx": sfx_ids,
        "music": None,
        "mix": {"musicVolume": DEFAULT_MUSIC_VOLUME, "ducking": None},
        "loudnessTarget": None,
        "exclusions": [],
    }

    if mode == MODE_NONE:
        offenders = []
        if narration_ids:
            offenders.append("narration %s" % narration_ids)
        if sfx_ids:
            offenders.append("sfx %s" % sfx_ids)
        if music_entry:
            offenders.append("a music bed")
        if offenders:
            raise mode_violation(
                "audio mode is none (silent deliverable) but the plan "
                "carries %s" % " and ".join(offenders),
                mode=mode, narration=narration_ids, sfx=sfx_ids,
                music=bool(music_entry))
        return plan

    if mode == MODE_INHERITED:
        if narration_ids or sfx_ids:
            raise mode_violation(
                "audio mode is inherited (the parent owns narration "
                "and music, so the insert is silent) but the compiled "
                "plan places %s"
                % " and ".join(x for x in (
                    "narration %s" % narration_ids if narration_ids else "",
                    "sfx %s" % sfx_ids if sfx_ids else "") if x),
                mode=mode, narration=narration_ids, sfx=sfx_ids)
        if music_entry:
            plan["exclusions"].append({
                "kind": "music",
                "code": "ASSEMBLE_AUDIO_PARENT_OWNED",
                "declaration": music_entry,
                "reason": "the parent owns the music bed; a bed "
                          "carried by the insert package is never "
                          "mixed in, so the parent soundtrack is not "
                          "duplicated",
            })
        plan["narration"] = []
        plan["sfx"] = []
        return plan

    # mode == own: the job makes an independent final mix.
    if music_entry:
        if "path" in music_entry:
            plan["music"] = {"kind": "supplied", "path": music_entry["path"]}
        elif "synthesized" in music_entry:
            synth = music_entry["synthesized"] or {}
            plan["music"] = {
                "kind": "synthesized",
                "bpm": float(synth.get("bpm", 120)),
                "seed": int(synth.get("seed", 7)),
                "path": None,
            }
        else:
            raise mode_violation(
                "media registry music entry must declare a supplied "
                "path or a synthesized score: %r" % (music_entry,),
                music=music_entry)

    found, volume = _declared(media, "musicVolume")
    if found:
        plan["mix"]["musicVolume"] = float(volume)
    found, ducking = _declared(media, "ducking")
    if found:
        plan["mix"]["ducking"] = ducking
    elif narration_ids and plan["music"]:
        plan["mix"]["ducking"] = dict(DEFAULT_DUCKING)

    if narration_ids or sfx_ids or plan["music"]:
        found, target = _declared(media, "loudnessTarget")
        if found and target:
            plan["loudnessTarget"] = {
                "integratedLufs": float(target["integratedLufs"]),
                "truePeakDb": float(target["truePeakDb"]),
            }
        else:
            plan["loudnessTarget"] = dict(DEFAULT_LOUDNESS_TARGET)
    return plan


# --------------------------------------------------------------------
# PCM measurement helpers (stdlib only, matching assemble.py).
# Decoded samples are mono int16 array('h') at SAMPLE_RATE.
# --------------------------------------------------------------------

def decode_pcm(ffmpeg, path, rate=SAMPLE_RATE):
    """Decode any audio file to mono int16 samples at `rate`."""
    fd, tmp = tempfile.mkstemp(prefix="mg023-pcm-", suffix=".wav")
    os.close(fd)
    try:
        proc = subprocess.run(
            [ffmpeg, "-v", "error", "-y", "-i", path, "-ac", "1",
             "-ar", str(rate), tmp], capture_output=True, text=True)
        if proc.returncode != 0:
            raise qc_failure(
                "ASSEMBLE_AUDIO_MEASUREMENT_FAILED",
                "could not decode %s for measurement: %s"
                % (path, proc.stderr[-500:]))
        with wave.open(tmp) as w:
            raw = w.readframes(w.getnframes())
        out = array.array("h")
        out.frombytes(raw[:len(raw) - (len(raw) % 2)])
        if struct.pack("=h", 1) != struct.pack("<h", 1):
            out.byteswap()
        return out
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def rms_dbfs(samples):
    if not samples:
        return -120.0
    total = 0.0
    for s in samples:
        total += float(s) * float(s)
    rms = math.sqrt(total / len(samples)) / 32768.0
    if rms <= 0.0:
        return -120.0
    return 20.0 * math.log10(rms)


def peak_dbfs(samples):
    peak = 0
    for s in samples:
        a = -s if s < 0 else s
        if a > peak:
            peak = a
    if peak == 0:
        return -120.0
    return 20.0 * math.log10(peak / 32768.0)


def clipping_report(samples):
    """Peak plus flat-top evidence. A hot-but-clean signal peaks near
    full scale on isolated samples; a clipped one sits there."""
    n = len(samples)
    if n == 0:
        return {"peakDbfs": -120.0, "fullScaleRatio": 0.0, "clipped": False}
    threshold = 32767.0 * CLIP_PEAK_FRACTION
    full = 0
    peak = 0
    for s in samples:
        a = -s if s < 0 else s
        if a > peak:
            peak = a
        if a >= threshold:
            full += 1
    ratio = full / n
    return {
        "peakDbfs": round(20.0 * math.log10(peak / 32768.0), 2) if peak else -120.0,
        "fullScaleRatio": round(ratio, 6),
        "clipped": bool(peak >= threshold and ratio > CLIP_MAX_RATIO),
    }


def window(samples, rate, t0, t1):
    a = max(0, int(t0 * rate))
    b = min(len(samples), int(t1 * rate))
    if b <= a:
        return array.array("h")
    return samples[a:b]


# --------------------------------------------------------------------
# Loudness: ffmpeg loudnorm measurement and measured application.
# --------------------------------------------------------------------

def measure_loudness(ffmpeg, path, target=None):
    """One loudnorm analysis pass. Returns the input measurements
    (integrated LUFS, true peak dBTP, LRA, threshold, offset)."""
    target = target or DEFAULT_LOUDNESS_TARGET
    filt = ("loudnorm=I=%.2f:TP=%.2f:LRA=%.2f:print_format=json"
            % (target["integratedLufs"], target["truePeakDb"], LOUDNORM_LRA))
    proc = subprocess.run([ffmpeg, "-v", "info", "-i", path, "-af", filt,
                           "-f", "null", "-"],
                          capture_output=True, text=True)
    text = proc.stderr
    start = text.rfind("{")
    end = text.rfind("}")
    if proc.returncode != 0 or start < 0 or end <= start:
        raise qc_failure("ASSEMBLE_AUDIO_MEASUREMENT_FAILED",
                         "loudnorm measurement failed on %s" % path,
                         stderr=text[-500:])
    data = json.loads(text[start:end + 1])
    return {
        "integratedLufs": float(data["input_i"]),
        "truePeakDb": float(data["input_tp"]),
        "lra": float(data["input_lra"]),
        "threshold": float(data["input_thresh"]),
        "offset": float(data["target_offset"]),
    }


def loudnorm_apply_filter(measured, target):
    """The second-pass filter: apply loudnorm with the MEASURED input
    values (linear mode), never just the requested settings."""
    return ("loudnorm=I=%.2f:TP=%.2f:LRA=%.2f:"
            "measured_I=%.2f:measured_TP=%.2f:measured_LRA=%.2f:"
            "measured_thresh=%.2f:offset=%.2f:linear=true"
            % (target["integratedLufs"], target["truePeakDb"], LOUDNORM_LRA,
               measured["integratedLufs"], measured["truePeakDb"],
               measured["lra"], measured["threshold"], measured["offset"]))


def loudness_verdict(measured, target):
    """Compare an encoded output's measurements with the target."""
    delta = measured["integratedLufs"] - target["integratedLufs"]
    peak_over = measured["truePeakDb"] - target["truePeakDb"]
    ok = (abs(delta) <= LOUDNESS_TOLERANCE_LU
          and peak_over <= TRUE_PEAK_TOLERANCE_DB)
    return {"ok": ok, "integratedDeltaLufs": round(delta, 2),
            "truePeakOverDb": round(peak_over, 2),
            "measured": measured, "target": target}


# --------------------------------------------------------------------
# Content checks on decoded output samples.
#
# Presence is proven by BAND energy, not broadband energy: a music
# bed under a narration window would mask a missing narration in a
# broadband measurement. For each narration window, the source
# segment's dominant spectral bands are found in the source itself,
# and the output must carry a real fraction of the source's energy
# in those same bands. Broadband figures are still recorded for
# transparency. (The tone-fixture case is exact under this method;
# for speech it is a stated heuristic: narration enters the mix at
# unity, so its dominant bands survive at a healthy fraction unless
# the segment was cut or never mixed.)
# --------------------------------------------------------------------

# Presence requires the energy-weighted dominant-band ratio
# (see _band_ratios) at or above this.
BAND_PRESENCE_RATIO = 0.25


def goertzel(samples, rate, freq):
    """Single-bin DFT magnitude, normalized per sample (the method
    MG-022's acceptance tooling proved on these fixtures when the
    exact tone frequency is known)."""
    n = len(samples)
    if n == 0:
        return 0.0
    k = 2 * math.pi * freq / rate
    coeff = 2 * math.cos(k)
    s1 = s2 = 0.0
    for x in samples:
        s0 = x + coeff * s1 - s2
        s2, s1 = s1, s0
    return math.sqrt(max(s1 * s1 + s2 * s2 - coeff * s1 * s2, 0.0)) / n


_FRAME = 2048
_HOP = 1024
_HANN_CACHE = {}


def _hann(n):
    win = _HANN_CACHE.get(n)
    if win is None:
        win = [0.5 - 0.5 * math.cos(2 * math.pi * i / (n - 1))
               for i in range(n)]
        _HANN_CACHE[n] = win
    return win


def band_amplitude(samples, rate, freq, frame=_FRAME, hop=_HOP):
    """Hann-windowed DFT magnitude at `freq`, averaged over frames,
    in int16 amplitude units (a pure tone of amplitude A reads about
    A at its own frequency).

    Windowing is not optional here: an unwindowed DFT over a long
    window puts a pure tone between grid frequencies into near-null
    bins (a 440 Hz tone over 2 s reads 240x low at the nearest
    third-octave grid point), which would make source/output band
    ratios meaningless. The Hann main lobe is wide enough that a
    tone registers consistently in the bands around it in any
    window of the same signal, which is what the ratios need."""
    n = len(samples)
    if n == 0:
        return 0.0
    k = 2 * math.pi * freq / rate
    coeff = 2 * math.cos(k)

    def frame_mag(seg, win):
        s1 = s2 = 0.0
        for x, w in zip(seg, win):
            s0 = x * w + coeff * s1 - s2
            s2, s1 = s1, s0
        mag = math.sqrt(max(s1 * s1 + s2 * s2 - coeff * s1 * s2, 0.0))
        return 2.0 * mag / max(sum(win), 1.0)

    if n <= frame:
        return frame_mag(samples, _hann(n))
    win = _hann(frame)
    total = 0.0
    count = 0
    start = 0
    while start + frame <= n:
        total += frame_mag(samples[start:start + frame], win)
        count += 1
        start += hop
    if start - hop + frame < n:  # tail frame anchored at the end
        total += frame_mag(samples[n - frame:n], win)
        count += 1
    return total / max(count, 1)


def dominant_bands(samples, rate, count=4):
    """The `count` strongest third-octave bands of a window, as
    [{freq, amplitude}] with amplitude in int16 units."""
    if not samples:
        return []
    freqs = []
    f = 100.0
    while f < min(4000.0, rate / 4.0):
        freqs.append(int(round(f)))
        f *= 2 ** (1 / 3.0)
    scored = [(band_amplitude(samples, rate, f), f) for f in freqs]
    scored.sort(reverse=True)
    return [{"freq": f, "amplitude": round(a, 1)}
            for a, f in scored[:count] if a > 0]


def _band_ratios(src_window, out_window, rate):
    """Per-band output/source ratios for the source's dominant
    bands, plus one aggregate: the energy-weighted ratio over the
    SIGNIFICANT bands (those carrying at least a tenth of the
    strongest band's amplitude).

    The significance floor is load-bearing. A pure tone's minor
    "dominant" bands are leakage floor (amplitudes of 1-20 int16
    units); codec noise in any real output exceeds that floor, so
    an unweighted median over all top bands reports a silent tail
    as present at ratios of 9-11x. Only bands that carry the
    source's actual energy may vote."""
    bands = dominant_bands(src_window, rate)
    for b in bands:
        out_amp = band_amplitude(out_window, rate, b["freq"])
        b["outputAmplitude"] = round(out_amp, 1)
        b["ratio"] = round(out_amp / b["amplitude"], 3) if b["amplitude"] else 0.0
    if not bands:
        return bands, 0.0
    floor = 0.1 * bands[0]["amplitude"]
    significant = [b for b in bands if b["amplitude"] >= floor]
    src_sum = sum(b["amplitude"] for b in significant)
    out_sum = sum(b["outputAmplitude"] for b in significant)
    aggregate = round(out_sum / src_sum, 3) if src_sum else 0.0
    return bands, aggregate


def segment_presence_report(out_samples, source_samples, seg_start,
                            seg_end, rate=SAMPLE_RATE):
    """A whole placed narration segment: present in the encoded
    output at its dominant bands, or it was never mixed (or was
    cut). The source window is the placed range of the source file
    (placement starts at the file's first sample)."""
    seg_len = seg_end - seg_start
    src = source_samples[0:seg_len]
    out = out_samples[seg_start:seg_end]
    src_rms = rms_dbfs(src)
    bands, ratio = _band_ratios(src, out, rate)
    source_present = src_rms > PRESENCE_DBFS
    return {
        "sourceRmsDbfs": round(src_rms, 2),
        "outputRmsDbfs": round(rms_dbfs(out), 2),
        "bands": bands,
        "bandRatio": ratio,
        "sourcePresent": source_present,
        "present": bool((not source_present) or ratio >= BAND_PRESENCE_RATIO),
    }


def narration_tail_report(out_samples, source_samples, seg_start,
                          seg_end, rate=SAMPLE_RATE, tail_seconds=0.3):
    """The final narration segment must still be there at its
    planned end: the last `tail_seconds` of the placed range,
    compared band by band against the source segment's own tail."""
    seg_len = seg_end - seg_start
    tail = min(int(tail_seconds * rate), seg_len)
    src_tail = source_samples[seg_len - tail:seg_len]
    out_tail = out_samples[seg_end - tail:seg_end]
    src_rms = rms_dbfs(src_tail)
    bands, ratio = _band_ratios(src_tail, out_tail, rate)
    source_present = src_rms > PRESENCE_DBFS
    return {
        "sourceTailRmsDbfs": round(src_rms, 2),
        "outputTailRmsDbfs": round(rms_dbfs(out_tail), 2),
        "bands": bands,
        "bandRatio": ratio,
        "sourcePresent": source_present,
        "presentAtPlannedEnd": bool(
            (not source_present) or ratio >= BAND_PRESENCE_RATIO),
    }


def longest_gap(windows, total_samples, min_seconds=0.3, rate=SAMPLE_RATE):
    """Longest sample window not covered by `windows` (sorted
    (start, end) sample ranges). Returns (start, end) or None."""
    gaps = []
    cursor = 0
    for start, end in sorted(windows):
        if start > cursor:
            gaps.append((cursor, start))
        cursor = max(cursor, end)
    if cursor < total_samples:
        gaps.append((cursor, total_samples))
    best = None
    for g in gaps:
        if g[1] - g[0] >= int(min_seconds * rate):
            if best is None or (g[1] - g[0]) > (best[1] - best[0]):
                best = g
    return best


def score_audibility_report(out_samples, narration_ranges, total_samples,
                            music_rms_dbfs, music_volume, rate=SAMPLE_RATE):
    """The chosen score must be audible where nothing else speaks:
    measure the longest narration-free window and compare it with
    the music source's own level scaled by the declared volume."""
    gap = longest_gap(narration_ranges, total_samples, rate=rate)
    if gap is None:
        return {"applicable": False,
                "reason": "no narration-free window of 0.3s or longer"}
    win = out_samples[gap[0]:gap[1]]
    measured = rms_dbfs(win)
    # A lone SFX burst inside the window must not fake a continuous
    # bed: the trailing quarter-second has to carry energy too.
    tail = win[-int(0.25 * rate):] if len(win) > int(0.25 * rate) else win
    tail_rms = rms_dbfs(tail)
    expected = music_rms_dbfs + (20.0 * math.log10(music_volume)
                                 if music_volume > 0 else -120.0)
    return {
        "applicable": True,
        "windowSeconds": [round(gap[0] / rate, 3), round(gap[1] / rate, 3)],
        "windowRmsDbfs": round(measured, 2),
        "windowTailRmsDbfs": round(tail_rms, 2),
        "expectedRmsDbfs": round(expected, 2),
        "audible": bool(measured > SILENCE_DBFS
                        and tail_rms > SILENCE_DBFS
                        and measured >= expected - SCORE_AUDIBLE_SLACK_DB),
    }
