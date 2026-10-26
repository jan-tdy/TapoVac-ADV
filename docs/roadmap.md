# Roadmap

!!! note "TODO"
    Not written yet. Should track actual planned work, sourced from open
    [issues](https://github.com/jan-tdy/TapoVac-ADV/issues) and
    [discussions](https://github.com/jan-tdy/TapoVac-ADV/discussions) -
    not a wish list invented for this page.

Known open items to pull in here once this page is written for real:

- Resolving a cleaning preset's `custom_rule_id` back to its room list -
  see [Protocol notes - undiscovered commands](protocol/undiscovered-commands.md).
  Currently believed to require TP-Link's cloud API; tracked in
  [Discussion #8](https://github.com/jan-tdy/TapoVac-ADV/discussions/8).
- Verifying the planner's "finish the current room, then dock when
  someone comes home" behavior on real hardware - see
  [Smart cleaning planner → Known limitation](planner.md#known-limitation).
- This documentation site itself was the last item on the README's own
  roadmap note ("Docs | README only (site on roadmap)") - once GitHub
  Pages is wired up for it, update the README's comparison table to point
  here instead of listing docs as a gap.

## Planned feature ideas

Not yet tracked against a specific issue; listed here so they aren't
lost, and to be moved above (with a real issue/discussion link) once
work actually starts.

- **Per-run map selection for the smart planner** - let a planner run
  target a specific saved map/floor explicitly, instead of only ever
  acting on whatever map the robot currently has active.
- **Dustbin/auto-empty planning** - coordinate the dock's auto-empty
  behavior with the smart planner, the way room cleans are already
  scheduled around occupancy and cleaning windows, instead of leaving
  auto-empty as a bare on/off switch (see [Entities → Switch](entities.md#switch)).
