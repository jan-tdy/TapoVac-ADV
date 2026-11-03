# FAQ

## Hardware and compatibility

### Which models are supported?

Any Tapo robot vacuum that speaks the TPAP (SPAKE2+) protocol on firmware
1.2.x+, plus older RV30C-era models through the AES transport fallback.
"Confirmed" means someone has actually run a given integration version
against that model, not an exhaustive compatibility list - see
[Home → Supported hardware](index.md#supported-hardware) for the current
table. If your vacuum works but isn't listed, open an
[issue](https://github.com/jan-tdy/TapoVac-ADV/issues) so it can be added.

### Does it work on RV30C / RV30C Mop (the older AES models)?

Yes, through the AES transport fallback - TPAP/SPAKE2+ is only used on
firmware that offers it. See
[Installation → Requirements](installation.md#requirements).

### What if my robot has no mop - which entities do I lose?

Entity creation follows what the robot actually reports: a vacuum-only
model never gets Water Level, mop-related switches
(Automatic Re-mopping, Clean Along Floor, Extended Mopping), the
Mop Attached binary sensor, mop-related consumable entities, or mop error
codes. Everything else (rooms, planner, maps, schedules) works the same.
See [Entities](entities.md) for the full per-platform breakdown.

### Does Matter commissioning work the same as in the Tapo app?

The integration exposes an **Open Matter Pairing Window** button, a
Matter sensor reporting commissioning/fabric status, and the
[`get_matter_setup_code`](services.md#get_matter_setup_code) /
[`remove_matter_fabric`](services.md#remove_matter_fabric) services - see
[Entities → Button](entities.md#button) and
[Services → Matter](services.md#matter). It's a thin wrapper around the
robot's own Matter support, not a separate implementation.

## Cloud vs. local, and security

### Does this need the internet / cloud for normal operation?

No - day-to-day control (status, cleaning, maps, schedules) talks to the
robot directly over your LAN via the local TPAP (SPAKE2+) or AES
protocol, with no cloud round-trip. See [Home](index.md).

### What is the Tapo account (email/password) actually used for, then?

It's used to authenticate the local handshake with the robot (the same
credentials the Tapo app uses), and for a handful of features that do
involve TP-Link's cloud by nature: fetching cloud map backups
([`fetch_cloud_map_backups`](services.md#fetch_cloud_map_backups) /
[`restore_map_backup`](services.md#restore_map_backup)) and copying a map
over HTTP when the robot needs to pull it
([`copy_map`](services.md#copy_map)). Everyday cleaning, status and
sensor polling don't touch the cloud at all.

### Are my credentials logged anywhere?

No. As noted in
[Troubleshooting → Reading the integration's own log](troubleshooting.md#reading-the-integrations-own-log),
credentials are never logged - a `cannot_connect` error logs the
underlying exception with host/port only - and they're never included in
**Download diagnostics** either (see
[Entities → Diagnostics](entities.md#diagnostics)).

## Installation and setup

### Why does setup fail on Home Assistant older than 2026.3?

The integration requires `VacuumEntityFeature.CLEAN_AREA`, the `Segment`
type and the `async_get_segments`/`async_clean_segments` entity methods
used for [Native area mapping](area-mapping.md), none of which exist on
older cores. There's no supported way to run it below 2026.3 - see
[Troubleshooting → Integration fails to load](troubleshooting.md#integration-fails-to-load-on-home-assistant--20263)
and [Installation → Requirements](installation.md#requirements).

### How do I migrate from `epg-pers/tapo-rv30-ha` without losing history or plans?

Remove the old integration and its HACS repository, add **TapoVac-ADV**
from HACS, restart, then re-add it through
**Settings → Devices & Services → Add Integration** and let it
auto-discover the robot locally - see the README's
["Migrating from epg-pers/tapo-rv30-ha"](https://github.com/jan-tdy/TapoVac-ADV#-migrating-from-epg-perstapo-rv30-ha)
section for the exact steps. Since it's a new config entry, Home
Assistant history under the old entity IDs doesn't carry over; the
robot's own clean records, schedules, maps and presets (stored on the
robot itself) are unaffected either way.

### What happens if the robot's IP address changes?

A known entry's IP is updated automatically via the integration's DHCP
discovery rule (`E0D362*` MAC prefix) - see
[Configuration → Setting up the config entry](configuration.md#setting-up-the-config-entry).
A static DHCP lease/reservation is still recommended to avoid relying on
that.

### How do I re-authenticate after a factory reset or replacing the robot?

Use the config entry's **Reconfigure** flow. Note that Reconfigure (like
Reauthenticate) resets the stored security baseline to whatever the
robot offers at that moment, without comparing it to the old baseline -
only use it when you trust the robot you're currently talking to. See
[Configuration → Reconfiguring credentials](configuration.md#reconfiguring-credentials).

### Beta, latest, or SuperStable - which release should I install?

- **Pre-release (`X.XbX`)** - if you want to help test and catch bugs.
- **Latest non-beta** - if you want current features that already work.
- **[SuperStable]** - if you want something tested multiple times that
  just works, even if it's a couple of major releases behind; SuperStable
  releases can still get patches after a newer beta has shipped.

See the README's
["Updating and releases"](https://github.com/jan-tdy/TapoVac-ADV#updating-and-releases)
section.

## Entities and sensors

### Why don't I see Water Level / mop-related entities?

They're only created for mop-capable models, decided by what the
connected robot reports - see
[Hardware and compatibility → no mop](#what-if-my-robot-has-no-mop---which-entities-do-i-lose)
above and [Entities](entities.md).

### What does the "Planner Status" sensor mean?

It reports what the [smart cleaning planner](planner.md) is doing right
now (idle, waiting on occupancy, running, etc.) - see
[Planner → Status and logging](planner.md#status-and-logging). For *why*
it's in that state, check the Planner tab's decision log on the
[Vacuum sidebar page](dashboard.md), not just the sensor state.

### How is "hours remaining" calculated for consumables?

Each tracked consumable (main brush, side brush, filter, sensor, charge
contacts) gets a pair of sensors: hours used so far, and hours remaining
against the robot's own rated life for that part - see
[Entities → Sensor](entities.md#sensor). The rated life comes from the
robot, not from this integration.

### Why isn't battery level on the `vacuum` entity itself?

Home Assistant core removed the legacy `battery_level` property from the
`vacuum` entity, so battery is reported through its own dedicated sensor
instead - see [Entities → Vacuum](entities.md#vacuum).

### What's the difference between "Last Clean Area" and "Total Area Cleaned"?

**Last Clean Area** is the area covered by the most recent completed
clean record; **Total Area Cleaned** is the lifetime counter across every
clean record the robot has reported. Same relationship as **Last Clean**
(a timestamp) vs. **Total Cleans** (a lifetime count) - see
[Entities → Sensor](entities.md#sensor). If it's still confusing: the
"Last …" sensors describe one run, the "Total …" sensors accumulate
across all of them.

## Services

### What's the difference between `rooms` and `room_ids` in `clean_rooms`?

Two ways to say the same thing - `rooms` takes names as shown in the Tapo
app/sidebar map, `room_ids` takes the numeric IDs directly. Provide
either one (not both); `map`/`map_id` are optional in both cases. See
[Services → `clean_rooms`](services.md#clean_rooms).

### Will switching from `suction` to `fan_speed` break my existing automations?

No - `suction` still works. `fan_speed` is simply the newer, Home
Assistant-standard name for the same field; if both are given in the
same call, `fan_speed` wins. See
[Services → shared fields](services.md#services).

### Why does the integration offer `Ultra` fan speed if my Tapo app doesn't show it?

The fan speed list isn't filtered per model - some robots (e.g. certain
RV30 variants) only surface four speeds in the Tapo app, with `Ultra`
hidden or temporary there, but the integration still exposes it as a
valid value. See [Services → shared fields](services.md#services).

### What happens if I call a service against a map/room that doesn't exist?

The service call fails with a validation error naming the problem,
rather than silently doing nothing or hitting an obscure device error -
see [Area mapping → stale segment handling](area-mapping.md#how-the-contract-is-implemented)
for the equivalent behavior on the native `clean_area` path, which
applies the same care.

### How do I restore a map backup as a new map instead of overwriting the current one?

Pass `new_name` to [`restore_map_backup`](services.md#restore_map_backup)
- it restores the backup as a new map under that name instead of
overwriting the target `map`. The same "restore as new" option is
available from the Settings tab's Maps card on the
[Vacuum sidebar page](dashboard.md#the-vacuum-sidebar-page).

### Why doesn't diacritic/accent spelling matter when I call a service?

Only when *typing* a room name into a field: accents are stripped and
both sides are lowercased before comparing, so "Kúpeľňa" matches
`kupelna`, a partial match like `pel`, or the exact accented spelling.
Room names shown in lists/dropdowns are always the correctly decoded
original. See
[Configuration → Diacritics and room names](configuration.md#diacritics-and-room-names).

## Smart cleaning planner

### Why does the planner do nothing even though it's switched on?

The most likely reason: it's still in **preview** mode, which is the
default and safe-by-default behavior - it only logs what it would have
cleaned (via the Planner Status sensor and the decision log) without
starting anything. Flip it to **live** mode on the Planner tab once
you're happy with what the decision log shows it would do. See
[Planner → Safe by default](planner.md#safe-by-default).

### What exactly does preview mode do, and how do I go live?

Preview mode runs the full due/occupancy/window logic and records what
it *would* start, without ever sending a clean to the robot. Switching
to live mode on the Planner tab (Vacuum sidebar page) is the only change
needed - the rest of the configuration carries over unchanged. See
[Planner → Safe by default](planner.md#safe-by-default).

### Can the morning and evening cleaning windows overlap?

No - the two windows of a day must not overlap. Each window otherwise
runs its own independent run policy, so a morning run doesn't affect
whether the evening window runs. See
[Planner → Cleaning windows](planner.md#cleaning-windows).

### What's the difference between "Once per window" and "Repeat"?

**Once per window** starts a single run even if more rooms become due
later in the same window. **Repeat** keeps starting runs while rooms
remain due, with a configurable minimum gap between runs so it doesn't
restart immediately after finishing. See
[Planner → Run policy](planner.md#run-policy).

### How does the planner interact with the robot's own schedule store?

They're independent and additive - the planner starts cleans on its own
when rooms come due inside your configured windows, while the robot's
own schedule store (managed via
[`add_schedule`/`set_schedule`](services.md#schedules), see
[Protocol notes - schedules](protocol/schedules.md)) keeps working
exactly as it always has. Neither one disables the other.

### Where do I see why the planner did or didn't start a run?

The Planner tab on the [Vacuum sidebar page](dashboard.md) shows the
last 40 decision-log steps - the quickest way to understand a specific
decision - alongside the Planner Status sensor for the current state.
See [Planner → Status and logging](planner.md#status-and-logging).

## Native area mapping

### How do I map the robot's rooms to Home Assistant areas?

Open the vacuum's more-info dialog, click the settings (⚙) icon, and use
**Map vacuum segments to areas**. This requires Home Assistant **2026.3+**.
See [Native area mapping](area-mapping.md).

### Why does `clean_area` fail with a "different maps" error?

Because the robot can only be on one floor/map at a time: if the areas
you selected span several saved maps and none of them is the currently
active one, the call is rejected with that error instead of silently
picking one. If the selection spans maps but one of them *is* active,
the rooms on that active map are used and the rest are dropped. See
[Native area mapping → How the contract is implemented](area-mapping.md#how-the-contract-is-implemented).

### What happens to old (pre-namespacing) segment IDs after upgrading?

Segment IDs are namespaced `<map_id>:<room_id>` because room IDs are only
unique *within* a map. Home Assistant's area mapping keeps old IDs around
indefinitely, so bare pre-namespacing IDs - and IDs from maps that no
longer exist - are simply dropped from a `clean_area` request rather than
failing the whole call; only when *nothing* valid remains does the call
fail, pointing at redoing the area mapping. See
[Native area mapping → How the contract is implemented](area-mapping.md#how-the-contract-is-implemented).

### Does native area mapping work with multiple floors/saved maps?

Yes - `async_get_segments()` reports the rooms of *every* saved map, not
just the active one, with each map's rooms grouped under that map's own
name in the mapping dialog. See
[Native area mapping → How the contract is implemented](area-mapping.md#how-the-contract-is-implemented).

## Dashboard and sidebar panel

### How do I turn off the "Vacuum" sidebar page?

It's enabled by default; toggle **Show sidebar panel** off in the
integration's options flow. See [Configuration → Options](configuration.md#options).

### How does Auto-empty work, and why won't "Empty now" run?

The Auto-empty tab runs a Home Assistant schedule (1-30 day frequency and
a run time) that, when enabled, disables the robot's firmware auto-empty
switch and runs the Empty Bin command itself while the robot is docked.
**Empty now** is disabled while the robot is cleaning or paused - dock it
or wait for the run to finish first. See
[Dashboard → The Vacuum sidebar page](dashboard.md#the-vacuum-sidebar-page).

### What happens when a scheduled auto-empty run fails?

It's retried after 15 minutes by default; turn **Retry after an error**
off to skip the retry and wait for the next scheduled run instead. If
your dock doesn't actually support the Empty Bin command, the run fails
and shows up as the "Last empty" sensor failing to update - that's
expected on hardware without a dust bucket. See
[Dashboard → The Vacuum sidebar page](dashboard.md#the-vacuum-sidebar-page).

### How do I switch between multiple robots on the sidebar page?

A robot switcher at the top of the Vacuum sidebar page lets you flip
between configured vacuums without leaving the page. See
[Dashboard → The Vacuum sidebar page](dashboard.md#the-vacuum-sidebar-page).

### How do I see a past clean's map without downloading it?

The History tab's **View** action opens a clean-history map directly in
the sidebar page, instead of only offering a download. See
[Dashboard → The Vacuum sidebar page](dashboard.md#the-vacuum-sidebar-page).

## Standalone CLI

### Can I use `tapo_vacuum.py` alongside Home Assistant without conflicts?

Yes - it talks to the robot directly over the same local protocol Home
Assistant uses, the same way the Tapo app or a second Home Assistant
instance could. There's no exclusive lock; just be aware that commands
sent from the CLI (e.g. a room clean) show up in Home Assistant the next
time it polls, same as anything started from the Tapo app. See
[Standalone CLI](cli.md).

### When should I reach for the CLI instead of Home Assistant?

- Verifying connectivity and credentials *before* setting up the config
  entry.
- Reproducing a protocol issue in isolation when filing a bug - a CLI
  transcript is much easier to share than a full Home Assistant debug
  log.
- Exploring the device with raw calls (equivalent to
  [`send_raw`](services.md#send_raw)) without touching a live Home
  Assistant instance.

See [Standalone CLI → When to reach for this instead of Home Assistant](cli.md#when-to-reach-for-this-instead-of-home-assistant).

## Troubleshooting

### The map camera shows "unavailable" - what now?

If you're upgrading from a very old version, this was a `NameError`
affecting the Map camera entity after an earlier entity-mixin refactor -
see the [changelog](https://github.com/jan-tdy/TapoVac-ADV#changelog) for
the fix version, and restart after upgrading to a current release. See
[Troubleshooting → Map camera shows "unavailable"](troubleshooting.md#map-camera-shows-unavailable).

### How do I enable debug logging for just this integration?

Add to `configuration.yaml`:

```yaml
logger:
  default: warning
  logs:
    custom_components.tapo_rv30: debug
```

The Vacuum sidebar page's **Log** tab is usually faster for a quick look,
since it shows the integration's own recent log records without needing
debug logging turned on at all. See
[Troubleshooting → Reading the integration's own log](troubleshooting.md#reading-the-integrations-own-log).

### Where do I look up what a robot error code means?

[Troubleshooting → Error codes](troubleshooting.md#error-codes) has the
full table decoded from the Tapo app's `RobotCleanErrorType` enum. The
`Error` sensor only ever shows codes the connected robot can actually
produce (e.g. no mop errors on a vacuum-only model).

### Why do I get "Unknown segment id" or a similar error cleaning an area?

This was the old behavior when a single stale segment ID (from a deleted
map, or a pre-namespacing bare ID) failed the *entire* `clean_area` call.
Current versions drop only the invalid IDs and proceed with the rest,
failing only if nothing valid remains - see
[Area mapping → stale segment handling](#why-does-clean_area-fail-with-a-different-maps-error)
above. If you still see this on a current release, it's worth opening an
issue.

### The robot restarts cleaning instead of resuming after a pause - is that a bug?

No - resuming after a pause, and correctly rejecting/erroring a new
clean request while one is already running or paused (rather than
silently starting over), are both explicitly fixed in this fork versus
upstream. If you still see it misbehave, open an
[issue](https://github.com/jan-tdy/TapoVac-ADV/issues) with your version
and debug logs - it should not be happening. See the README's
["Fixed here but not upstream"](https://github.com/jan-tdy/TapoVac-ADV#fixed-here-but-not-upstream)
section.

### Still stuck?

Check the [changelog](https://github.com/jan-tdy/TapoVac-ADV#changelog)
for a fix that may already cover it, then open an
[issue](https://github.com/jan-tdy/TapoVac-ADV/issues) with your robot
model, firmware version, and debug logs. See
[Troubleshooting → Still stuck?](troubleshooting.md#still-stuck).

## Differences from other integrations

### How does this differ from the official TP-Link Tapo integration?

They're separate integrations built on different approaches to the
device. This project is a fork of
[epg-pers/tapo-rv30-ha](https://github.com/epg-pers/tapo-rv30-ha), built
specifically for Tapo robot vacuums over their local TPAP/AES protocol,
with a planner, map tooling and dashboard layered on top - see
[Home](index.md) for what it is.

### What's different from upstream `epg-pers/tapo-rv30-ha`, and is it worth switching?

Both speak the same local protocol and expose the same 11 entity
platforms and 25 services, so anything you automate works identically
either way. The difference is what's built on top: a full-featured
smart planner (preview mode, occupancy, preferred times), richer map
tooling (restore-as-new, map-rotation as an entity, clean-history "View"
in the sidebar), an in-app **Log** tab, and a much larger automated test
suite. The full side-by-side comparison lives in the README's
["Upstream vs. this fork"](https://github.com/jan-tdy/TapoVac-ADV#upstream-vs-this-fork)
table - worth reading in full rather than duplicated here, since it's
kept up to date there.

### Can I run this integration and the official one on the same robot at once?

Both connect to the robot the same way the Tapo app does (concurrent
local sessions are how the Tapo app itself coexists with a running
integration), but running two Home Assistant integrations against the
same physical vacuum isn't a configuration this project tests or
supports - expect duplicate entities and no coordination between them.
Pick one.

## Multi-robot and multi-floor

### How do I set up multiple robots, possibly on different floors?

Add each robot as its own config entry (**Settings → Devices & Services
→ Add Integration → TapoVac-ADV**, once per robot). On the
[Vacuum sidebar page](dashboard.md#the-vacuum-sidebar-page), the robot
switcher at the top lets you flip between them without leaving the page.
Multiple floors on a *single* robot are handled through its saved maps -
see [`set_map`](services.md#set_map-select-the-active-map) and
[`set_map_lock`](services.md#set_map_lock) to stop the robot
auto-merging a locked map into another one while mapping.

### Do multiple robots share one config entry, or does each get its own?

Each robot gets its own config entry, its own set of entities, and its
own planner settings - nothing is shared between robots except the
sidebar page's UI, which switches between them.
