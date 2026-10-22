"""budget_contingency — the ONE planning contingency (v3.0 plan section 8).

Baseline B = one planned successful execution of every required job at the
verified tariff, read from the shot/cue job manifest:

    Baseline B        = sum of the planned jobs priced at the verified tariff
    Contingency       = RATE x B          (a planning allowance, not a promise)
    Planning envelope = (1 + RATE) x B

The rate lives here and nowhere else. Rounding: Decimal ROUND_HALF_UP to the
cent, one rule for every caller.

A contingency is MEASURED only from a manifest that names its planned shots
and cues. Without one, ``measure``/``remeasure`` raise
``ContingencyUnmeasured`` (code ``CONTINGENCY_UNMEASURED``) and the caller
must surface "unmeasured"; nothing here falls back to a bare percentage.

Stdlib only.
"""
from decimal import Decimal, ROUND_HALF_UP

#: The requested planning allowance (v3.0 section 8). The only copy.
RATE = Decimal("0.50")
CODE = "CONTINGENCY_UNMEASURED"
BASIS = "shot-cue-manifest"


class ContingencyUnmeasured(ValueError):
    """No shot/cue manifest: the contingency cannot be computed."""

    def __init__(self, why):
        super().__init__("%s: %s" % (CODE, why))
        self.code = CODE


def percent():
    return int((RATE * 100).to_integral_value())


def label():
    return "%d%%" % percent()


def multiplier():
    """1 + RATE, for callers that scale by the envelope rather than add it."""
    return Decimal(1) + RATE


def _usd(value, what="baseline"):
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal, str)):
        raise ContingencyUnmeasured("%s must be a dollar amount, got %r"
                                    % (what, value))
    try:
        amount = Decimal(str(value))
    except Exception:                                     # noqa: BLE001
        raise ContingencyUnmeasured("%s is not a dollar amount: %r"
                                    % (what, value))
    if not amount.is_finite() or amount < 0:
        raise ContingencyUnmeasured("%s must be a finite, non-negative amount, "
                                    "got %r" % (what, value))
    return amount


def _minor(amount):
    """Dollar Decimal -> whole minor units, half-up (the one rounding rule)."""
    return int((amount * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def _rows(manifest, key):
    if not isinstance(manifest, dict):
        raise ContingencyUnmeasured("no shot/cue manifest (got %s)"
                                    % type(manifest).__name__)
    rows = manifest.get(key)
    if not isinstance(rows, (list, tuple)) or not rows:
        raise ContingencyUnmeasured("manifest names no %s" % key)
    return rows


def _count(manifest):
    """(shots, cues) after validating every planned job and cue."""
    shots = _rows(manifest, "shots")
    for i, shot in enumerate(shots):
        if not isinstance(shot, dict):
            raise ContingencyUnmeasured("shot %d is not a record" % (i + 1))
        if not isinstance(shot.get("shot_id"), str) or not shot["shot_id"]:
            raise ContingencyUnmeasured("shot %d has no shot_id" % (i + 1))
        seconds = shot.get("seconds")
        if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) \
                or seconds <= 0:
            raise ContingencyUnmeasured("shot %s has no planned seconds"
                                        % shot["shot_id"])
    cues = _rows(manifest, "cues")
    for i, cue in enumerate(cues):
        if not isinstance(cue, dict) or not isinstance(cue.get("cue_id"), str) \
                or not cue["cue_id"]:
            raise ContingencyUnmeasured("cue %d has no cue_id" % (i + 1))
    return len(shots), len(cues)


def _result(shots, cues, baseline_usd, projected):
    baseline = _usd(baseline_usd)
    base_minor = _minor(baseline)
    contingency_minor = _minor(baseline * RATE)
    return {
        "basis": BASIS,
        "rate": float(RATE),
        "percent": percent(),
        "label": "%s planning allowance" % label(),
        "shots": shots,
        "cues": cues,
        "baseline_usd": base_minor / 100.0,
        "contingency_usd": contingency_minor / 100.0,
        "envelope_usd": (base_minor + contingency_minor) / 100.0,
        "projected": bool(projected),
    }


def measure(manifest, baseline_usd):
    """Measured contingency + envelope for a manifest-priced baseline."""
    shots, cues = _count(manifest)
    return _result(shots, cues, baseline_usd, manifest.get("projected"))


def remeasure(measured, baseline_usd):
    """Carry a measured manifest onto a new baseline (extra lines, batch sum).

    Raises ContingencyUnmeasured when there is no measured basis to carry.
    """
    if not isinstance(measured, dict) or measured.get("basis") != BASIS:
        raise ContingencyUnmeasured("no measured shot/cue manifest to carry "
                                    "forward")
    shots, cues = measured.get("shots"), measured.get("cues")
    for name, value in (("shots", shots), ("cues", cues)):
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ContingencyUnmeasured("measured manifest names no %s" % name)
    return _result(shots, cues, baseline_usd, measured.get("projected"))


def contingency(baseline_usd):
    """RATE x an already manifest-measured baseline, half-up to the cent."""
    return _minor(_usd(baseline_usd) * RATE) / 100.0


def envelope(baseline_usd):
    """Planning envelope for an already manifest-measured baseline."""
    amount = _usd(baseline_usd)
    return (_minor(amount) + _minor(amount * RATE)) / 100.0
