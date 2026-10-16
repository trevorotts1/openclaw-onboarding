import { AbsoluteFill, useCurrentFrame } from "remotion";

// Invalid Remotion scene (MG-030 lint fixture): a CSS transition on a
// style object animates on the wall clock between frames, so the same
// frame number can paint differently depending on when it is sampled.
export function CssScene() {
  const frame = useCurrentFrame();
  return (
    <AbsoluteFill style={{ backgroundColor: "#F7F4EE" }}>
      <div
        style={{
          width: frame * 2,
          height: 90,
          backgroundColor: "#C04A26",
          transition: "width 0.3s",
        }}
      />
    </AbsoluteFill>
  );
}
