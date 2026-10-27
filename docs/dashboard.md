# Dashboard & sidebar panel

## The Vacuum sidebar page

TapoVac-ADV registers a custom sidebar page called **Vacuum**, enabled by
default (toggle it off in [Configuration](configuration.md#options)). It
is a full control surface for the robot, organized as tabs:

- **Home** - the live map with tappable rooms, quick cleaning controls and
  saved presets.
- **Schedules** - the robot's own schedule store (the same one
  [`add_schedule`/`set_schedule`](services.md#schedules) manage).
- **Planner** - settings and status for the [smart cleaning
  planner](planner.md), plus its last 40 decision-log steps.
- **Auto-empty** - a Home Assistant schedule with a 1–30 day frequency and
  run time, plus an **Empty now** action. When enabled, it disables the
  vacuum's firmware auto-empty switch and runs the same Empty Bin command
  when the vacuum is docked. You can turn the schedule on right away -
  it no longer requires a successful **Empty now** first; if your model
  doesn't actually support the command, the run will fail and the error
  shows up as "Last empty" fails to update. **Empty now** is disabled
  while the vacuum is cleaning or paused - dock it (or wait for the run
  to finish) first.
- **History** - past cleans, including a **View** action that opens a
  clean-history map directly in the sidebar page instead of only
  downloading it.
- **Room freshness** - how long since each room was last cleaned.
- **Remote drive** - manual driving controls, backed by the
  [`remote_drive`](services.md#remote_drive) service.
- **Maintenance** - consumable wear and reset buttons.
- **Settings** - a Maps card (rename, copy, lock/unlock, delete, restore
  backups - see [Services → Maps](services.md#maps) and
  [Services → Backups](services.md#backups)) plus the robot switcher for
  multi-robot setups.

A robot switcher at the top of the page lets you flip between multiple
vacuums without leaving the page.

## Stock-card Lovelace dashboard

If you'd rather not use the sidebar page - or want a starting point for
your own - [`jarvis_dashboard.yaml`](https://github.com/jan-tdy/TapoVac-ADV/blob/main/jarvis_dashboard.yaml)
at the repository root is a Lovelace view built entirely from stock Home
Assistant tile cards (the `sections` view type). No third-party card
library is required for the controls themselves; only
[card-mod](https://github.com/thomasloven/lovelace-card-mod) is needed,
and only to rotate the map camera image to match
[Map Rotation](configuration.md#options).

To use it: open the file, copy its contents into a new dashboard view in
raw YAML mode, and replace the entity IDs with your own vacuum's.

## Rendering the schedule list

The `Schedules` sensor's state is just a count; the actual entries live in
its `schedules` attribute. See
[Protocol notes - schedules → Viewing schedules in a dashboard](protocol/schedules.md#viewing-schedules-in-a-dashboard)
for a Markdown card that renders it as a table, including two YAML/Jinja
gotchas that silently break the table if you copy the snippet
incorrectly.
