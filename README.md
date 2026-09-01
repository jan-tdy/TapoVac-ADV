# This is jan-tdy's fork called TapoVac-ADV!
**If you found this useful, please give this repo a star!** **Also check out my other repos!**

<details>
<summary>What is better in this fork?</summary>
- Native room-by-room cleaning through Home Assistant's own vacuum dialog
  (map vacuum segments to areas, across every saved map/floor — no custom
  actions needed)
- Read your saved Tapo-app schedules, and actually launch one on demand
  (`tapo_rv30.run_schedule`, including cleaning-preset-based schedules)
- Mop pad attached sensor
- Spot clean support, and a `send_command` escape hatch for raw device calls
- Faster map updates while cleaning
- Fixed resume-after-pause (the original silently did nothing)
- Fixed starting a new clean while one's already running (device `-3002`)
- `clean_percent` etc. now come with a proper `%` sensor, not just an attribute
- A proper integration icon, and an MIT license (the original had neither)
- Screenshots in the README.md
- Want something added? See [Contributing](#contributing) below
</details>

# Tapo RV20/RV30/RV50 Robot Vacuums — Home Assistant Integration

Warning: this is not an official integration!

Local-only Home Assistant integration for the **TP-Link Tapo RV30 Max Plus** robot vacuum.

Implements the **TPAP / SPAKE2+** authentication protocol reverse-engineered from
[python-kasa PR #1592](https://github.com/python-kasa/python-kasa/pull/1592).
No cloud dependency — communicates directly with the vacuum over your LAN.

## Verified supported Models
- **RV30 Max (EU)** according to @jan-tdy
- **RV50 Pro Omni (EU)** according to @asiar1993
- 
**Does your vacuum work with this integration but isn't in the list? Open an issue, please!**

Should work on any Tapo RobovAC using TPAP.

Dock controls are available as button entities — see [Dock support (Plus /
Omni)](#dock-support-plus--omni) below. **Plus** docks (auto-empty only,
e.g. RV30 Max Plus) and **Omni** docks (all-in-one, e.g. RV50 (Pro) Omni —
auto-empty *and* mop wash/dry) are different hardware tiers: which
buttons actually appear is decided per device by probing what its
firmware confirms it has, not assumed from "Plus" or "Omni" in a model
name.


---

### 🗺️ Map Limitations & Tips

#### ⏱️ Update Frequency
The robot vacuum cannot easily stream live map data every few seconds. Even the official Tapo app only updates roughly every 20 seconds. To optimize performance, this integration is configured to refresh at the following intervals:
* **While cleaning:** Updates every **60 seconds**
* **While idle/docked:** Updates every **5 minutes**

#### 🔄 Map Rotation Fix
If your map is oriented incorrectly, you can rotate it using [card-mod](https://github.com). Add the following style block to your Lovelace card configuration:

```yaml
card_mod:
  style: |
    ha-card {
      transform: rotate(180deg);
      transition: none !important;
    }
```
*(You can change `180deg` to whatever angle fits your layout).*

#### 🛋️ Missing Furniture
Furniture items placed within the official Tapo app are stored in the TP-Link cloud and cannot be pulled directly into Home Assistant. 
* **Current workaround:** Use Home Assistant `picture-elements` to manually layer your furniture over the map.
* **Future roadmap:** A custom card is currently **under development** that will allow you to easily rotate the map and add furniture elements natively. Stay tuned!


---

### 🧺 Dock support (Plus / Omni)

Adds up to four dock-action button entities, each created **only** if the
vacuum's own firmware confirms (via a live probe at startup) that it has
that specific feature — nothing is assumed from the model name, and a
device the probe finds nothing for (e.g. a plain RV30/RV20 with no dock
at all) gets none of these entities:

| Button | Feature key | Typically found on |
|---|---|---|
| **Empty Dust Bin** | `dust_collection` | **Plus** docks (auto-empty only) *and* **Omni** docks |
| **Wash Mop** | `back_wash_mode` | **Omni** docks only — Plus docks have no mop-washing hardware |
| **Dry Mop** | `dry_mop_mode` | **Omni** docks only |
| **Remove Hair** | `cut_hair_mode` | Varies by model — this is a robot self-cleaning feature, not strictly tied to dock tier |

So a **Plus** dock owner should expect to see just *Empty Dust Bin*; an
**Omni** dock owner should additionally see *Wash Mop*/*Dry Mop* if their
firmware confirms them.

**Confirmed working** against a real RV50 Pro Omni (credit: @asiar1993).
The underlying TPAP method names (`setSwitchDustCollection`,
`setWashMopSwitch`, `setDryMopSwitch`, `setCutHairSwitch`, and the
`getDustCollectionInfo` / `getBackWashMode` / `getDryMopMode` /
`getCutHairMode` probes used to detect them) were ported from
[cavefire/tapo-vacuum-ha](https://github.com/cavefire/tapo-vacuum-ha) — a
sibling fork that independently reverse-engineered RV50 support — rather
than guessed from scratch here.

Seeing something different from the table above (missing button, wrong
action fires)? That's still useful to know — see
[Contributing](#contributing).

---

<details>
<summary>Features</summary>
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
- **`room_geometry`** attribute on the map camera entity — each room's
  centroid, bounding box and rendered colour, in the same pixel space as
  the map image itself, for frontend cards (e.g.
  [VacuumCard-ADV](https://github.com/jan-tdy/VacuumCard-ADV)) to do
  click-to-room hit-testing directly against the `<img>` without
  reimplementing this integration's scale/flip conventions
- Fan speed selection (Quiet / Standard / Turbo / Max / Ultra)
- Water level select (Off / Low / Medium / High)
- Clean passes select (1 / 2 / 3)
- Battery sensor
- Mop pad attached binary sensor
- Clean progress sensor (`%`, proper `native_unit_of_measurement` — usable
  directly in Tile cards etc. without hacking a literal `%` into `state_content`)
- **Current Room sensor** — which room the vacuum is currently in, inferred
  locally from its position against the map's room geometry (no extra
  device call). Reads `unknown` when the vacuum isn't inside a mapped room
  (e.g. a hallway), and updates at the same cadence as the map image.
- Error state sensor (e.g. "Ok", "Dust Bin Removed", "Trapped")
- Consumable wear sensors (main brush, side brush, filter, sensor, charge contacts)
- **Schedules sensor** — view of the schedules you've saved in the Tapo app
  (time, repeat days, rooms, clean settings), decoded from
  `get_schedule_rules` (credit:
  [peggleg/tapo-rv30](https://github.com/peggleg/tapo-rv30), who discovered
  this call — see [Protocol notes —
  schedules](#protocol-notes-schedules) below)
- **Run a saved schedule on demand** via `tapo_rv30.run_schedule` — no
  device call to trigger a schedule by ID is known to exist, so this
  reads the schedule's settings and replays them through the same
  room-cleaning calls, right now instead of waiting for its own time (see
  [Protocol notes — schedules](#protocol-notes-schedules))
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

</details>

<details>
<summary>Screenshots</summary>
  
<img width="588" height="415" alt="image" src="https://github.com/user-attachments/assets/57c284ea-e3e3-420e-8103-914416bc2569" /> <img width="417" height="410" alt="image" src="https://github.com/user-attachments/assets/0c5d03db-167d-4f1b-914f-92c167feeda1" /> <img width="1873" height="916" alt="image" src="https://github.com/user-attachments/assets/e8121f4f-2122-4eaa-aa52-3eebd5078aa2" />

</details>

<details>
<summary>Requirements</summary>
  
- Home Assistant **2026.3+** (required for the native `vacuum.clean_area`
  room-mapping dialog — see [Requirements
  bump](#requirements-bump-to-home-assistant-20263) below)
- [HACS](https://hacs.xyz) installed
- Tapo RV30 or RV20 (RV30 Max works...) on firmware **1.2.x+** (TPAP protocol)
- Python packages (installed automatically by HACS): `requests`, `ecdsa`, `Pillow`

</details>

## Installation via HACS

[![Add to Home Assistant](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=jan-tdy&repository=TapoVac-ADV&category=integration)

Click the button above, or manually:

1. In HACS → **Integrations** → ⋮ menu → **Custom repositories**
2. Add `https://github.com/jan-tdy/TapoVac-ADV` as category **Integration**
3. Install **TapoVac ADV**
4. Restart Home Assistant
5. **Settings → Devices & Services → + Add Integration → TapoVac-ADV**
6. Enter your vacuum's IP address, Tapo account email, and password

--

## Dashboard

See [`jarvis_dashboard.yaml`](jarvis_dashboard.yaml) for a Lovelace dashboard view built entirely from
stock Home Assistant tile cards (`sections` view type) — no third-party card library needed for the
controls themselves.

Requires the HACS frontend card:
- [card-mod](https://github.com/thomasloven/lovelace-card-mod) (only for rotating the map camera image)

Furniture placed on the map in the Tapo app isn't rendered in the map camera
image — see [Furniture isn't rendered on the
map](#furniture-isnt-rendered-on-the-map) for why, and a Picture Elements
overlay workaround.

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
  [Protocol notes](#protocol-notes---room-cleaning) below), split into one
  call per map if your selection spans more than one. The vacuum can only
  physically be on one floor at a time, so at most the first call can
  actually start a clean; a second call for a different map gets caught by
  `clean_rooms()`'s own already-cleaning guard rather than doing anything
  unexpected. **Multi-map behavior is untested against a real device** —
  picking rooms from a single map/floor (the common case) is low-risk since
  it's the same call the original single-map version made.

**Upgrading from an older version:** segment IDs changed from bare
`<room_id>` to `<map_id>:<room_id>`. Any area mapping you'd already set up
in the dialog uses the old bare-id format; `async_clean_segments()`
recognizes ids with no `<map_id>:` prefix and sends them against whichever
map the vacuum is currently on, so `vacuum.clean_area` keeps working
without a crash. Still, open **Map vacuum segments to areas** again and
redo it once you get a chance, since a bare id is ambiguous across multiple
saved maps/floors. The older `tapo_rv30.clean_rooms` service is unaffected
either way, since it always accepts an optional `map` name and re-resolves
everything live on every call.

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

</details>

---

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
```

Configure it via three environment variables — `TAPO_HOST` (the vacuum's
local IP address), `TAPO_USER` and `TAPO_PASS` (your TP-Link/Tapo account
email and password — the same account you sign in with in the Tapo app).
Running any command without all three set exits immediately with a message
naming which one(s) are missing, instead of an opaque connection failure.

Simplest is to export them directly in your shell:

```bash
export TAPO_HOST=192.168.1.50 TAPO_USER=you@example.com TAPO_PASS=yourpassword
python3 tapo_vacuum.py status
python3 tapo_vacuum.py map
python3 tapo_vacuum.py clean kitchen lounge
```

Or keep them in a `.env` file (already excluded by `.gitignore`) and load
it into the shell before running — no extra dependency needed:

```bash
cat > .env <<'EOF'
TAPO_HOST=192.168.1.50
TAPO_USER=you@example.com
TAPO_PASS=yourpassword
EOF

set -a; source .env; set +a
python3 tapo_vacuum.py status
```

## Supported Models

<details>
<summary>Developer notes</summary>

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

</details>

## Protocol notes — undiscovered commands

Three things aren't implemented because no working device call for them is
known: **LOCATE** ("find me", a native `vacuum` feature with no TPAP
equivalent found), resolving a schedule's `custom_rule_id` back to the
actual room names it covers (see [Protocol notes —
schedules](#protocol-notes--schedules) above), and furniture placed on the
map in the Tapo app (see [Furniture isn't rendered on the
map](#furniture-isnt-rendered-on-the-map) below). A real device traffic
capture points at the first two being handled through TP-Link's cloud API
rather than the local protocol this integration speaks — full write-up,
what was tried, and why, is in [Discussion
#8](https://github.com/jan-tdy/TapoVac-ADV/discussions/8) rather than here.

### Furniture isn't rendered on the map

The `getMapData` response this integration renders the map camera image
from — room polygons in `area_list`, the LZ4 pixel buffer, dock/vacuum
coordinates — has no field identified as carrying furniture placement, and
there's no known device call to fetch it separately. It may only be
computed/stored client-side in the Tapo app, or sit behind a call nobody's
captured yet — if you can grab a traffic capture of the app showing
furniture that would help, see [Discussion
#8](https://github.com/jan-tdy/TapoVac-ADV/discussions/8) for how.

Until then, the workaround is to overlay furniture yourself with a
[Picture Elements
card](https://www.home-assistant.io/dashboards/picture-elements/) on top
of the map camera image — icons placed at fixed `x`/`y` percentages hold
their position across map refreshes as long as the vacuum doesn't remap:

```yaml
type: picture-elements
image: /api/camera_proxy/camera.jarvis_map   # replace with your own map camera entity id
elements:
  - type: icon
    icon: mdi:sofa
    style:
      top: 42%
      left: 61%
```

## Contributing

Ideas, findings, issues, and PRs are all welcome — this fork exists because
someone filed a feature request on the original repo and someone else
picked it up. If you want to dig into an undiscovered command (see above)
or propose something new, start a thread in
[Discussions](https://github.com/jan-tdy/TapoVac-ADV/discussions); for
concrete bugs or ready changes, open an
[issue](https://github.com/jan-tdy/TapoVac-ADV/issues) or a pull request
directly.

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

The Plus/Omni dock actions (empty/wash/dry/hair-removal — see [Dock
support (Plus / Omni)](#dock-support-plus--omni) above) port the TPAP
method names discovered by
[cavefire/tapo-vacuum-ha](https://github.com/cavefire/tapo-vacuum-ha)'s
independent RV50 work.
