# Skill 78 selection UI contract (S78-04)

Component: comparison matrix and selection UI model. Owner S78 (doc 16).
Offer price display component owner: S79, with S78 reviewing factual
accuracy against the approved catalog. Native binding owner: S06.

## Structure

- Bridging headline and one plain choosing paragraph (copy profile rules).
- Offer group as a real radio group: fieldset with legend "Packages", one
  labelled radio input per offer, at most one checked. The whole offer card
  is the label, so the click target is the full card; the radio remains the
  operable control for keyboard and assistive technology.
- Keyboard model: native radio-group behavior. Arrow keys move between
  options and select the focused option, Space selects, Tab moves into and
  out of the group as one stop. No custom key handling may break this.
- Selected state: one explicit visual state (border plus shadow via the
  data-selected attribute) that always matches the checked radio.
- Recommendation: a badge plus its approved reason text, adjacent to the
  recommended offer only. It never pre-checks a radio, in any state: the
  default preview checks nothing, and only the separate selected-state
  preview shows one checked radio, with data-selected on that same card.
- Error state: submitting with nothing selected shows "Choose a package to
  continue." in an alert region linked by aria-describedby, and moves no one
  forward. It never silently selects a default.
- Reconfirm state: when terms changed, a banner states the change and asks
  for confirmation; the stored choice is shown, never swapped.

## Responsive behavior

- Desktop: offers in a grid (auto-fit, minimum 240px columns), comparison
  matrix as a full table with scoped headers, presented in a disclosure
  that the progressive-enhancement script opens on wide viewports and that
  opens by hand at any width.
- Mobile (max-width 640px): offers stack in approved order with equivalent
  visibility; the matrix moves into a disclosure; material exclusions are
  rendered outside the disclosure, always visible, in both layouts.
- Billing schedule choice, when a package has several approved schedules,
  is a separate control inside that offer, never a separate page.

## States that must be produced as previews

default, selected, focus, error, reconfirm, and (at install) loading. The
local renderer produces default, selected, error, and reconfirm HTML; a
small progressive-enhancement script (not required for the form to work)
keeps data-selected in sync with the checked radio and opens the
comparison disclosure on wide viewports. Focus is a CSS state in
components/selection-ui/selection.css.

## CSS boundary (doc 16 section 6)

Namespaced sl78- classes and --sl78-* variables only. No global resets.
Native form internals are not styled from the parent; the native-element
styling map is produced by S06 at install time.
