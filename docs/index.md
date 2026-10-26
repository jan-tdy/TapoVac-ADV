# TapoVac-ADV

TapoVac-ADV is a Home Assistant custom integration for TP-Link Tapo robot
vacuums (RV30 Max, RV30 Max Plus, RV20 Max Plus, RV50 Pro Omni and other
models that speak the same local protocol). It talks to the robot directly
over your LAN — no cloud round-trip for day-to-day operation — and exposes
the same local protocol upstream reverse-engineered, plus a full planner,
map tooling and dashboard built on top of it.

This is a fork of [epg-pers/tapo-rv30-ha](https://github.com/epg-pers/tapo-rv30-ha).
Both projects speak the same protocol and expose the same 11 entity
platforms and 25 services, so anything you can drive from an automation
works identically on either. What this fork adds is covered page by page
in this site; a side-by-side comparison with upstream lives in the
[project README](https://github.com/jan-tdy/TapoVac-ADV#upstream-vs-this-fork).

## What's in this documentation

- **[Installation](installation.md)** — HACS setup and requirements.
- **[Configuration](configuration.md)** — the config flow, options, and the
  config-category entities that control polling, map rendering and history.
- **[Entities](entities.md)** — every entity platform the integration
  creates, and what each entity reports or controls.
- **[Services](services.md)** — full reference for all 25 `tapo_rv30.*`
  services (room cleaning, zones, presets, schedules, maps, diagnostics).
- **[Dashboard & sidebar panel](dashboard.md)** — the stock-card Lovelace
  dashboard and the custom **Vacuum** sidebar page.
- **[Smart cleaning planner](planner.md)** — rule-based automatic room
  cleaning, independent of the robot's own scheduler.
- **[Native area mapping](area-mapping.md)** — how `vacuum.clean_area` and
  Home Assistant's "map vacuum segments to areas" dialog are implemented.
- **[Standalone CLI](cli.md)** — driving the robot from a terminal, without
  Home Assistant.
- **[Protocol notes](protocol/room-cleaning.md)** — the reverse-engineered
  wire format for room cleaning and schedules, for anyone extending the
  integration or cross-checking against their own traffic capture.
- **[Troubleshooting](troubleshooting.md)** — reading the integration's own
  log, decoding the robot's error codes, and the failure modes that come up
  most often.
- **[Contributing](contributing.md)** — running the test suite and where to
  bring new findings.

## Supported hardware

Any Tapo robot vacuum speaking the TPAP (SPAKE2+) protocol on firmware
1.2.x+ should work, and the AES transport used by older RV30C-era models is
supported as a fallback. Confirmed working models are tracked in the
[README](https://github.com/jan-tdy/TapoVac-ADV#verified-supported-models) —
please open an issue if yours works but isn't listed.

## Requirements

- Home Assistant 2026.3 or newer (needed for the native
  `vacuum.clean_area` room-mapping dialog, see
  [Native area mapping](area-mapping.md))
- [HACS](https://hacs.xyz)
- A Tapo account (the one used in the Tapo app) and the robot's local IP
  address

## License

GPL-3.0, same as upstream. See
[LICENSE](https://github.com/jan-tdy/TapoVac-ADV/blob/main/LICENSE).
