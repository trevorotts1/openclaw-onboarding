/**
 * CWE-045, finding F-4: the data-directory refusal boundary is EXACT.
 *
 * skillRootFromModule() previously climbed a fixed three levels from
 * the module directory, which is right for src/cli and dist/cli but
 * lands on the skill folder's PARENT for the bundled CLI
 * (dist/blackceo-council.mjs, one level shallower). resolveDataDir
 * therefore refused any data directory inside the parent folder, a
 * fail-closed superset of the Section 16.1 rule. These tests pin the
 * exact boundary: directories inside the skill tree (and the skill
 * root itself) are refused; directories outside it, including the
 * parent folder and siblings of the skill folder, are allowed.
 */

import assert from 'node:assert/strict';
import { existsSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { test } from 'node:test';

import { skillRootFromModule } from '../src/cli/dispatcher.js';
import { resolveDataDir } from '../src/cli/paths.js';

test('F-4: skillRootFromModule resolves the skill folder itself, not its parent', () => {
  const root = skillRootFromModule();
  assert.equal(root.split('/').at(-1), '77-council-of-wise-elders');
  assert.ok(existsSync(join(root, 'SKILL.md')), 'skill root carries SKILL.md');
  assert.ok(existsSync(join(root, 'runtime')), 'skill root carries the runtime directory');
  assert.ok(existsSync(join(root, 'advisors')), 'skill root carries the advisor packs');
});

test('F-4: data directories inside the skill tree are refused, exactly', () => {
  const root = skillRootFromModule();
  assert.throws(() => resolveDataDir({ override: root, skillRoot: root }), /inside the skill folder/);
  assert.throws(
    () => resolveDataDir({ override: join(root, 'state'), skillRoot: root }),
    /inside the skill folder/,
  );
  assert.throws(
    () => resolveDataDir({ override: join(root, 'runtime', 'state'), skillRoot: root }),
    /inside the skill folder/,
  );
  assert.throws(
    () => resolveDataDir({ override: join(root, 'advisors', 'oprah-winfrey', 'state'), skillRoot: root }),
    /inside the skill folder/,
  );
});

test('F-4: data directories outside the skill tree are allowed, including the parent folder', () => {
  const root = skillRootFromModule();
  const parent = dirname(root);
  // The parent folder itself: refused by the old superset boundary.
  assert.equal(resolveDataDir({ override: parent, skillRoot: root }), parent);
  // A sibling of the skill folder: refused by the old superset boundary.
  const sibling = join(parent, 'wise-elders-data');
  assert.equal(resolveDataDir({ override: sibling, skillRoot: root }), sibling);
  // A path that merely shares a string prefix with the skill root.
  const prefixSibling = join(parent, '77-council-of-wise-elders-data');
  assert.equal(resolveDataDir({ override: prefixSibling, skillRoot: root }), prefixSibling);
  // An unrelated absolute path.
  const elsewhere = join(parent, 'elsewhere', 'wise-elders');
  assert.equal(resolveDataDir({ override: elsewhere, skillRoot: root }), elsewhere);
});
