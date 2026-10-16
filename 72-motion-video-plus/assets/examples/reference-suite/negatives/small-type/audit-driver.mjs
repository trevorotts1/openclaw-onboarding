import { readFileSync, writeFileSync } from "node:fs";
import { auditLayout } from "/home/hatch/workspace/skill72-v2/wt-mg044/72-motion-video-plus/runtime/dist/src/typography/audit.js";
import { loadTypographyTokens } from "/home/hatch/workspace/skill72-v2/wt-mg044/72-motion-video-plus/runtime/dist/src/typography/tokens.js";
const record = JSON.parse(readFileSync(process.argv[2], 'utf8'));
const tokens = loadTypographyTokens();
const result = auditLayout(record, tokens);
writeFileSync(process.argv[3], JSON.stringify(result, null, 2) + '\n');
console.log(JSON.stringify({ pass: result.pass, findings: result.findings.length }));
