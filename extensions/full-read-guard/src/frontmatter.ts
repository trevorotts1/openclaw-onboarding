// Tiny YAML-subset reader for SKILL.md frontmatter. No dependency.
// Understands: `key: value`, `key: [a, b]`, and block lists (`key:` followed by `- item` lines).
// Only the keys the guard needs are interpreted by callers: name, depends_on, lookup.

export type Frontmatter = Record<string, string | string[]>;

function unquote(s: string): string {
  const t = s.trim();
  if (t.length >= 2 && ((t[0] === '"' && t[t.length - 1] === '"') || (t[0] === "'" && t[t.length - 1] === "'"))) {
    return t.slice(1, -1);
  }
  return t;
}

function splitInline(list: string): string[] {
  const out: string[] = [];
  let cur = '';
  let quote = '';
  for (const ch of list) {
    if (quote) {
      if (ch === quote) quote = '';
      cur += ch;
    } else if (ch === '"' || ch === "'") {
      quote = ch;
      cur += ch;
    } else if (ch === ',') {
      out.push(cur);
      cur = '';
    } else cur += ch;
  }
  if (cur.trim() !== '') out.push(cur);
  return out.map(unquote).filter((x) => x !== '');
}

export function parseFrontmatter(text: string): Frontmatter {
  const result: Frontmatter = {};
  const norm = text.replace(/^﻿/, '').replace(/\r\n/g, '\n');
  if (!norm.startsWith('---\n')) return result;
  const end = norm.indexOf('\n---', 4);
  if (end === -1) return result;
  const lines = norm.slice(4, end).split('\n');
  let listKey: string | null = null;
  for (const raw of lines) {
    if (/^\s*#/.test(raw) || raw.trim() === '') continue;
    const item = /^\s+-\s+(.*)$/.exec(raw) || /^-\s+(.*)$/.exec(raw);
    if (item && listKey) {
      (result[listKey] as string[]).push(unquote(item[1]));
      continue;
    }
    const kv = /^([A-Za-z0-9_.-]+)\s*:\s*(.*)$/.exec(raw);
    if (!kv) continue;
    const key = kv[1];
    const value = kv[2].trim();
    if (value === '') {
      result[key] = [];
      listKey = key;
    } else if (value.startsWith('[') && value.endsWith(']')) {
      result[key] = splitInline(value.slice(1, -1));
      listKey = null;
    } else {
      result[key] = unquote(value);
      listKey = null;
    }
  }
  // A key that opened a block list but received no items is an empty string list; keep as [].
  return result;
}

export function asList(v: string | string[] | undefined): string[] {
  if (v === undefined) return [];
  return Array.isArray(v) ? v : v.trim() === '' ? [] : [v];
}
