"""Verify delivery against a gateway registry or a previously observed exact receipt.

A retained receipt proves a historical send after the gateway's rolling registry
expires. An unverified message ID, old success flag, or changed artifact cannot.
"""
from __future__ import annotations
import hashlib
import json
import math
import os
from pathlib import Path
import sys
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / '23-ai-workforce-blueprint' / 'scripts'))
from workforce_state import read, update
from workforce_completion import closeout_artifact_digest
from gateway_sqlite_receipts import SQLiteReceipts, AUTHORITY as SQLITE_AUTHORITY

def verify(path, registry_path, required, sqlite_path=None, session_store=None):
    snapshot = read(path)
    digest = closeout_artifact_digest(snapshot)
    build = snapshot.get('buildId')
    chat = str(snapshot.get('ownerChat') or '')
    now = datetime.now(timezone.utc).isoformat()
    registry = None
    try:
        parsed = json.loads(Path(registry_path).read_text())
        if isinstance(parsed, dict): registry = parsed
    except (OSError, ValueError): pass
    sqlite = SQLiteReceipts(sqlite_path or os.environ.get('ZHC_TG_STATE_DB'),session_store or os.environ.get('ZHC_TG_SESSION_STORE'))
    used_authorities=set()
    retained = snapshot.get('telegramDeliveryReceipts') or {}
    if not isinstance(retained, dict): retained = {}
    captured = snapshot.get('messagesDelivered') or []
    results, additions = [], {}
    rc = 0
    slots = set(required) | {r.get('n') for r in captured if isinstance(r, dict) and isinstance(r.get('n'), int)}
    for slot in sorted(slots):
        record = next((r for r in captured if isinstance(r, dict) and r.get('n') == slot), {})
        mid = str(record.get('messageId') or '')
        valid = bool(build and chat and mid and str(record.get('chatId') or '') == chat and record.get('status') != 'send-failed')
        identity = {'buildId': build, 'artifactDigest': digest, 'ownerChat': chat, 'messageId': mid, 'slot': slot}
        key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
        old = retained.get(key) or {}
        timestamp = ((registry or {}).get(chat) or {}).get(mid) if isinstance((registry or {}).get(chat), dict) else None
        live = valid and isinstance(timestamp, (int, float)) and not isinstance(timestamp, bool) and math.isfinite(timestamp) and timestamp > 0
        retained_timestamp = old.get('registryTimestamp')
        retained_timestamp_valid = isinstance(retained_timestamp, (int, float)) and not isinstance(retained_timestamp, bool) and math.isfinite(retained_timestamp) and retained_timestamp > 0
        sql_receipt = sqlite.lookup(chat,mid) if valid and not live else None
        old_authority=old.get('authority')
        old_source_valid = old_authority=='gateway-json-registry' or (old_authority==SQLITE_AUTHORITY and sqlite.retained_source_matches(old.get('source'),chat,mid))
        prior = valid and old.get('version') == 1 and old.get('identity') == identity and old_source_valid and retained_timestamp_valid and bool(old.get('verifiedAt'))
        if live:
            used_authorities.add('gateway-json-registry')
            verdict, note = 'pass-present', 'Observed in the authoritative gateway registry.'
            additions[key] = {'version': 1, 'identity': identity, 'authority': 'gateway-json-registry', 'registryTimestamp': timestamp, 'verifiedAt': now}
        elif sql_receipt:
            used_authorities.add(SQLITE_AUTHORITY)
            verdict,note='pass-present','Observed in the exact Telegram plugin-state scope.'
            additions[key]={'version':1,'identity':identity,'authority':SQLITE_AUTHORITY,'registryTimestamp':sql_receipt['timestamp'],'verifiedAt':now,'source':sql_receipt}
        elif prior:
            used_authorities.add(old_authority)
            verdict, note = 'pass-verified-receipt', 'Exact historical gateway receipt retained before registry rotation.'
        elif slot not in required and not mid:
            verdict, note = 'skip-no-messageId-optional', 'No optional message captured.'
        else:
            verdict = 'fail-no-messageId' if not valid else 'fail-missing-recent' if registry is not None or sqlite.available else 'capability-unavailable'
            note = 'No independent receipt proves this exact client, build, artifact and message.'
            if slot in required:
                rc = max(rc, 7 if registry is None and not sqlite.available else 4 if not valid else 3)
        results.append({'n': slot, 'messageId': mid, 'required': slot in required, 'verdict': verdict, 'note': note})
    sqlite.close()
    authority=SQLITE_AUTHORITY if SQLITE_AUTHORITY in used_authorities else 'gateway-json-registry'
    def commit(state):
        nonlocal rc
        bound = state.get('buildId') == build and closeout_artifact_digest(state) == digest
        if not bound: rc = 7
        if bound:
            ledger = state.setdefault('telegramDeliveryReceipts', {})
            ledger.update(additions)
        state['telegramDeliveryVerification'] = {'version': 2, 'status': 'pass' if rc == 0 else 'pending' if rc == 7 else 'fail', 'rc': rc, 'results': results,
            'requiredSlots': ','.join(str(n) for n in sorted(required)), 'verifiedAt': now, 'authority': authority, 'buildId': build, 'artifactDigest': digest}
    update(path, commit)
    for result in results: print('[verify-telegram] slot={n} verdict={verdict} {note}'.format(**result))
    return rc

if __name__ == '__main__':
    try:
        required = {int(n) for n in sys.argv[3].split(',')}
        if not required or any(n < 1 for n in required): raise ValueError('invalid required slots')
        sys.exit(verify(sys.argv[1], sys.argv[2], required))
    except (OSError, ValueError, TypeError, KeyError) as error:
        print('[verify-telegram] receipt verification unavailable: ' + type(error).__name__, file=sys.stderr)
        sys.exit(7)
