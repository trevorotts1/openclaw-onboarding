#!/usr/bin/env python3
# oc-schema-migrate.py — v1.0.0
#
# The `agents.list` -> `agents.entries` schema transform, plus the detector and
# the losslessness verifier that guard it. Pure, offline, stdlib-only, and it
# NEVER writes the file it is pointed at: `apply` writes to a separate output
# path and the caller performs the swap. That split exists so the shell driver
# (scripts/oc-atomic-upgrade.sh) can do the swap THROUGH the original inode and
# keep the config's owner/group/mode, which a root-run cron would otherwise
# destroy.
#
# ─── WHY THIS FILE EXISTS AT ALL ─────────────────────────────────────────────
#
# `openclaw doctor --fix` CANNOT perform this migration. Measured, not assumed:
# on 12 boxes the config's SHA-256 was byte-identical before and after a
# `doctor --fix` run, and `openclaw config schema` on 2026.7.1 / 2026.7.1-2
# reports the `agents` properties as exactly ["defaults","list"] — there is no
# `entries` for it to migrate to. It also has a measured SIDE EFFECT: on one box
# it silently rewrote `agents.defaults.models` pins. Any code that calls
# `doctor --fix` expecting a schema migration is calling a tool that does not do
# this job, and is risking model pins for nothing.
#
# ─── THE FOUR FACTS THAT FORCE THIS SHAPE ────────────────────────────────────
#
# 1. `additionalProperties: false` is set on `agents` in BOTH the old and the
#    new schema. So `entries` is INVALID on the old build and `list` is INVALID
#    on the new one. There is no config that is valid on both. A migration is
#    therefore never "safe to do early" — it is only ever safe to do in the same
#    window as the binary change.
#
# 2. The deployed runtime has no `entries` reader. agent-scope-config-BxAUeF6t.js
#    (identical on 2026.7.1 and 2026.7.1-2) contains only
#        listAgentEntries(cfg) { const list = cfg.agents?.list; ... }
#    A full-bundle scan of 4,597 files found ZERO real reads of `agents.entries`
#    against a control of 105 files referencing `agents.list`. Writing `entries`
#    onto a box still running that build enumerates ZERO agents: a silent, total
#    outage — strictly worse than the loud crash-loop it was meant to avoid.
#    The beta bundle (agent-scope-config-BxKPUdGc.js) DOES read both, but that
#    tolerance exists only AFTER the binary is installed.
#
# 3. A live process rewrites openclaw.json roughly once per minute,
#    byte-identically — observed while only `stat`/`sha256sum` were running.
#    Inference (labelled as such, not measured): it serializes the gateway's
#    in-memory model, which only knows `agents.list`. A hand-written `entries`
#    would therefore be normalized straight back out within about a minute. Any
#    migration performed while the gateway is UP will be silently reverted.
#
# 4. The runtime re-injects the id: it reads an entry and spreads `{...entry, id}`
#    using the DICT KEY as the id. Confirmed against a live box already on the
#    new shape: its `entries` is a dict whose entry objects carry NO `id` field.
#    That is why `apply` drops `id` from the body — leaving it in would be
#    harmless but off-shape, and `verify` asserts the exact round-trip.
#
# ─── THE TRANSFORM ───────────────────────────────────────────────────────────
#
#     agents.list: [ {id: "main", ...rest}, {id: "x", ...rest} ]
#       becomes
#     agents.entries: { "main": {...rest}, "x": {...rest} }
#
# `id` moves INTO the key and is REMOVED from the body; `agents.list` is
# deleted. Nothing else in the file is touched. A hand-performed conversion of
# exactly this shape was proven lossless on a live box: 177 agents before, 177
# after, sets identical.
#
# ─── WHAT THIS REFUSES TO DO ─────────────────────────────────────────────────
#
# Anything it cannot prove. A non-dict entry, a missing/blank/non-string `id`, a
# duplicate `id`, or a config already carrying BOTH keys all produce
# UNDETERMINED and exit 3. Guessing any of those would trade a loud crash-loop
# for silent agent loss, which is the exact failure mode this whole family of
# gates exists to prevent.
#
# ─── SUBCOMMANDS ─────────────────────────────────────────────────────────────
#
#   detect <config>
#       Print a one-line JSON verdict. Read-only.
#       exit 0  = CLEAN     (NEW_ENTRIES, or no `agents` block at all)
#       exit 10 = LEGACY    (`agents.list` present — needs migration)
#       exit 3  = UNDETERMINED (unreadable, unparseable, or ambiguous)
#
#   apply <config> <out>
#       Write the migrated config to <out>. <config> is never modified.
#       exit 0 = written, 3 = refused (reason on stderr), 1 = write failed.
#
#   verify <before> <after>
#       Prove the migration was lossless. exit 0 = proven, 1 = FAILED
#       (every failed assertion printed), 3 = could not be checked.
#
#   workspace <config>
#       Print the workspace this config resolves to, under the DUAL-SHAPE
#       precedence (entries.main -> list[id=main] -> defaults). Empty if none.
#       Always exit 0 — an absent workspace is a legitimate answer.
#
#   schema-keys <schema.json>
#       Read the output of `openclaw config schema` and print which keys the
#       INSTALLED BINARY actually accepts under `agents`, one per line. This is
#       the question the whole procedure turns on: the transform is only correct
#       against a build that reads `entries`, and the only authority on that is
#       the binary itself. exit 0 = answered, 3 = could not be determined (which
#       the caller MUST treat as "do not migrate", never as "migrate anyway").
#
# ─── PYTHON COMPAT ───────────────────────────────────────────────────────────
# %-formatting and no f-strings throughout, matching the inline detectors
# already embedded in update-skills.sh / setup-weekly-update.sh, so this file
# runs on the oldest python3 any box in the fleet carries.

