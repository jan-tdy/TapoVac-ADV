# This is jan-tdy's fork called TapoVac-ADV!

Want to see what is this? Jump [Here](#user-content-jump1)

Want to install it?       Jump [Here](#user-content-jump2)


**If you found this useful, please give this repo a star, it helps me a lot!** **Also check out my other repos!**

<details>
<summary>**SCREENSHOTS**, click to expand</summary>

<img width="1645" height="925" alt="image" src="https://github.com/user-attachments/assets/6d616391-e45e-4ed2-9236-d17566295213" />

<img width="479" height="505" alt="image" src="https://github.com/user-attachments/assets/2d1ac78a-6ab0-4ab3-95f9-0224ec98124d" />

<img width="1061" height="227" alt="image" src="https://github.com/user-attachments/assets/7f45c2f4-0eb5-475d-a021-0163c55c92c6" />

<img width="638" height="834" alt="image" src="https://github.com/user-attachments/assets/f683593e-2c53-486e-a539-5d911fc38ac5" />

<img width="1062" height="761" alt="image" src="https://github.com/user-attachments/assets/37c2f4c6-ef7c-4fdd-a7d0-57c2a5cabd6e" />

<img width="1064" height="428" alt="image" src="https://github.com/user-attachments/assets/68cbbd44-c40c-4239-a3f2-2cea0071bf41" />

<img width="1059" height="540" alt="image" src="https://github.com/user-attachments/assets/6ab9d6f3-2dd1-4e7a-9706-7226cc2a7e2b" />

<img width="1054" height="402" alt="image" src="https://github.com/user-attachments/assets/adfdd3c8-fbeb-43e9-8357-6c3eff79ba85" />

<img width="551" height="762" alt="image" src="https://github.com/user-attachments/assets/d05ba458-11a4-4a1b-82cb-efef155dee36" />

<img width="960" height="799" alt="image" src="https://github.com/user-attachments/assets/5ad21b68-3029-468c-a604-4afb5a302703" />

_________________________________________________________________________________________________
_________________________________________________________________________________________________

</details>


You can take a look at my issue and pr queue if you are wondering why is something stale for days [here](https://github.com/issues/assigned?q=is%3Aissue+or+is%3Apr+state%3Aopen+archived%3Afalse+user%3Ajan-tdy+sort%3Acreated-asc)

## UPDATING AND RELEASES:
Want to test and catch bugs? Install X.X.XbX pre-release

Want something working? Install the latest non-beta

Want something stable and really working? Look for [SuperStable]; those are tested MULTIPLE times, and just work and yes, can be even 2 major releases out-of-date. And SuperStable releases can still get patches sometimes; even v2.5.1 SuperStable could get a patch while v7.2.1b0 is latest...

## Upstream vs. this fork

Both integrations speak the same local protocol (TPAP over SPAKE2+) and expose
the same **11 entity platforms** and the same **25 services** — so anything you
can drive from an automation works identically. What differs is what's built on
top of that protocol.

| Area | Upstream `epg-pers/tapo-rv30-ha` | This fork `TapoVac-ADV` |
| --- | --- | --- |
| Version (as of this comparison) | `0.36.1` | `6.2.0b4` |
| Smart cleaning planner | Yes | Same + more configurability |
| Map image | Rooms + furniture + path + basic robot & dock icons| same + path swept strip ~33 cm wide + robot & dock nice icons |
| Clean map history | Kept on disk, with retention controls (select + number) | same, plus a **View** action that opens the map right in the sidebar page instead of only downloading it |
| Map rotation | Per saved map, stored on the robot (`rotate_angle`) | One **Map Rotation** select entity per robot — an integration setting, not a per-browser preference (kept as-is; see the v6.2.0b4 changelog entry) |
| Map management | Rename, copy, delete, lock any saved map; restore a backup as a new map | Same four services, plus restore-as-new, from the Settings tab's Maps card |
| Integration log | Home Assistant's own log only | A **Log** sidebar tab shows this integration's recent log records (ring buffer), with refresh/clear |
| Planner preview | Logs what it would do | **Dry-run card** and **Upcoming** timeline projecting the next several cleaning windows |
| Tests | 8 test files | **23 test files / 250 tests**, incl. end-to-end SPAKE2+ interop against an in-repo `FakeDevice` |
| Docs | mkdocs site (GitHub Pages) | README only (site on roadmap) |
| CI | `validate` + `docs` + `release` | `hassfest` + `tests` + `validate` |
| Branding | — | Integration icon + README screenshots |
| Why to use | You like new features and AI card design | You can wait a few days for a feature if it works better and prefer the H.A. card design |
| Special features | Build-in card | Long term support releases, H.A. design |

<details>
<summary>Click to expand MORE INFO</summary>

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

</details>

<details>
<summary>Changelog, click to expand</summary>
### Changelog

- **v6.2.0b4:** ported upstream's map-management work (v0.33–v0.36): a Maps
  card on the Settings tab (and matching `rename_map`, `copy_map`,
  `delete_map` and `set_map_lock` services) to rename, copy, lock/unlock and
  delete any saved map, and `restore_map_backup` can now restore a backup as
  a new map (`new_name`) instead of overwriting the original — the Backups
  tab's Restore button asks which. Copying and restoring-as-new give the
  backup a fresh id (`mapbackup.reid_bkmap`) so the original is never
  touched. Not ported: upstream's per-map, robot-stored rotation
  (`rotate_angle`) — this fork keeps its existing per-robot **Map Rotation**
  select instead of replacing it, since the two are different models (a
  display setting here vs. a value the Tapo app itself reads back) and
  merging them safely needs more design than this release's scope; so are
  upstream's progress bars for map jobs, the map-lock padlock/eye-preview
  UI and editing any saved map (not just the live one) on the Edit map tab
  — the services and Maps-card controls work today, the richer per-map UI
  is a follow-up. Also new: a **Log** sidebar tab showing this
  integration's own recent log records (a bounded in-memory ring buffer
  attached to its logger), with refresh and clear.
- **v6.2.0b3:** keep the map visible when declining the temporary-zone
  confirmation; rebuild the map pane after the dialog closes.
- **v6.2.0b2:** wait until zone cleaning, pause or return ends before restoring
  map zones, and retry rejected writes. A stopped robot can be restored from
  idle as well as docked state.
- **v6.2.0b1:** retry restoring the map's saved zones after a zone clean
  finishes, preventing the robot from leaving the temporary clean rectangle
  visible on the map.
- **v6.2.0b0:** Maintenance now places each available reset button beside its
  matching consumable's remaining-life bar, instead of collecting reset buttons
  in a separate actions list.
- **v6.1.0b1:** the Vacuum tab's **Clean a zone** control now offers a
  temporary drawn zone or a saved zone preset. Saved presets for the active
  map are outlined on the map and can be selected by clicking the outline or
  its name, then started with **Clean selected zone**.
- **v6.1.0 (stable):** the Vacuum tab's **Clean a zone** control offers a
  temporary drawn zone or a saved zone preset. Running either asks for
  confirmation; clicking outside closes the dropdown, and clicking a saved
  outline on the map asks to run it directly. Temporary zones are cleared from
  the rendered map after the robot accepts the clean. Dining-chair symbols no
  longer have an internal dividing line.
- **v6.1.0b0:** the new Zones sidebar tab has a map for drawing and saving
  named zone presets, plus controls to run, rename and delete them. Presets
  are kept per vacuum in Home Assistant storage. They keep their own
  coordinates and map ID, so they do not occupy or overwrite the robot's
  shared saved-area slots; a preset can only run while its original map is
  active. They are also available through the `create_zone_preset`,
  `get_zone_presets`, `run_zone_preset`, `update_zone_preset` and
  `delete_zone_preset` services.
- **v6.0.1:** `tapo_rv30.clean_zone` sends its zones to the robot as "area"
  zones, the same type the map keeps as saved/drawn zones - once the robot
  had started the job, nothing ever cleared them back out, so an ad-hoc
  zone clean left a permanent outline on the map. They're now cleared right
  after the job starts, restoring whatever saved zones were already on the
  map first (Codex review finding: an earlier version of this fix cleared
  every "area" zone unconditionally, which would have wiped out a zone the
  user had actually saved, in this integration or the Tapo app, along with
  the ad-hoc one).
- **v6.0.0 (stable):** the beta labels are dropped. Since v6.0.0b5:
  - **Vacuum marker redesign.** Simplified to a thin blue rim around a light
    face with a small centred lidar dome (matching the integration's own
    logo) - an earlier pass dropped the dome entirely after an off-centre
    version of it implied a heading the protocol doesn't actually report;
    centred, it implies no direction, just the logo's look.
  - **Vacuum marker no longer sits on top of the dock while docked.** Its
    diameter (sized to the sweep width) is wider than the dock plate on
    every side, so centred on the dock it used to hide the plate completely.
    It's now nudged to one side (towards the open room, away from the wall
    the dock backs onto) so both show, and clamped so a dock near the image
    edge can't push the marker off it.
  - **Go to point and Clean a zone, from the sidebar map.** Both already
    existed as services (`tapo_rv30.go_to`, `tapo_rv30.clean_zone`) with no
    UI beyond Developer Tools; the Map card now has toggle buttons for both
    - tap the map to drive there, or drag a rectangle and release to clean
    it - working correctly under Map Rotation too.
  - Map edits (no-go zones, virtual walls, furniture, **room renaming**)
    remain **admin-only** - confirmed as part of this release, both in the
    editor UI (controls are disabled for a non-admin) and on the backend
    (the save websocket command requires it independently).
  - Fixed a delayed final map render right after a clean finishes and the
    robot docks, and a false-positive "fix the area mapping" repair issue
    on a plain room rename (the id is unchanged, so the mapping was never
    broken).
  - Furniture no longer fully hides the robot or its cleaning trail
    underneath it - redrawn once more on top at reduced opacity, the way
    the Tapo app shows it.
- **v6.0.0b5:**
  - **Vacuum marker shown off the dock while docked.** `vac_coor`/`real_vac_coor`
    can still be the robot's last pre-dock position rather than the dock
    itself; while docked, the dock's own coordinate is now tried first. Fixed
    properly in two passes: the first pass read the docked status back off
    `self.status_code`, which isn't updated to the current poll until after
    it's read, so it was still one poll stale on the exact poll (just after
    docking) this mattered most on - the status is now passed through fresh
    instead.
  - **Delayed final map render right after a clean finishes and docks**
    (introduced by v6.0.0b4's docked re-render cadence, found by Codex review
    on this release's own PR): the just-finished run's map could sit stale
    for up to the full docked interval. An immediate render is now forced on
    the one poll the robot docks.
  - **False-positive "fix the area mapping" repair issue on a plain room
    rename.** It now only fires when a room's id actually disappears
    (split/merged/removed/map redone) - a rename keeps the same id, so the
    mapping was never broken and had nothing to fix.
  - **Furniture no longer fully hides the robot/trail cleaning under it.**
    It's redrawn once more on top of the live position overlay at reduced
    opacity, the same way the Tapo app shows it.
- **v6.0.0b4:**
  - **Fixed issue #70: robots that send their device attestation certificates
    as base64-of-PEM text (seen on RV30 Max Plus Gen2, firmware 1.3.5) failed
    setup with `DAC verification failed: ... unexpected tag 13` and were sent
    into a pointless reauth flow. Certificates are now read as base64 PEM,
    plain PEM or base64 DER, and the attestation chain is accepted under
    either TP-Link device root the Tapo app pins (ported from upstream
    v0.32.2).**
  - **Fixed the vacuum marker sometimes not showing on the map at all.**
    `coordinator.py` called `maprender._draw_vacuum()` without ever importing
    it, so every single position overlay silently raised `NameError` and fell
    back to drawing the bare map; only the first occurrence got logged
    (`"Map position overlay failed, drawing the bare map"`), which made a
    constant failure look intermittent.
  - Fixed a startup crash in the `button` platform: it called a `has_part()`
    method that didn't exist on the coordinator, so "Reset ..." buttons
    (main brush, side brush, filter, etc.) never got created.
  - **Rotated furniture that silently failed to save is now reported.** The
    map editor's save previously only checked that a furniture item's *id*
    survived a write; the robot can keep an item under its old id while
    quietly ignoring an in-place move or rotation. The check now also
    compares the saved shape to what was sent (with a small tolerance for the
    robot's own grid snapping) and reports which item's new position/rotation
    wasn't kept.
  - **Room renaming in the map editor.** The backend already round-tripped
    room names; the editor's Rooms list is no longer view-only — each room
    gets an editable name field, and a rename is included (and
    read-after-write verified, same as furniture) the next time you Save.
  - The dock marker is green now, instead of grey.
  - While docked, the full map re-render is stretched out to every 30
    minutes instead of every 5 - nothing on the map can change while the
    robot isn't moving, so there's no reason to pay that cost on the usual
    cadence. A map edit (which can only be saved while docked) still forces
    an immediate re-render afterwards.
  - The per-poll position overlay no longer asks Pillow to search for the
    smallest PNG encoding (`optimize=True`) - that search is several times
    slower than a plain encode and was running on every single poll, not
    just the occasional full re-render it was originally meant for. Resulting
    files are a little larger; nothing else changes.
- **v6.0.0b3:**
  - **Furniture rendering no longer supersamples the whole map image.**
    Since v6.0.0b1 flipped `draw_furniture` on by default, every full map
    render for anyone with furniture placed was allocating and
    downsampling a 2x copy of the *entire* image just to draw a handful
    of small glyphs — the same ~300 ms-per-poll cost the vacuum/dock
    markers moved away from a while ago. Furniture now gets its own
    small supersampled tile per item (like the markers), so the cost is
    bounded by how much furniture is on the map, not by the map's size.
  - The dock marker's colours were too close to the plain floor colour
    to read clearly; darkened both the body and its outline.
- **v6.0.0b2:**
  - **Furniture rotation.** Selected furniture in the map editor now has a
    round handle beyond its top edge — drag it to rotate the piece freely
    around its own centre (not just 90° steps), so a washbasin or sofa
    against an angled wall can actually be lined up. Resizing is still
    only offered for an unrotated piece, as before.
  - The front-load washer glyph (402) carried the same kind of elevation
    detail as the icons fixed in v6.0.0b1 — a circular door seen from the
    front, which nothing looking straight down at the machine would ever
    see. Redrawn as a plain top-down rectangle with a control-panel strip.
  - The recorder purge for the retired Matter Setup Code sensor retried
    on a failed attempt instead of giving up forever on it (CodeRabbit
    finding on the v6.0.0b1 PR, fixed right after that PR merged but one
    push after the merge itself landed; re-applied here).
- **v6.0.0b1:**
  - Removing the leftover Matter Setup Code sensor on upgrade now also
    purges its own recorder history, not just the registry entry (a
    Codex review finding on the v6.0.0b0 PR) — otherwise the code it was
    meant to stop exposing was still sitting in old recorded states.
  - History tab: a kept run that has since dropped off the robot's own
    (short) record list, or that the robot cannot currently answer for,
    now gets its own row too, so it can still be viewed or forgotten
    instead of being invisible (another Codex finding).
  - The Map Rotation setting now applies live: changing it from another
    browser or an automation updates every open sidebar page without
    needing to switch robots or reload (another Codex finding), and it
    now also rotates the History tab's map view dialog and the Edit map
    canvas (including click/drag placement), not just the Vacuum tab.
  - Furniture glyphs are redrawn as plan-view (top-down) symbols only —
    the TV cabinet, pet house and vertical air conditioner used to carry
    a little side-on/elevation detail (a "floating" TV screen, a gabled
    roof, front louvres) that looked out of place from directly above.
  - Three more furniture types: a dining table, a standalone dining
    chair, and a washbasin — see "Furniture on the map" below for the
    caveat on these three (not confirmed app/firmware codes).
- **v6.0.0b0:** ported upstream `0.32.0`/`0.32.1`, plus more fixes and
  controls of this fork's own:
  - **Security fix (ported from upstream 0.32.0):** the Matter Setup Code
    sensor and its `setup_code`/`setup_payload` attributes are gone — every
    Home Assistant user could read them, and the recorder kept them. The
    code now comes only from the new admin-only `get_matter_setup_code`
    action. If that sensor was enabled, `recorder.purge_entities` clears
    its old history.
  - **Clean map history + retention controls (ported from upstream 0.32.0):**
    the History tab's runs now keep their map on Home Assistant's disk (no
    extra robot calls — it's read from the record the integration already
    reads), with **View** (opens it right in the sidebar page) and
    **Forget**, alongside the existing map download. A **Clean Map
    History** select (Off, 1 week, 1 month, 3 months (default), 1 year,
    Forever) and a **Clean Map History Limit** number (200 by default, 10
    to 1000) control how long and how many are kept — from the History
    tab, the Settings tab, or an automation. Diagnostics report how many
    are kept and the space used.
  - **Map editor furniture fix:** furniture placed in the editor was being
    written to the robot correctly (it kept showing up when the editor
    was reopened) but never showed up on the map image itself, because
    "draw furniture on the map image" defaulted to off, on the assumption
    that a dashboard card would draw it from `map_geometry` — this fork
    ships no such card, so for most setups furniture was simply invisible.
    It now defaults to **on**. The map editor also reads the map straight
    back after saving furniture and reports a clear error if the robot
    ever accepts the write but doesn't keep it, instead of silently
    claiming success.
  - **Map rotation is now a Map Rotation select entity** (an integration
    option), not a per-browser preference: rotate it once and every
    browser, device and automation sees the same rotation for that robot.
  - **Planner preview, made useful:** the Planner tab now has a "Dry run"
    card (what would run right now and why, in preview mode) and an
    "Upcoming" timeline — a forward projection of the next several
    cleaning windows and which rooms would be due in each, instead of
    only a one-line status buried in the log.
- **v5.1.0:** fixed Assist stop commands raising an error after stopping the
  robot, and removed a blocking file-existence check from the map-restore
  request handler. Sidebar map rotation now persists per robot across reloads.
- **v5.0.2:** bounded the anti-aliased cleaning-path overlays to the path area
  and capped temporary overlay memory on large maps.
- **v5.0.1:** fixed the live vacuum marker disappearing when firmware omits
  grid coordinates, improved marker contrast, and smoothed the grey cleaning
  trace at turns.
- **v5.0.0 (stable):** complete v5 release, based on upstream `0.31.0` and
  extended with TapoVac-ADV controls and fixes:
  - Restored the full **Vacuum** sidebar with Vacuum, Schedules, Planner,
    History, Rooms, Drive, Maintenance, Edit map, Backups and Settings tabs.
  - Fixed sidebar map sizing and history chart scaling; added map rotation,
    robot and dock markers at the map rendering layer, and downloads for
    individual clean-history maps.
  - Added the map editor for no-go zones, virtual walls and furniture. Fixed
    editor refresh/save issues, prevented duplicate furniture writes, added
    virtual-wall endpoint resizing, and limited saves to layers that changed.
    Newly drawn zones receive unique IDs; failed saves are logged with useful
    details for diagnosis.
  - Extended Planner notification destinations to Home Assistant `text`
    entities alongside persistent notifications, `input_text` helpers and
    notify services.
  - Added automatic map setup snapshots, protected historical map reads and
    serialized map writes; fixed restore refusal handling, stale settings
    failures, paused vacuum resume and voice command refresh after robot changes.
  - Ported upstream protocol and reliability hardening, added the Home
    Assistant network dependency, and fixed compatibility issues found by
    hassfest and CI.
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
  notification, your own `input_text` or `text` entity, and/or any notify service) when a
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

</details>

Want something added? See [Contributing](#contributing) below.

<h1 id=jump1>Tapo RV20/RV30/RV50 Robot Vacuums — Home Assistant Integration</h1>

Warning: this is not an official integration!

Local-only Home Assistant integration for the **TP-Link Tapo RV30 Max Plus** robot vacuum.

Implements the **TPAP / SPAKE2+** authentication protocol reverse-engineered from
[python-kasa PR #1592](https://github.com/python-kasa/python-kasa/pull/1592).
No cloud dependency — communicates directly with the vacuum over your LAN.

## Verified supported Models
- **RV30 Max (EU)** according to @jan-tdy
- **RV50 Pro Omni (EU)** according to @asiar1993

**Does your vacuum work with this integration but isn't in the list? Open an issue, please!**

Should work on any Tapo Robot Vacuum using TPAP.

<details>
<summary>Requirements</summary>
  
- Home Assistant **2026.3+** (required for the native `vacuum.clean_area`
  room-mapping dialog — see [Requirements
  bump](#requirements-bump-to-home-assistant-20263) below)
- [HACS](https://hacs.xyz) installed
- Tapo RV30 or RV20 (RV30 Max works...) on firmware **1.2.x+** (TPAP protocol)
- Python packages (installed automatically by HACS): `requests`, `ecdsa`, `Pillow`

</details>

<h1 id=jump2>Installation via HACS</h1>

[![Add to Home Assistant](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=jan-tdy&repository=TapoVac-ADV&category=integration)

Click the button above, or manually:

1. In HACS, search **TapoVac ADV** (YES, WE ARE DEFAULT NOW!)
3. Install **TapoVac ADV**
4. Restart Home Assistant
5. **Settings → Devices & Services → + Add Integration → TapoVac-ADV**
6. Enter your vacuum's IP address, Tapo account email, and password

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
  own `input_text` helper or `text` entity, and/or calling any notify service: when a run
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

### Furniture on the map

Furniture is drawn on the map image by default (toggle it off in the
integration's Options if you draw it yourself from `map_geometry.furniture`
on a custom card — both the camera image and `map_geometry` always carry
it). All glyphs are drawn top-down (floor-plan view), not as little side-on
elevations. 19 of the 22 furniture types are confirmed TP-Link app/firmware
codes (see `FURNITURE_TYPES` in `const.py`); the other 3 — a dining table,
a standalone dining chair and a washbasin — are this fork's own, using the
next free numbers in their category, since no traffic capture has shown a
code for them: saving one is still verified against a read-back of the
robot's map, so a robot that does not keep it says so plainly instead of
silently dropping it. Items placed or resized in the sidebar page's map
editor get their type's real-world size and are drawn under the zones so a
no-go zone inside a sofa is still visible and selectable.

If furniture you placed and saved in the map editor shows up again when you
reopen the editor (so the robot did keep it) but still doesn't appear on the
map image or in `map_geometry`, that is unexpected — the editor now reads
the map straight back after saving and reports a clear error if the robot
ever accepts a furniture write without actually keeping it. Please open an
issue with your robot model/firmware and, if you can, debug logs for
`custom_components.tapo_rv30` around the save.

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

## Star History

<a href="https://www.star-history.com/?repos=jan-tdy%2Ftapovac-adv&type=date&releases=&legend=bottom-right">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/chart?repos=jan-tdy/tapovac-adv&type=date&theme=dark&legend=bottom-right" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/chart?repos=jan-tdy/tapovac-adv&type=date&legend=bottom-right" />
   <img alt="Star History Chart" src="https://api.star-history.com/chart?repos=jan-tdy/tapovac-adv&type=date&legend=bottom-right" />
 </picture>
</a>

The Plus/Omni dock actions (empty/wash/dry/hair-removal — see [Dock
support (Plus / Omni)](#dock-support-plus--omni) above) port the TPAP
method names discovered by
[cavefire/tapo-vacuum-ha](https://github.com/cavefire/tapo-vacuum-ha)'s
independent RV50 work.
