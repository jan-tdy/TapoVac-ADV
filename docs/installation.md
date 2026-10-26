# Installation

## Requirements

- Home Assistant **2026.3+** - required for the native `vacuum.clean_area`
  room-mapping dialog described in [Native area mapping](area-mapping.md).
  Older cores will fail to load the integration; see
  [Troubleshooting](troubleshooting.md).
- [HACS](https://hacs.xyz) installed.
- A Tapo RV30 or RV20 (or compatible model, see [Home](index.md#supported-hardware))
  on firmware **1.2.x+** for the TPAP transport. Older AES-transport models
  (RV30C, RV30C Mop) are supported through a fallback transport.
- The Python packages `ecdsa` and `python-kasa` - declared in the
  integration's `manifest.json` and installed automatically by HACS.
  `requests`, `cryptography` and `Pillow` are also required (for the TPAP
  transport and map rendering) but aren't declared separately, since
  Home Assistant core already bundles them for its own use.

## Install via HACS

1. In HACS, search for **TapoVac ADV** (the integration is listed in the
   default HACS repository, no custom repository URL needed).
2. Install **TapoVac ADV**.
3. Restart Home Assistant.
4. Go to **Settings → Devices & Services → + Add Integration** and search
   for **TapoVac-ADV**.
5. Enter the vacuum's local IP address and the Tapo account email and
   password you use in the Tapo app.

The config flow authenticates against the robot directly (SPAKE2+ over the
TPAP transport, or AES on older hardware) and stores the result as a config
entry. See [Configuration](configuration.md) for what happens if the
connection check fails, and for the options you can change afterwards.

## Manual installation

If you are not using HACS, copy the `custom_components/tapo_rv30` folder
from this repository into your Home Assistant's own `custom_components`
directory, restart, and continue from step 4 above. HACS is strongly
recommended instead, since it tracks updates and installs the Python
dependencies for you.

## Dashboard

A sidebar page (**Vacuum**) is installed automatically and enabled by
default - see [Dashboard & sidebar panel](dashboard.md). A manual Lovelace
dashboard built entirely from stock Home Assistant tile cards is also
provided in [`jarvis_dashboard.yaml`](https://github.com/jan-tdy/TapoVac-ADV/blob/main/jarvis_dashboard.yaml)
at the repository root, for anyone who prefers not to use the bundled
sidebar page, or wants a starting point to build their own view. It needs
no third-party card library except [card-mod](https://github.com/thomasloven/lovelace-card-mod),
and only for rotating the map camera image.

## Upgrading

HACS handles upgrades the same way as any other integration: update
through HACS, then restart Home Assistant. Check the
[changelog](https://github.com/jan-tdy/TapoVac-ADV#changelog) for
breaking changes before upgrading across major versions - in particular,
segment IDs used by [area mapping](area-mapping.md) changed format in a
past release, which requires redoing the area mapping once.
