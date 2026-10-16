// MG-029 fixture: print the process environment as JSON so tests can
// prove exactly what a render child can see. Not a secret itself; it
// reports whatever environment it was launched with.
"use strict";
const out = {};
for (const key of Object.keys(process.env).sort()) out[key] = process.env[key];
process.stdout.write(JSON.stringify(out) + "\n");