import json
import os
import sys

SCHEMA_KEY_LEGACY = 'list'
SCHEMA_KEY_NEW = 'entries'

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_USAGE = 2
EXIT_UNDETERMINED = 3
EXIT_LEGACY = 10


class Undetermined(Exception):
    """The instrument could not reach a verdict. NEVER collapses into a pass."""
    pass


def _load(path):
    try:
        with open(path, encoding='utf-8') as fh:
            return json.load(fh)
    except IOError as e:
        raise Undetermined('cannot read %s: %s' % (path, e))
    except ValueError as e:
        raise Undetermined('cannot parse %s as JSON: %s' % (path, e))
    except Exception as e:  # pragma: no cover - defensive
        raise Undetermined('cannot load %s: %s' % (path, e))


def _agents_block(cfg, path):
    if not isinstance(cfg, dict):
        raise Undetermined('%s does not contain a JSON object at the top level' % path)
    agents = cfg.get('agents')
    if agents is None:
        return None
    if not isinstance(agents, dict):
        raise Undetermined(
            '`agents` in %s is a %s, not an object — cannot determine the schema shape'
            % (path, type(agents).__name__))
    return agents


def _sniff_indent(path):
    """Match the file's existing indentation so a migration is a minimal diff.

    Falls back to 2, which is what every config observed in the fleet uses.
    Never fails: formatting is cosmetic and must not be able to block a
    migration.
    """
    try:
        with open(path, encoding='utf-8') as fh:
            for line in fh:
                stripped = line.lstrip(' ')
                if stripped != line and stripped.strip():
                    return len(line) - len(stripped)
    except Exception:
        pass
    return 2


def _ids_from_list(lst, path):
    """Extract the id of every legacy entry, refusing anything ambiguous."""
    if not isinstance(lst, list):
        raise Undetermined(
            '`agents.%s` in %s is a %s, not an array — this is not the legacy shape'
            % (SCHEMA_KEY_LEGACY, path, type(lst).__name__))
    ids = []
    seen = {}
    for idx, entry in enumerate(lst):
        if not isinstance(entry, dict):
            raise Undetermined(
                '`agents.%s[%d]` in %s is a %s, not an object — refusing to guess an id for it'
                % (SCHEMA_KEY_LEGACY, idx, path, type(entry).__name__))
        aid = entry.get('id')
        if not isinstance(aid, str) or not aid.strip():
            raise Undetermined(
                '`agents.%s[%d]` in %s has no usable string `id` (got %r) — the id becomes the '
                'dict KEY in the new shape, so an entry without one cannot be migrated without '
                'inventing a name for it' % (SCHEMA_KEY_LEGACY, idx, path, aid))
        if aid in seen:
            raise Undetermined(
                '`agents.%s` in %s declares id %r at BOTH index %d and index %d. The new shape is '
                'a dict keyed by id, so migrating would silently DROP one of them.'
                % (SCHEMA_KEY_LEGACY, path, aid, seen[aid], idx))
        seen[aid] = idx
        ids.append(aid)
    return ids


