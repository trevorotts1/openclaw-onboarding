# Command Center tenant configuration before rollout

Every client deployment must have its own registered public hostname, canonical database company ID, stable installation ID, and stable tenant ID. Preserve these IDs across interview edits, updates, and retries. Do not derive the database ID from a display name or substitute another client's resources.

Before upgrading, the operator must configure the Command Center service environment (the enrollment and remote receiver details are in the paired Command Center repository's `docs/tenant-interview-rollout.md`):

- `MC_INSTALLATION_ID`: this installation's persistent ID.
- `MC_TENANT_REGISTRY_JSON`: an explicit hostname entry with `kind: "self"`, this `tenantId`, `companyId`, `installationId`, and either the authorized Cloudflare Access `subjects`, `issuer`, `audience`, or an explicitly issued signed enrollment invitation.
- `MC_TENANT_SESSION_SECRET` and the client-owned `MC_API_TOKEN`: private service secrets.
- `MC_INTERVIEW_REMOTE_SECRET` when this client serves the shared remote interview interface. Its central client mapping must point at this own URL and matching installation identity.

The Command Center service also requires `MC_PERSONA_COMPANY_CONTEXTS_JSON`, keyed by the same canonical database company ID. Each value supplies absolute `companyRoot`, absolute `companyConfig`, canonical `companySlug`, and absolute `personaCatalog` for that client. The company root is its own `zero-human-company/<canonical-slug>` directory; the company config must identify that same company; the persona catalog is the verified catalog intended for that deployment. Do not use discovery by newest folder or copy another client's configuration. Verify each path is readable by the Command Center service user. The authenticated readiness probe must report this mapping ready before activation; missing mappings block persona-governed tasks.

An operator prepares this JSON from the canonical state/config and installed paths, adds it to the service's own persistent environment, then re-runs the authenticated readiness check. This template does not guess an installation path or database UUID and does not silently modify a running service environment.

The installer verification environment also needs `MC_TENANT_ID`, `MC_COMPANY_ID`, `MC_INSTALLATION_ID`, `MC_TENANT_PUBLIC_URL` (the client's own HTTPS origin), and `MC_API_TOKEN`. Set `MC_REQUIRE_REMOTE_RECEIVER=1` when shared remote interviews are enabled. These are operator inputs; this template deliberately does not generate example production identities or copy secrets between clients.

Run `python3 32-command-center-setup/scripts/verify-tenant-readiness.py /exact/company/build-state.json`. The read-only authenticated request to the exact origin's `/api/auth/tenant-ready` must return matching tenant, company, installation, host and protocol identities. The verifier rejects redirects, missing configuration, mismatches, and unavailable receiver capabilities. It records `commandCenterTenantReady` and the verification result in that build state. The full installer performs this check before its final status. Until it passes, Command Center and closeout remain pending/degraded, and recovery stays available.

Publishing a repository release does not deploy or enroll a client. Deployment requires configuring each client and verifying its own receipt after upgrade. No owner messages or invitation sends occur automatically as part of this verifier.
