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
// Unmapped / unknown department slugs default to the Technology cluster so
// the chart never drops a department silently. Add new mappings below as the
// canonical 16-dept list evolves.
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

const DEFAULT_CLUSTER = 'tec';

function slugify(s) {
  if (!s || typeof s !== 'string') return '';
  return s
    .toLowerCase()
    .replace(/&/g, 'and')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
}

function classify(depts) {
  const buckets = { ops: [], rev: [], cre: [], tec: [] };
  if (!Array.isArray(depts)) return buckets;
  depts.forEach((d) => {
    if (!d || typeof d !== 'object') return;
    const slug = slugify(d.slug || d.id || d.key || d.name || '');
    const cluster = CLUSTER_MAP[slug] || DEFAULT_CLUSTER;
    buckets[cluster].push({
      emoji: d.emoji || '',
      name: d.name || d.slug || d.id || 'Department',
      roles: Number(d.roles || d.rolesDone || 0)
    });
  });
  return buckets;
}

export { classify, slugify, CLUSTER_MAP, DEFAULT_CLUSTER };
