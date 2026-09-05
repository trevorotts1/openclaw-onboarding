"""Runtime binding proofs in isolated filesystem and SQLite fixtures."""
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'shared-utils'))
from sync_ceo_runtime_bindings import sync

class BindingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.company = Path(self.temp.name) / 'own'
        self.workspace = self.company / 'departments/ceo-dept'
        self.workspace.mkdir(parents=True)
        self.runtime = Path(self.temp.name) / 'runtime/main/agent'
        self.runtime.mkdir(parents=True)
        self.config = {'agents': {'list': [{'id': 'main', 'workspace': str(self.workspace), 'agentDir': str(self.runtime)}]}}
        self.db = sqlite3.connect(':memory:')
        self.addCleanup(self.db.close)
        self.db.executescript('''CREATE TABLE workspaces(id TEXT,slug TEXT,company_id TEXT,archived_at TEXT);
        CREATE TABLE agents(id TEXT,workspace_id TEXT,openclaw_agent_id TEXT,is_master INTEGER);
        INSERT INTO workspaces VALUES('own-ceo','ceo','own',NULL),('foreign-ceo','ceo','foreign',NULL);
        INSERT INTO agents VALUES('own-agent','own-ceo',NULL,1),('foreign-agent','foreign-ceo',NULL,1);''')

    def result(self):
        return sync(self.db, self.config, 'own', self.company)

    def test_valid_unique_main_binds_only_own_ceo(self):
        self.assertEqual(self.result()['bound'], 1)
        self.assertEqual(list(self.db.execute('SELECT openclaw_agent_id FROM agents')), [('main',), (None,)])
        self.assertEqual(self.result()['bound'], 0)

    def test_foreign_workspace_never_binds(self):
        other = Path(self.temp.name) / 'foreign/departments/ceo-dept'
        other.mkdir(parents=True)
        self.config['agents']['list'][0]['workspace'] = str(other)
        self.assertEqual(self.result()['bound'], 0)

    def test_ambiguous_registry_and_board_do_not_bind(self):
        self.config['agents']['list'].append(dict(self.config['agents']['list'][0], id='dept-ceo'))
        self.assertEqual(self.result()['bound'], 0)
        self.config['agents']['list'].pop()
        self.db.execute("INSERT INTO agents VALUES('second','own-ceo',NULL,1)")
        self.assertEqual(self.result()['bound'], 0)

    def test_owner_binding_and_foreign_runtime_binding_preserved(self):
        self.db.execute("UPDATE agents SET openclaw_agent_id='custom' WHERE id='own-agent'")
        self.assertEqual(self.result()['bound'], 0)
        self.db.execute("UPDATE agents SET openclaw_agent_id=NULL WHERE id='own-agent'")
        self.db.execute("UPDATE agents SET openclaw_agent_id='main' WHERE id='foreign-agent'")
        self.assertEqual(self.result()['bound'], 0)

    def test_missing_real_agent_dir_never_claims_ready(self):
        self.config['agents']['list'][0]['agentDir'] = str(self.runtime / 'absent')
        self.assertEqual(self.result()['bound'], 0)

    def test_old_schema_defers(self):
        self.db.execute('DROP TABLE agents')
        self.db.execute('CREATE TABLE agents(id TEXT)')
        self.assertEqual(self.result()['status'], 'deferred-schema-133')

    def test_ceo_trio_binds_only_the_master(self):
        self.db.executemany('INSERT INTO agents VALUES(?,?,NULL,0)',
                            [('lead', 'own-ceo'), ('qc', 'own-ceo'), ('specialist', 'own-ceo')])
        self.assertEqual(self.result()['bound'], 1)
        self.assertEqual(list(self.db.execute("SELECT id FROM agents WHERE openclaw_agent_id='main'")), [('own-agent',)])

    def test_archived_workspace_is_never_bound(self):
        self.db.execute("UPDATE workspaces SET archived_at='2026-09-05' WHERE id='own-ceo'")
        self.assertEqual(self.result()['bound'], 0)

    def test_non_master_ceo_row_is_never_bound(self):
        self.db.execute("UPDATE agents SET is_master=0 WHERE id='own-agent'")
        self.assertEqual(self.result()['bound'], 0)

    def test_general_task_actual_runtime_supported(self):
        general = self.company / 'departments/general-task-dept'
        general.mkdir()
        self.config['agents']['list'][0].update(id='dept-general-task', workspace=str(general))
        self.db.execute("UPDATE workspaces SET slug='general-task' WHERE id='own-ceo'")
        self.assertEqual(self.result()['bound'], 1)

if __name__ == '__main__': unittest.main()
