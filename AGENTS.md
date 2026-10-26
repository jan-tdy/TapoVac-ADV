# Agent instructions for this repository

## README.md

`README.md` is a living document, not an append-only log. When a change
touches something the README already describes:

- **Do not** bolt on a new section at the bottom (or anywhere else) just
  to describe the latest change. That is how this file turns into an
  unreadable pile of near-duplicate sections over time.
- **Do** find the existing section the change belongs to and rewrite it
  in place so the README still reads as one coherent document describing
  the project *as it is now* - not a changelog of how it got there.
- The **Changelog** section is the one exception: that is where a dated
  entry for the change belongs.
- This is not a request to rewrite the README from scratch on every edit.
  Keep everything that is still accurate; edit mindfully, touching only
  what the change actually affects, the way you'd edit any other file in
  this repo.

If you are unsure whether something belongs in the README at all versus
in `docs/`, prefer `docs/` for anything that isn't essential to getting a
user installed and oriented in the first few minutes.

## docs/

`docs/` (the MkDocs site published to GitHub Pages) is held to the same
standard as the README: it must stay accurate for the project *as it is
now*. When a change adds, removes or changes behavior that an existing
page in `docs/` describes (an entity, a service, a config option, a
protocol detail), update that page in the same change, in place, the
same way you would update the README's matching section. Don't leave
`docs/` describing an older version of the integration just because the
change didn't explicitly ask for a docs update. New, genuinely new
functionality that has nowhere to go yet can be added as a new page or
section, same as the README's rule for genuinely new sections, but
existing pages are edited, not left stale.

## Pull requests

- Keep each requested change in its own pull request. Do not bundle unrelated
  changes together.
- Every pull request must have at least one existing GitHub label that
  accurately describes the change before it is presented for review. If no
  existing label fits, create an appropriate repository label and apply it.
