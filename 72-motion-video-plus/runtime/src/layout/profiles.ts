// Safe-area profiles (Directive MG-014: "Derive safe areas from the
// actual player, caption, and overlay profile").
//
// A profile is a data record: the destination canvas it was measured
// for, the zones on that canvas the destination's own chrome occupies
// (caption rendering bands, a presenter picture-in-picture block, an
// overlay bug), and the source the numbers came from. A layout is
// judged against the profile of the player it will actually play in.
//
// The discipline the directive names is enforced in resolve.ts, not
// assumed here: a social-platform chrome profile is a legal profile
// only for a destination that explicitly declares platform delivery.
// The default mobile VSL plays in the VSL producer's player and uses
// that player's profile; it never inherits a social platform's
// like-rail and action bar.

import type { Box, Size } from "../compositing";

export type SafeAreaProfileKind = "clean" | "player" | "overlay" | "social_platform";

export interface UnsafeZone {
  id: string;
  box: Box;
  reason: string;
}

export interface SafeAreaProfile {
  id: string;
  kind: SafeAreaProfileKind;
  /** Where these numbers come from, stated in the record. */
  source: string;
  canvas: Size;
  unsafeZones: UnsafeZone[];
}

const PROFILES: SafeAreaProfile[] = [
  {
    id: "clean-full-frame-1920x1080",
    kind: "clean",
    source:
      "The destination renders the full frame with no overlay: a full-slide " +
      "PowerPoint placement or a clean desktop player. No chrome occupies " +
      "any part of the frame.",
    canvas: { width: 1920, height: 1080 },
    unsafeZones: [],
  },
  {
    id: "clean-full-frame-1080x1920",
    kind: "clean",
    source:
      "The parent VSL player profile for vertical inserts whose captions " +
      "ride the parent's caption track instead of a burned band: the player " +
      "draws no chrome over the insert's frame.",
    canvas: { width: 1080, height: 1920 },
    unsafeZones: [],
  },
  {
    id: "vsl-player-captions-1920x1080",
    kind: "player",
    source:
      "The VSL producer's desktop player renders captions in a band across " +
      "the bottom 120 px of the 1920x1080 frame when captions are on. A " +
      "desktop VSL insert must keep essential content out of that band.",
    canvas: { width: 1920, height: 1080 },
    unsafeZones: [
      {
        id: "caption-band",
        box: { x: 0, y: 960, width: 1920, height: 120 },
        reason: "player caption rendering band, bottom 120 px",
      },
    ],
  },
  {
    id: "vsl-player-captions-1080x1920",
    kind: "player",
    source:
      "The VSL producer's vertical player renders captions in a band " +
      "across the bottom 260 px of the 1080x1920 frame when captions are " +
      "on, and reserves the top 110 px for the player's title chrome. A " +
      "mobile VSL insert composed for this player keeps essential content " +
      "out of both zones.",
    canvas: { width: 1080, height: 1920 },
    unsafeZones: [
      {
        id: "caption-band",
        box: { x: 0, y: 1660, width: 1080, height: 260 },
        reason: "player caption rendering band, bottom 260 px",
      },
      {
        id: "player-title-chrome",
        box: { x: 0, y: 0, width: 1080, height: 110 },
        reason: "player title chrome across the top of the vertical frame",
      },
    ],
  },
  {
    id: "webinar-overlay-1920x1080",
    kind: "overlay",
    source:
      "The webinar composition the presentation pipeline ships: the " +
      "presenter's picture-in-picture block sits at the bottom right and " +
      "a lower-third name band runs along the bottom left when the " +
      "presenter is named. A graphic placed into that composition keeps " +
      "essential content out of both blocks.",
    canvas: { width: 1920, height: 1080 },
    unsafeZones: [
      {
        id: "presenter-pip",
        box: { x: 1452, y: 708, width: 468, height: 372 },
        reason: "presenter picture-in-picture block, bottom right",
      },
      {
        id: "lower-third",
        box: { x: 0, y: 928, width: 1150, height: 92 },
        reason: "lower-third presenter name band, bottom left",
      },
    ],
  },
  {
    id: "social-platform-1080x1920",
    kind: "social_platform",
    source:
      "A social platform's vertical player chrome: an action rail down " +
      "the right side and a caption/action zone across the bottom. Legal " +
      "ONLY for a destination that explicitly declares platform delivery; " +
      "a mobile VSL in the VSL producer's player does not carry this " +
      "chrome and must not be composed around it.",
    canvas: { width: 1080, height: 1920 },
    unsafeZones: [
      {
        id: "action-rail",
        box: { x: 948, y: 700, width: 132, height: 760 },
        reason: "platform action rail (like, comment, share) down the right side",
      },
      {
        id: "platform-caption-zone",
        box: { x: 0, y: 1560, width: 1080, height: 360 },
        reason: "platform caption and action zone across the bottom",
      },
    ],
  },
];

const BY_ID = new Map(PROFILES.map((p) => [p.id, p]));

export function getSafeAreaProfile(id: string): SafeAreaProfile | null {
  return BY_ID.get(id) ?? null;
}

export function listSafeAreaProfiles(): SafeAreaProfile[] {
  return [...PROFILES];
}
