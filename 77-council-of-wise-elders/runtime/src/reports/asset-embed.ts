/**
 * CTR-147/CTR-150/CTR-154: packaged report display assets.
 *
 * The print document is rendered offline by the host PDF capability, so
 * every image it uses must already be inside the document as a base64
 * data URI. These helpers read packaged display files and return that
 * data URI; the HTML never carries a local file path and no renderer
 * ever fetches a network asset.
 *
 * Resolution mirrors the chamber asset roots in the front door so the
 * same files are found from the TypeScript source, the tsc output and
 * the esbuild single-file bundle. A missing packaged asset returns null:
 * the document then omits the image instead of inventing one or printing
 * a broken image.
 *
 * CTR-150: the report cover uses the nine portraits the chamber already
 * serves, in the shared seat order, rather than the empty-table
 * `assets/seats/cover.png`. Only the fixed seat ids below are readable;
 * a caller can never use this module to read an arbitrary local file.
 * The portrait files stay in `public/chamber/portraits` and are already
 * packaged by `package.json#files`; no duplicate copies are created.
 *
 * The originals live under `assets/report` and `assets/seats` and are
 * never rewritten here. `public/report/ASSET-MANIFEST.json` records the
 * KIE source and derivative hashes.
 */

import { readFileSync } from 'node:fs';

const REPORT_ASSET_ROOTS: readonly URL[] = [
  new URL('../../public/report/', import.meta.url),
  new URL('../public/report/', import.meta.url),
];

const CHAMBER_PORTRAIT_ROOTS: readonly URL[] = [
  new URL('../../public/chamber/portraits/', import.meta.url),
  new URL('../public/chamber/portraits/', import.meta.url),
];

export const REPORT_COVER_ASSET = 'cover-report.webp';
export const REPORT_FRAME_ASSET = 'council-page-frame-a4.webp';
export const REPORT_DIVIDER_ASSET = 'council-section-divider-wide.webp';

const REPORT_ASSET_NAMES: ReadonlySet<string> = new Set([
  REPORT_COVER_ASSET,
  REPORT_FRAME_ASSET,
  REPORT_DIVIDER_ASSET,
]);

const dataUriCache = new Map<string, string | null>();

function toDataUri(url: URL, mime: string): string | null {
  try {
    return `data:${mime};base64,${readFileSync(url).toString('base64')}`;
  } catch {
    return null;
  }
}

/**
 * One packaged report asset as a data URI, or null when it is absent or
 * not one of the fixed packaged names. The allowlist means a caller
 * cannot turn this helper into an arbitrary local-file read.
 */
export function loadReportAssetDataUri(
  name: string,
  mime: string = 'image/webp',
): string | null {
  if (!REPORT_ASSET_NAMES.has(name)) return null;
  const key = `${mime}:${name}`;
  const cached = dataUriCache.get(key);
  if (cached !== undefined) return cached;
  let uri: string | null = null;
  for (const root of REPORT_ASSET_ROOTS) {
    uri = toDataUri(new URL(name, root), mime);
    if (uri !== null) break;
  }
  dataUriCache.set(key, uri);
  return uri;
}

/** The compressed derivative of the exact Council hero (`assets/seats/cover.png`). */
export function loadReportCoverDataUri(): string | null {
  return loadReportAssetDataUri(REPORT_COVER_ASSET);
}

/** The KIE page-frame plate, as a compressed display derivative. */
export function loadReportFrameDataUri(): string | null {
  return loadReportAssetDataUri(REPORT_FRAME_ASSET);
}

/** The KIE section divider, as a compressed display derivative. */
export function loadReportDividerDataUri(): string | null {
  return loadReportAssetDataUri(REPORT_DIVIDER_ASSET);
}

export interface ReportSeatPortrait {
  seat_id: string;
  display_name: string;
  /** File name inside `public/chamber/portraits`; never a path. */
  file_name: string;
}

/**
 * The shared nine-seat order, copied from `config/advisors.json` (order
 * 1-9) and `public/chamber/chamber-seats.js` (`SEATS`). The unexecuted
 * CTR-150 regression pins this array against `config/advisors.json`.
 */
export const REPORT_SEAT_PORTRAITS: readonly ReportSeatPortrait[] = [
  { seat_id: 'simon-sinek', display_name: 'Simon Sinek', file_name: 'simon-sinek.webp' },
  { seat_id: 'td-jakes', display_name: 'T. D. Jakes', file_name: 'td-jakes.webp' },
  { seat_id: 'oprah-winfrey', display_name: 'Oprah Winfrey', file_name: 'oprah-winfrey.webp' },
  { seat_id: 'tiffany-aliche', display_name: 'Tiffany Aliche', file_name: 'tiffany-aliche.webp' },
  { seat_id: 'russell-brunson', display_name: 'Russell Brunson', file_name: 'russell-brunson.webp' },
  { seat_id: 'michelle-obama', display_name: 'Michelle Obama', file_name: 'michelle-obama.webp' },
  { seat_id: 'brene-brown', display_name: 'Brené Brown', file_name: 'brene-brown.webp' },
  { seat_id: 'dennis-kimbro', display_name: 'Dr. Dennis Kimbro', file_name: 'dennis-kimbro.webp' },
  { seat_id: 'les-brown', display_name: 'Les Brown', file_name: 'les-brown.webp' },
];

/**
 * One served chamber portrait as a data URI. Unknown ids return null so
 * the caller cannot turn this into an arbitrary file read.
 *
 * CTR-154: never call this for a redacted export. `service.ts` states
 * that a redacted report embeds no image bytes because a redaction target
 * cannot be proven absent from compressed pixels. The cover renderer
 * skips portraits and static seat names entirely when `model.redacted`
 * is true; this helper stays a pure asset read so the policy lives in one
 * place rather than being re-derived from the model here.
 */
export function loadReportPortraitDataUri(seatId: string): string | null {
  const seat = REPORT_SEAT_PORTRAITS.find((entry) => entry.seat_id === seatId);
  if (seat === undefined) return null;
  const key = `portrait:${seat.seat_id}`;
  const cached = dataUriCache.get(key);
  if (cached !== undefined) return cached;
  let uri: string | null = null;
  for (const root of CHAMBER_PORTRAIT_ROOTS) {
    uri = toDataUri(new URL(seat.file_name, root), 'image/webp');
    if (uri !== null) break;
  }
  dataUriCache.set(key, uri);
  return uri;
}
