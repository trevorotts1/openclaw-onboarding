// Bundle entry point for the Remotion adapter. The bundler
// (@remotion/bundler from the shared runtime) bundles this file and the
// composition tree it registers; the adapter passes this file's path as
// the bundle entry point. Kept separate from Root.ts so the registered
// root stays importable without side effects.
import { registerRoot } from "remotion";
import { RemotionRoot } from "./Root";

registerRoot(RemotionRoot);
