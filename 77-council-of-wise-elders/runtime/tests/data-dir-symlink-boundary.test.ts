/**
 * RP-046-2, finding F-046-1: the Section 16.1 data-directory refusal
 * must not be evadable by spelling.
 *
 * CWE-045's F-4 fix made the boundary exact for textual spellings, but
 * resolveDataDir compared path text against the skill root without
 * canonicalizing symlinks. On an installed machine the skill folder
 * itself is a symlink from the config root into the installed tree
 * (~/.claude/skills/council-of-wise-elders), so the same physical
 * location spelled through that symlink was ACCEPTED and a store
 * opened inside the synchronized tree (VERIFIED live by the CWE-046
 * canary; the physical spelling was refused correctly). These tests
 * pin the canonicalized boundary: inside-tree refused under every
 * spelling, genuinely outside paths still allowed. Fixtures are built
 * in this file's own scratch space.
 */

import assert from 'node:assert/strict';
import { mkdirSync, mkdtempSync, rmSync, symlinkSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { test, type TestContext } from 'node:test';

import { CouncilError } from '../src/cli/errors.js';
import { resolveDataDir } from '../src/cli/paths.js';

interface Fixture {
  scratch: string;
  /** Physical skill tree: <scratch>/installed/council-of-wise-elders */
  physicalRoot: string;
  /** Config-root spelling: <scratch>/config/skills/council-of-wise-elders (symlink to physicalRoot) */
  linkedRoot: string;
}

function makeFixture(t: TestContext): Fixture {
  const scratch = mkdtempSync(join(tmpdir(), 'cwe-f046-1-'));
  t.after(() => rmSync(scratch, { recursive: true, force: true }));
  const physicalRoot = join(scratch, 'installed', 'council-of-wise-elders');
  mkdirSync(join(physicalRoot, 'runtime'), { recursive: true });
  const skillsDir = join(scratch, 'config', 'skills');
  mkdirSync(skillsDir, { recursive: true });
  const linkedRoot = join(skillsDir, 'council-of-wise-elders');
  symlinkSync(physicalRoot, linkedRoot, 'dir');
  return { scratch, physicalRoot, linkedRoot };
}

function assertRefused(fn: () => unknown): void {
  assert.throws(fn, (err: unknown) => {
    assert.ok(err instanceof CouncilError, 'refusal is the typed CouncilError');
    assert.equal(err.code, 'COUNCIL_INVALID_INPUT');
    assert.equal(err.exitCode, 2);
    assert.match(err.message, /inside the skill folder/);
    return true;
  });
}

test('F-046-1 (a): a data dir spelled through the symlinked skill root is refused', (t) => {
  const { physicalRoot, linkedRoot } = makeFixture(t);
  // The canary spelling: the store directory already exists, created
  // through the symlink, exactly as the live probe created it.
  mkdirSync(join(linkedRoot, 'state'), { recursive: true });
  assertRefused(() =>
    resolveDataDir({ override: join(linkedRoot, 'state'), skillRoot: physicalRoot }),
  );
  // The symlinked root itself, spelled through the symlink.
  assertRefused(() => resolveDataDir({ override: linkedRoot, skillRoot: physicalRoot }));
  // Reverse direction: physical data dir, skill root spelled via the symlink.
  assertRefused(() =>
    resolveDataDir({ override: join(physicalRoot, 'state'), skillRoot: linkedRoot }),
  );
  // A not-yet-existing directory below the symlinked root.
  assertRefused(() =>
    resolveDataDir({ override: join(linkedRoot, 'new-state', 'db'), skillRoot: physicalRoot }),
  );
});

test('F-046-1 (b): a data dir under a symlinked ancestor that resolves inside the tree is refused', (t) => {
  const { scratch, physicalRoot } = makeFixture(t);
  // An ancestor symlink that points INTO the tree (at a subtree), so
  // no path segment names the skill root at all.
  const ancestorLink = join(scratch, 'innocent-name');
  symlinkSync(join(physicalRoot, 'runtime'), ancestorLink, 'dir');
  assertRefused(() =>
    resolveDataDir({ override: join(ancestorLink, 'state'), skillRoot: physicalRoot }),
  );
  // The target directory does not exist yet: canonicalizing the
  // nearest existing ancestor must still expose the smuggled path.
  assertRefused(() =>
    resolveDataDir({ override: join(ancestorLink, 'deep', 'state'), skillRoot: physicalRoot }),
  );
});

test('F-046-1 (c): the physical spelling stays refused', (t) => {
  const { physicalRoot } = makeFixture(t);
  assertRefused(() => resolveDataDir({ override: physicalRoot, skillRoot: physicalRoot }));
  assertRefused(() =>
    resolveDataDir({ override: join(physicalRoot, 'state'), skillRoot: physicalRoot }),
  );
  assertRefused(() =>
    resolveDataDir({ override: join(physicalRoot, 'runtime', 'state'), skillRoot: physicalRoot }),
  );
});

test('F-046-1 (d): a symlinked path that resolves outside the tree stays allowed', (t) => {
  const { scratch, physicalRoot } = makeFixture(t);
  const outside = join(scratch, 'outside-data');
  mkdirSync(outside, { recursive: true });
  const outsideLink = join(scratch, 'data-link');
  symlinkSync(outside, outsideLink, 'dir');
  // The symlink itself as the data dir: resolves outside, allowed, and
  // the caller's spelling is returned unchanged (F-4 semantics).
  assert.equal(resolveDataDir({ override: outsideLink, skillRoot: physicalRoot }), outsideLink);
  // A not-yet-existing directory below the outside symlink.
  const below = join(outsideLink, 'council');
  assert.equal(resolveDataDir({ override: below, skillRoot: physicalRoot }), below);
  // A sibling of the skill root reached through a symlinked parent:
  // the parent resolves outside the tree, so the sibling stays allowed.
  const installedLink = join(scratch, 'installed-link');
  symlinkSync(join(scratch, 'installed'), installedLink, 'dir');
  const sibling = join(installedLink, 'wise-elders-data');
  assert.equal(resolveDataDir({ override: sibling, skillRoot: physicalRoot }), sibling);
});

test('F-046-1 (e): F-4 exactness survives canonicalization for outside spellings', (t) => {
  const { scratch, physicalRoot } = makeFixture(t);
  // The parent of the skill root, spelled through a symlinked ancestor:
  // genuinely outside, stays allowed (F-4 allowed the parent itself).
  const installedLink = join(scratch, 'installed-link');
  symlinkSync(join(scratch, 'installed'), installedLink, 'dir');
  assert.equal(
    resolveDataDir({ override: installedLink, skillRoot: physicalRoot }),
    installedLink,
  );
  // A prefix-sharing sibling name reached through the same symlink:
  // its canonical form shares a string prefix with the canonical root
  // but is not inside it, so it stays allowed.
  const prefixSibling = join(installedLink, 'council-of-wise-elders-data');
  assert.equal(
    resolveDataDir({ override: prefixSibling, skillRoot: physicalRoot }),
    prefixSibling,
  );
});
