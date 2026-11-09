# Classic community privacy and access controls

`community_access.py` implements the captured classic Settings > Details controls
for Public/Private, Accessible from switcher, Allow members to invite, and Show
mandatory profile modal. The portal must already be authenticated through the
existing trusted host. This module has no login, alternate tenant or activation
fallback. A Forbidden/new portal surface remains an access/capture stop.

Use the synthetic JSON example as a schema reference, not as a ready client job.
`access.expected` must provide all four existing values from the native inventory.
`access.desired` provides a nonempty subset of those fields. The current state
must equal the expected inventory or the complete desired state before writing.
Name, slug and description are protected and checked again before Save and after
an independent reload/reopen. The handler never sends invitations or changes the
group's active/inactive status.

Access expansion includes private-to-public privacy, enabling switcher access or
member invitations, and removing the mandatory profile requirement. These changes
require a live, exact, same-page authorization from the installed host:

```python
authorization = authorize_access_change(
    page, inputs, portal_context=context,
    confirm_at_action_time=host_confirmation_capability,
)
result = run_access(
    page, inputs, evidence_root,
    portal_context=context, access_authorization=authorization,
)
```

The confirmation capability must actually ask the owner at action time for the
bound request. It is a trusted host capability, not source text, a JSON approval
flag or an automatically approving lambda. Authorizations expire after 60 seconds
and cannot cross page, user, group, location or input configuration. A missing or
expired authorization yields `ACCESS_CONFIRMATION_REQUIRED` before expansion.
The authorization is consumed immediately before the one Save and cannot approve
another write, even if that Save's outcome becomes uncertain.
Restrictive changes and no-op reuses do not expand access. Completed replay never
performs another write and does not reuse saved authorization as write permission.

The saved outcome remains `NEEDS_VERIFICATION` with `behavior_verified:false`.
Creation of this source is separate from live script execution or functional
verification. Optional testing is deferred at the owner's request.
