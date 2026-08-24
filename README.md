# This is jan-tdy's fork!
What is better here?
- Native room-by-room cleaning through Home Assistant's own vacuum dialog
  (map vacuum segments to areas — no custom actions needed)
- Mop pad attached sensor
- Faster map updates while cleaning
- Fixed resume-after-pause (the original silently did nothing)
- `clean_percent` etc. now come with a proper `%` sensor, not just an attribute

# Tapo RV30 Robot Vacuum — Home Assistant Integration

Local-only Home Assistant integration for the **TP-Link Tapo RV30 Max Plus** robot vacuum.

Implements the **TPAP / SPAKE2+** authentication protocol reverse-engineered from
[python-kasa PR #1592](https://github.com/python-kasa/python-kasa/pull/1592).
No cloud dependency — communicates directly with the vacuum over your LAN.

## Features

- Full vacuum control — start, pause, stop, dock, **spot clean**
  (`vacuum.clean_spot`)
- **Native room cleaning, across every saved map/floor** — the vacuum's
  more-info dialog lets you map its rooms to Home Assistant areas and clean
  them with the standard `vacuum.clean_area` action (Home Assistant
  2026.3+, see below); rooms from multiple saved maps show up grouped by
  floor in the mapping dialog
- **Room-by-room cleaning** via `tapo_rv30.clean_rooms` service, for
  automations/scripts (supports partial name match and an optional map filter)
- Live colour **map image** rendered from LZ4 pixel data — refreshes every
  60s while actively cleaning, every 5 min otherwise (idle/docked)
- Fan speed selection (Quiet / Standard / Turbo / Max / Ultra)
- Water level select (Off / Low / Medium / High)
- Clean passes select (1 / 2 / 3)
- Battery sensor
- Mop pad attached binary sensor
- Clean progress sensor (`%`, proper `native_unit_of_measurement` — usable
  directly in Tile cards etc. without hacking a literal `%` into `state_content`)
- Error state sensor (e.g. "Ok", "Dust Bin Removed", "Trapped")
- Consumable wear sensors (main brush, side brush, filter, sensor, charge contacts)
- **Schedules sensor** — view of the schedules you've saved in the Tapo app
  (time, repeat days, rooms, clean settings), decoded from
  `get_schedule_rules` (credit:
  [peggleg/tapo-rv30](https://github.com/peggleg/tapo-rv30), who discovered
  this call — see [Protocol notes —
  schedules](#protocol-notes--schedules) below)
- **Run a saved schedule on demand** via `tapo_rv30.run_schedule` — no
  device call to trigger a schedule by ID is known to exist, so this
  reads the schedule's settings and replays them through the same
  room-cleaning calls, right now instead of waiting for its own time (see
  [Protocol notes — schedules](#protocol-notes--schedules))
- **`vacuum.send_command`** — raw passthrough to any device method (e.g.
  `command: getConsumablesInfo`), for calling anything this integration
  doesn't have a dedicated action for yet. Response is logged at info level
  on the `custom_components.tapo_rv30` logger.
- **Repair issue on room changes** — if the currently active map's rooms no
  longer match what you last mapped to Home Assistant areas (renamed,
  added, removed), Home Assistant raises a repair issue pointing back at
  the mapping dialog instead of silently leaving stale area mappings.
- Config flow UI — set up from Settings → Devices & Services
- Fixed: resuming after a pause now actually resumes (the upstream
  `start()` re-sent the same `setSwitchClean` call, which the device
  silently ignores while already `clean_on: true`)

## Requirements

- Home Assistant **2026.3+** (required for the native `vacuum.clean_area`
  room-mapping dialog — see [Requirements
  bump](#requirements-bump-to-home-assistant-20263) below)
- [HACS](https://hacs.xyz) installed
- Tapo RV30 or RV20 (RV30 Max works...) on firmware **1.2.x+** (TPAP protocol)
- Python packages (installed automatically by HACS): `requests`, `ecdsa`, `Pillow`

## Installation via HACS

[![Add to Home Assistant](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=jan-tdy&repository=TapoVac-ADV&category=integration)

Click the button above, or manually:

1. In HACS → **Integrations** → ⋮ menu → **Custom repositories**
2. Add `https://github.com/jan-tdy/TapoVac-ADV` as category **Integration**
3. Install **TapoVac ADV**
4. Restart Home Assistant
5. **Settings → Devices & Services → + Add Integration → Tapo RV30**
6. Enter your vacuum's IP address, Tapo account email, and password

## Dashboard

See [`jarvis_dashboard.yaml`](jarvis_dashboard.yaml) for a complete Lovelace dashboard.

Requires HACS frontend cards:
- [Mushroom](https://github.com/piitaya/lovelace-mushroom)
- [Xiaomi Vacuum Map Card](https://github.com/PiotrMachowski/lovelace-xiaomi-vacuum-map-card)

## Native room cleaning (vacuum more-info dialog)

Home Assistant 2026.3 added native "map vacuum segments to areas" support to
the standard vacuum entity: open the vacuum's more-info dialog, click the
settings (⚙) icon, and use **Map vacuum segments to areas** to match each
room reported by the vacuum to a Home Assistant area. Once mapped, the
**Clean area** action (`vacuum.clean_area`) lets you pick one or more HA
areas straight from the dialog — no YAML, scripts, or custom actions needed.

This integration implements that contract directly:
- `async_get_segments()` reports the rooms of **every saved map** (fetched
  live from the device each time you open the mapping dialog) — not just
  whichever one happens to be active. Room IDs are only unique *within* a
  map, so each segment's id is namespaced `<map_id>:<room_id>`, and its
  `group` is set to the map's own name — multiple floors/saved maps show up
  as separate groups in the mapping dialog rather than only ever exposing
  one of them.
- `async_clean_segments()` sends the selected rooms to the vacuum using the
  same `setSwitchClean` payload as the `tapo_rv30.clean_rooms` service (see
  [Protocol notes](#protocol-notes--room-cleaning) below), split into one
  call per map if your selection spans more than one. The vacuum can only
  physically be on one floor at a time, so at most the first call can
  actually start a clean; a second call for a different map gets caught by
  `clean_rooms()`'s own already-cleaning guard rather than doing anything
  unexpected. **Multi-map behavior is untested against a real device** —
  picking rooms from a single map/floor (the common case) is low-risk since
  it's the same call the original single-map version made.

**Upgrading from an older version:** segment IDs changed from bare
`<room_id>` to `<map_id>:<room_id>`. Any area mapping you'd already set up
in the dialog will stop matching (HA will report those areas as unmapped in
`vacuum.clean_area`, not error) — open **Map vacuum segments to areas**
again and redo it once. The older `tapo_rv30.clean_rooms` service is
unaffected either way, since it always accepts an optional `map` name and
re-resolves everything live on every call.

**Diacritics in room names:** the Tapo app lets you rename rooms with
accented characters (e.g. Slovak *á, č, ľ, ň, š, ť* …). The device reports
room names base64-encoded, and this integration decodes them as UTF-8
(`_b64name()` in `coordinator.py`), so they *display* correctly — e.g. in
the `Segment.name` shown in the area-mapping dialog and in the `rooms`
attribute, where you only ever pick from a list and never type anything.

Typing an accented room name back in, however, is a different problem:
Home Assistant's Developer Tools → Actions text fields (used with the
older `tapo_rv30.clean_rooms` service — see [Features](#features)) can
make accented characters awkward or impossible to type depending on your
keyboard/OS. To work around this, room and map name matching in
`resolve_rooms_live()` (`coordinator.py`) is diacritic-insensitive: it
strips accents (and lowercases) from both the pattern you type and the
room names before comparing. So for a room named "Kúpeľňa" you can type
the exact name, or a plain-ASCII stand-in like `kupelna`, or even just a
substring like `pel` — all three match.

### Requirements bump to Home Assistant 2026.3+

`VacuumEntityFeature.CLEAN_AREA`, the `Segment` type, and the
`async_get_segments`/`async_clean_segments` entity methods used above were
only added to Home Assistant core in the 2026.3 release. This also required
removing the entity's now-obsolete `VacuumEntityFeature.BATTERY` flag and
`battery_level` property (both fully removed from Home Assistant core
some time before this release) — battery level is unaffected and remains
available as its own sensor entity.

## Standalone CLI

[`tapo_vacuum.py`](tapo_vacuum.py) is a standalone command-line tool (no HA required):

```bash
pip install requests ecdsa lz4 Pillow
python3 tapo_vacuum.py status
python3 tapo_vacuum.py map
python3 tapo_vacuum.py clean kitchen lounge
```

## Supported Models

- **RV30 Max Plus (EU)** firmware 1.3.2
- **RV20 Max Plus (EU)** firmware 1.2.0

Should work on any Tapo RobovAC using TPAP.

## Protocol notes — room cleaning

The `setSwitchClean` payload for selective room cleaning was reverse-engineered
from live device traffic and, as far as we know, is not documented anywhere else.
Neither [python-kasa](https://github.com/python-kasa/python-kasa) (which only
implements whole-house `clean_mode: 0`) nor the official Home Assistant Tapo
integration implement room cleaning at the time of writing.

The correct payload is:

```json
{
  "clean_mode": 3,
  "clean_on": true,
  "clean_order": true,
  "force_clean": false,
  "map_id": <int>,
  "room_list": [<room_id>, ...],
  "start_type": 1
}
```

Key points:
- `clean_mode: 2` is **spot clean** — the `rooms` array is silently ignored
- `clean_mode: 3` is selective room clean
- `clean_mode: 5` is a saved **cleaning preset** ("custom rule") — instead
  of `room_list`, it takes `custom_rule_id: <int>` (see [Protocol notes —
  schedules](#protocol-notes--schedules) below)
- `room_list` is a plain integer array of room IDs (the pixel values used in the LZ4 map)
- Discovered by reading `getSwitchClean` while the official Tapo app performed a room clean

## Protocol notes — schedules

`get_schedule_rules` (params `{"start_index": 0}`, response at
`result.rule_list`) returns your saved Tapo app schedules. This call was
discovered by [peggleg/tapo-rv30](https://github.com/peggleg/tapo-rv30) — in
response to [epg-pers/tapo-rv30-ha#13](https://github.com/epg-pers/tapo-rv30-ha/issues/13)
— and confirmed there against an **AES-transport RV30C Mop**. It also works
against **TPAP-transport hardware** (the kind this fork's `tpap.py` talks
to) — confirmed by a user's real RV30 Max, returning entries like:

```yaml
- id: S1
  enabled: true
  time: '14:35'
  days: [Mon, Tue, Wed, Thu, Fri]
  repeat: true
  rooms: []
  room_ids: []
  clean_order: false
  suction: 2
  water_level: 2
  clean_passes: 1
```

Each rule's `week_day` is a bitmask, `Sun=1, Mon=2, Tue=4, Wed=8, Thu=16,
Fri=32, Sat=64` — confirmed against a real device: a schedule set for
Mon/Wed/Fri came back as `week_day=42`, and `2+8+32=42` exactly.

**Cleaning presets:** if a schedule is configured in the Tapo app against a
saved "cleaning preset" instead of picking rooms directly, `rooms`/`room_ids`
above come back empty — the preset is referenced instead through
`clean_attr.clean_mode: 5` and `clean_attr.custom_rule_id: <int>` (confirmed
against a real device's raw schedule data; also present:
`clean_attr.map_id`, which the room-list schedules carry too). There's no
known call to resolve a `custom_rule_id` back to the actual room names it
covers, so the decoded `custom_rule_id`/`is_preset` fields are as specific
as this integration can currently get — `rooms` stays empty for these.

No device call to trigger a saved schedule directly by ID has been found in
either fork. `tapo_rv30.run_schedule` instead **synthesizes** the same
effect: it looks up the schedule via `get_schedule_rules`, applies its
`clean_attr` (suction, water level, clean passes) with `setCleanAttr`, then:
- if `custom_rule_id` is set, runs that preset via `clean_custom_rule()`
  (the same `setSwitchClean` shape as room cleaning, but `clean_mode: 5` +
  `custom_rule_id` instead of `clean_mode: 3` + `room_list`);
- else if `room_list` is set, cleans those rooms via `clean_rooms()`;
- else starts a whole-house clean.

This should produce the same clean the schedule would run on its own — but
it's an inference from the data shape, not a confirmed device "run now"
feature, and hasn't been tested end-to-end against a real device.

### Viewing schedules in a dashboard

The `Schedules` sensor's own state is just a count — the actual list lives
in its `schedules` attribute, which a Tile/entity card won't show by
default. A Markdown card renders it as a readable table (swap in your own
entity ID). Two easy-to-miss gotchas this snippet already accounts for:

- **`content: |`, not `content: >`.** YAML's folded style (`>`) joins every
  line with a space, destroying the table's row structure entirely (each
  Markdown table row must be on its own physical line). Literal style (`|`)
  keeps line breaks exactly as written — that's what you actually want here.
- **The `{%-`/`-%}` whitespace-trim markers around the loop.** Without
  them, Jinja leaves a blank line where each `{% for %}`/`{% endfor %}` tag
  sat on its own line, which breaks the Markdown table right after the
  header (you'd see a table with only the header row, then the data rows
  dumped as plain text below it).

```yaml
type: markdown
content: |
  {% set scheds = state_attr('sensor.YOUR_VACUUM_schedules', 'schedules') or [] %}
  {% if scheds %}
  | Time | Days | Rooms | Enabled |
  |---|---|---|---|
  {%- for s in scheds %}
  | {{ s.time }} | {{ s.days | join(', ') }} | {{ s.rooms | join(', ') if s.rooms else ('Preset #' ~ s.custom_rule_id if s.is_preset else 'Whole house') }} | {{ '✅' if s.enabled else '❌' }} |
  {%- endfor %}
  {% else %}
  No schedules found.
  {% endif %}
```

## Protocol notes — undiscovered commands

Two things aren't implemented because no working device call for them is
known: **LOCATE** ("find me", a native `vacuum` feature with no TPAP
equivalent found), and resolving a schedule's `custom_rule_id` back to the
actual room names it covers (see [Protocol notes —
schedules](#protocol-notes--schedules) above).

`vacuum.send_command` (raw passthrough to any device method — see
[Features](#features)) is there partly as an escape hatch for trying to
find these. Guessed against a real TPAP-transport RV30 Max: `setRobotFindMe`,
`setFindMe`, `playFindMe`, `get_custom_clean_rules` (with and without a
`start_index` param) — all four returned the identical `Device error -1002`,
which is most likely a generic "unrecognized method" response rather than
anything specific to those names. Guessing further this way is probably low
yield without a real captured request to work from (as the original
`setSwitchClean`/`get_schedule_rules` discoveries both had) — if you want to
keep trying, `send_command`'s error now surfaces the actual device error
directly in the action's response as of the fix for the "Unknown error"
issue above, no log-diving needed.

## Credits

This is a fork of [epg-pers/tapo-rv30-ha](https://github.com/epg-pers/tapo-rv30-ha),
which did the hard work of reverse-engineering the TPAP protocol, room
cleaning, and map rendering in the first place. All credit for that
foundation goes there; this fork builds native Home Assistant area-mapping
support and a few other additions on top of it.

The saved-schedules sensor is ported from
[peggleg/tapo-rv30](https://github.com/peggleg/tapo-rv30), which discovered
`get_schedule_rules` — see [Protocol notes —
schedules](#protocol-notes--schedules) above.

SPAKE2+ protocol implementation based on reverse engineering by the
[python-kasa](https://github.com/python-kasa/python-kasa) project.
