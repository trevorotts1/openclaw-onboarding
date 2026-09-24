#!/usr/bin/env python3
"""Read-only interview prompt admission; NEVER authorization to build or pass QC."""
import json
import os
import sqlite3
import sys
from pathlib import Path

from resolve_db import is_db_found
from service_env import decode_value

IDENTITY = {'tenantId': 'MC_TENANT_ID', 'companyId': 'MC_COMPANY_ID', 'installationId': 'MC_INSTALLATION_ID'}

SERVICE_KEYS = {*IDENTITY.values(), 'MC_TENANT_REGISTRY_JSON', 'DATABASE_PATH', 'DASHBOARD_DB_PATH'}


def service_values(file):
    if not file.is_absolute() or not file.is_file() or file.stat().st_size > 1024 * 1024:
        raise ValueError('service environment unavailable')
    stored = {}
    for line in file.read_text().splitlines():
        key, separator, value = line.partition('=')
        key = key.strip()
        if not separator or key not in SERVICE_KEYS:
            continue
        value = decode_value(value, structured=key.endswith('_JSON'))
        if not isinstance(value, str) or not value or (key in stored and stored[key] != value):
            raise ValueError('invalid service environment')
        stored[key] = value
    return stored


def installed_service(selected):
    """Resolve configured app, never discover it by database existence or cron cwd."""
    directory = selected.get('CC_APP_DIR')
    process_env = {}
    if directory is None:
        pm2_home = Path(selected.get('PM2_HOME') or Path(selected.get('HOME') or Path.home()) / '.pm2')
        dump = pm2_home / 'dump.pm2'
        if not pm2_home.is_absolute() or not dump.is_file() or dump.stat().st_size > 16 * 1024 * 1024:
            raise ValueError('installed service unavailable')
        processes = json.loads(dump.read_text())
        if not isinstance(processes, list) or any(not isinstance(row, dict) for row in processes):
            raise ValueError('invalid installed service')
        matches = [row for row in processes if row.get('name') in ('blackceo-command-center', 'mission-control')]
        if len(matches) != 1:
            raise ValueError('ambiguous installed service')
        process = matches[0]
        directory = process.get('pm_cwd')
        nested = process.get('env', {})
        if not isinstance(nested, dict):
            raise ValueError('invalid installed service environment')
        for source in (nested, process):
            for key in SERVICE_KEYS & source.keys():
                value = source[key]
                if not isinstance(value, str) or not value or (key in process_env and process_env[key] != value):
                    raise ValueError('conflicting installed service environment')
                process_env[key] = value
    if not isinstance(directory, str) or not directory or not Path(directory).is_absolute():
        raise ValueError('installed app directory missing')
    app = Path(directory)
    package = json.loads((app / 'package.json').read_text())
    if not isinstance(package, dict) or package.get('name') not in ('mission-control', 'blackceo-command-center'):
        raise ValueError('installed app identity mismatch')
    stored = service_values(app / '.env.local')
    # Process-manager and file pins must agree; do not guess which stale value won.
    for key, value in process_env.items():
        if key in stored and stored[key] != value:
            raise ValueError('service file/process conflict')
        stored[key] = value
    for key in ('DATABASE_PATH', 'DASHBOARD_DB_PATH'):
        if key in stored:
            stored[key] = str((app / stored[key]).resolve())
    if not stored.get('DATABASE_PATH') and not stored.get('DASHBOARD_DB_PATH'):
        stored['DATABASE_PATH'] = str(app / 'mission-control.db')
    return stored