def resolve_workspace(cfg):
    """Resolve the workspace under DUAL-SHAPE precedence.

    Mirrors oc_resolve_workspace_announced() in update-skills.sh, which reads the
    main agent's own workspace BEFORE agents.defaults.workspace. The new-shape
    read is first so that this function returns the SAME answer either side of a
    migration — which is exactly the invariant the atomic upgrade asserts.

    That invariance is load-bearing, not cosmetic: the resolved workspace is
    CANON_DIR, the symlink TARGET for the box's shared AGENTS.md / TOOLS.md /
    USER.md. A migration that moved it would trade a loud outage for a silent
    one.

    Returns (path, source). path is '' when nothing is declared.
    """
    if not isinstance(cfg, dict):
        return ('', 'none')
    agents = cfg.get('agents')
    if not isinstance(agents, dict):
        return ('', 'none')

    entries = agents.get(SCHEMA_KEY_NEW)
    if isinstance(entries, dict):
        main = entries.get('main')
        if isinstance(main, dict) and main.get('workspace'):
            return (os.path.expanduser(main['workspace']), 'agents.entries.main.workspace')

    legacy = agents.get(SCHEMA_KEY_LEGACY)
    if isinstance(legacy, list):
        for entry in legacy:
            if isinstance(entry, dict) and entry.get('id') == 'main' and entry.get('workspace'):
                return (os.path.expanduser(entry['workspace']),
                        'agents.list[id=main].workspace')

    defaults = agents.get('defaults')
    if isinstance(defaults, dict) and defaults.get('workspace'):
        return (os.path.expanduser(defaults['workspace']), 'agents.defaults.workspace')

    return ('', 'none')


def detect(path):
    """Return (verdict, payload_dict). Raises Undetermined; never guesses."""
    cfg = _load(path)
    agents = _agents_block(cfg, path)
    ws, ws_src = resolve_workspace(cfg)

    payload = {
        'config': path,
        'workspace': ws,
        'workspace_source': ws_src,
        'agent_count': 0,
        'ids': [],
    }

    if agents is None:
        payload['verdict'] = 'NO_AGENTS'
        payload['detail'] = 'no `agents` block at all — neither schema key can be present'
        return payload

    has_legacy = SCHEMA_KEY_LEGACY in agents
    has_new = SCHEMA_KEY_NEW in agents

    if has_legacy and has_new:
        raise Undetermined(
            '%s carries BOTH `agents.%s` and `agents.%s`. `additionalProperties: false` is set on '
            '`agents` in both schema versions, so this config is INVALID ON EVERY BUILD. Refusing '
            'to pick a winner — a human has to decide which one is real.'
            % (path, SCHEMA_KEY_LEGACY, SCHEMA_KEY_NEW))

    if has_new:
        entries = agents[SCHEMA_KEY_NEW]
        if not isinstance(entries, dict):
            raise Undetermined(
                '`agents.%s` in %s is a %s, not an object — that is not the new shape either'
                % (SCHEMA_KEY_NEW, path, type(entries).__name__))
        payload['verdict'] = 'NEW_ENTRIES'
        payload['agent_count'] = len(entries)
        payload['ids'] = sorted(entries.keys())
        payload['detail'] = 'already on the new `agents.%s` shape (%d agent(s))' % (
            SCHEMA_KEY_NEW, len(entries))
        return payload

    if has_legacy:
        ids = _ids_from_list(agents[SCHEMA_KEY_LEGACY], path)
        payload['verdict'] = 'LEGACY_LIST'
        payload['agent_count'] = len(ids)
        payload['ids'] = sorted(ids)
        payload['detail'] = (
            'legacy `agents.%s` array present (%d agent(s)) — the 2026.7.2-beta line rejects this '
            'key with `agents: Unrecognized key: "list"` and exits 78 (EX_CONFIG) ~0.4s after start'
            % (SCHEMA_KEY_LEGACY, len(ids)))
        return payload

    payload['verdict'] = 'NO_AGENTS'
    payload['detail'] = (
        '`agents` block present (%d key(s)) but carries NEITHER `%s` NOR `%s` — no agents are '
        'declared here at all' % (len(agents), SCHEMA_KEY_LEGACY, SCHEMA_KEY_NEW))
    return payload


