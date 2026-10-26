# Standalone CLI

[`tapo_vacuum.py`](https://github.com/jan-tdy/TapoVac-ADV/blob/main/tapo_vacuum.py)
at the repository root is a standalone command-line tool - it talks to the
robot directly and does **not** require Home Assistant. Useful for
scripting, debugging the protocol, or controlling the robot from a
machine that doesn't run Home Assistant at all.

## Install

```bash
pip install requests ecdsa lz4 Pillow cryptography
```

## Configure

Three environment variables are required: `TAPO_HOST` (the robot's local
IP address), `TAPO_USER` and `TAPO_PASS` (the same Tapo account email and
password used in the Tapo app). Running any command with one or more
missing exits immediately naming which variable(s) are missing, instead
of failing with an opaque connection error.

**Directly in the shell:**

```bash
export TAPO_HOST=192.168.1.50 TAPO_USER=you@example.com TAPO_PASS=yourpassword
python3 tapo_vacuum.py status
python3 tapo_vacuum.py map
python3 tapo_vacuum.py clean kitchen lounge
```

**Via a `.env` file** (already excluded by `.gitignore`), no extra
dependency needed:

```bash
cat > .env <<'EOF'
TAPO_HOST=192.168.1.50
TAPO_USER=you@example.com
TAPO_PASS=yourpassword
EOF

set -a; source .env; set +a
python3 tapo_vacuum.py status
```

## When to reach for this instead of Home Assistant

- Verifying connectivity and credentials before setting up the config
  entry.
- Reproducing a protocol issue in isolation when filing a bug (much
  easier to share a CLI transcript than a Home Assistant debug log).
- Exploring the device with [`send_raw`](services.md#send_raw)-equivalent
  calls without touching a live Home Assistant instance - see
  [Protocol notes - undiscovered commands](protocol/undiscovered-commands.md)
  for the safety caveats around calling unknown methods.
