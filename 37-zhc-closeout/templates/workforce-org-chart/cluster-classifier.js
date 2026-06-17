// cluster-classifier.js
// Maps the 16 canonical Zero-Human Company department slugs (per the
// department-naming-map in Skill 23) into the 4 visual clusters used in the
// workforce-structure infographic:
//
//   Operations  (navy   #1B2A4E)
//   Revenue     (gold   #C9A14B)
//   Creative    (teal   #2E8B8B)
//   Technology  (burgundy #7B2D3A)
//
// Classification order (v10.14.5):
//   1. exact slug match against CLUSTER_MAP
//   2. keyword fallback (substring scan against KEYWORDS) when a client's
//      dept slugs do not match the canonical naming map -- this is what
//      stopped a client's 7 non-canonical depts from all collapsing into the
//      Technology box.
//   3. last resort -> Technology
//   4. lopsidedness guard: if the result crams >5 depts into one cluster
//      while at least one other cluster is empty, fall back to a flat even
//      distribution across all 4 clusters so the chart never looks broken.
//
// Input:  array of { slug, name, roles, emoji? } (any order; emoji optional)
// Output: { ops: [...], rev: [...], cre: [...], tec: [...] } with the same
//         shape preserved.

'use strict';

const CLUSTER_MAP = {
  // Operations (navy) - the day-to-day machinery of the business.
  'executive-office':    'ops',
  'executive':           'ops',
  'operations':          'ops',
  'human-resources':     'ops',
  'hr':                  'ops',
  'risk-compliance':     'ops',
  'risk-and-compliance': 'ops',
  'compliance':          'ops',
  'risk':                'ops',
  'accounting':          'ops',
  'tax':                 'ops',
  'legal':               'ops',
  'openclaw-maintenance':'ops',
  'maintenance':         'ops',
  'billing-finance':     'ops',
  'finance':             'ops',
  'billing':             'ops',

  // Revenue (gold) - anything that brings money in.
  'sales':               'rev',
  'crm':                 'rev',
  'marketing':           'rev',
  'paid-advertising':    'rev',
  'paid-advertisement':  'rev',
  'paid-ads':            'rev',
  'paid-media':          'rev',
  'government-contracting':'rev',
  'gov-contracting':     'rev',
  'partnerships':        'rev',

  // Creative (teal) - anything that produces visual / audio / story output.
  'graphics':            'cre',
  'graphics-design':     'cre',
  'graphics-and-design': 'cre',
  'design':              'cre',
  'video':               'cre',
  'video-production':    'cre',
  'audio':               'cre',
  'audio-production':    'cre',
  'social-media':        'cre',
  'social':              'cre',
  'communications':      'cre',
  'comms':               'cre',
  'pr':                  'cre',
  'content':             'cre',

  // Technology (burgundy) - anything that ships software, support, or research.
  'app-development':     'tec',
  'app':                 'tec',
  'mobile':              'tec',
  'web-development':     'tec',
  'web':                 'tec',
  'customer-support':    'tec',
  'support':             'tec',
  'research':            'tec',
  'data':                'tec',
  'engineering':         'tec'
};

// Keyword fallback (v10.14.5). Each cluster lists substrings that, if found
// anywhere in the dept slug OR name, classify the dept into that cluster.
// Evaluated in array order; FIRST cluster with any hit wins. Order chosen so
// the most specific business intent wins (revenue/creative before the broad
// operations/technology buckets).
const KEYWORDS = {
  rev: [
    'sales', 'acquisition', 'crm', 'marketing', 'advertising', 'advertisement',
    'distribution', 'revenue', 'business-development', 'gov-contracting',
    'government', 'alumni', 'community', 'fundraising', 'partnership'
  ],
  cre: [
    'author', 'production', 'graphics', 'design', 'video', 'audio', 'social',
    'media', 'communications', 'comms', 'content', 'brand', 'creative'
  ],
  ops: [
    'executive', 'finance', 'operations', 'human-resources', 'risk',
    'compliance', 'legal', 'tax', 'accounting', 'admin', 'maintenance',
    'openclaw', 'strategy', 'billing'
    // note: bare 'hr' handled below to avoid matching words that contain "hr"
  ],
  tec: [
    'app', 'web', 'dev', 'development', 'support', 'research', 'data',
    'engineering', 'it', 'tech'
  ]
};

const KEYWORD_ORDER = ['rev', 'cre', 'ops', 'tec'];
const DEFAULT_CLUSTER = 'tec';
const LOPSIDED_LIMIT = 5; // >5 in one cluster while another is empty -> rebalance

function slugify(s) {
  if (!s || typeof s !== 'string') return '';
  return s
    .toLowerCase()
    .replace(/&/g, 'and')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
}

// Keyword fallback classifier. Returns a cluster key or null if no keyword hit.
function keywordCluster(slug, name) {
  const hay = (slug + ' ' + slugify(name || '')).replace(/-/g, ' ');
  // Special-case bare "hr" department (ops) without matching substrings like
  // "threshold" that merely contain the letters h-r.
  if (/\bhr\b/.test(hay)) return 'ops';
  for (const cluster of KEYWORD_ORDER) {
    for (const kw of KEYWORDS[cluster]) {
      if (hay.indexOf(kw) !== -1) return cluster;
    }
  }
  return null;
}

function classify(depts) {
  const buckets = { ops: [], rev: [], cre: [], tec: [] };
  if (!Array.isArray(depts)) return buckets;

  // Normalize once so we can rebalance later without losing dept payloads.
  const items = [];
  depts.forEach((d) => {
    if (!d || typeof d !== 'object') return;
    const slug = slugify(d.slug || d.id || d.key || d.name || '');
    const payload = {
      emoji: d.emoji || '',
      name: d.name || d.slug || d.id || 'Department',
      roles: Number(d.roles || d.rolesDone || 0)
    };
    items.push({ slug, name: payload.name, payload });
  });

  items.forEach((it) => {
    // 1. exact slug map  2. keyword fallback  3. last-resort Technology
    const cluster =
      CLUSTER_MAP[it.slug] || keywordCluster(it.slug, it.name) || DEFAULT_CLUSTER;
    buckets[cluster].push(it.payload);
  });

  // 4. Lopsidedness guard. If one cluster has > LOPSIDED_LIMIT depts while at
  // least one other cluster is empty, the classification is effectively broken
  // for the chart layout. Rebalance to a flat even spread across all 4.
  const keys = ['ops', 'rev', 'cre', 'tec'];
  const counts = keys.map((k) => buckets[k].length);
  const maxCount = Math.max(...counts);
  const anyEmpty = counts.some((c) => c === 0);
  if (maxCount > LOPSIDED_LIMIT && anyEmpty && items.length > 0) {
    const flat = { ops: [], rev: [], cre: [], tec: [] };
    items.forEach((it, i) => {
      flat[keys[i % keys.length]].push(it.payload);
    });
    return flat;
  }

  return buckets;
}

export { classify, slugify, keywordCluster, CLUSTER_MAP, KEYWORDS, DEFAULT_CLUSTER };