def transform(cfg, path):
    """Return the migrated config. Pure: `cfg` is not modified.

    Key ORDER is preserved and `entries` is written exactly where `list` was, so
    the migration reads as a one-key rename in a diff rather than a reshuffle.
    """
    agents = _agents_block(cfg, path)
    if agents is None or SCHEMA_KEY_LEGACY not in agents:
        raise Undetermined(
            '%s has no `agents.%s` to migrate — refusing to write a config that was not asked for'
            % (path, SCHEMA_KEY_LEGACY))
    if SCHEMA_KEY_NEW in agents:
        raise Undetermined(
            '%s carries BOTH schema keys — refusing to migrate (see detect)' % path)

    legacy = agents[SCHEMA_KEY_LEGACY]
    ids = _ids_from_list(legacy, path)

    entries = {}
    for entry, aid in zip(legacy, ids):
        body = dict(entry)
        # The id becomes the dict KEY. The runtime re-injects it as
        # `{...entry, id}` from that key, so keeping it in the body would be
        # redundant — and a live box already on the new shape carries no `id`
        # inside its entry objects.
        body.pop('id', None)
        entries[aid] = body

    new_agents = {}
    for key, value in agents.items():
        if key == SCHEMA_KEY_LEGACY:
            new_agents[SCHEMA_KEY_NEW] = entries
        else:
            new_agents[key] = value

    new_cfg = {}
    for key, value in cfg.items():
        new_cfg[key] = new_agents if key == 'agents' else value
    return new_cfg


def verify(before_path, after_path):
    """Prove the migration was lossless. Returns a list of failures (empty = proven)."""
    before = _load(before_path)
    after = _load(after_path)
    b_agents = _agents_block(before, before_path)
    a_agents = _agents_block(after, after_path)
    failures = []

    if b_agents is None or SCHEMA_KEY_LEGACY not in b_agents:
        raise Undetermined(
            'the BEFORE config %s has no `agents.%s` — there is no migration to verify'
            % (before_path, SCHEMA_KEY_LEGACY))
    if a_agents is None:
        failures.append('AFTER config %s has no `agents` block at all' % after_path)
        return failures

    # 1. the legacy key is gone
    if SCHEMA_KEY_LEGACY in a_agents:
        failures.append(
            'AFTER config STILL carries `agents.%s` — the migration did not happen'
            % SCHEMA_KEY_LEGACY)

    # 2. the new key exists and is a dict
    entries = a_agents.get(SCHEMA_KEY_NEW)
    if not isinstance(entries, dict):
        failures.append(
            'AFTER config `agents.%s` is %s, not an object'
            % (SCHEMA_KEY_NEW, type(entries).__name__ if entries is not None else 'absent'))
        return failures

    legacy = b_agents[SCHEMA_KEY_LEGACY]
    try:
        b_ids = _ids_from_list(legacy, before_path)
    except Undetermined as e:
        failures.append('BEFORE config could not be enumerated: %s' % e)
        return failures

    # 3. COUNT is identical
    if len(entries) != len(b_ids):
        failures.append(
            'AGENT COUNT CHANGED: %d before, %d after — %d agent(s) would be lost'
            % (len(b_ids), len(entries), len(b_ids) - len(entries)))

    # 4. the KEY SET equals the ID SET exactly (both directions, named)
    b_set = set(b_ids)
    a_set = set(entries.keys())
    missing = sorted(b_set - a_set)
    extra = sorted(a_set - b_set)
    if missing:
        failures.append(
            'AGENTS LOST: %d id(s) present before and MISSING after: %s'
            % (len(missing), ', '.join(missing)))
    if extra:
        failures.append(
            'AGENTS INVENTED: %d key(s) after that were not ids before: %s'
            % (len(extra), ', '.join(extra)))

    # 5. every entry round-trips EXACTLY through the runtime's own `{...entry, id}`
    for entry, aid in zip(legacy, b_ids):
        if aid not in entries:
            continue
        rebuilt = dict(entries[aid])
        rebuilt['id'] = aid
        if rebuilt != entry:
            b_keys = set(entry.keys())
            a_keys = set(rebuilt.keys())
            lost = sorted(b_keys - a_keys)
            gained = sorted(a_keys - b_keys)
            changed = sorted(
                k for k in (b_keys & a_keys) if entry.get(k) != rebuilt.get(k))
            failures.append(
                'AGENT %r DID NOT ROUND-TRIP: lost=%s gained=%s changed=%s'
                % (aid, lost or 'none', gained or 'none', changed or 'none'))

    # 6. every OTHER key inside `agents` is untouched
    for key in set(b_agents.keys()) | set(a_agents.keys()):
        if key in (SCHEMA_KEY_LEGACY, SCHEMA_KEY_NEW):
            continue
        if key not in b_agents:
            failures.append('`agents.%s` was ADDED by the migration' % key)
        elif key not in a_agents:
            failures.append('`agents.%s` was REMOVED by the migration' % key)
        elif b_agents[key] != a_agents[key]:
            failures.append(
                '`agents.%s` was MODIFIED by the migration — the transform must only touch the '
                'schema key' % key)

    # 7. every OTHER top-level key is untouched
    for key in set(before.keys()) | set(after.keys()):
        if key == 'agents':
            continue
        if key not in before:
            failures.append('top-level key `%s` was ADDED by the migration' % key)
        elif key not in after:
            failures.append('top-level key `%s` was REMOVED by the migration' % key)
        elif before[key] != after[key]:
            failures.append(
                'top-level key `%s` was MODIFIED by the migration — the transform must only touch '
                '`agents`' % key)

    # 8. the resolved workspace did not move
    ws_b, src_b = resolve_workspace(before)
    ws_a, src_a = resolve_workspace(after)
    if ws_b != ws_a:
        failures.append(
            'RESOLVED WORKSPACE MOVED: %r (from %s) -> %r (from %s). That path is CANON_DIR, the '
            'symlink target for this box\'s shared AGENTS.md/TOOLS.md/USER.md — accepting this '
            'would trade a loud crash-loop for a silent one.'
            % (ws_b or '<none>', src_b, ws_a or '<none>', src_a))

    return failures


