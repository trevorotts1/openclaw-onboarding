import type { CopySection } from "./types";
import styles from "./scroll-stage.module.css";

export interface ConversionSectionsProps {
  sections: CopySection[];
}

/**
 * Renders the locked content-manifest's approved copy sections as real DOM
 * text (spec 13.3: "headlines and body copy as real DOM text"; "no critical
 * conversion action may depend solely on animation"). These fragments are
 * resolved at generation time by scripts/build_site.py from a locked
 * content-manifest.json's `approved_copy_paths` — filesystem paths into a
 * delegate skill's own sacred-copy artifacts (ADR-10) or this engine's own
 * fixture fragments, never text this component (or an LLM at request time)
 * authors. That is what makes `dangerouslySetInnerHTML` here safe and
 * correct rather than an XSS smell: the HTML is a build-time, locally
 * resolved, already-approved artifact — not runtime user input.
 *
 * This block renders AFTER the cinematic scroll stage in both the normal
 * and the `prefers-reduced-motion` layouts (ScrollScrubEngine), so every
 * CTA, form, and offer stays reachable and complete even with zero motion.
 *
 * Defense-in-depth: scripts/build_site.py additionally strips
 * `<script>`/`<style>` tags, `on*=` event-handler attributes, and
 * `javascript:`-scheme URLs out of every fragment BEFORE it is written into
 * `lib/site-data.generated.ts` (see `sanitize_copy_fragment()`), so this
 * component never receives markup it hasn't already had adversarial content
 * removed from, even though the source fragments are locked/approved and
 * not runtime user input.
 */
export function ConversionSections({ sections }: ConversionSectionsProps) {
  return (
    <div className={styles.conversionStack} data-cwfe-conversion-sections="true">
      {sections.map((section) => (
        <section
          key={section.id}
          id={section.id}
          className={styles.conversionSection}
          dangerouslySetInnerHTML={{ __html: section.html }}
        />
      ))}
    </div>
  );
}
