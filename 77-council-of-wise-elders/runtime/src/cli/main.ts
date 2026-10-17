#!/usr/bin/env node
/**
 * blackceo-council executable entry point (CWE-004).
 *
 * Importing this module only wires the dispatcher; running it executes
 * exactly one command and exits with the command's exit code. It never
 * opens a database, starts a job, or spends a provider request at
 * import time.
 */
import { runCli } from './dispatcher.js';

process.exitCode = await runCli(process.argv.slice(2));