def _resolve_ref(doc, node, depth=0):
    """Follow a local `$ref` (#/a/b/c) one or more hops. Returns node or None."""
    while isinstance(node, dict) and '$ref' in node and depth < 16:
        ref = node.get('$ref')
        if not isinstance(ref, str) or not ref.startswith('#/'):
            return None
        cur = doc
        for part in ref[2:].split('/'):
            part = part.replace('~1', '/').replace('~0', '~')
            if not isinstance(cur, dict) or part not in cur:
                return None
            cur = cur[part]
        node = cur
        depth += 1
    return node


def _find_agents_props(doc):
    """Find the property names the schema allows under `agents`.

    Tries the obvious location first, then walks the whole document for any
    mapping whose key is `agents` and whose (possibly $ref'd) value declares
    `properties`. Deliberately conservative: it returns None rather than a
    guess, because the caller uses this to decide whether to REWRITE a live
    config, and a wrong answer there is a silent total outage.
    """
    direct = None
    if isinstance(doc, dict):
        props = doc.get('properties')
        if isinstance(props, dict) and 'agents' in props:
            direct = _resolve_ref(doc, props['agents'])
    if isinstance(direct, dict) and isinstance(direct.get('properties'), dict):
        return sorted(direct['properties'].keys())

    stack = [doc]
    seen = 0
    while stack and seen < 20000:
        node = stack.pop()
        seen += 1
        if isinstance(node, dict):
            for key, value in node.items():
                if key == 'agents':
                    resolved = _resolve_ref(doc, value)
                    if isinstance(resolved, dict) and isinstance(resolved.get('properties'), dict):
                        return sorted(resolved['properties'].keys())
                if isinstance(value, (dict, list)):
                    stack.append(value)
        elif isinstance(node, list):
            for value in node:
                if isinstance(value, (dict, list)):
                    stack.append(value)
    return None


