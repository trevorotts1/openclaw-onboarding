# Council runtime rollback

Active release: `rel-7bdc0b6e3565`
Previous release: `rel-a1ab77dff250`
Prefix: `<operator-home>/.claude/state/council-elders/lanes/W11-U001-lane/prefix`

## Automated rollback

```bash
node "<operator-home>/.claude/state/council-elders/lanes/W11-U001-lane/repo/77-council-of-wise-elders/scripts/install-runtime.mjs" --prefix "<operator-home>/.claude/state/council-elders/lanes/W11-U001-lane/prefix" --rollback
```

This atomically re-points `active.json` at the previous verified release and
preserves the current receipt. Durable user data in the data directory is
never touched.

## Manual rollback

Restore `<operator-home>/.claude/state/council-elders/lanes/W11-U001-lane/prefix/previous-active.json` over `<operator-home>/.claude/state/council-elders/lanes/W11-U001-lane/prefix/active.json`.
Both files are written atomically by this installer; a manual copy is the
last resort if the installer is unavailable.

## Limits

A rollback re-points the executable. It does NOT downgrade or reverse a
schema migration. If a release applied a destructive migration, restore the
database backup taken by the owning application before that migration; the
application that owns the store, not this installer, applies migrations.
