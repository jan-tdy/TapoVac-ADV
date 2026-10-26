# Protocol notes — undiscovered commands

A short list of things that are not implemented because no working device
call for them is known yet, plus why calling unknown methods at random is
not a safe way to find out.

## Resolving a preset back to its rooms

Resolving a schedule's or preset's `custom_rule_id` back to the room names
it actually covers (see
[Protocol notes — schedules](schedules.md#cleaning-presets-referenced-by-a-schedule))
isn't possible locally. A real device traffic capture points at this
being handled through TP-Link's cloud API rather than the local protocol
this integration speaks. The full write-up — what was tried, and why —
is in [Discussion #8](https://github.com/jan-tdy/TapoVac-ADV/discussions/8)
rather than duplicated here.

## Still undiscovered locally

- **Setting** the robot's voice/announcement language. The two *getters*
  (`getSupportVoiceLanguage` / `getCurrentVoiceLanguage` — the `speaker`
  component's calls, as
  [python-kasa documents them](https://github.com/python-kasa/python-kasa/blob/master/devtools/helpers/smartrequests.py))
  answer fine and have been included in the diagnostics download since
  v3.2.0, but no set-side method name is documented anywhere, so no
  language select entity is offered.
- Any **usage-statistics call beyond `getCleanRecords`**. `getStatistics`,
  `getUsageInfo`, `getDevLog` and similar guesses all came back
  `UNKNOWN_METHOD_ERROR`.
- The **`dev_log` component's log-access call**. `getComponentList`
  advertises `dev_log: 1` on every firmware version seen so far, but no
  public source names the method that actually reads those logs.

All three are likely handled through TP-Link's cloud API rather than the
local protocol.

## Why guessing method names is not an option

Calling an unknown method at a live device is **not** a safe way to probe
for these. An unknown method can factory-reset the robot — this happened
to the project's author, who lost a saved map set and clean history that
way mid-run. Any new call documented here has to come from a real traffic
capture, or a published method dump, not trial and error against hardware
you care about.

If you can capture traffic for one of the calls above (or any other
undocumented one), open a thread in
[Discussions](https://github.com/jan-tdy/TapoVac-ADV/discussions) — ideally
[#8](https://github.com/jan-tdy/TapoVac-ADV/discussions/8) if it's related
to preset/cloud resolution — with the request/response pair and which
transport (TPAP or AES) and firmware version it came from.

## A resolved case, for context

LOCATE ("find me") used to be listed here as undiscovered; that was
stale. The Tapo app's find-my-robot call is `playSelectAudio` with
`audio_type: seek_me`, shipped in this integration since v2.6.0 — see
[Entities](../entities.md) and the project's
[changelog](https://github.com/jan-tdy/TapoVac-ADV#changelog).

## Firmware images can't be unpacked offline

The downloadable `.scv` firmware images (the `?>ldrobot.scv<?!` container,
including the publicly-listed debug builds) are fully encrypted: the
payload is AES with a key derived from the device's own flash, so no
published binary contains it. This has been confirmed independently by
[tpbreak-cli](https://github.com/haxorthematrix/tpbreak-cli), which breaks
TP-Link's other firmware formats (the camera/router RSA + AES scheme) but
lists the Tapo RV vacuum's format as out of reach for exactly this reason.

Practical consequence: method names, voice-prompt strings and log paths
have to come from app traffic captures or published method dumps —
unpacking a stock or debug firmware image at home is not possible.
