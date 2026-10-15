// Seek harness for standalone __setTime scenes (Directive MG-026).
// The two production adapters drive their engines' controlled
// timelines (Remotion's frame clock, the Hyperframes snapshot clock).
// The legacy __setTime surface has no adapter in the V2 runtime, but
// its purity rule is the same rule the adapters rely on: a frame must
// be a pure function of the time it is asked for. This harness drives
// a standalone scene page in the pinned chrome-headless-shell through
// puppeteer-core (resolved from the shared runtime install, the same
// way the Remotion adapter resolves its modules), applies a seek
// sequence, and captures the resulting frame as a PNG. The verifier
// feeds it the determinism fixtures: a seeded control scene that must
// capture identically under every seek history, and drift fixtures
// whose rendering secretly depends on wall clock time or unseeded
// randomness and must not.

import { createRequire } from "node:module";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import { resolveSharedRuntime } from "../adapters/hyperframes";

interface PuppeteerPage {
  setViewport(viewport: { width: number; height: number; deviceScaleFactor?: number }): Promise<unknown>;
  goto(url: string, opts?: { waitUntil?: string; timeout?: number }): Promise<unknown>;
  evaluate(fn: string | ((...args: never[]) => unknown), ...args: unknown[]): Promise<unknown>;
  screenshot(opts: { path: string; type?: string }): Promise<unknown>;
}

interface PuppeteerBrowser {
  newPage(): Promise<PuppeteerPage>;
  close(): Promise<void>;
}

interface PuppeteerModule {
  launch(opts: {
    executablePath: string;
    headless: boolean;
    args: string[];
    userDataDir: string;
  }): Promise<PuppeteerBrowser>;
}

function puppeteerModule(): PuppeteerModule {
  const runtime = resolveSharedRuntime();
  const req = createRequire(join(runtime.currentDir, "package.json"));
  return req("puppeteer-core") as PuppeteerModule;
}

function browserExecutable(): string {
  const runtime = resolveSharedRuntime();
  return join(
    runtime.currentDir,
    "node_modules/.remotion/chrome-headless-shell/linux64/chrome-headless-shell-linux64/chrome-headless-shell"
  );
}

export interface SceneCaptureOptions {
  /** Path to the scene HTML file (a fixture under tests/fixtures). */
  htmlPath: string;
  width: number;
  height: number;
  /** Times (seconds) applied in order through window.__setTime. The
   * screenshot is taken after the final seek. */
  seeks: number[];
  /** Real wall-clock milliseconds to wait immediately before the
   * final seek. A scene that secretly reads the wall clock renders
   * differently after this wait; a pure scene does not notice it. */
  waitBeforeFinalSeekMs?: number;
  /** Where the captured PNG is written. */
  outPath: string;
  /** Fresh browser profile directory for this capture. */
  profileDir: string;
}

const sleep = (ms: number): Promise<void> => new Promise((r) => setTimeout(r, ms));

/** Load a scene in a fresh browser process, apply the seek sequence,
 * and capture the frame after the final seek. Fonts are awaited before
 * the first seek, matching the "wait for assets" clause of the seek
 * contract. */
export async function captureSceneFrame(opts: SceneCaptureOptions): Promise<void> {
  const puppeteer = puppeteerModule();
  const browser = await puppeteer.launch({
    executablePath: browserExecutable(),
    headless: true,
    args: ["--no-sandbox", "--disable-dev-shm-usage", "--force-color-profile=srgb"],
    userDataDir: opts.profileDir,
  });
  try {
    const page = await browser.newPage();
    await page.setViewport({ width: opts.width, height: opts.height, deviceScaleFactor: 1 });
    await page.goto(pathToFileURL(opts.htmlPath).href, { waitUntil: "load", timeout: 60000 });
    await page.evaluate("document.fonts.ready.then(() => true)");
    const seeks = opts.seeks;
    for (let i = 0; i < seeks.length; i += 1) {
      const isFinal = i === seeks.length - 1;
      if (isFinal && opts.waitBeforeFinalSeekMs && opts.waitBeforeFinalSeekMs > 0) {
        await sleep(opts.waitBeforeFinalSeekMs);
      }
      const t = seeks[i];
      await page.evaluate(`window.__setTime(${JSON.stringify(t)})`);
      // Let the seek paint before any screenshot or further seek, the
      // same discipline the production snapshot path applies.
      await page.evaluate(
        "new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)))"
      );
    }
    await page.screenshot({ path: opts.outPath, type: "png" });
  } finally {
    await browser.close();
  }
}
