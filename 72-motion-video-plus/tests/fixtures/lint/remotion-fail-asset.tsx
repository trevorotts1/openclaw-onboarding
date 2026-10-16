import { AbsoluteFill, useCurrentFrame } from "remotion";

// Invalid Remotion scene (MG-030 lint fixture): a network fetch during
// render means the scene's assets are not ready before frame 0; the
// frame can wait on, or differ by, network timing.
export function AssetScene() {
  const frame = useCurrentFrame();
  fetch("https://example.com/data.json");
  return (
    <AbsoluteFill style={{ backgroundColor: "#F7F4EE" }}>
      <div style={{ width: frame, height: 90, backgroundColor: "#C04A26" }} />
    </AbsoluteFill>
  );
}
