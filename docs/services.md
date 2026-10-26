# Services

All services target one or more `vacuum` entities of this integration
(`Developer Tools → Actions`, or `service: tapo_rv30.<name>` in a script /
automation). Fields that accept room names, map names or preset names
resolve live against the robot on every call and are
[diacritic-insensitive](configuration.md#diacritics-and-room-names).

Suction, water level and passes fields that appear across several services
share the same values everywhere:

- **Suction:** `Quiet`, `Standard`, `Turbo`, `Max`, `Ultra`
- **Water:** `off`, `low`, `medium`, `high` (mop-capable models only)
- **Passes:** `1`–`3`

## Cleaning

### `clean_rooms`

Starts a selective room clean.

| Field | Required | Description |
| --- | --- | --- |
| `rooms` | no | List of room names (as shown in the Tapo app / sidebar map). |
| `room_ids` | no | List of numeric room IDs, as an alternative to `rooms`. |
| `map` | no | Which saved map to resolve rooms against; defaults to the active map. |
| `map_id` | no | Numeric map ID, as an alternative to `map`. |
| `suction`, `water`, `passes` | no | Override the clean settings for this run only. |

Provide either `rooms` or `room_ids`; `map`/`map_id` are optional in both
cases - see [Protocol notes - room cleaning](protocol/room-cleaning.md)
for the wire format this builds.

### `clean_zone`

Cleans one or more rectangular zones instead of whole rooms.

| Field | Required | Description |
| --- | --- | --- |
| `zones` | yes | List of `[x1, y1, x2, y2]` coordinate rectangles, in the robot's own millimeter coordinate space (same space as `go_to`). |
| `suction`, `water`, `passes` | no | Override for this run only. |

### `clean_zone` coordinates vs. zone presets

Finding zone coordinates by trial and error is tedious; see
[`create_zone_preset`](#create_zone_preset) below to save a zone once
(e.g. from the map editor on the sidebar page) and reuse it by name.

### `set_room_settings`

Persists suction/water/passes for specific rooms on the robot itself, so
future cleans of those rooms (including ones started from the Tapo app)
use these settings without needing this integration involved.

| Field | Required | Description |
| --- | --- | --- |
| `rooms` | yes | Room names to update. |
| `map` | no | Which map the rooms belong to. |
| `suction`, `water`, `passes` | no | New settings for the listed rooms. |

### `go_to`

Sends the robot to a specific point.

| Field | Required | Description |
| --- | --- | --- |
| `x`, `y` | yes | Target coordinates in millimeters, robot coordinate space. |

### `remote_drive`

Manual driving, mirroring the Tapo app's remote-control mode.

| Field | Required | Description |
| --- | --- | --- |
| `command` | yes | One of `enter`, `forward`, `backward`, `left`, `right`, `stop`, `exit`. Call with `enter` first to put the robot in remote-control mode, `exit` to leave it. |

## Zone presets

Zone presets save a rectangle (or set of rectangles) under a name, so you
don't need to re-enter coordinates every time.

### `create_zone_preset`

| Field | Required | Description |
| --- | --- | --- |
| `name` | yes | Preset name. |
| `zones` | yes | List of `[x1, y1, x2, y2]` rectangles. |
| `map_id` | no | Restrict the preset to a specific map. |

### `get_zone_presets`

No fields. Returns the saved presets for the target vacuum as service
response data.

### `run_zone_preset`

| Field | Required | Description |
| --- | --- | --- |
| `preset` | yes | Preset name. |
| `suction`, `water`, `passes` | no | Override for this run only. |

### `update_zone_preset`

| Field | Required | Description |
| --- | --- | --- |
| `preset` | yes | Preset to update. |
| `name` | no | New name. |
| `zones` | no | New rectangle list. |

### `delete_zone_preset`

| Field | Required | Description |
| --- | --- | --- |
| `preset` | yes | Preset to delete. |
| `confirm` | yes | Must be `true` - a safety guard against an accidental call. |

## Cleaning presets

Presets ("custom rules" in the device's own terms) bundle a room set with
its own suction/water/passes/clean-order, matching what the Tapo app calls
a saved cleaning preset. Each existing preset also gets its own
[button entity](entities.md#button) automatically.

### `create_preset`

| Field | Required | Description |
| --- | --- | --- |
| `name` | yes | Preset name. |
| `rooms` | yes | Room names included in the preset. |
| `map` | no | Which map the rooms belong to. |
| `suction`, `water`, `passes` | no | Settings for the preset. |
| `clean_order` | no (default `true`) | Whether rooms are cleaned in map order rather than an arbitrary order. |

### `update_preset`

| Field | Required | Description |
| --- | --- | --- |
| `preset` | yes | Preset to update. |
| `name`, `rooms`, `suction`, `water`, `passes`, `clean_order` | no | Fields to change. |

### `delete_preset`

| Field | Required | Description |
| --- | --- | --- |
| `preset` | yes | Preset to delete. |
| `confirm` | yes | Must be `true`. |

### `run_preset`

| Field | Required | Description |
| --- | --- | --- |
| `preset` | yes | Preset to run. |

## Schedules

These mirror the robot's own schedule store (the same one the Tapo app
edits) - see [Protocol notes - schedules](protocol/schedules.md) for the
reverse-engineered format, including how `run_schedule` works around there
being no device call to trigger a saved schedule directly.

### `add_schedule`

| Field | Required | Description |
| --- | --- | --- |
| `time` | yes | Time of day. |
| `days` | yes | List of `Mon`…`Sun`. |
| `rooms` / `room_ids` | no | Rooms to clean; omit for a whole-house schedule. |
| `preset` | no | Run a saved preset instead of a room list. |
| `map` | no | Map the rooms/preset belong to. |
| `suction`, `water`, `passes` | no | Clean settings for this schedule. |
| `enabled` | no (default `true`) | Whether the schedule is active. |
| `ignore_dnd` | no (default `false`) | Run even during the Do Not Disturb window. |

### `set_schedule`

Same fields as `add_schedule`, plus a required `schedule_id` (e.g. `S1`,
as reported by the Schedules sensor) identifying which existing schedule
to update. Only the fields you pass are changed.

### `remove_schedule`

| Field | Required | Description |
| --- | --- | --- |
| `schedule_id` | no | Schedule to remove. |
| `all` | no (default `false`) | Remove every schedule instead of one. |

### `run_schedule`

| Field | Required | Description |
| --- | --- | --- |
| `schedule_id` | yes | Schedule to run now, synthesized from its saved settings - see [Protocol notes - schedules](protocol/schedules.md) for exactly how. |

## Maps

### `save_map_setup`

Snapshots the current map's rooms, zones and furniture layout so it can be
restored later.

| Field | Required | Description |
| --- | --- | --- |
| `map` | no | Map to snapshot; defaults to the active map. |
| `force` | no (default `false`) | Overwrite an existing snapshot for that map without asking. |

### `apply_map_setup`

Restores a previously saved layout onto a map.

| Field | Required | Description |
| --- | --- | --- |
| `map` | no | Target map. |
| `source_map` | no | Map whose saved setup to apply, if different from `map`. |
| `dry_run` | no (default `false`) | Report what would change without writing it. |
| `confirm` | no (default `false`) | Required to actually write when not a dry run. |

### `rename_map`

| Field | Required | Description |
| --- | --- | --- |
| `map` | yes | Map to rename. |
| `name` | yes | New name. |

### `copy_map`

| Field | Required | Description |
| --- | --- | --- |
| `map` | yes | Map to copy. |
| `name` | yes | Name for the copy. |
| `base_url` | no | Home Assistant base URL, used when the robot needs to fetch the copy over HTTP. |
| `verification_code` | no | Tapo account 2FA code, if the robot's cloud step requires one. |

### `delete_map`

| Field | Required | Description |
| --- | --- | --- |
| `map` | yes | Map to delete. |
| `confirm` | yes | Must be `true`. |

### `set_map` (select the active map)

| Field | Required | Description |
| --- | --- | --- |
| `map` | yes | Map to make active. |

### `set_map_lock`

Prevents the robot from auto-merging a locked map into another one while
mapping (useful on multi-floor setups).

| Field | Required | Description |
| --- | --- | --- |
| `map` | no | Map to lock/unlock; defaults to the active map. |
| `locked` | yes | `true` to lock, `false` to unlock. |

## Backups

### `fetch_cloud_map_backups`

Refreshes the list of cloud map backups available to restore from.

| Field | Required | Description |
| --- | --- | --- |
| `verification_code` | no | Tapo account 2FA code, if required. |

### `restore_map_backup`

| Field | Required | Description |
| --- | --- | --- |
| `map` | no | Map to restore onto. |
| `file` | yes | Backup filename, as listed by `fetch_cloud_map_backups`. |
| `base_url` | no | Home Assistant base URL for the robot to fetch the file from. |
| `use_cloud_url` | no (default `false`) | Use TP-Link's cloud URL instead of `base_url`. |
| `new_name` | no | Restore as a new map with this name instead of overwriting `map`. |
| `verification_code` | no | Tapo account 2FA code, if required. |
| `confirm` | yes | Must be `true`. |

## Diagnostics

### `get_clean_records`

| Field | Required | Description |
| --- | --- | --- |
| `limit` | no | Maximum number of records to return (1–100). |

Returns clean history records as service response data.

### `send_raw`

Sends a raw TPAP/AES method call directly to the device. Intended for
development and reverse-engineering - see
[Protocol notes - undiscovered commands](protocol/undiscovered-commands.md)
before guessing method names: an unknown method can, in the worst case,
factory-reset the robot.

| Field | Required | Description |
| --- | --- | --- |
| `method` | yes | Method name, e.g. `getCleanAttr`. |
| `params` | no | JSON object of parameters. |
| `force` | no (default `false`) | Send even if the method isn't in the integration's known-safe list. |

## Matter

### `get_matter_setup_code`

No fields. Returns the robot's current Matter setup code as service
response data (also available via the Matter pairing button's attributes
and the Matter sensor).

### `remove_matter_fabric`

| Field | Required | Description |
| --- | --- | --- |
| `fabric_index` | yes | Index of the Matter fabric to remove (1–255), as reported by the Matter sensor's attributes. |
