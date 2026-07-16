import { ScrollScrubEngine } from "@/components/ScrollScrubEngine";
import { SITE_DATA } from "@/lib/site-data.generated";
import { resolveGhlFormEmbeds } from "@/lib/resolve-ghl-embeds";

/**
 * The real Server/Client boundary for this app (build unit U16 QC fix): no
 * `"use client"` here or in any ancestor, so this is the one place a
 * dynamic `process.env[...]` lookup for a GHL embed URL is guaranteed to
 * run server-side. `resolveGhlFormEmbeds` reads those env vars once per
 * request and hands `ScrollScrubEngine` (a Client Component, and every
 * Client Component it renders) only the already-resolved result — never
 * the lookup itself. See `lib/resolve-ghl-embeds.ts` and
 * `components/GhlFormEmbed.tsx`.
 */
export default function Page() {
  const resolvedEmbeds = resolveGhlFormEmbeds(SITE_DATA.ctaMap);
  return (
    <main>
      <ScrollScrubEngine siteData={SITE_DATA} resolvedEmbeds={resolvedEmbeds} />
    </main>
  );
}
