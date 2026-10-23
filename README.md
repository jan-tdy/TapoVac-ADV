# This is jan-tdy's fork called TapoVac-ADV!
**If you found this useful, please give this repo a star!** **Also check out my other repos!**

You can take a look at my issue and pr queue if you are wondering why is something stale for days [here](https://github.com/issues/assigned?q=is%3Aissue+or+is%3Apr+state%3Aopen+archived%3Afalse+user%3Ajan-tdy+sort%3Acreated-asc)

## Upstream vs. this fork

Both integrations speak the same local protocol (TPAP over SPAKE2+) and expose
the same **11 entity platforms** and the same **14 services** — so anything you
can drive from an automation works identically. What differs is what's built on
top of that protocol.

| Area | Upstream `epg-pers/tapo-rv30-ha` | This fork `TapoVac-ADV` |
| --- | --- | --- |
| Version | `0.20.0` | `4.0.0` |
| Protocol | TPAP over SPAKE2+ | same |
| Entity platforms | 11 | 11 (same set) |
| Services | 14 | 14 (same set) |
| License | GPL-3.0 | GPL-3.0 (same) |
| Native room cleaning | `clean_rooms` service only | Service **mapped into HA's own vacuum dialog** — tick rooms in the more-info card, across every saved map/floor, no custom actions |
| Schedules | Written only (`add`/`set`/`remove`) | **Read back and launchable on demand** via `run_schedule`, incl. cleaning-preset schedules, with Do-Not-Disturb checks |
| Smart cleaning planner | Sidebar page: due rooms, cleaning windows, one run per window, away = person entities only | **Sidebar page of its own, everything configurable** — run policy (one run per window / repeat with a minimum gap), away condition watching **any entity** (`input_boolean`, tracker, group), room occupancy from area sensors **or a person's area presence or any manual entity** (works without motion sensors), per-room "ignore occupancy", notifications (persistent / `input_text` / notify service). **Off until you turn it on; preview-only by default** |
| Map image | Rooms + furniture | Rooms, **live cleaning path** (swept strip ~33 cm wide + centre line), **last-clean history**, robot & dock drawn as logo-styled markers |
| Furniture on the map | Drawn by default | **Off by default** (dashboard cards already draw it from `map_geometry`); Options-flow toggle to re-enable |
| Options flow | Sidebar panel on/off | Poll interval + draw-furniture toggle + planner page on/off |
| Extras | Mop-pad sensor, spot clean, `send_raw` escape hatch, faster map updates | same, plus Matter pairing state, Assist voice sentences, device triggers, blueprints, network discovery with IP tracking, and read-only info getters in the diagnostics (clock, Wi-Fi state, voice language, auto-dust) |
| Frontend assets | `tapo-rv30-card.js`, `-panel.js`, `-strategy.js` | **`tapo-planner-panel.js`** — the planner page, styled like this repo's dashboard cards; stock HA cards elsewhere |
| Tests | 8 test files | **10 test files / 125 tests**, incl. end-to-end SPAKE2+ interop against an in-repo `FakeDevice` |
| Docs | mkdocs site (GitHub Pages) | README only |
| CI | `validate` + `docs` + `release` | `hassfest` + `tests` + `validate` |
| Branding | — | Integration icon + README screenshots |

### Fixed here but not upstream

- Resume-after-pause (the original silently did nothing)
- Starting a new clean while one's already running (device `-3002`)
- A room/spot clean requested while already cleaning or paused raising a raw
  `-3001`/`-3002` error (or being silently dropped) — now a readable error
- `send()` blindly re-authenticating and resending a command the device had
  already answered with a real error code — it could double-execute a room clean
- A single failed dock-feature probe discarding every dock feature already
  confirmed, hiding those buttons until the next restart
- Action calls surfacing device errors as raw "Unexpected exception" tracebacks
  instead of a readable error in the action's response (also on the Volume
  number, Clean Passes/Water Level/Area Unit selects, Child Lock switch and the
  room-mapping dialog — see [#50](https://github.com/jan-tdy/TapoVac-ADV/issues/50))
- Dock-action buttons reporting a hardcoded "Tapo RV30 Max Plus" instead of the
  model actually read from the device
- Failing to load at all on HA 2026.10+, which removed
  `async_extract_referenced_entity_ids` — now version-detected, not assumed
- The Map camera entity permanently showing "unavailable" (a `NameError` on
  every setup after the v2.0.0 entity-mixin refactor)
- A "401 Client Error: Unknown Status" failure loop — a stale `stok` answered
  with plain HTTP 401 is now re-handshaked instead of failing every poll
- Water level / schedule writes being reverted by stale reads
  ([#51](https://github.com/jan-tdy/TapoVac-ADV/issues/51))

Plus: status polls retry briefly on a transport blip instead of flipping every
entity unavailable; `cannot_connect` now logs the real exception (host/port only,
never credentials, [#47](https://github.com/jan-tdy/TapoVac-ADV/issues/47)); polls
batch their ~10 getters through `multipleRequest`, cutting encrypted round trips
from ~10 to 2 (with automatic fallback); and `clean_percent` etc. come with a
proper `%` sensor rather than an attribute only.

### Changelog

- **v3.0.1:** added live cleaning path and last-clean maps, per-room cleaning
  freshness and coverage, robot schedule editing with Do Not Disturb checks,
  remote drive and go-to-point controls, rendered furniture, Matter pairing
  state and commissioning, Assist voice sentences, device triggers and
  blueprints, and network discovery with IP tracking. The sidebar page and
  dashboard strategy are not included.
- **v3.0.2:** refined the map furniture appearance for readability.
- **v3.0.3:** the live cleaning path is drawn as the strip the robot's head
  actually covered — a grey swath as wide as the vacuum (~33 cm) — with the
  blue path line down its centre, instead of a bare line.
- **v3.0.4:** fixed the "401 Client Error: Unknown Status" failure loop — an
  expired session (the device answers a stale `stok` with plain HTTP 401) is
  now treated as session loss and re-handshakes instead of failing every poll.
  Furniture placed in the Tapo app is no longer drawn on the map image by
  default (it duplicated what dashboard cards already draw from
  `map_geometry`); a new "Vacuum options" entry option turns it back on.
- **v3.1.0:** the robot is drawn as the integration's own disc logo — blue
  rim, light face, lidar dome — sized to the strip its head sweeps, so the
  marker sits inside its own trail. The dock is a small plate with a status
  LED, scaled off the same strip but clearly smaller than the robot. Both
  replace the plain coloured dots.
- **v3.2.0:** four new read-only info calls, all in the diagnostics
  download — the vacuum's **clock/timezone** (`getDeviceTime`), its
  **Wi-Fi association state** (`getWirelessConnectedStatus`), the **TTS
  voice language** (the `speaker` component's `getSupportVoiceLanguage` +
  `getCurrentVoiceLanguage`) and the older-name **auto-dust-collection
  getter** (`getAutoDustCollection`). Every method name comes from
  python-kasa's documented vacuum component table, not from guessing. The
  README's protocol notes were corrected to match reality: LOCATE has
  shipped since v2.6.0 (the notes still called it undiscovered), and the
  firmware-image section now records that `.scv` images are encrypted with
  a device-flash-derived key and cannot be unpacked offline.
- **v4.0.0b0 (beta):** the **smart cleaning planner** from upstream
  `epg-pers/tapo-rv30-ha` v0.20.0, rebuilt for this fork — a **sidebar
  page of its own** (`Tapo Planner`) with everything configurable, plus a
  `Planner` switch and a `Planner Status` sensor. It starts a room clean on
  its own when rooms come due inside your cleaning windows; until you turn
  it on it does nothing, and in **preview** (the default) it only logs what
  it would have cleaned. Over upstream it adds: a run policy (one run per
  window, or repeat while rooms are due with a minimum gap); an away
  condition that can watch **any entity** (`input_boolean`, tracker, group)
  instead of only person entities; room occupancy that works **without
  motion sensors** — a person whose state is a room's area name counts, and
  any entity can be added per room with its own "busy" states; per-room
  "ignore occupancy"; and optional **notifications** (persistent
  notification, your own `input_text`, and/or any notify service) when a
  run starts or a due set keeps waiting. The pure decision logic is covered
  by tests; the finish-room-then-dock behaviour is **untested on real
  hardware** (hence beta).
- **v4.0.0b1 (beta):** the **Tapo Planner page grew into the full page
  upstream ships — retitled **Vacuum** in the sidebar — same tabs, this
  fork's design: the robot's own
  **schedules** (add / edit / delete, with Do Not Disturb warnings), the
  planner, a **history** tab with statistics and per-day / per-week
  charts, **rooms** with  and one-tap cleaning, **remote drive**
  (the app's dpad, including "vacuum while driving"), **maintenance**
  (consumables and the robot's action buttons) and **settings** (every
  switch, select, number and time entity of the robot). The page embeds
  VacuumCard-ADV when the Lovelace card is loaded as a resource, or a
  compact status card with quick controls otherwise; multi-robot
  households switch robots from the page header.
- **v4.0.0 (stable):** the sidebar page grew a **Vacuum home tab**
  (the default one): the robot's **map image with tappable rooms** —
  tap one or more rooms and press *Clean selected*, which runs a
  multi-room clean through the standard `clean_rooms` service — next to
  quick controls (clean / pause / stop / dock / locate), the current
  state, battery, Do Not Disturb and your saved presets as one-tap
  chips. The beta labels are dropped. Also fixes a **regression in
  `vacuum.clean_area`**: Home Assistant's area mapping keeps segment ids
  from earlier maps (remaps, re-pairings, pre-v2.6.0 plain ids), and the
  vacuum rejected the whole request with `Unknown segment id` as soon as
  one stale id was included. The handler now drops ids the vacuum no
  longer knows, prefers the **active map** when a request spans several,
  and raises a clear validation error (pointing you at re-mapping) only
  when nothing valid remains. Also fixes the **current map image staying
  empty** (`image.*_map_image` unknown, camera image blank) while the
  last-clean map rendered fine: on a fresh map the position/path overlay
  (vacuum marker, cleaning path) could throw — e.g. before the map
  carries `real_origin_coor` — which aborted the refresh after the map
  was rendered but before the image bytes were stored. The overlay is now
  best-effort: a failed draw logs a warning and the bare map is still
  published.

Want something added? See [Contributing](#contributing) below.

# Tapo RV20/RV30/RV50 Robot Vacuums — Home Assistant Integration

Warning: this is not an official integration!

Local-only Home Assistant integration for the **TP-Link Tapo RV30 Max Plus** robot vacuum.

Implements the **TPAP / SPAKE2+** authentication protocol reverse-engineered from
[python-kasa PR #1592](https://github.com/python-kasa/python-kasa/pull/1592).
No cloud dependency — communicates directly with the vacuum over your LAN.

## Verified supported Models
- **RV30 Max (EU)** according to @jan-tdy
- **RV50 Pro Omni (EU)** according to @asiar1993

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
The integration adapts polling to the vacuum's state and batches compatible
status requests. It also refreshes maps more frequently during active cleaning
so the live path stays current without forcing the same rate while docked.

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

#### 🛋️ Furniture
Furniture items placed within the official Tapo app *are* available locally
— `getMapData` includes a `furniture_list` field (id, type code, rotation
angle, polygon corners) that earlier versions of this integration missed.
Since v2.0.0 the map camera entity's `room_geometry` attribute exposes it
pre-converted into the same pixel space as the room polygons, as
`room_geometry.furniture` — each entry has `id`, `type`, `angle`, `points`
(the polygon), and `bbox`.
* **Current state:** the bundled map card renders furniture with the
  integration's known type table; unknown type codes remain available in
  `room_geometry.furniture` for diagnostics and custom cards.


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
- **Locate / "Find my robot"** (`vacuum.locate`, since v2.6.0) — makes the
  vacuum announce itself via the app's own `playSelectAudio` `seek_me`
  preset, the same call the Tapo app's find-my-robot button sends
- **Native room cleaning, across every saved map/floor** — the vacuum's
  more-info dialog lets you map its rooms to Home Assistant areas and clean
  them with the standard `vacuum.clean_area` action (Home Assistant
  2026.3+, see below); rooms from multiple saved maps show up grouped by
  floor in the mapping dialog
- **Room-by-room cleaning** via `tapo_rv30.clean_rooms` service, for
  automations/scripts (supports partial name match and an optional map filter)
- Live colour **map image** rendered from LZ4 pixel data — refreshed on an
  adaptive schedule: ~every 10 s while actively cleaning, ~every 30 s when
  idle/docked, with map data pulled only when it can have changed (the
  older fixed 60 s/5 min cadence pre-dates v2.6.0)
- **`room_geometry`** attribute on the map camera entity — each room's
  centroid, bounding box and rendered colour, in the same pixel space as
  the map image itself, for frontend cards (e.g.
  [VacuumCard-ADV](https://github.com/jan-tdy/VacuumCard-ADV)) to do
  click-to-room hit-testing directly against the `<img>` without
  reimplementing this integration's scale/flip conventions. Also carries
  `map_id`/`map_name` for the currently-displayed saved map, so a
  multi-map/multi-floor house can be told apart on the frontend (room ids
  are only unique within one saved map, not across all of them)
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
Remote drive, go-to-point, saved schedule changes and Matter fabric removal
are available as `tapo_rv30` actions. The separate
[VacuumCard-ADV](https://github.com/jan-tdy/VacuumCard-ADV) card can expose
these controls alongside the map.

### Manual dashboard (stock cards)

See [`jarvis_dashboard.yaml`](jarvis_dashboard.yaml) for a Lovelace dashboard view built entirely from
stock Home Assistant tile cards (`sections` view type) — no third-party card library needed for the
controls themselves.

Requires the HACS frontend card:
- [card-mod](https://github.com/thomasloven/lovelace-card-mod) (only for rotating the map camera image)

This fork does not use upstream's dashboard strategy — the dashboard is
built from stock HA cards. Its sidebar page, **Vacuum** (v4.0.0, see
the changelog), is upstream's full page in this fork's design: a robot
switcher and tabs for a **home tab** (the map with tappable rooms,
quick controls and presets), the robot's own schedules, the planner,
cleaning history, room freshness, remote drive, maintenance and
settings.

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
- `async_clean_segments()` uses the same `setSwitchClean` payload as the
  `tapo_rv30.clean_rooms` service (see [Protocol notes](#protocol-notes---room-cleaning)
  below). Before sending, it checks the request against the maps the vacuum
  still has: **segment ids from maps that no longer exist (or plain pre-v2.6.0
  ids) are dropped**, since Home Assistant's area mapping keeps them around
  forever — remaps and re-pairings just add the new map's ids next to the old
  ones, and a single stale id used to fail the whole call with
  `Unknown segment id`. If the request spans several maps, the rooms on the
  **active map** (the one the vacuum reports in the same live read) are used;
  if the selection touches several maps and none of them is active, the call
  is rejected with a clear "different maps" error rather than sent — the
  vacuum can only be on one floor at a time. Only when *nothing* valid
  remains do you get a validation error, pointing you at redoing the area
  mapping.

**Upgrading from an older version:** segment IDs changed from bare
`<room_id>` to `<map_id>:<room_id>`. Any area mapping you'd already set up
in the dialog uses the old bare-id format; those bare ids are now simply
ignored by `async_clean_segments()` (they can't be matched to a map
unambiguously, and keeping them would fail the call), so open
**Map vacuum segments to areas** and redo the mapping once you get a
chance — until then, use the areas you re-mapped or the
`tapo_rv30.clean_rooms` service, which always accepts an optional `map`
name and re-resolves everything live on every call. The `clean_rooms`
service itself is unaffected either way.

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

## Smart cleaning planner (v4.0.0)

A **Tapo Planner** sidebar page (plus a `Planner` switch and a `Planner Status`
sensor) that starts room cleans on its own when rooms come due, inside the
cleaning windows you set. Ported from upstream v0.20.0 and rebuilt so that
everything is configurable. Since v4.0.0b1 the page is titled **Vacuum**
in the sidebar and is the full upstream-style sidebar: around this
planner sit tabs for the robot's own schedules, cleaning history, room
freshness, remote drive, maintenance and settings.

- **Safe by default** — the planner is **off** until you enable it, and in
  **preview** (the default) it only logs what it would have cleaned.
- **Run policy** — one run per window, or repeat while rooms are due, with a
  minimum gap between runs.
- **Away condition** — nobody home before it starts: watch person entities
  (like upstream) or **any entity** — an `input_boolean`, a device tracker, a
  group — with your own "home" states.
- **Room occupancy without motion sensors** — besides motion / occupancy /
  presence sensors in the room's areas, a person whose Home Assistant state is
  the area's name counts as the room being in use, and any entity can be added
  per room with its own "busy" states. Per-room "ignore occupancy" is there
  too.
- **Notifications** (optional) — a persistent notification, writing into your
  own `input_text` helper, and/or calling any notify service: when a run
  starts, and/or (at most half-hourly) when a due set keeps waiting.
- Rooms map to Home Assistant areas through the vacuum entity's own **Map
  vacuum segments to areas** setting — one mapping, shared by the vacuum
  dialog, `clean_area` and the planner. **Match areas by name** on the panel
  fills it in for you.

Settings live on the panel (saved per robot); the last 40 decision-log steps
are shown there too. The pure decision logic is covered by
`tests/test_planlogic.py`. Beta caveat: the "finish the current room, then
dock when someone comes home" behaviour is **untested on real hardware**.

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

One thing isn't implemented because no working device call for it is
known: resolving a schedule's `custom_rule_id` back to the actual room
names it covers (see [Protocol notes —
schedules](#protocol-notes--schedules) above). A real device traffic
capture points at it being handled through TP-Link's cloud API rather
than the local protocol this integration speaks — full write-up, what was
tried, and why, is in [Discussion
#8](https://github.com/jan-tdy/TapoVac-ADV/discussions/8) rather than here.

(LOCATE — "find me" — used to be listed here as undiscovered too; that
was stale. The Tapo app's find-my-robot call is `playSelectAudio` with
`audio_type: seek_me`, shipped in v2.6.0 and listed under Features above.)

Still undiscovered locally:

- **Setting** the vacuum's voice/announcement language — the two *getters*
  (`getSupportVoiceLanguage` / `getCurrentVoiceLanguage`, the `speaker`
  component's calls as [python-kasa documents
  them](https://github.com/python-kasa/python-kasa/blob/master/devtools/helpers/smartrequests.py))
  answer fine and are included in the diagnostics download since v3.2.0,
  but no set-side method name is documented anywhere, so no language
  select is offered.
- Any **usage-statistics call beyond `getCleanRecords`** (`getStatistics`,
  `getUsageInfo`, `getDevLog`, and similar guesses all came back
  `UNKNOWN_METHOD_ERROR`).
- The **`dev_log` component's log-access call** — `getComponentList`
  advertises `dev_log: 1` on every firmware seen so far, but no public
  source names the method that reads those logs.

All three are likely handled through TP-Link's cloud API. Note that
guessing method names at a live device is not an option: an unknown
method can factory-reset the vacuum (the project's author lost a map set
and the clean history that way mid-run) — any new call has to come from a
real traffic capture or a published method dump; see Discussion #8 for
how to contribute one.

### Firmware images can't be unpacked offline

The downloadable `.scv` firmware images (`?>ldrobot.scv<?!` container,
including the publicly-listed debug builds) are fully encrypted: the
payload is AES with a key derived from the device's own flash, so no
published binary contains it. Confirmed independently by
[tpbreak-cli](https://github.com/haxorthematrix/tpbreak-cli), which breaks
TP-Link's other firmware formats (the camera/router RSA + AES scheme) but
lists the Tapo RV vacuum's format as out of reach for exactly this reason.
Practical consequence: method names, voice-prompt strings and log paths
have to come from app captures or published method dumps — unpacking a
stock or debug image at home is not possible.

### Furniture isn't rendered on the map (yet)

Furniture *is* available locally as of v2.0.0 — `getMapData`'s
`furniture_list` field (id, type code, rotation angle, polygon corners)
was previously missed. The map camera entity's `room_geometry` attribute
now exposes it pre-converted into the image's pixel space, as
`room_geometry.furniture`. What's still missing is a confirmed `type` code
→ furniture category table (values like 2, 102, 201, 202, 303, 401, 402,
601 have been observed but not identified), so nothing renders an actual
sofa/bed/table icon yet — see [🛋️ Furniture](#furniture) above for
details and how to help.

Until the `type` codes are decoded, the workaround is to overlay furniture
yourself with a [Picture Elements
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

### Tests

The SPAKE2+/TPAP handshake (`tpap.py`) and the LZ4/schedule/map decoding
(`coordinator.py`) have a `pytest` suite under `tests/` — including an
independent SPAKE2+ device-side simulation (`tests/fake_device.py`) that the
client authenticates against in-process, so a regression in the crypto
derivation or transcript no longer needs a real device to surface. Run it
locally with:

```bash
pip install -r requirements_test.txt
pytest
```

CI runs the same suite on every push/PR (`.github/workflows/tests.yml`).

## Credits

This is a fork of [epg-pers/tapo-rv30-ha](https://github.com/epg-pers/tapo-rv30-ha),
which did the hard work of reverse-engineering the TPAP protocol, room
cleaning, and map rendering in the first place. All credit for that
foundation goes there. The v3.0.1 additions for live and last-clean maps,
per-room freshness, map furniture, schedule management and Do Not Disturb,
go-to-point and remote driving, Matter, voice, discovery, device triggers,
and blueprints are adapted from that project. See
the [upstream repository](https://github.com/epg-pers/tapo-rv30-ha) for its
full documentation and development history. This project remains under
GPL-3.0; see [LICENSE](LICENSE).

The fork also retains native Home Assistant area mapping and its
TapoVac-ADV-specific additions.

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
