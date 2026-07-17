"use client";

import { useEffect, useRef, useState } from "react";
import type { SceneConfig } from "./types";
import type { SceneBlend } from "./useScrollScrub";
import styles from "./scroll-stage.module.css";

export interface SceneVideoLayerProps {
  scene: SceneConfig;
  blend: SceneBlend;
  videoRef: (el: HTMLVideoElement | null) => void;
}

/**
 * One scene's video/poster pair. Rendering (not rendering) this component
 * at all is the mount-radius preload gate from useScrollScrub; once
 * mounted, it still shows the poster image until the browser reports the
 * video has decoded at least the current frame (spec 13.2 "provide poster
 * fallback"), and it never calls `.play()` — useScrollScrub drives
 * `currentTime` directly, and playback stays muted+inline so browser
 * autoplay policies never block it (spec 13.2/13.3).
 */
export function SceneVideoLayer({ scene, blend, videoRef }: SceneVideoLayerProps) {
  const [ready, setReady] = useState(false);
  const elRef = useRef<HTMLVideoElement | null>(null);

  useEffect(() => {
    const video = elRef.current;
    if (!video) return;
    const onLoadedData = () => setReady(true);
    video.addEventListener("loadeddata", onLoadedData);
    if (video.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA) setReady(true);
    return () => video.removeEventListener("loadeddata", onLoadedData);
  }, []);

  return (
    <div
      className={styles.sceneLayer}
      data-cwfe-scene-id={scene.sceneId}
      data-cwfe-scene-ready={ready ? "true" : "false"}
      style={{ opacity: blend.opacity, zIndex: blend.zIndex }}
      aria-hidden={blend.opacity < 0.05}
    >
      {/* Decorative motion-still: alt="" + role="presentation" is the
          correct a11y treatment (jsx-a11y/alt-text passes it as-is) — the
          real content lives in ConversionSection's DOM text (spec 13.3). */}
      <img
        src={scene.posterSrc}
        alt=""
        role="presentation"
        className={styles.poster}
        style={{ opacity: ready ? 0 : 1 }}
        loading="lazy"
      />
      <video
        ref={(el) => {
          elRef.current = el;
          videoRef(el);
        }}
        className={styles.video}
        style={{ opacity: ready ? 1 : 0 }}
        src={scene.videoSrc}
        muted
        playsInline
        preload={blend.shouldMount ? "auto" : "none"}
        aria-hidden="true"
        tabIndex={-1}
        data-cwfe-scene-video={scene.sceneId}
      />
    </div>
  );
}
