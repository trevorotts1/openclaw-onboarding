#!/usr/bin/env python3
"""Bind existing same-company CC agents to proven OpenClaw registry identities.

No seeding, runtime creation, broad dashboard discovery or display-name inference.
Schema <133 and unprovisioned clients defer without fabricating readiness.
"""
import argparse
import json
from pathlib import Path
import sqlite3
import sys
from ceo_execution_policy import registry_rows

ALIASES = {'ceo': 'ceo', 'master-orchestrator': 'ceo', 'general-task': 'general-task'}


def sync(db, config, company_id, company_dir):
    columns = {r[1] for r in db.execute('PRAGMA table_info(agents)')}
    if 'openclaw_agent_id' not in columns:
        return {'status': 'deferred-schema-133', 'bound': 0}
    workspace_columns = {r[1] for r in db.execute('PRAGMA table_info(workspaces)')}
    if 'is_master' not in columns or 'archived_at' not in workspace_columns:
        return {'status': 'deferred-ownership-schema', 'bound': 0}
    if not company_id or not company_dir.is_dir():
        return {'status': 'deferred-company', 'bound': 0}
    root = (company_dir / 'departments').resolve()
    candidates = {'ceo': [], 'general-task': []}
    for entry in registry_rows(config):
        if not isinstance(entry, dict):
            continue
        rid, ws, agent_dir = entry.get('id'), entry.get('workspace'), entry.get('agentDir')
        if not all(isinstance(x, str) and x for x in (rid, ws, agent_dir)):
            continue
        workspace = Path(ws).expanduser().resolve()
        if not workspace.is_dir() or not Path(agent_dir).expanduser().is_dir():
            continue
        try:
            parts = workspace.relative_to(root).parts
        except ValueError:
            continue  # Includes another client's main workspace.
        if not parts:
            continue
        dept = parts[0].removesuffix('-dept')
        kind = ALIASES.get(dept)
        # Actual main is accepted only inside this company's canonical CEO tree.
        permitted = {'main', 'ceo', 'master-orchestrator', 'dept-ceo', 'dept-master-orchestrator'} if kind == 'ceo' else {'dept-general-task'}
        if kind and rid in permitted:
            candidates[kind].append(rid)
    bound = 0
    with db:
        rows = list(db.execute('''SELECT a.id, a.openclaw_agent_id, w.slug, a.is_master FROM agents a
            JOIN workspaces w ON w.id=a.workspace_id WHERE w.company_id=? AND w.archived_at IS NULL''', (company_id,)))
        for kind in candidates:
            ids = candidates[kind]
            eligible = [row for row in rows if ALIASES.get(row[2]) == kind
                        and (kind != 'ceo' or row[3] == 1)]
            if len(ids) != 1 or len(eligible) != 1:
                continue  # Ambiguous registry/board identity cannot confer authority.
            agent_id, current, _, _ = eligible[0]
            if current:
                continue  # Owner-established bindings are immutable here.
            if db.execute('SELECT 1 FROM agents WHERE openclaw_agent_id=?', (ids[0],)).fetchone():
                continue  # Never reuse a binding across clients or agents.
            bound += db.execute('''UPDATE agents SET openclaw_agent_id=? WHERE id=?
                AND (openclaw_agent_id IS NULL OR openclaw_agent_id='')
                AND EXISTS (SELECT 1 FROM workspaces w WHERE w.id=agents.workspace_id AND w.company_id=? AND w.archived_at IS NULL)
                AND (? != 'ceo' OR is_master=1)
                AND NOT EXISTS (SELECT 1 FROM agents other WHERE other.openclaw_agent_id=?)''',
                (ids[0], agent_id, company_id, kind, ids[0])).rowcount
    return {'status': 'verified' if bound else 'unchanged-or-unproven', 'bound': bound}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--db', required=True, type=Path)
    parser.add_argument('--config', required=True, type=Path)
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument('--company-id')
    scope.add_argument('--company-slug')
    parser.add_argument('--company-dir', type=Path)
    parser.add_argument('--build-state', type=Path)
    args = parser.parse_args()
    company_dir = args.company_dir
    if company_dir is None and args.build_state and args.build_state.is_file():
        from reconcile_command_center_runtime import _resolve_company_dir
        state = json.loads(args.build_state.read_text())
        if (state.get('companySlug') or state.get('clientSlug')) != (args.company_slug or args.company_id):
            raise ValueError('Explicit company differs from selected build-state')
        company_dir = _resolve_company_dir(args.build_state.parent, None, state)
    if company_dir is None or not args.db.is_file() or not args.config.is_file():
        print(json.dumps({'status': 'deferred-unprovisioned', 'bound': 0}))
        return
    config = json.loads(args.config.read_text())
    # mode=rw cannot silently create an empty DB at a mistaken path.
    with sqlite3.connect(args.db.resolve().as_uri() + '?mode=rw', uri=True) as db:
        company_id = args.company_id
        if args.company_slug:
            columns = {row[1] for row in db.execute('PRAGMA table_info(companies)')}
            if 'slug' not in columns:
                print(json.dumps({'status': 'deferred-company-id', 'bound': 0}))
                return
            rows = list(db.execute('SELECT id FROM companies WHERE slug=?', (args.company_slug,)))
            if len(rows) != 1:
                print(json.dumps({'status': 'deferred-company-id', 'bound': 0}))
                return
            company_id = rows[0][0]
        print(json.dumps(sync(db, config, company_id, company_dir)))

if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, RuntimeError, sqlite3.Error) as exc:
        print(f'Runtime binding deferred: {exc}', file=sys.stderr)
        sys.exit(2)
