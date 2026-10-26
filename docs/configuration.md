# Configuration

## Setting up the config entry

The config flow (**Settings → Devices & Services → + Add Integration →
TapoVac-ADV**) asks for:

| Field | Description |
| --- | --- |
| Host | The robot's local IP address. A static DHCP lease or reservation is recommended — the integration also ships a DHCP discovery rule (`E0D362*` MAC prefix) that updates a known entry's IP automatically if it changes. |
| Username | The email address of the Tapo account used in the Tapo app. |
| Password | The Tapo account password. |

On submit, the flow connects to the robot and performs the handshake for
whichever transport it offers (TPAP/SPAKE2+ on current firmware, AES on
older RV30C-class hardware). If the robot's offered security is weaker than
what a previously paired entry recorded, the flow refuses the downgrade
rather than silently accepting a less secure handshake.

## Options

Open the entry's **Configure** button to change:

| Option | Default | Description |
| --- | --- | --- |
| Poll interval | 30 s | How often fast-changing data (status, battery, live attributes) is refreshed. Allowed range is 10–300 s. The map image and settings are refreshed on a slower, separate cadence (5 minutes while active, 30 minutes while docked — nothing on the map can change while the robot hasn't moved). |
| Draw furniture | on | Whether furniture glyphs are rendered on the map camera image. Turn this off if you render `map_geometry.furniture` yourself on a custom card — the geometry data is always available either way. |
| Show sidebar panel | on | Whether the **Vacuum** sidebar page (see [Dashboard & sidebar panel](dashboard.md)) is registered at all. |

These three live in the options flow dialog. A few more settings are
exposed as regular, reconfigurable entities instead (so they show up in
automations, history, and the entity list) rather than hidden in a
dialog:

| Entity | Type | Purpose |
| --- | --- | --- |
| Poll Interval | `number` | Same poll interval as above, adjustable without reopening the options dialog. |
| History Limit | `number` | Maximum number of saved clean-history maps to keep per robot. |
| History Retention | `select` | How long a clean-history map is kept before automatic cleanup, independent of the count limit above. |
| Map Rotation | `select` | Rotation (0°/90°/180°/270°) applied to the map everywhere it's shown — an integration-level setting rather than a per-browser preference, so every dashboard and user sees the same orientation. |
| Auto Empty, Do Not Disturb, Auto Firmware Update | `switch` | Mirrors the matching Tapo app toggle; only created when the robot reports the matching settings group. |
| Child Lock, Carpet Boost, AI Obstacle Avoidance, Automatic Re-mopping, Clean Along Floor, Extended Mopping, Pet Area Deep Clean, Sweep Walk, Auto-change Map | `switch` | One switch per boolean setting the robot actually answers for — a robot that doesn't support a feature simply doesn't get that switch. |
| Volume | `number` | Robot speaker volume. |

See [Entities](entities.md) for the complete entity reference, including
sensors, buttons and read-only diagnostics.

## Diacritics and room names

The Tapo app allows renaming rooms with accented characters (e.g. Slovak
*á, č, ľ, ň, š, ť*). The robot reports room names base64-encoded; the
integration decodes them as UTF-8 so they display correctly everywhere a
room name is shown. When *typing* a room name into a service call field
(as opposed to picking it from a list), matching is diacritic-insensitive:
accents are stripped and the comparison is lowercased on both sides, so a
room named "Kúpeľňa" matches `kupelna`, a partial match like `pel`, or the
exact accented name.

## Reconfiguring credentials

If the Tapo account password changes, use the config entry's
**Reconfigure** flow instead of removing and re-adding the integration —
this keeps the same entities, history and automations pointed at the
existing config entry.
