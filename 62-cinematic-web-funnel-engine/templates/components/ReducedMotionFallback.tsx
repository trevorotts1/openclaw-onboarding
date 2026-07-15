import type { SceneConfig } from "./types";
import styles from "./scroll-stage.module.css";

export interface ReducedMotionFallbackProps {
  scenes: SceneConfig[];
}

/**
 * Static, complete substitute for the scroll-scrub stage when the browser
 * reports `prefers-reduced-motion: reduce` (spec 13.4: "`prefers-reduced-
 * motion` mode that disables scroll scrubbing and presents static or
 * minimally animated content"; "content remains complete without video").
 *
 * Each scene renders as its poster image only — no <video> element is
 * mounted at all, so there is nothing to scrub and nothing that can
 * autoplay motion a user asked not to see.
 */
export function ReducedMotionFallback({ scenes }: ReducedMotionFallbackProps) {
  return (
    <div className={styles.reducedMotionStage} data-cwfe-reduced-motion="true">
      {scenes.map((scene) => (
        <figure key={scene.sceneId} className={styles.reducedMotionScene}>
          <img src={scene.posterSrc} alt="" role="presentation" className={styles.reducedMotionPoster} />
        </figure>
      ))}
    </div>
  );
}
