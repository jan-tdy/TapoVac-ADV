# Entities

TapoVac-ADV creates entities across 11 Home Assistant platforms. Which
entities actually appear depends on what the connected robot reports - a
robot without a mop, for instance, gets no water-level or mop-related
entities. Diagnostic and configuration entities are categorized
accordingly (`EntityCategory.DIAGNOSTIC` / `CONFIG`) so they sort out of
the way in the default UI.

## Vacuum

The core `vacuum` entity: start, pause, stop, return to dock, set fan
speed, and (on Home Assistant 2026.3+) the native `clean_area` /
`get_segments` area-cleaning contract - see
[Native area mapping](area-mapping.md). Battery level is reported through
its own sensor rather than the vacuum entity's legacy battery property,
which Home Assistant core removed.

## Sensor

| Entity | Notes |
| --- | --- |
| Status | Human-readable robot state (Cleaning, Mapping, Returning, Charging, Paused, …), decoded from the robot's `RobotStatusType` code. |
| Battery | Battery percentage. |
| Error | Current error, decoded from the robot's `RobotCleanErrorType` code - see [Troubleshooting](troubleshooting.md#error-codes) for the full table. |
| Clean Progress | Percentage complete for the running clean. |
| Current Room | The room the robot is currently cleaning, when known. |
| Last Clean | Timestamp of the most recent completed clean record. |
| Last Clean Area | Area covered by the most recent clean. |
| Total Cleans / Total Area Cleaned / Total Cleaning Time | Lifetime counters from the robot's clean records. |
| Schedules | A count; the full schedule list is in its `schedules` attribute - see [Protocol notes - schedules](protocol/schedules.md#viewing-schedules-in-a-dashboard) for a dashboard card that renders it as a table. |
| Wi-Fi Signal | Robot's own Wi-Fi signal report. |
| Matter | Matter commissioning / fabric status. |
| Planner Status | What the smart planner is doing right now (see [Smart cleaning planner](planner.md)). |
| *Consumable* Remaining / Used | One pair of sensors per consumable the robot tracks (main brush, side brush, filter, sensor, charge contacts), reporting hours remaining against the robot's own rated life and hours used so far. |

## Binary sensor

| Entity | Notes |
| --- | --- |
| Charging | On while docked and charging. |
| Mop Attached | On when the robot reports a mop plate installed (mop-capable models). |
| Do Not Disturb Active | On during the configured DND window. |
| Problem | On whenever `Error` is non-zero; a `problem` device-class sensor for alerting. |
| Consumable Warning | On when any tracked consumable has crossed its replace-soon threshold. |

## Switch

| Entity | Notes |
| --- | --- |
| Auto Empty, Do Not Disturb, Auto Firmware Update | Only created when the robot reports the matching settings group. |
| Child Lock, Carpet Boost, AI Obstacle Avoidance, Automatic Re-mopping, Clean Along Floor, Extended Mopping, Pet Area Deep Clean, Sweep Walk, Auto-change Map | One switch per boolean setting the robot actually answers for. |
| Planner | Turns the [smart cleaning planner](planner.md) on or off; its detailed settings live on the Vacuum sidebar page, not as separate entities. |

## Number

| Entity | Notes |
| --- | --- |
| Volume | Robot speaker volume. |
| Poll Interval | See [Configuration](configuration.md#options). |
| History Limit | Maximum saved clean-history maps kept. |

## Select

| Entity | Notes |
| --- | --- |
| Clean Passes | 1–3 passes per clean, mirrored by the `passes` field on most cleaning services. |
| Water Level | Off / Low / Medium / High, on mop-capable models. |
| Auto Empty Mode | Dock auto-empty behavior, where the robot exposes one. |
| History Retention | See [Configuration](configuration.md#options). |
| Map Rotation | See [Configuration](configuration.md#options). |

## Button

| Entity | Notes |
| --- | --- |
| Empty Bin | Only created on docks with a dust bucket. |
| Reset *Consumable* | One per trackable consumable (main brush, side brush, filter, sensor, charge contacts, main brush lid, mop cloth) - only for the ones the connected hardware actually reports. |
| *Dock action* (Wash Mop, Dry Mop, Remove Hair) | Only created for the dock features the robot answers a probe for; a single failed probe no longer hides every other confirmed dock button. |
| Open Matter Pairing Window | Starts Matter commissioning; diagnostic category. |
| *Preset name* | One button per saved Tapo-app cleaning preset - created and removed automatically as presets are added, renamed or deleted in the app, or via [`tapo_rv30.create_preset`](services.md#create_preset) and friends. |

## Time

| Entity | Notes |
| --- | --- |
| Do Not Disturb Start/End | The configured DND window, read/write. |

## Update

| Entity | Notes |
| --- | --- |
| Firmware | Reports available firmware updates. Installing from Home Assistant is intentionally **not** supported (`UpdateEntityFeature(0)`) - firmware is still installed from the Tapo app. |

## Camera

| Entity | Notes |
| --- | --- |
| Map | Live rendering of the current map: rooms, furniture (optional, see [Configuration](configuration.md#options)), no-go zones, the swept-path strip, and robot/dock icons. Refreshed on the slower map cadence described in [Configuration](configuration.md#options). |

## Image

| Entity | Notes |
| --- | --- |
| Last Clean Map | A static snapshot of the map as it looked at the end of the most recent completed clean, independent of the live Map camera. |

## Diagnostics

Beyond entities, the integration also supports Home Assistant's built-in
**Download diagnostics** button on the config entry, which includes
decoded settings, supported features and (since v3.2.0) the voice-language
getters mentioned in
[Protocol notes - undiscovered commands](protocol/undiscovered-commands.md).
Credentials are never included.
