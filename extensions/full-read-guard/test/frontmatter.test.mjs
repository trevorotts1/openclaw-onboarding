import test from 'node:test';
import assert from 'node:assert/strict';
import { parseFrontmatter, asList } from '../dist/index.js';

test('inline list, block list, scalar, quotes', () => {
  const fm = parseFrontmatter('---\nname: "alpha"\ndescription: Does things: with colons\ndepends_on: [a, "b c", \'d\']\nlookup:\n  - x/*.md\n  - "y.json"\n---\nbody');
  assert.equal(fm.name, 'alpha');
  assert.equal(fm.description, 'Does things: with colons');
  assert.deepEqual(fm.depends_on, ['a', 'b c', 'd']);
  assert.deepEqual(fm.lookup, ['x/*.md', 'y.json']);
});

test('no frontmatter returns empty object', () => {
  assert.deepEqual(parseFrontmatter('# Title\nno frontmatter'), {});
  assert.deepEqual(parseFrontmatter('---\nname: x\nnever closed'), {});
});

test('CRLF line endings and BOM are handled', () => {
  const fm = parseFrontmatter('﻿---\r\nname: crlf\r\ndepends_on:\r\n  - one\r\n  - two\r\n---\r\nbody');
  assert.equal(fm.name, 'crlf');
  assert.deepEqual(fm.depends_on, ['one', 'two']);
});

test('empty key opens an empty list; comments and blank lines are ignored', () => {
  const fm = parseFrontmatter('---\n# comment\n\nlookup:\nname: n\n---\n');
  assert.deepEqual(fm.lookup, []);
  assert.equal(fm.name, 'n');
});

test('asList normalises scalar, list and undefined', () => {
  assert.deepEqual(asList(undefined), []);
  assert.deepEqual(asList('one'), ['one']);
  assert.deepEqual(asList(['a', 'b']), ['a', 'b']);
  assert.deepEqual(asList(''), []);
});
