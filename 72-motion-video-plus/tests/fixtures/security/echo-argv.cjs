// MG-029 fixture: print argv as JSON. Proves command-like copy passed
// as a single argument arrives verbatim and is never shell-split or
// executed.
"use strict";
process.stdout.write(JSON.stringify(process.argv.slice(2)) + "\n");
