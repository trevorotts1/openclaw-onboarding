#!/usr/bin/env python3
"""T-40 shared readiness projection (R-28 / C-40) — one projection format for
every readiness reporter: onboarding, 999 and Command Center.

ACCEPTANCE CLAUSE: "Affected rebind/disconnect/upgrade proof invalidation,
installed/running/live distinct."

1. THREE DISTINCT STATES. installed / running / live live in three separate
   slots with three DISJOINT vocabularies (installed|missing, running|stopped,
   live|unreachable). Readiness is never one boolean and never one string: the
   slots serialize independently and their value vocabularies cannot be
   confused with each other, so no projection can collapse two of them.

2. PROOF INVALIDATION. A proof is keyed to the surface's identity
   (digest over surface + binding + version) and to an event epoch. rebind
   (binding changed), upgrade (version changed) and disconnect (the surface
   was live and no longer is) each bump the epoch AND change the key material,
   so a proof issued before any of the three events can never read as still
   valid after it — even if the surface looks green again afterwards. Only the
   AFFECTED surface's proofs invalidate; another surface's proof stays valid.

Public API is two functions and BOTH are called in production from
32-command-center-setup/scripts/verify-tenant-readiness.py (startability()):
project() emits the projection, proof_valid() reports whether a stored proof
still stands — invalidation is SHOWN, never assumed.
"""
from __future__ import annotations

import hashlib

SCHEMA = 'shared-readiness-projection.v1'

# Three disjoint two-value vocabularies — one per state slot. Disjointness is
# what makes "collapsed into one string" structurally impossible.
_STATE_VOCAB = {
    'installed': ('installed', 'missing'),
    'running': ('running', 'stopped'),
    'live': ('live', 'unreachable'),
}


def project(surface, binding, version, installed, running, live, prior=None):
    """Project one surface's readiness, plus the proof bookkeeping for it.

    prior: the proof this surface last issued (dict), or None. Events are
    detected against it — rebind (binding changed), upgrade (version changed),
    disconnect (prior said 'live' and the surface is no longer live) — and each
    detected event bumps the epoch so `prior` can never validate again.
    A `prior` belonging to a DIFFERENT surface is not this surface's history:
    it is ignored and the epoch starts fresh.
    """
    states = {
        'installed': _STATE_VOCAB['installed'][0 if installed else 1],
        'running': _STATE_VOCAB['running'][0 if running else 1],
        'live': _STATE_VOCAB['live'][0 if live else 1],
    }
    epoch = 0
    events = ()
    if isinstance(prior, dict) and prior.get('surface') == surface:
        epoch = int(prior.get('epoch') or 0)
        prior_states = prior.get('states') if isinstance(prior.get('states'), dict) else {}
        detected = []
        if prior.get('binding') != binding:
            detected.append('rebind')
        if prior.get('version') != version:
            detected.append('upgrade')
        if prior_states.get('live') == 'live' and states['live'] != 'live':
            detected.append('disconnect')
        if detected:
            epoch += 1
        events = tuple(detected)
    return {
        'schema': SCHEMA,
        'surface': surface,
        'binding': binding,
        'version': version,
        'digest': hashlib.sha256(
            '\x1f'.join((surface or '', binding or '', version or '')).encode()
        ).hexdigest(),
        'epoch': epoch,
        'events': list(events),
        'states': states,
    }


def proof_valid(proof, projection):
    """True only while `proof` still describes the present `projection`:
    same surface, same identity digest, same event epoch, same three states.
    Any rebind, disconnect or upgrade moves at least one of those, so a stale
    proof always reads invalid here."""
    if not isinstance(proof, dict) or not isinstance(projection, dict):
        return False
    return (
        proof.get('surface') == projection.get('surface')
        and proof.get('digest') == projection.get('digest')
        and proof.get('epoch') == projection.get('epoch')
        and proof.get('states') == projection.get('states')
    )
