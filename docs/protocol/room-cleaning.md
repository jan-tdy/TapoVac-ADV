# Protocol notes - room cleaning

The `setSwitchClean` payload used for selective room cleaning was
reverse-engineered from live device traffic and, as far as the project is
aware, isn't documented anywhere else. Neither
[python-kasa](https://github.com/python-kasa/python-kasa) (which only
implements whole-house `clean_mode: 0`) nor the official Home Assistant
Tapo integration implement room cleaning.

## Payload

```json
{
  "clean_mode": 3,
  "clean_on": true,
  "clean_order": true,
  "force_clean": false,
  "map_id": 1792568378,
  "room_list": [2, 4],
  "start_type": 1
}
```

## Key points

- `clean_mode: 2` is the **Tapo app's own** spot-clean mode - the
  room/zone data is silently ignored. The integration doesn't send this
  mode itself; see `clean_mode: 4` below for how it implements spot
  clean.
- `clean_mode: 3` is **selective room clean**, driven by `room_list`.
- `clean_mode: 4` is a rectangular **zone clean**, driven by `area_list`
  instead of `room_list` (see [`clean_zone`](../services.md#clean_zone)).
  The integration's own spot clean is implemented on top of this: a
  1.5 m square centered on the robot's current position, sent as a
  single-zone `clean_mode: 4` call.
- `clean_mode: 5` is a saved **cleaning preset** ("custom rule"). Instead
  of `room_list`, it takes `custom_rule_id: <int>` - see
  [Protocol notes - schedules](schedules.md) for how schedules reference
  the same preset mechanism. Running a preset this way (rather than
  through whatever call the Tapo app itself uses to start one) is
  **inferred from the schedule data shape**, not confirmed against the
  app.
- `room_list` is a plain integer array of room IDs - the same pixel
  values used in the LZ4-compressed map data.
- The room-clean (`clean_mode: 3`) shape above was discovered by reading
  `getSwitchClean` while the official Tapo app performed a room clean
  against a live device.

## Where this is used in the integration

- The [`clean_rooms`](../services.md#clean_rooms) service builds this
  payload directly from room names or IDs resolved live against the
  robot.
- [Native area mapping](../area-mapping.md)'s `async_clean_segments()`
  uses the exact same payload shape, after resolving Home Assistant
  segment IDs back to `<map_id>, room_id` pairs.
- [`run_preset`](../services.md#run_preset) and schedules referencing a
  saved preset use `clean_mode: 5` with `custom_rule_id` instead - the
  inferred mechanism described above.

## Contributing a new finding

If you capture traffic for a command this page doesn't cover, open a
thread in [Discussions](https://github.com/jan-tdy/TapoVac-ADV/discussions)
rather than guessing at method names against a live device - see
[Protocol notes - undiscovered commands](undiscovered-commands.md) for why
that matters.
