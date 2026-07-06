/**
 * Podcast Production Engine dashboard: client-safe formatting helpers.
 * No node-only imports here; this module ships to the browser bundle.
 */

import { formatDistanceToNow, format as formatDate } from 'date-fns';

/** Parse an engine timestamp (SQLite datetime('now'), UTC, no zone suffix). */
export function parseEngineTime(iso: string | null): Date | null {
  if (!iso) return null;
  const normalized = iso.includes('T') ? iso : iso.replace(' ', 'T');
  const withZone = /Z$|[+-]\d{2}:?\d{2}$/.test(normalized) ? normalized : normalized + 'Z';
  const d = new Date(withZone);
  return Number.isNaN(d.getTime()) ? null : d;
}

/** "3 hours ago" style relative time; empty string when unknown. */
export function relativeTime(iso: string | null): string {
  const d = parseEngineTime(iso);
  if (!d) return '';
  return formatDistanceToNow(d, { addSuffix: true });
}

/** Absolute timestamp for title attributes (accessibility, Section 14). */
export function absoluteTime(iso: string | null): string {
  const d = parseEngineTime(iso);
  if (!d) return '';
  return formatDate(d, 'yyyy-MM-dd HH:mm:ss');
}

/** Initials for the avatar circle. */
export function initialsOf(first: string | null, last: string | null): string {
  const f = (first ?? '').trim();
  const l = (last ?? '').trim();
  const a = f.length > 0 ? f[0] : '';
  const b = l.length > 0 ? l[0] : '';
  const joined = (a + b).toUpperCase();
  return joined.length > 0 ? joined : '?';
}

/** Deterministic avatar gradient index 1..5 from the submitter name. */
export function avatarGradientIndex(first: string | null, last: string | null): number {
  const name = `${first ?? ''} ${last ?? ''}`.trim() || 'unknown';
  let hash = 0;
  for (let i = 0; i < name.length; i += 1) {
    hash = (hash * 31 + name.charCodeAt(i)) >>> 0;
  }
  return (hash % 5) + 1;
}

/** Full display name with a graceful fallback for scrubbed rows. */
export function displayName(first: string | null, last: string | null): string {
  const joined = `${first ?? ''} ${last ?? ''}`.trim();
  return joined.length > 0 ? joined : 'Submitter';
}

/** "about N minutes" runtime copy (design Section 8.1 facts grid). */
export function runtimeCopy(runtimeMinutes: number | null): string {
  if (runtimeMinutes === null || runtimeMinutes === undefined) return '';
  return `about ${Math.round(runtimeMinutes)} minutes`;
}

/** Currency for operator surfaces. */
export function usd(value: number | null | undefined): string {
  if (value === null || value === undefined) return '$0.00';
  return `$${value.toFixed(2)}`;
}
