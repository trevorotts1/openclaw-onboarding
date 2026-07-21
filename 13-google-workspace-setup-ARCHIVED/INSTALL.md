# ARCHIVED — DO NOT RUN — Skill 13 installation guide

> **There is no installation procedure for this skill any more. Do not run it.**
>
> **Successor: Skill 14 — Google Workspace Integration (`14-google-workspace-integration/`).**

The procedure this file used to carry created a Google Cloud project, enabled six
APIs, created a service account, downloaded a JSON key to disk and configured
Domain-Wide Delegation, all at install time. The fleet reaches Google through
per-session MCP authentication now, so that key material has no consumer and
should not be created. Parts of the procedure also deferred to a skill number and
a helper script that do not exist in this repository, so an agent following it
stalls partway through with nothing to run.

To install the live skill, follow `14-google-workspace-integration/INSTALL.md`.

See `SKILL.md` and `ARCHIVED.md` in this folder for the capability map.
