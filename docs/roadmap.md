# Roadmap

This page lists work already tracked in project issues and discussions. It
captures current priorities, not release promises.

## Planned

- [Choose a map for planner runs](https://github.com/jan-tdy/TapoVac-ADV/issues/100) - let a smart cleaning plan target a saved map instead of always using the robot's active map.
- [Add per-run cleaning settings and a preset service](https://github.com/jan-tdy/TapoVac-ADV/issues/53) - expose suction, water, passes and room order for one clean, then consider an experimental service for cleaning a saved Tapo preset.

## Research and verification

- [Resolve a preset's `custom_rule_id` to its room list](https://github.com/jan-tdy/TapoVac-ADV/discussions/8) - investigate whether the room mapping can be read without relying on the TP-Link cloud API.
- [Verify planner docking behavior on hardware](planner.md#known-limitation) - confirm that the vacuum finishes its current room and then docks when someone comes home.
