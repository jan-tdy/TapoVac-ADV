# Contributing

Ideas, findings, issues, and pull requests are all welcome — this fork
exists because someone filed a feature request on the original repo and
someone else picked it up.

- For an undiscovered protocol command (see
  [Protocol notes — undiscovered commands](protocol/undiscovered-commands.md))
  or to propose something new, start a thread in
  [Discussions](https://github.com/jan-tdy/TapoVac-ADV/discussions).
- For a concrete bug or a ready change, open an
  [issue](https://github.com/jan-tdy/TapoVac-ADV/issues) or a pull
  request directly.

## Running the tests

The SPAKE2+/TPAP handshake (`tpap.py`) and the LZ4/schedule/map decoding
(`coordinator.py`) have a `pytest` suite under `tests/` — including an
independent SPAKE2+ device-side simulation (`tests/fake_device.py`) that
the client authenticates against in-process, so a regression in the
crypto derivation or transcript no longer needs a real device to surface.

```bash
pip install -r requirements_test.txt
pytest
```

CI runs the same suite on every push and pull request
(`.github/workflows/tests.yml`), alongside `hassfest` and `validate`
checks (`.github/workflows/hassfest.yml`,
`.github/workflows/validate.yml`).

## Reverse-engineering new protocol behavior

If you're investigating an undocumented device call:

- **Never** guess method names against a robot you care about. An
  unknown method can factory-reset the device — see
  [Protocol notes — undiscovered commands](protocol/undiscovered-commands.md)
  for why, and what happened the one time it was tried on this project.
- Capture real traffic from the official Tapo app performing the action
  you're trying to understand, then bring the request/response pair to a
  [Discussion](https://github.com/jan-tdy/TapoVac-ADV/discussions),
  noting the transport (TPAP or AES) and firmware version it came from.
- [`send_raw`](services.md#send_raw) is useful once you already know the
  method name and parameter shape, to confirm it against your own
  hardware without writing code first.

## Documentation

This site lives under `docs/` and is built with
[MkDocs](https://www.mkdocs.org/) and the
[Material theme](https://squidfunk.github.io/mkdocs-material/). To build
and preview it locally:

```bash
pip install mkdocs-material
mkdocs serve
```

`README.md` stays focused on getting a user installed and oriented in the
first few minutes (screenshots, quick comparison with upstream,
changelog); everything else — the full services reference, protocol
notes, configuration details — belongs here instead. See
[`AGENTS.md`](https://github.com/jan-tdy/TapoVac-ADV/blob/main/AGENTS.md)
at the repository root for how the README itself should be edited.
