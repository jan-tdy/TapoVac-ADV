# Smart cleaning planner

The planner starts room cleans on its own when rooms come due, inside
cleaning windows you define - independent of (and in addition to) the
robot's own schedule store described in
[Protocol notes - schedules](protocol/schedules.md). It is ported from
upstream's v0.20.0 planner and rebuilt to be fully configurable.

Settings live on the **Planner** tab of the [Vacuum sidebar
page](dashboard.md#the-vacuum-sidebar-page), saved per robot, not as
separate Home Assistant entities (aside from the on/off switch and status
sensor below) - this keeps the settings in one place rather than spread
across dozens of helper entities.

## Safe by default

- The planner is **off** until you turn on its [switch
  entity](entities.md#switch).
- Even when on, it starts in **preview** mode (the default): it only logs
  what it would have cleaned, via the Planner Status sensor and the
  decision log, without actually starting a clean. Flip it to live mode on
  the Planner tab once you're happy with what it would do.

## Run policy

Choose, per cleaning window:

- **Once per window** - a single run, even if more rooms become due
  during the window.
- **Repeat** - keep running while rooms remain due, with a configurable
  minimum gap between runs so it doesn't restart immediately after
  finishing.

## Away condition

The planner can require nobody home before it starts a run:

- Watch specific **person** entities (as upstream does), or
- Watch **any entity** - an `input_boolean`, a device tracker, a group -
  with your own list of "home" states.

If the house never empties, set **Clean anyway after waiting** (15 minutes
to 4 hours; default *never*). Once a run is otherwise ready (inside the
window, robot docked and charged, a room due) and someone has been home that
long, the planner starts anyway. The wait is counted from the moment the run
first became ready, and a run started this way is not sent back to the dock
when someone is home.

## Room occupancy, without motion sensors

Rooms map to Home Assistant areas, and the planner treats a room as
occupied when any of the following is true:

- A motion, occupancy or presence sensor assigned to the room's area is
  on.
- A **person** entity's state equals the area's own name (so you don't
  need a dedicated presence sensor in every room a person might be in).
- Any entity you've added for that room reports one of its configured
  "busy" states.

Per-room **ignore occupancy** is available for rooms where occupancy
should never block a clean.

## Notifications

Optional, and off by default:

- A persistent notification.
- Writing a summary into your own `input_text` helper or `text` entity.
- Calling any `notify` service.

Notifications can fire when a run starts, and - at most every 30 minutes -
while a due set of rooms keeps waiting (e.g. because someone is home).

## Rooms and what is coming up

The **Rooms** card shows each room's freshness over the last 4 days: a line
that drops to 0 at every clean and rises towards the room's target, with a
dashed line at 1 (due). A room is cleaned from the moment its line crosses
that dashed line, inside an open window.

The **Upcoming** timeline projects the next several cleaning windows,
starting with today's while it has not closed yet. Each window lists the
rooms that fall due during it, with the time each one falls due (for example
`Kitchen 15:25`); rooms due before the window opens are listed without a time.
Today's window is left out once it has been skipped or has already run.

The freshness history comes from a per-room log of clean times, kept for 8
days in the integration's storage. Cleans recorded before the log existed are
filled in from the runs the robot still lists, a few at a time, so the graph
may take a few polls to fill in after an upgrade.

## Preferred time per room

Each room can have a **preferred time**, for example `19:00`, with a tolerance
of 90 minutes by default (30 to 240 minutes in the Rooms card). The planner
then cleans the room as soon as the time is within that tolerance of the
preferred time: from `17:30` to `20:30` in the example. Until then a due room
waits, while other due rooms are cleaned as usual.

The preference is only a preference. It is skipped when:

- the room's window or the tolerance band does not fall inside today's
  cleaning window, so a run is not possible at that time;
- someone came or went, so the run is started by presence;
- you press **Clean due rooms now**.

Leave the time empty to clean the room whenever it is due, as before.

## Status and logging

- **Planner Status** sensor reports what the planner is doing right now.
- The last 40 decision-log steps are shown on the Planner tab, which is
  the quickest way to understand why a run did or didn't happen.
- The pure decision logic (which rooms are due, whether the away
  condition is met, run-policy bookkeeping) is covered by
  `tests/test_planlogic.py` in the repository, independent of any real
  device.

## Known limitation

The "finish the current room, then dock when someone comes home"
behavior is implemented but **untested on real hardware** as of this
writing - treat it as beta and watch the decision log the first few times
it triggers.