def prompt_status(state, env=None):
    """COMPLETE/DECLARED suppress prompts; only proven INCOMPLETE permits them.

    UNKNOWN covers missing identity, unavailable stores and migration gaps. Local
    installation config supplies scope; request parameters never select a tenant.
    No flag, database, answers, or quality evidence is created or changed.
    """
    if not isinstance(state, dict):
        return 'UNKNOWN'
    if state.get('interviewComplete') is True or state.get('interview_complete') is True or state.get('buildCompletedAt'):
        return 'COMPLETE'
    selected = dict(os.environ if env is None else env)
    launch = state.get('launchBootstrap')
    pinned = launch.get('serviceEnvPath') if isinstance(launch, dict) else None
    try:
        stored = {}
        if pinned is not None:
            stored = service_values(Path(pinned))
            if any(not stored.get(key) for key in IDENTITY.values()):
                return 'UNKNOWN'
        elif not selected.get('DATABASE_PATH') and not selected.get('DASHBOARD_DB_PATH'):
            stored = installed_service(selected)
            if not stored.get('MC_COMPANY_ID') or not stored.get('MC_INSTALLATION_ID'):
                return 'UNKNOWN'
        for key, value in stored.items():
            if selected.get(key) and selected[key] != value:
                return 'UNKNOWN'
            selected[key] = value
        # Older installations pin company/installation and register the tenant by
        # hostname instead of exporting MC_TENANT_ID. Only trusted self entries
        # may fill that gap; state and request host never select a registry row.
        registry_text = selected.get('MC_TENANT_REGISTRY_JSON')
        if registry_text is not None:
            registry = json.loads(registry_text)
            if not isinstance(registry, dict) or not registry:
                return 'UNKNOWN'
            tenants = set()
            for host, registration in registry.items():
                if not host.strip() or not isinstance(registration, dict):
                    return 'UNKNOWN'
                if registration.get('kind') != 'self':
                    continue
                if any(not isinstance(registration.get(key), str) or not registration[key].strip() for key in IDENTITY):
                    return 'UNKNOWN'
                if (registration['companyId'] == selected.get('MC_COMPANY_ID') and
                        registration['installationId'] == selected.get('MC_INSTALLATION_ID')):
                    tenants.add(registration['tenantId'])
            if len(tenants) != 1:
                return 'UNKNOWN'
            tenant = next(iter(tenants))
            if 'MC_TENANT_ID' in selected and selected['MC_TENANT_ID'] != tenant:
                return 'UNKNOWN'
            selected['MC_TENANT_ID'] = tenant
        scope = []
        for key, variable in IDENTITY.items():
            value = selected.get(variable)
            if not isinstance(value, str) or not value.strip() or state.get(key) != value:
                return 'UNKNOWN'
            scope.append(value)
        # Candidate order and cron cwd cannot prove the running server's DB.
        # Require its explicit environment/service-file pin; never read a decoy.
        pinned_db = selected.get('DASHBOARD_DB_PATH') or selected.get('DATABASE_PATH')
        if not pinned_db:
            return 'UNKNOWN'
        db = Path(pinned_db)
        if not is_db_found(db):
            return 'UNKNOWN'
        # A missing explicit pin must never silently fall through to a decoy DB.
        for variable in ('DATABASE_PATH', 'DASHBOARD_DB_PATH'):
            pin = selected.get(variable)
            if pin and (not Path(pin).is_absolute() or Path(pin).resolve() != db.resolve()):
                return 'UNKNOWN'
        connection = sqlite3.connect(db.resolve().as_uri() + '?mode=ro', uri=True, timeout=2)
        try:
            row = connection.execute('''SELECT 1 FROM interview_prior_completion_declarations
                WHERE tenant_id=? AND company_id=? AND installation_id=?
                AND source='owner-self-attestation' LIMIT 1''', scope).fetchone()
        finally:
            connection.close()
        return 'DECLARED' if row else 'INCOMPLETE'
    except (OSError, ValueError, TypeError, sqlite3.Error):
        # UNKNOWN is deliberately NOT incomplete: callers must not nag on errors.
        return 'UNKNOWN'


if __name__ == '__main__':
    try:
        state = json.loads(Path(sys.argv[1]).read_text())
    except (OSError, ValueError, IndexError):
        state = None
    print(prompt_status(state))
