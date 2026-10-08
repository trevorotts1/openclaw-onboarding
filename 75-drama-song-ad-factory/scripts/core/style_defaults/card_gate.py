"""card_gate.py -- Part F F15 (Critical, owner order 2026-10-08): the four
choices are always asked before launch, in plain words.

One choice card, four picks -- video style, audio style, length, video
model -- each pick explained with ONE plain fifth-grade sentence and a
RECOMMENDED pick the person can change. No run (direct, Social Media
Planner, or an operator/agent launching from a brief) starts any paid job
until the card has been shown and its answers recorded. A brief can
pre-fill the RECOMMENDED picks; it can never skip the card.

What this module owns and nothing else:

* the fail-closed gate:
    - ``answers_recorded(card)`` -> ``(True, None)`` when all four answers
      are recorded, else ``(None, refusal)`` with reason ``CARD_UNANSWERED``
      naming the missing fields;
    - ``answered_stamped(card, who, when_utc)`` -> the receipt block
      ``{answers, who, at}`` with ``at`` stamped in UTC;
    - ``gate_run_state(run_state)`` -- the dispatch-side entry point exposed
      for the W-F-U16 wiring.
* the card's pick renderers (one plain sentence per pick, RECOMMENDED
  markers), including the video-model menu parsed from
  ``references/price-menu.md``;
* the length menu read through ``defaults`` (2 minutes added by F15 between
  90 s and 3 minutes).

Wiring note for W-F-U16: ``kie_dispatch.dispatch()`` takes an explicit
``run_id``/``ledger_db`` and reads the spend ledger only -- it has no run
state handle today, so dispatch cannot run this gate itself. The gate runs
where a run starts instead: ``intake_preflight.intake.evaluate`` pauses
complete/resumed briefs with reason ``CARD_UNANSWERED`` and
``intake_preflight.preflight.check`` rejects any paid-work check whose run
state lacks the recorded card receipt. ``gate_run_state`` stays exposed so
the W-F-U16 state-store wiring can call the same refusal.

Directive 24.3 conflict resolved (owner order 2026-10-08): the card is one
step with four picks, so the three-question cap applies to the story
questions only; the card is never skipped and never counted against the cap.

stdlib only: no network, no provider, no paid call, no file writes. The
price-menu parser reads the repo snapshot only when no live Skill 74 prices
are handed in -- the live card still reads Skill 74 ``price``.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from . import defaults as D

TOOL_NAME = "card_gate"
TOOL_VERSION = "1.0.0"
SCHEMA_VERSION = "blackceo.card-gate/v1"

#: The four choices, verbatim from F15. One card, four picks.
CARD_REQUIRED_FIELDS = ("video_style", "audio_style", "length", "video_model")

#: The fail-closed reason code every refusal here carries.
CARD_UNANSWERED = "CARD_UNANSWERED"

#: The RECOMMENDED pick per field (D24 style/music, decision 32 length,
#: decision 5 video model). Every pick can be changed on the card.
RECOMMENDED = {
    "video_style": "Lifelike 3D",
    "audio_style": "Soul Ballad",
    "length": "60 seconds",
    "video_model": "MiniMax H3 768P",
}

CARD_NEXT_ACTION = ("Show the choice card (one card, four picks) and record "
                    "all four answers, with who and when, in the run state "
                    "before any paid job; no paid job starts until then.")

#: The length-menu note the owner ordered, F15.
LENGTH_MENU_NOTE = "2 minutes is new, added by F15 (owner order 2026-10-08)."


class CardGateError(Exception):
    """A refusal this gate owns: answers missing or a bad stamp."""

    def __init__(self, code, message):
        super().__init__("%s: %s" % (code, message))
        self.code = code


# ------------------------------------------------------------ gate -----------

#: What an answer value may still be while meaning "not answered".
_REFUSAL_WORDS = frozenset(("", "none", "no choice", "nochoice", "unanswered",
                            "skip", "default"))

_VIDEO_MODEL_RECOMMENDED_PREFIX = "MiniMax H3"


def _unanswered(value):
    """True when the value cannot count as a recorded answer.

    Fail-closed: None, blank text, the plain refusal spellings, empty
    containers and bools are all "not answered"; a real pick is a non-empty
    string (or a number, e.g. length 120).
    """
    if value is None or isinstance(value, bool):
        return True
    if isinstance(value, str):
        return value.strip().lower() in _REFUSAL_WORDS
    if isinstance(value, (int, float)):
        return False
    if isinstance(value, dict):
        return not value
    return False


def card_answers(card):
    """The answers dict the card record carries, or None.

    Accepts the stamped receipt (``{"answers": {...}, "who": ..., "at":
    ...}``) or a plain record holding the four fields at its top level. A
    brief is never a card: intake brief fields that merely pre-fill the
    RECOMMENDED picks never reach this gate -- only the card's recorded
    answer record satisfies it.
    """
    if not isinstance(card, dict):
        return None
    for key in ("answers", "card_answers"):
        inner = card.get(key)
        if isinstance(inner, dict):
            return inner
    return card


def missing_fields(card):
    """The CARD_REQUIRED_FIELDS not recorded on the card record, in order."""
    answers = card_answers(card)
    return [f for f in CARD_REQUIRED_FIELDS
            if answers is None or _unanswered(answers.get(f))]


def answers_recorded(card):
    """-> ``(True, None)`` when all four answers are recorded, else
    ``(None, refusal)`` with reason ``CARD_UNANSWERED`` listing the missing
    fields. Fail-closed: nothing but a complete record counts.
    """
    missing = missing_fields(card)
    if missing:
        return None, {
            "reason_code": CARD_UNANSWERED,
            "missing": missing,
            "next_action": CARD_NEXT_ACTION,
        }
    return True, None


def _at_utc(when_utc):
    """-> 'YYYY-MM-DDTHH:MM:SSZ'. Naive datetimes and blank-zone text are
    taken as UTC; aware values convert to UTC."""
    if isinstance(when_utc, (int, float)) and not isinstance(when_utc, bool):
        dt = datetime.fromtimestamp(when_utc, tz=timezone.utc)
        return dt.replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")
    if isinstance(when_utc, datetime):
        dt = (when_utc if when_utc.tzinfo is not None
              else when_utc.replace(tzinfo=timezone.utc))
        return dt.astimezone(timezone.utc).replace(
            microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")
    if isinstance(when_utc, str) and when_utc.strip():
        text = when_utc.strip()
        if text.upper().endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            raise CardGateError(
                "CARD_STAMP_INVALID",
                "when_utc text %r is not an ISO timestamp" % when_utc) from None
        dt = (dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None
              else dt.astimezone(timezone.utc))
        return dt.replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")
    raise CardGateError(
        "CARD_STAMP_INVALID",
        "when_utc must be a datetime, epoch seconds or ISO text, got %r"
        % (when_utc,))


def answered_stamped(card, who, when_utc):
    """-> the receipt block ``{answers, who, at}`; ``at`` is stamped in UTC.

    Refuses (``CARD_UNANSWERED``) when the card lacks any of the four
    answers, and refuses a blank ``who`` or an unstampable ``when_utc``
    (``CARD_STAMP_INVALID``) -- a stamp proves who answered and when.
    """
    ok, refusal = answers_recorded(card)
    if not ok:
        raise CardGateError(
            refusal["reason_code"],
            "missing card answers: %s" % ", ".join(refusal["missing"]))
    if not isinstance(who, str) or not who.strip():
        raise CardGateError("CARD_STAMP_INVALID", "who must name the answerer")
    return {"answers": dict(card_answers(card)), "who": who.strip(),
            "at": _at_utc(when_utc)}


def gate_run_state(run_state, card_receipt=None):
    """The dispatch-side gate, exposed for the W-F-U16 wiring.

    kie_dispatch.dispatch() has no run-state handle today (explicit
    run_id/ledger_db only), so whoever holds the run state calls this
    before any paid job and refuses on ``CARD_UNANSWERED``. The run state
    itself (or its recorded card receipt under ``card_receipt``) is what
    the gate reads. Returns ``(True, None)`` or ``(None, refusal)``.
    """
    record = card_receipt if card_receipt is not None else run_state
    return answers_recorded(record if isinstance(record, dict) else None)


# ------------------------------------------------------------ card -------- --

def _plain(text):
    """One plain sentence: strip, keep the author's words, end with a full
    stop. The look/music descriptions are already fifth-grade; no rewrite,
    no invented sentences (F6: no invented anything)."""
    text = re.sub(r"\s+", " ", str(text)).strip()
    if not text:
        return text
    return text if text.endswith(".") else text + "."


def video_style_picks():
    """One plain sentence per look; Lifelike 3D marked RECOMMENDED (D24)."""
    lines = []
    for lid in D.LOOKS.LOOK_ORDER:
        label = D.LOOKS.LOOK_LABELS[lid]
        desc = D.LOOKS.LOOK_DESCRIPTIONS[lid]
        mark = " (RECOMMENDED)" if lid == D.LOOKS.DEFAULT_LOOK_ID else ""
        lines.append("%s%s = %s" % (label, mark, _plain(desc)))
    return lines


def audio_style_picks():
    """One plain sentence per music style; Soul Ballad marked RECOMMENDED
    (D24). The sentences are the D18 style table's own 'sound' lines --
    e.g. Soul Rise = starts slow and soulful through the pain, lifts into
    an upbeat groove at the turning point."""
    lines = []
    for sid in D.MUSIC_STYLES.style_ids():
        style = D.MUSIC_STYLES.style(sid)
        label = style["label"]
        desc = style.get("sound") or style.get("notes") or ""
        mark = " (RECOMMENDED)" if sid == D.DEFAULT_MUSIC_STYLE else ""
        lines.append("%s%s = %s" % (label, mark, _plain(desc)))
    return lines


def length_picks():
    """Length menu from defaults (F15: 120 s between 90 s and 180 s) with
    60 s marked RECOMMENDED and the owner's F15 note on the 2-minute line."""
    lines = []
    for secs in D.LENGTH_OPTIONS_S:
        label = D.LENGTH_LABELS_S[secs]
        if secs == D.RECOMMENDED_LENGTH_S:
            lines.append("%s (RECOMMENDED) = %d seconds." % (label, secs))
        elif secs == 120:
            lines.append("%s = %d seconds (%s)." % (label, secs, LENGTH_MENU_NOTE))
        else:
            lines.append("%s = %d seconds." % (label, secs))
    lines.append("Each length is its own song and timing map, never a "
                 "cut-down of a longer one.")
    return lines


# --------------------------------------------------- price-menu snapshot -----

def _price_menu_path():
    """references/price-menu.md of this skill, or None (never a hard-coded
    user path; walk up from this module like kie_dispatch does)."""
    start = Path(__file__).resolve()
    for parent in (start, *start.parents):
        cand = parent / "references" / "price-menu.md"
        if cand.is_file():
            return cand
    return None


def _clean_model(cell):
    """"MiniMax H3 **(CHEAPEST)**" -> ("MiniMax H3", "(CHEAPEST)"/None)."""
    note = None
    m = re.search(r"\*\*\(?(CHEAPEST|PREMIUM)\)?\*\*", cell)
    if m:
        note = "(%s)" % m.group(1)
    clean = cell.replace("**", "")
    clean = re.sub(r"\s*\((?:CHEAPEST|PREMIUM)\)\s*", " ", clean).strip()
    return re.sub(r"\s+", " ", clean), note


def _num(cell):
    m = re.search(r"\$?(\d+(?:\.\d+)?)", str(cell))
    return float(m.group(1)) if m else None


_LENGTH_HEADING_RE = re.compile(r"^(\d+ (?:minutes|seconds)[^(]*)")
_RATES_HEADING = "Rates used"


def parse_price_menu(text=None):
    """Every length table in price-menu.md -> {section: [rows]}, plus
    {"rates": {model: row}} from the "Rates used" table. Snapshot data,
    parsed only: no rate is invented here (F6), and the live card still
    reads Skill 74 ``price`` first."""
    if text is None:
        path = _price_menu_path()
        if not path:
            return {}
        text = path.read_text(encoding="utf-8")

    tables, rates, section = {}, {}, None
    for line in text.splitlines():
        stripped = line.strip()
        m = re.match(r"^### (.+)$", stripped)
        if m:
            section = m.group(1).strip()
            continue
        if not stripped.startswith("|") or section is None:
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if len(cells) < 2 or cells[0].startswith("Model") or set(cells[0]) <= {"-"}:
            continue                          # header / separator row
        lm = _LENGTH_HEADING_RE.match(section)
        if lm and len(cells) >= 6:            # Model|Res|Shots|One|Both|Retakes
            model, note = _clean_model(cells[0])
            tables.setdefault(lm.group(1).strip(), []).append({
                "model": model, "note": note,
                "resolution": cells[1], "shots": _num(cells[2]),
                "one_shape": _num(cells[3]), "both_shapes": _num(cells[4]),
                "retakes": _num(cells[5]),
            })
            continue
        if section.startswith(_RATES_HEADING) and len(cells) >= 5:
            name = cells[0].replace("**", "").strip()
            base = re.split(r"\s*\(", name, maxsplit=1)[0].strip()
            rates[base] = {"model": base, "low": cells[1], "high": cells[2],
                           "max_clip": cells[3], "native": cells[4]}
    tables["rates"] = rates
    return tables


def _res_class(resolution):
    """'low' or 'high': which published rate column the row's resolution
    bills at. '720p and 1080p (same price)' bills at the low column."""
    low = resolution.lower()
    if low.startswith("720") or low.startswith("768") or "same price" in low:
        return "low"
    if low.startswith("1080") or low.startswith("2k"):
        return "high"
    return "low"


#: One-sentence "what you get" per approved model row, built from the rate
#: table's own wording -- nothing is invented here (F6).
def _model_sentence(row, rates):
    rate = rates.get(row["model"]) or {}
    cell = rate.get(_res_class(row["resolution"])) or "rate not in menu"
    parts = ["one shape $%.2f" % row["one_shape"],
             "both shapes $%.2f" % row["both_shapes"],
             "+20%% retakes +$%.2f on one shape" % row["retakes"],
             "rate %s" % cell,
             "max clip %s" % rate.get("max_clip", "n/a")]
    marks = "".join(" %s" % row["note"] for m in (row["note"],) if m)
    marks += " (RECOMMENDED)" if _is_recommended_model(row) else ""
    return "%s%s at %s: %s." % (row["model"], marks, row["resolution"],
                                "; ".join(parts))


def _is_recommended_model(row):
    return (row["model"].startswith(_VIDEO_MODEL_RECOMMENDED_PREFIX)
            and _res_class(row["resolution"]) == "low")


def video_model_picks(length_label="60 seconds", prices=None):
    """Video-model menu lines for the card: MiniMax H3 768P RECOMMENDED with
    every other approved model, its price and one plain sentence each.

    ``prices``: a dict from ``parse_price_menu`` (or live Skill 74 data in
    the same shape); when None the repo snapshot is parsed. Order follows
    the menu's own tables, so the RECOMMENDED default is the decision-5
    pick and the CHEAPEST/PREMIUM markers travel with their rows.
    """
    data = prices if isinstance(prices, dict) and prices else parse_price_menu()
    if not data:
        return ["Video model: the price snapshot is unavailable and the live "
                "Skill 74 price did not answer; the card says the price is "
                "unavailable and no paid work starts."]
    rows = data.get(length_label) or []
    rates = data.get("rates") or {}
    return [_model_sentence(r, rates) for r in rows]


def render_card(length_label="60 seconds", prices=None):
    """The four picks as one card: every pick a one-line plain sentence with
    its RECOMMENDED marker, plus the Directive 24.3 note."""
    return {
        "video_style": video_style_picks(),
        "audio_style": audio_style_picks(),
        "length": length_picks(),
        "video_model": video_model_picks(length_label=length_label,
                                         prices=prices),
        "note": ("One card, four picks; every RECOMMENDED pick can be "
                 "changed. A brief may pre-fill the RECOMMENDED picks but "
                 "never skips the card. Directive 24.3's three-question cap "
                 "applies to the story questions only; it does not count "
                 "this card (owner order 2026-10-08)."),
    }