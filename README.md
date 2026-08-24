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

- Full vacuum control — start, pause, stop, dock
- **Native room cleaning** — the vacuum's more-info dialog lets you map its
  rooms to Home Assistant areas and clean them with the standard
  `vacuum.clean_area` action (Home Assistant 2026.3+, see below)
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
- **Schedules sensor** — read-only view of the schedules you've saved in the
  Tapo app (time, repeat days, rooms, clean settings), decoded from
  `get_schedule_rules` (credit:
  [peggleg/tapo-rv30](https://github.com/peggleg/tapo-rv30), who discovered
  this call — see the caveat in
  [Native room cleaning](#native-room-cleaning-vacuum-more-info-dialog)
  below). This only shows what's scheduled; no call to trigger a schedule
  on demand has been found yet.
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
- `async_get_segments()` reports the rooms of the vacuum's *currently active*
  map (fetched live from the device each time you open the mapping dialog).
- `async_clean_segments()` sends the selected rooms to the vacuum using the
  same `setSwitchClean` payload as the `tapo_rv30.clean_rooms` service (see
  [Protocol notes](#protocol-notes--room-cleaning) below).

**Limitation — multiple saved maps:** room IDs are only unique *within* a
map, and the segment list only ever reflects the map that is active at the
time. If your vacuum has multiple saved maps (e.g. multiple floors), only
the currently active one can be mapped to areas; switching the active map
on the device may require re-doing the area mapping. The older
`tapo_rv30.clean_rooms` service is unaffected by this, since it accepts an
optional `map` name and re-resolves it live on every call.

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
- `room_list` is a plain integer array of room IDs (the pixel values used in the LZ4 map)
- Discovered by reading `getSwitchClean` while the official Tapo app performed a room clean

## Protocol notes — schedules

`get_schedule_rules` (params `{"start_index": 0}`, response at
`result.rule_list`) returns your saved Tapo app schedules. This call was
discovered by [peggleg/tapo-rv30](https://github.com/peggleg/tapo-rv30) — in
response to [epg-pers/tapo-rv30-ha#13](https://github.com/epg-pers/tapo-rv30-ha/issues/13)
— and confirmed there against an **AES-transport RV30C Mop**. It has *not*
been independently confirmed against TPAP-transport hardware (the kind this
fork's `tpap.py` talks to) — ported here on the reasonable-but-unproven bet
that it's the same device firmware surface either way, just reached through
a different login/encryption layer. If your `sensor.*_schedules` entity
comes back empty or errors, that's the most likely reason — open an issue.

Each rule's `week_day` is a bitmask, `Sun=1, Mon=2, Tue=4, Wed=8, Thu=16,
Fri=32, Sat=64` — confirmed against a real device: a schedule set for
Mon/Wed/Fri came back as `week_day=42`, and `2+8+32=42` exactly.

Only reading schedules is implemented. No call to trigger one on demand
(as opposed to waiting for its own time) has been found in either fork.

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
