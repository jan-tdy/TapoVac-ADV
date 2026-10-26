# Native area mapping

Home Assistant 2026.3 added native "map vacuum segments to areas" support
to the standard `vacuum` entity. Open the vacuum's more-info dialog, click
the settings (⚙) icon, and use **Map vacuum segments to areas** to match
each room the robot reports to a Home Assistant area. Once mapped, the
**Clean area** action (`vacuum.clean_area`) lets you pick one or more
areas straight from the dialog — no YAML, scripts, or custom service
calls needed.

This requires Home Assistant **2026.3+**; see
[Installation → Requirements](installation.md#requirements) and
[Troubleshooting](troubleshooting.md) if the integration won't load on an
older core.

## How the contract is implemented

- **`async_get_segments()`** reports the rooms of *every* saved map,
  fetched live from the robot each time the mapping dialog is opened — not
  just whichever map is currently active. Because room IDs are only
  unique *within* a map, each segment's ID is namespaced
  `<map_id>:<room_id>`, and its `group` is set to the map's own name —
  so multiple floors/saved maps show up as separate groups in the mapping
  dialog instead of only ever exposing one.
- **`async_clean_segments()`** sends the same `setSwitchClean` payload as
  the [`clean_rooms`](services.md#clean_rooms) service — see
  [Protocol notes — room cleaning](protocol/room-cleaning.md). Before
  sending, the request is checked against the maps the robot still has:

  - Segment IDs from maps that no longer exist (or pre-namespacing bare
    IDs — see **Upgrading** below) are dropped, since Home Assistant's
    area mapping keeps old IDs around indefinitely; a single stale ID used
    to fail the entire call with `Unknown segment id`.
  - If the request spans several maps, the rooms on the *active* map (as
    read live in the same call) are used.
  - If the selection touches several maps and none of them is active, the
    call is rejected with a clear "different maps" error instead of being
    sent — the robot can only be on one floor at a time.
  - Only when *nothing* valid remains does the call fail with a validation
    error pointing at redoing the area mapping.

## Upgrading from an older version

Segment IDs changed from a bare `<room_id>` to the namespaced
`<map_id>:<room_id>` format. Any area mapping set up before this change
uses the old bare-ID format; `async_clean_segments()` now simply ignores
those bare IDs (they can't be matched to a specific map unambiguously, and
honoring them would risk cleaning the wrong room on the wrong floor).

**What to do:** open **Map vacuum segments to areas** again and redo the
mapping once you get a chance. Until then, either use areas you've already
re-mapped, or fall back to the [`clean_rooms`](services.md#clean_rooms)
service, which always accepts an explicit `map` name and re-resolves
everything live on every call — `clean_rooms` is unaffected by this change
either way.

## Diacritics in room names

See [Configuration → Diacritics and room names](configuration.md#diacritics-and-room-names).
Segment names shown in the mapping dialog are always decoded correctly;
the diacritic-insensitive matching described there only matters when
*typing* a room name into a service call field.
