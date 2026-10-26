# Protocol notes — schedules

`get_schedule_rules` (params `{"start_index": 0}`, response at
`result.rule_list`) returns the schedules saved in the Tapo app. This call
was discovered by [peggleg/tapo-rv30](https://github.com/peggleg/tapo-rv30)
— in response to
[epg-pers/tapo-rv30-ha#13](https://github.com/epg-pers/tapo-rv30-ha/issues/13)
— and confirmed there against an **AES-transport RV30C Mop**. It also
works against **TPAP-transport hardware** (the kind `tpap.py` in this
repository talks to), confirmed against a real RV30 Max, returning entries
shaped like:

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

## Day bitmask

Each rule's `week_day` field is a bitmask:

| Day | Value |
| --- | --- |
| Sun | 1 |
| Mon | 2 |
| Tue | 4 |
| Wed | 8 |
| Thu | 16 |
| Fri | 32 |
| Sat | 64 |

Confirmed against a real device: a schedule set for Mon/Wed/Fri came back
as `week_day = 42`, and `2 + 8 + 32 = 42` exactly.

## Cleaning presets referenced by a schedule

If a schedule is configured in the Tapo app against a saved cleaning
preset instead of picking rooms directly, `rooms`/`room_ids` come back
empty. The preset is referenced instead through `clean_attr.clean_mode: 5`
and `clean_attr.custom_rule_id: <int>` (confirmed against a real device's
raw schedule data; `clean_attr.map_id` is also present, same as for
room-list schedules).

There is no known call to resolve a `custom_rule_id` back to the room
names it actually covers — see
[Protocol notes — undiscovered commands](undiscovered-commands.md). The
decoded `custom_rule_id` / `is_preset` fields are as specific as this
integration can currently get; `rooms` stays empty for these schedules.

## How `run_schedule` works

No device call to trigger a saved schedule directly by ID has been found
in either this fork or upstream. The
[`run_schedule`](../services.md#run_schedule) service instead
**synthesizes** the same effect:

1. Look up the schedule via `get_schedule_rules`.
2. Apply its `clean_attr` (suction, water level, clean passes) with
   `setCleanAttr`.
3. Then, in order of preference:
   - if `custom_rule_id` is set, run that preset via `clean_custom_rule()`
     — the same `setSwitchClean` shape as room cleaning, but
     `clean_mode: 5` + `custom_rule_id` instead of `clean_mode: 3` +
     `room_list`;
   - else if `room_list` is set, clean those rooms via `clean_rooms()`;
   - else start a whole-house clean.

This should reproduce the clean the schedule would run on its own, but it
is an inference from the data shape, not a confirmed device "run now"
feature — it has not been verified end-to-end against a real device
running the schedule unattended for comparison.

## Viewing schedules in a dashboard

The `Schedules` sensor's own state is just a count — the full list lives
in its `schedules` attribute, which a Tile or entity card won't show by
default. A Markdown card renders it as a readable table:

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

Two easy-to-miss gotchas this snippet already accounts for:

- **`content: |`, not `content: >`.** YAML's folded style (`>`) joins
  every line with a space, destroying the table's row structure (each
  Markdown table row has to be on its own physical line). Literal style
  (`|`) keeps line breaks exactly as written.
- **The `{%-`/`-%}` whitespace-trim markers around the loop.** Without
  them, Jinja leaves a blank line where each `{% for %}`/`{% endfor %}`
  tag sat on its own line, which breaks the table right after the header
  row — you'd see a table with only the header, then the data rows dumped
  below it as plain text.

Replace `sensor.YOUR_VACUUM_schedules` with your actual entity ID.
