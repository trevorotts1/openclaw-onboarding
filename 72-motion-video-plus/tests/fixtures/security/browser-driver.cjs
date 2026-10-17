// MG-029 fixture: drive the provisioned Chromium through
// puppeteer-core (the same control path the render engines use),
// load a file:// page, wait, and print the serialized DOM. The
// dump-dom headless flag proved unreliable on this machine; this
// driver is not.
//
// argv: node browser-driver.cjs <puppeteerCoreDir> <chromePath>
//       <profileDir> <htmlPath> <waitMs>
"use strict";
const puppeteer = require(process.argv[2]);
(async () => {
  const browser = await puppeteer.launch({
    executablePath: process.argv[3],
    headless: true,
    args: [
      "--no-sandbox",
      "--disable-dev-shm-usage",
      "--disable-gpu",
      "--user-data-dir=" + process.argv[4],
    ],
  });
  try {
    const page = await browser.newPage();
    await page.goto("file://" + process.argv[5], {
      waitUntil: "load",
      timeout: 30000,
    });
    await new Promise((r) => setTimeout(r, Number(process.argv[6] || "6000")));
    const html = await page.evaluate(() => document.documentElement.outerHTML);
    process.stdout.write(html);
  } finally {
    await browser.close();
  }
})().catch((e) => {
  process.stderr.write("browser-driver error: " + (e && e.message) + "\n");
  process.exit(1);
});