def _usage(stream=sys.stderr):
    stream.write(
        'Usage:\n'
        '  oc-schema-migrate.py detect    <config>          # 0=clean 10=legacy 3=undetermined\n'
        '  oc-schema-migrate.py apply     <config> <out>    # 0=written 3=refused 1=write failed\n'
        '  oc-schema-migrate.py verify    <before> <after>  # 0=proven 1=FAILED 3=uncheckable\n'
        '  oc-schema-migrate.py workspace <config>          # prints the resolved workspace\n'
        '  oc-schema-migrate.py schema-keys <schema.json>   # 0=answered 3=undeterminable\n')


def main(argv):
    if len(argv) < 2:
        _usage()
        return EXIT_USAGE
    cmd = argv[1]

    if cmd == 'detect':
        if len(argv) != 3:
            _usage()
            return EXIT_USAGE
        try:
            payload = detect(argv[2])
        except Undetermined as e:
            print(json.dumps({'verdict': 'UNDETERMINED', 'detail': str(e), 'config': argv[2]},
                             sort_keys=True))
            return EXIT_UNDETERMINED
        print(json.dumps(payload, sort_keys=True))
        return EXIT_LEGACY if payload['verdict'] == 'LEGACY_LIST' else EXIT_OK

    if cmd == 'apply':
        if len(argv) != 4:
            _usage()
            return EXIT_USAGE
        src, out = argv[2], argv[3]
        try:
            cfg = _load(src)
            new_cfg = transform(cfg, src)
        except Undetermined as e:
            sys.stderr.write('REFUSED: %s\n' % e)
            return EXIT_UNDETERMINED
        indent = _sniff_indent(src)
        try:
            with open(out, 'w', encoding='utf-8') as fh:
                json.dump(new_cfg, fh, indent=indent, ensure_ascii=False)
                fh.write('\n')
        except Exception as e:
            sys.stderr.write('WRITE FAILED: could not write %s: %s\n' % (out, e))
            return EXIT_FAIL
        agents = new_cfg.get('agents') or {}
        sys.stderr.write('migrated %d agent(s) from `agents.%s` to `agents.%s` -> %s\n' % (
            len(agents.get(SCHEMA_KEY_NEW) or {}), SCHEMA_KEY_LEGACY, SCHEMA_KEY_NEW, out))
        return EXIT_OK

    if cmd == 'verify':
        if len(argv) != 4:
            _usage()
            return EXIT_USAGE
        try:
            failures = verify(argv[2], argv[3])
        except Undetermined as e:
            sys.stderr.write('UNDETERMINED: %s\n' % e)
            return EXIT_UNDETERMINED
        if failures:
            sys.stderr.write('MIGRATION VERIFICATION FAILED (%d):\n' % len(failures))
            for f in failures:
                sys.stderr.write('  - %s\n' % f)
            return EXIT_FAIL
        print('VERIFIED: migration is lossless')
        return EXIT_OK

    if cmd == 'workspace':
        if len(argv) != 3:
            _usage()
            return EXIT_USAGE
        try:
            cfg = _load(argv[2])
        except Undetermined:
            # An unreadable config has no resolvable workspace, and this
            # subcommand's contract is "print the answer or print nothing".
            # The CALLER's detect/verify step is what fails closed on
            # unreadability — duplicating that here would just make the
            # workspace probe a second, redundant failure path.
            return EXIT_OK
        ws, _src = resolve_workspace(cfg)
        sys.stdout.write(ws)
        return EXIT_OK

    if cmd == 'schema-keys':
        if len(argv) != 3:
            _usage()
            return EXIT_USAGE
        try:
            doc = _load(argv[2])
        except Undetermined as e:
            sys.stderr.write('UNDETERMINED: %s\n' % e)
            return EXIT_UNDETERMINED
        keys = _find_agents_props(doc)
        if keys is None:
            sys.stderr.write(
                'UNDETERMINED: could not locate the `agents` property set in %s. Refusing to guess '
                'which schema this binary speaks — the caller must NOT migrate on an unanswered '
                'schema probe.\n' % argv[2])
            return EXIT_UNDETERMINED
        for key in keys:
            print(key)
        return EXIT_OK

    _usage()
    return EXIT_USAGE


if __name__ == '__main__':
    sys.exit(main(sys.argv))
