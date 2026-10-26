# Troubleshooting

## Reading the integration's own log

The [Vacuum sidebar page](dashboard.md) has a **Log** tab showing this
integration's recent log records (a ring buffer, independent of Home
Assistant's own log), with refresh and clear actions - usually the
fastest way to see what's happening without turning on debug logging.

For more detail, enable debug logging for the integration in
`configuration.yaml`:

```yaml
logger:
  default: warning
  logs:
    custom_components.tapo_rv30: debug
```

Credentials are never logged; `cannot_connect` errors log the real
underlying exception with host/port only.

## Integration fails to load on Home Assistant < 2026.3

This integration requires Home Assistant **2026.3+** - see
[Installation → Requirements](installation.md#requirements). On older
cores, setup fails because `VacuumEntityFeature.CLEAN_AREA`, the
`Segment` type, and the `async_get_segments`/`async_clean_segments`
entity methods used for [native area mapping](area-mapping.md) don't
exist yet. Upgrade Home Assistant core; there is no supported way to run
this integration on an older release.

## Map camera shows "unavailable"

If upgrading from a very old version, see the
[changelog](https://github.com/jan-tdy/TapoVac-ADV#changelog) for the fix
to a `NameError` that affected the Map camera entity after an earlier
entity-mixin refactor. Restarting after upgrading to a current release
resolves it.

## "401 Client Error: Unknown Status" in a loop

A stale session token (`stok`) answered with a plain HTTP 401 is
re-handshaked automatically rather than failing every poll. If you still
see repeated 401s, check that the robot's IP address hasn't changed
outside of DHCP discovery, and that the Tapo account password configured
in the entry still matches the one used in the Tapo app.

## Water level or schedule changes keep reverting

Writes being overwritten by a stale read shortly after is a known class
of issue the integration guards against for the settings it owns
directly (see the project's
[changelog](https://github.com/jan-tdy/TapoVac-ADV#changelog) for
specific fixes, e.g.
[#51](https://github.com/jan-tdy/TapoVac-ADV/issues/51)). If you see this
on a setting not covered by a known fix, open an issue with the setting
name and debug logs around the write.

## Furniture placed in the map editor doesn't appear on the map

If furniture placed and saved in the sidebar's map editor shows up again
when you reopen the editor (so the robot did keep it) but still doesn't
appear on the map image or in `map_geometry`, that's unexpected - the
editor reads the map back after saving and should report a clear error
if the robot ever accepts a furniture write without actually keeping it.
Please open an issue with your robot model/firmware and, if possible,
debug logs for `custom_components.tapo_rv30` around the save. See also
[Furniture on the map](#furniture-on-the-map) below for which glyphs are
confirmed TP-Link codes versus this fork's own additions.

### Furniture on the map

Furniture is drawn on the map image by default (toggle it off in
[Configuration](configuration.md#options) if you draw it yourself from
`map_geometry.furniture` on a custom card - both the camera image and
`map_geometry` always carry the data regardless of the toggle). All
glyphs are drawn top-down (floor-plan view), not as side-on elevations.
19 of the 22 furniture types are confirmed TP-Link app/firmware codes
(see `FURNITURE_TYPES` in `const.py`); the other 3 - a dining table, a
standalone dining chair, and a washbasin - are this fork's own, using the
next free numbers in their category, since no traffic capture has shown a
code for them. Saving one of these is still verified against a read-back
of the robot's map: a robot that doesn't keep it says so plainly instead
of silently dropping it. Items placed or resized in the map editor get
their type's real-world size and are drawn under no-go zones, so a zone
inside a sofa is still visible and selectable.

## Error codes

The `Error` sensor (see [Entities](entities.md#sensor)) decodes the
robot's `err_status` code. Full table, from the Tapo app's
`RobotCleanErrorType` enum:

| Code | Meaning |
| --- | --- |
| 0 | Ok |
| 1 | Wheel Stuck |
| 2 | Side Brush Stuck |
| 3 | Main Brush Stuck |
| 4 | Lifted Off Floor |
| 5 | Bumper Stuck |
| 6 | Trapped |
| 7 | Cliff Sensor Blocked |
| 8 | Battery Error |
| 9 | Wheel Error |
| 10 | Side Brush Motor Error |
| 11 | Main Brush Motor Error |
| 12 | Suction Fan Error |
| 13 | Water Pump Error |
| 14 | Dust Bin Removed |
| 15 | Tilted |
| 16 | Lidar Blocked |
| 17 | Lidar Stuck Or Tangled |
| 18 | Lidar Error |
| 19 | Can't Locate (Cleaning) |
| 20 | Can't Locate (Heading Home) |
| 21 | Dock Not Found |
| 22 | Low Battery, Recharging |
| 23 | Lidar Cover Stuck |
| 24 | No Dock, Stopped Returning |
| 25 | Dust Bin Needs Cleaning |
| 26 | Clean Water Tank Empty Or Missing |
| 27 | Dirty Water Tank Full Or Missing |
| 28 | Mop Auto-Install Failed |
| 29 | Clean Tray Missing From Dock |
| 30 | Clean Tray Overflow |
| 31 | Mop Detached |
| 32 | Mop Bracket Error |
| 33 | Mopping Arm Error |
| 34 | Mop Not Detected |
| 35 | Fan Motor Blocked |
| 36 | Mop Stuck |
| 37 | Extending Mop Stuck |
| 38 | Carpet Sensor Error |
| 39 | Front Line Laser Error |
| 40 | Side Line Laser Error |
| 41 | Dirty Water Pump Error |
| 42 | Drying Fan Error |
| 43 | Drying Heater Error |
| 44 | Dust Bag Not Installed |
| 45 | Mop Install Failed |

Not every model has every component (e.g. a vacuum-only model will never
report a mop error) - the sensor only ever shows codes the connected
robot can actually produce.

## Still stuck?

Check the [changelog](https://github.com/jan-tdy/TapoVac-ADV#changelog)
for a fix that may already cover your issue, then open an
[issue](https://github.com/jan-tdy/TapoVac-ADV/issues) with your robot
model, firmware version, and debug logs for
`custom_components.tapo_rv30`. See [Contributing](contributing.md) for
how reverse-engineering findings and protocol questions are handled
separately from bug reports.
