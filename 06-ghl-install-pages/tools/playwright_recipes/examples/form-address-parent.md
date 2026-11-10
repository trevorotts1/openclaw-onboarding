# Parent Address controls

`forms.configure` accepts a separate `address_parent` job. Supply the exact form
name, complete current query/type inventory, all five child query keys and full
child properties, expected parent flags and desired parent flags. The example
uses synthetic fixture values; replace them with the actual native inventory.

Captured controls: `#address-auto-complete` contains two exact label-bound rows,
Auto-Complete Address and Mandatory to Select Address in Search Bar. The nameless
switches expose `aria-checked`; the dependent switch uses `n-switch--disabled`
while autocomplete is off. Native parent-off atomically clears mandatory state.
Both expected and desired mandatory=true require autocomplete=true.

The writer enables autocomplete before enabling mandatory selection. Turning
parent autocomplete off takes one click and verifies that mandatory cleared.
It retains all five children and every query/type sibling, saves once only when
changed, independently reopens, and rereads controls plus preservation inventory.
An existing off-state Address has five inputs; its absence of a search input
must not authorize duplicate placement. Public CLI completed replay reads the
current native state and refuses drift without repeating a write.

Native capture evidence is in fixtures/address-parent-off-after-required-captured.html
and fixtures/address-parent-required-reopened-captured.html. These are editor
proof, not a respondent submission or external address-provider test.
