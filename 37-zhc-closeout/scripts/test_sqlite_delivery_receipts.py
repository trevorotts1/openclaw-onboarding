"""Actual-schema SQLite receipt fixtures; never opens an installed client DB."""
import contextlib,hashlib,io,json,sqlite3,sys,tempfile,time,unittest,os,subprocess
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from gateway_sqlite_receipts import SQLiteReceipts,AUTHORITY,scope_key,entry_key
from verify_delivery_receipts import verify
from workforce_state import atomic_write,read,update
class SQLiteDelivery(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.db=self.root/'own.sqlite';self.store=str(self.root/'agents/main/sessions/sessions.json');self.state=self.root/'build-state.json';self.registry=self.root/'missing-registry.json';self.now=time.time()*1000
  with sqlite3.connect(self.db) as db:db.execute('CREATE TABLE plugin_state_entries(plugin_id TEXT,namespace TEXT,entry_key TEXT,value_json TEXT,created_at INTEGER,expires_at INTEGER,PRIMARY KEY(plugin_id,namespace,entry_key))')
  atomic_write(self.state,{'companyId':'own-company','companySlug':'own','buildId':'own-build','ownerChat':'own-chat','messagesDelivered':[{'n':n,'messageId':str(n),'chatId':'own-chat','status':'sent'} for n in (1,6,7)]})
 def tearDown(self):self.temp.cleanup()
 def seed(self,plugin='telegram',namespace='telegram.sent-messages',value_scope=None,chat='own-chat',expires=None,timestamp=None):
  scope=scope_key(self.store)
  with sqlite3.connect(self.db) as db:
   db.execute('DELETE FROM plugin_state_entries')
   for n in (1,6,7):
    value={'scopeKey':value_scope or scope,'chatId':chat,'messageId':str(n),'timestamp':self.now-1000 if timestamp is None else timestamp}
    db.execute('INSERT INTO plugin_state_entries VALUES(?,?,?,?,?,?)',(plugin,namespace,entry_key(scope,'own-chat',str(n)),json.dumps(value),int(self.now-1000),int(self.now+60_000) if expires is None else expires))
 def verify(self,store=None):
  with contextlib.redirect_stdout(io.StringIO()):return verify(self.state,self.registry,{1,6,7},str(self.db),store or self.store)
 def test_exact_positive_receipt_and_readonly_database(self):
  self.seed();before=hashlib.sha256(self.db.read_bytes()).hexdigest();self.assertEqual(self.verify(),0);self.assertEqual(before,hashlib.sha256(self.db.read_bytes()).hexdigest())
  state=read(self.state);self.assertEqual(state['telegramDeliveryVerification']['authority'],AUTHORITY)
  self.assertEqual(len(state['telegramDeliveryReceipts']),3)
  for receipt in state['telegramDeliveryReceipts'].values():self.assertEqual(receipt['source']['scopeKey'],scope_key(self.store))
 def test_wrong_scope_chat_plugin_namespace_rejected(self):
  for override in ({'value_scope':'foreign-scope'},{'chat':'foreign-chat'},{'plugin':'other-plugin'},{'namespace':'telegram.message-cache'}):
   self.seed(**override);self.assertNotEqual(self.verify(),0)
 def test_expired_and_old_timestamp_unproven_rows_rejected(self):
  self.seed(expires=int(self.now-1));self.assertNotEqual(self.verify(),0)
  self.seed(timestamp=self.now-86_400_001);self.assertNotEqual(self.verify(),0)
 def test_invalid_timestamps_rejected(self):
  for timestamp in (True,False,0,-1,'123',None):
   self.seed()
   with sqlite3.connect(self.db) as db:
    for key,raw in db.execute('SELECT entry_key,value_json FROM plugin_state_entries').fetchall():
     value=json.loads(raw);value['timestamp']=timestamp;db.execute('UPDATE plugin_state_entries SET value_json=? WHERE entry_key=?',(json.dumps(value),key))
   self.assertNotEqual(self.verify(),0)
 def test_missing_table_and_database_failclosed_without_creation(self):
  with sqlite3.connect(self.db) as db:db.execute('DROP TABLE plugin_state_entries')
  self.assertEqual(self.verify(),7)
  missing=self.root/'never-created.sqlite';reader=SQLiteReceipts(str(missing),self.store);self.assertFalse(reader.available);self.assertFalse(missing.exists())
 def test_retained_sqlite_receipt_survives_rotation_but_not_changed_scope_or_build(self):
  self.seed();self.assertEqual(self.verify(),0)
  with sqlite3.connect(self.db) as db:db.execute('DELETE FROM plugin_state_entries')
  self.assertEqual(self.verify(),0);self.assertTrue(all(r['verdict']=='pass-verified-receipt' for r in read(self.state)['telegramDeliveryVerification']['results']))
  self.assertNotEqual(self.verify(self.store+'.foreign'),0)
  update(self.state,lambda state:state.update(buildId='different-build'));self.assertNotEqual(self.verify(),0)
 def test_shell_wrapper_explicit_sqlite_scope(self):
  self.seed()
  env=dict(os.environ,HOME=str(self.root),ZHC_STATE_FILE=str(self.state),ZHC_LOG_FILE=str(self.root/'log'),ZHC_TG_REGISTRY=str(self.registry),ZHC_TG_STATE_DB=str(self.db),ZHC_TG_SESSION_STORE=self.store)
  result=subprocess.run(['bash',str(Path(__file__).parent/'verify-telegram-delivery.sh')],env=env,capture_output=True,timeout=5)
  self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(read(self.state)['telegramDeliveryVerification']['authority'],AUTHORITY)
 def test_wrong_entry_key_or_message_value_cannot_prove_delivery(self):
  for wrong_key in (False,True):
   self.seed()
   with sqlite3.connect(self.db) as db:
    if wrong_key:db.execute("UPDATE plugin_state_entries SET entry_key='foreign-'||entry_key")
    else:
     for key,raw in db.execute('SELECT entry_key,value_json FROM plugin_state_entries').fetchall():
      value=json.loads(raw);value['messageId']='foreign-message';db.execute('UPDATE plugin_state_entries SET value_json=? WHERE entry_key=?',(json.dumps(value),key))
   self.assertNotEqual(self.verify(),0)
 def test_ambiguous_duplicate_rows_are_not_authoritative(self):
  self.seed()
  with sqlite3.connect(self.db) as db:
   db.execute('ALTER TABLE plugin_state_entries RENAME TO original_entries')
   db.execute('CREATE TABLE plugin_state_entries AS SELECT * FROM original_entries')
   db.execute('INSERT INTO plugin_state_entries SELECT * FROM original_entries')
  self.assertNotEqual(self.verify(),0)
 def test_retained_receipt_is_bound_to_database_path(self):
  self.seed();self.assertEqual(self.verify(),0)
  other=self.root/'other.sqlite'
  with sqlite3.connect(self.db) as db:
   db.execute('DELETE FROM plugin_state_entries');db.commit()
   with sqlite3.connect(other) as destination:db.backup(destination)
  with contextlib.redirect_stdout(io.StringIO()):result=verify(self.state,self.registry,{1,6,7},str(other),self.store)
  self.assertNotEqual(result,0)
 def test_state_override_does_not_enable_default_gateway_database(self):
  self.seed()
  # Synthetic own root contains matching proof, but the scratch-state override
  # must not silently opt into that gateway database or session-store scope.
  fake_root=self.root/'.openclaw';(fake_root/'state').mkdir(parents=True)
  fake_db=fake_root/'state/openclaw.sqlite'
  with sqlite3.connect(self.db) as source:
   with sqlite3.connect(fake_db) as destination:source.backup(destination)
  env=dict(os.environ,HOME=str(self.root),ZHC_STATE_FILE=str(self.state),ZHC_LOG_FILE=str(self.root/'log'),ZHC_TG_REGISTRY=str(self.registry),ZHC_TG_SESSION_STORE=self.store)
  env.pop('ZHC_TG_STATE_DB',None)
  result=subprocess.run(['bash',str(Path(__file__).parent/'verify-telegram-delivery.sh')],env=env,capture_output=True,timeout=5)
  self.assertEqual(result.returncode,7,result.stderr)
  self.assertNotEqual(read(self.state)['telegramDeliveryVerification']['status'],'pass')
 def test_busy_database_is_bounded_and_not_proof(self):
  self.seed()
  with sqlite3.connect(self.db) as db:
   db.execute('BEGIN EXCLUSIVE');start=time.monotonic();reader=SQLiteReceipts(str(self.db),self.store);self.assertFalse(reader.available);self.assertLess(time.monotonic()-start,1);db.rollback()
if __name__=='__main__':unittest.main()
