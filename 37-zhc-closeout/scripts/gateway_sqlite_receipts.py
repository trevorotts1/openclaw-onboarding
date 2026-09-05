"""Read-only OpenClaw 2026.9.1 Telegram plugin-state receipt adapter.

Contract is documented in ../GATEWAY-RECEIPTS.md. No discovery of another
agent/store/chat, no migration, no fallback to arbitrary plugin-state rows.
"""
from __future__ import annotations
import hashlib,json,math,sqlite3,time
from pathlib import Path

AUTHORITY='gateway-sqlite-plugin-state'
PLUGIN='telegram'
NAMESPACE='telegram.sent-messages'
TTL_MS=86_400_000

def positive_number(value):
    return isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value) and value>0

def scope_key(session_store):
    return hashlib.sha256(session_store.encode('utf-8')).hexdigest()[:24]

def entry_key(scope,chat,message):
    return hashlib.sha256((scope+'\0'+chat+'\0'+message).encode('utf-8')).hexdigest()[:32]

class SQLiteReceipts:
    def __init__(self,database_path=None,session_store=None,now_ms=None):
        self.db=None;self.available=False;self.reason='sqlite capability not configured'
        self.now_ms=time.time()*1000 if now_ms is None else now_ms
        self.source=None
        if not database_path or not session_store:return
        database=Path(database_path)
        if not database.is_absolute() or not Path(session_store).is_absolute():
            self.reason='receipt database and exact session store must be absolute';return
        # Session store is hashed exactly as the gateway configured it. Resolving
        # a symlink or looking for a newer agent store would change its authority.
        self.source={'databasePath':str(database.resolve()),'sessionStore':str(session_store),
                     'scopeKey':scope_key(str(session_store)),'pluginId':PLUGIN,'namespace':NAMESPACE}
        if not database.is_file():self.reason='receipt database missing';return
        try:
            self.db=sqlite3.connect(database.resolve().as_uri()+'?mode=ro',uri=True,timeout=.1)
            self.db.execute('PRAGMA query_only=ON')
            deadline=time.monotonic()+.5
            self.db.set_progress_handler(lambda:1 if time.monotonic()>deadline else 0,1000)
            columns={r[1] for r in self.db.execute('PRAGMA table_info(plugin_state_entries)')}
            required={'plugin_id','namespace','entry_key','value_json','created_at','expires_at'}
            if not required<=columns:raise ValueError('unsupported plugin-state schema')
            self.available=True;self.reason='supported plugin-state schema'
        except (OSError,ValueError,sqlite3.Error):
            self.reason='receipt schema unavailable';self.close()
    def close(self):
        if self.db:self.db.close();self.db=None
    def lookup(self,chat,message):
        if not self.available or not self.db:return None
        key=entry_key(self.source['scopeKey'],chat,message)
        try:
            deadline=time.monotonic()+.5
            self.db.set_progress_handler(lambda:1 if time.monotonic()>deadline else 0,1000)
            rows=self.db.execute('SELECT value_json,created_at,expires_at FROM plugin_state_entries WHERE plugin_id=? AND namespace=? AND entry_key=? LIMIT 2',(PLUGIN,NAMESPACE,key)).fetchall()
            if len(rows)!=1:return None
            raw,created,expires=rows[0]
            if not isinstance(raw,str) or len(raw)>65536:return None
            value=json.loads(raw)
            if not isinstance(value,dict):return None
            timestamp=value.get('timestamp')
            if not positive_number(timestamp) or not positive_number(created):return None
            if self.now_ms-timestamp>=TTL_MS:return None
            if expires is not None and (not positive_number(expires) or expires<=self.now_ms):return None
            if value.get('scopeKey')!=self.source['scopeKey'] or value.get('chatId')!=chat or value.get('messageId')!=message:return None
            return dict(self.source,entryKey=key,createdAt=created,expiresAt=expires,timestamp=timestamp)
        except (ValueError,TypeError,sqlite3.Error):
            self.available=False;self.reason='receipt query unavailable';return None
    def retained_source_matches(self,source,chat,message):
        if not self.source or not isinstance(source,dict):return False
        return (all(source.get(k)==v for k,v in self.source.items())
                and source.get('entryKey')==entry_key(self.source['scopeKey'],chat,message)
                and positive_number(source.get('createdAt')))
