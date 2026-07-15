"use client";

import type { SiteData } from "./types";
import { useScrollScrub } from "./useScrollScrub";
import { SceneVideoLayer } from "./SceneVideoLayer";
import { ReducedMotionFallback } from "./ReducedMotionFallback";
import { ConversionSections } from "./ConversionSection";
import { EmbedBridge } from "./EmbedBridge";
import styles from "./scroll-stage.module.css";

export interface ScrollScrubEngineProps {
  siteData: SiteData;
}

const VH_PER_SCENE = 150;

/**
 * Top-level page orchestrator: cinematic scroll-scrub stage (or its
 * `prefers-reduced-motion` static substitute) followed by the real-DOM
 * conversion sections, with a keyboard-reachable skip link ahead of both
 * (spec 13.4 "keyboard-accessible controls"; "no critical conversion action
 * may depend solely on animation" — the skip link lets any user, motion
 * preference aside, reach the offer immediately).
 */
export function ScrollScrubEngine({ siteData }: ScrollScrubEngineProps) {
  const { containerRef, registerVideoRef, blends, debugState, reducedMotion } = useScrollScrub(
    siteData.scenes,
  );

  const stageHeight = `${siteData.scenes.length * VH_PER_SCENE}vh`;

  return (
    <>
      <a href="#cwfe-conversion-start" className={styles.skipLink}>
        Skip cinematic intro
      </a>

      {reducedMotion ? (
        <ReducedMotionFallback scenes={siteData.scenes} />
      ) : (
        <div
          ref={containerRef}
          className={styles.stage}
          style={{ height: stageHeight }}
          data-cwfe-stage="true"
          data-cwfe-architecture={siteData.meta.architecture}
        >
          <div className={styles.stageSticky}>
            {siteData.scenes.map((scene) => {
              const blend = blends.find((b) => b.sceneId === scene.sceneId);
              if (!blend || !blend.shouldMount) return null;
              return (
                <SceneVideoLayer
                  key={scene.sceneId}
                  scene={scene}
                  blend={blend}
                  videoRef={registerVideoRef(scene.sceneId)}
                />
              );
            })}
          </div>
        </div>
      )}

      <div id="cwfe-conversion-start" className={styles.conversionAnchor} />
      <ConversionSections sections={siteData.sections} />

      <EmbedBridge debugState={debugState} embed={siteData.embed} />
    </>
  );
}
