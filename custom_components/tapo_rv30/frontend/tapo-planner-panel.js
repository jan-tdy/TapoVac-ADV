/* Tapo Robot Vacuum sidebar page.
 *
 * One page per Home Assistant, in the VacuumCard-ADV visual language (pill buttons,
 * accent colour, robot disc header): the robot's own schedules (add / edit / delete,
 * Do Not Disturb warnings), the smart cleaning planner, history and statistics from
 * the robot's clean records, per-room freshness, remote drive (the app's dpad),
 * maintenance and settings. Plain JavaScript, no build step. Registered by the
 * integration; toggle it in the integration's options.
 *
 * Talks to the integration over three websocket commands:
 *   tapo_rv30/planner/subscribe | set | action
 * and over the integration's services for everything else.
 */
const DOMAIN = "tapo_rv30";
const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const FAN = ["Quiet", "Standard", "Turbo", "Max", "Ultra"];
const WATER = ["off", "low", "medium", "high"];
const START = { 0: "button", 1: "app", 2: "Alexa", 3: "Google", 4: "schedule", 5: "automation", 6: "IFTTT", 7: "Alice" };
const FURN_FALLBACK = [[1, "Single bed"], [2, "Double bed"], [101, "Sofa"], [103, "Corner sofa"],
  [201, "Table & chairs"], [202, "Table"], [204, "Dining table"], [205, "Dining chair"],
  [301, "TV unit"], [302, "Wardrobe"], [401, "Fridge"], [402, "Washer"], [503, "Plant"],
  [601, "Toilet"], [602, "Washbasin"], [701, "Pet house"]];
const FURN_SIZE = { 1: [900, 2000], 2: [1500, 2000], 101: [850, 850], 102: [1600, 900], 103: [2600, 1600],
  201: [2200, 1170], 202: [900, 900], 203: [500, 500], 204: [1600, 900], 205: [450, 450], 301: [1600, 450],
  302: [1200, 600], 303: [450, 400], 401: [700, 700], 402: [600, 600], 403: [450, 350], 503: [500, 500],
  601: [400, 700], 602: [600, 450], 701: [600, 500], 702: [550, 450], 703: [400, 250] };
const FURN_MIN = 200;
const FURN_ROTATE_OFFSET = 220;   // mm beyond the top edge's midpoint where the rotate handle sits
const mmBox = (x0, y0, x1, y1) => { const l = Math.min(x0, x1), r = Math.max(x0, x1), b = Math.min(y0, y1), t = Math.max(y0, y1); return [[l, t], [r, t], [r, b], [l, b]]; };
const VOLATILE = new Set(["position_mm", "path_points", "battery_level", "battery_icon", "clean_area", "clean_time_min", "clean_percent", "entity_picture", "access_token"]);
const TABS = [["vacuum", "mdi:robot-vacuum", "Vacuum"], ["zones", "mdi:vector-square", "Zones"],
              ["schedules", "mdi:calendar-clock", "Schedules"],
              ["planner", "mdi:calendar-check", "Planner"],
              ["autoempty", "mdi:delete-sweep", "Auto-empty"],
              ["history", "mdi:history", "History"], ["rooms", "mdi:floor-plan", "Rooms"],
              ["drive", "mdi:gamepad-variant", "Drive"], ["maintenance", "mdi:wrench", "Maintenance"],
              ["edit", "mdi:pencil-ruler", "Edit map"], ["backups", "mdi:content-save-outline", "Backups"],
              ["settings", "mdi:tune", "Settings"], ["log", "mdi:text-box-outline", "Log"]];
const LOG_COLORS = { ERROR: "#db4437", CRITICAL: "#db4437", WARNING: "#e8a33d", INFO: "var(--vc-accent)", DEBUG: "#8a8f98" };
// Minutes after midnight inside the robot's Do Not Disturb window? Windows cross midnight.
const toMin = (hhmm) => { const [h, m] = String(hhmm || "0:0").split(":").map(Number); return h * 60 + m; };
const inDnd = (dnd, hhmm) => {
  if (!dnd || !dnd.enabled) return false;
  const t = toMin(hhmm), a = toMin(dnd.start), b = toMin(dnd.end);
  if (a === b) return true;
  return a < b ? (t >= a && t < b) : (t >= a || t < b);
};
const dndText = (dnd) => `Do Not Disturb (${dnd.start} to ${dnd.end})`;
const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const ago = (ts) => {
  if (!ts) return "never";
  const d = Math.max(0, Date.now() / 1000 - ts);
  if (d < 120) return "just now";
  if (d < 3600) return `${Math.round(d / 60)} min ago`;
  if (d < 86400 * 2) return `${Math.round(d / 3600)} h ago`;
  return `${Math.round(d / 86400)} days ago`;
};
const nOf = (c) => Object.assign({ persistent: false, input_text: null, text_entity: null, notify_service: null, when: "start" }, c.notify || {});

const STYLE = `
:host { display: block; height: 100%; background: var(--primary-background-color);
  color: var(--primary-text-color);
  --vc-accent: var(--primary-color, #34e0d6);
  --vc-dark: #0b0f14; }
[hidden] { display: none !important; }
.wrap { max-width: 1400px; margin: 0 auto; padding: 16px 16px 48px; display: grid; gap: 14px; }
.wrap.narrow { padding: 10px 10px 40px; }
.main { display: grid; grid-template-columns: 340px minmax(0, 1fr); gap: 14px; align-items: start; }
.wrap.narrow .main { grid-template-columns: 1fr; }
@media (max-width: 900px) { .main { grid-template-columns: 1fr; } }
.left, .right { min-width: 0; }

/* header, like the card's */
.head { display: flex; align-items: center; gap: 12px; padding: 0 2px; }
.disc { width: 54px; height: 54px; border-radius: 50%; flex: none; display: grid; place-items: center;
        background: var(--vc-accent); color: var(--vc-dark); }
.disc ha-icon { --mdc-icon-size: 28px; }
.head .txt { min-width: 0; }
.head .name { font-size: 1.18em; font-weight: 700; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.head .status { color: var(--secondary-text-color); font-size: .92em; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.robots { display: flex; gap: 6px; margin-left: auto; flex-wrap: wrap; }

/* tabs, pill shaped like everything else */
.tabs { display: flex; flex-wrap: wrap; gap: 6px; overflow: visible; scrollbar-width: none; margin-bottom: 12px; }
.tabs button { flex: none; border: 1px solid var(--divider-color); background: transparent;
  color: var(--secondary-text-color); border-radius: 999px; padding: 7px 14px; font: inherit;
  font-size: .85em; font-weight: 600; cursor: pointer; display: inline-flex; align-items: center; gap: 6px; }
.tabs button.on { background: var(--vc-accent); border-color: var(--vc-accent); color: var(--vc-dark); }
.tabs button ha-icon { --mdc-icon-size: 16px; }

ha-card, .card { background: var(--card-background-color); border: 1px solid var(--divider-color);
                 border-radius: 14px; padding: 14px 16px; display: block; margin-bottom: 12px; }
.card:last-child { margin-bottom: 0; }
h3 { margin: 0 0 10px; font-size: .95em; font-weight: 700; display: flex; align-items: center; gap: 8px; }
h3 .note { font-weight: 400; color: var(--secondary-text-color); font-size: .92em; margin-left: auto; }
h5 { margin: 12px 0 6px; font-size: .76em; font-weight: 500; letter-spacing: .04em; text-transform: uppercase;
     color: var(--secondary-text-color); }

/* pill buttons, exactly like the card */
.btn { border: 1px solid var(--vc-accent); color: var(--vc-accent); background: transparent;
       border-radius: 999px; padding: 8px 16px; font: inherit; font-size: .9em; font-weight: 600;
       cursor: pointer; display: inline-flex; align-items: center; gap: 6px; }
.btn:hover { background: var(--secondary-background-color, rgba(127,127,127,.12)); }
.btn.primary { background: var(--vc-accent); color: var(--vc-dark); }
.btn:disabled { opacity: .45; cursor: default; }
.btn ha-icon { --mdc-icon-size: 16px; }
.actions { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.icon-btn { border: none; background: none; cursor: pointer; color: var(--secondary-text-color);
            width: 34px; height: 34px; border-radius: 999px; display: grid; place-items: center; flex: none; }
.icon-btn:hover { background: var(--secondary-background-color, rgba(127,127,127,.12)); }
.icon-btn ha-icon { --mdc-icon-size: 18px; }

/* toggle, like the card's switch */
.switch { width: 42px; height: 24px; border-radius: 999px; border: 1px solid var(--divider-color);
          background: var(--secondary-background-color, rgba(127,127,127,.2)); position: relative;
          cursor: pointer; flex: none; padding: 0; }
.switch::after { content: ""; position: absolute; top: 2px; left: 2px; width: 18px; height: 18px;
                 border-radius: 50%; background: var(--secondary-text-color); transition: left .15s, background .15s; }
.switch.on { background: var(--vc-accent); border-color: var(--vc-accent); }
.switch.on::after { left: 20px; background: var(--vc-dark); }

.chips { display: flex; gap: 6px; flex-wrap: wrap; }
.chip { border: 1px solid var(--divider-color); color: var(--secondary-text-color); background: transparent;
        border-radius: 999px; padding: 5px 12px; font-size: .82em; cursor: default; }
.chip.on { border-color: var(--vc-accent); color: var(--vc-accent); }
.chip.btn.on { background: var(--vc-accent); border-color: var(--vc-accent); color: var(--vc-dark); font-weight: 600; }
.chip.warn { border-color: var(--error-color, #db4437); color: var(--error-color, #db4437); }
.chip.info { border-color: var(--divider-color); }
.chip.btn { cursor: pointer; }

.line { font-size: 1.05em; font-weight: 600; margin: 2px 0 8px; }
.sub { color: var(--secondary-text-color); font-size: .88em; }

/* condition / entity rows */
.row { display: flex; align-items: center; gap: 10px; padding: 9px 0; border-top: 1px solid var(--divider-color); }
.row:first-of-type { border-top: 0; }
.row .grow { flex: 1; min-width: 0; }
.row .t { font-size: .93em; }
.row .s { color: var(--secondary-text-color); font-size: .82em; }
.row.off .grow { opacity: .5; }
.ctl { display: flex; align-items: center; gap: 8px; flex: none; }
.seg { display: flex; border: 1px solid var(--divider-color); border-radius: 999px; overflow: hidden; }
.seg button { border: 0; background: transparent; color: var(--secondary-text-color); padding: 6px 12px;
              font: inherit; font-size: .84em; cursor: pointer; }
.seg button.on { background: var(--vc-accent); color: var(--vc-dark); font-weight: 700; }
.warn { color: var(--warning-color, #ff9800); font-size: .84em; display: flex; gap: 5px; align-items: center; margin-top: 3px; }
.warn ha-icon { --mdc-icon-size: 16px; }

select, input[type=time], input[type=number], input[type=text] {
  color: var(--primary-text-color); background: var(--card-background-color);
  border: 1px solid var(--divider-color); border-radius: 6px; padding: 6px 8px; font: inherit; font-size: .86em; }
input[type=number] { width: 74px; }
input[type=range] { accent-color: var(--vc-accent); width: 140px; }
ha-entity-picker { max-width: 300px; --ha-switch-checked-color: var(--vc-accent); }
.form { display: grid; gap: 12px; }
.form label { display: block; font-size: .8em; color: var(--secondary-text-color); margin-bottom: 4px; }
.grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }

/* quick status card (when the Lovelace card is not loaded) */
.quick-batt { display: flex; align-items: center; gap: 10px; }
.vac-live { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; margin-top: 10px; }
.vac-live .stat { padding: 9px 11px; }
.vac-live .stat .v { font-size: 1em; overflow-wrap: anywhere; }
.vac-live-progress { grid-column: 1 / -1; }
.vac-live-progress .bar { margin-top: 6px; }

/* rooms (planner) */
.room { border-top: 1px solid var(--divider-color); padding: 11px 0; }
.room:first-of-type { border-top: 0; }
.room .top { display: flex; align-items: center; gap: 10px; }
.room .nm { font-weight: 600; font-size: .96em; }
.bar { flex: 1; height: 6px; border-radius: 3px; background: var(--secondary-background-color, rgba(127,127,127,.18)); overflow: hidden; min-width: 60px; }
.bar > div { height: 100%; background: var(--vc-accent); }
.bar.due > div { background: var(--error-color, #db4437); }
.pillst { border-radius: 999px; padding: 4px 12px; font-size: .8em; border: 1px solid var(--divider-color); color: var(--secondary-text-color); white-space: nowrap; }
.pillst.over { border-color: var(--error-color, #db4437); color: var(--error-color, #db4437); }
.pillst.due { border-color: var(--vc-accent); color: var(--vc-accent); }
.pillst.fresh { border-color: var(--divider-color); color: var(--secondary-text-color); }
.pillst.out { opacity: .6; }
.room .bot { display: flex; align-items: center; gap: 8px; margin-top: 8px; flex-wrap: wrap; }
.room .bot .sub { flex: 1; min-width: 180px; }
.room .editor { margin-top: 10px; padding: 10px 12px; border: 1px dashed var(--divider-color); border-radius: 10px; }
.minibtn { border: 1px solid var(--divider-color); background: transparent; color: var(--secondary-text-color);
           border-radius: 999px; padding: 4px 12px; font: inherit; font-size: .8em; cursor: pointer; }
.minibtn:hover, .minibtn.on { border-color: var(--vc-accent); color: var(--vc-accent); }
.minibtn.danger:hover { border-color: var(--error-color, #db4437); color: var(--error-color, #db4437); }

.banner { display: flex; align-items: center; gap: 10px; padding: 10px 12px; border-radius: 10px;
          border: 1px solid var(--vc-accent); color: var(--vc-accent); font-size: .88em; margin-bottom: 10px; }
.banner.live { border-color: var(--divider-color); color: var(--primary-text-color); }
.banner ha-icon { --mdc-icon-size: 20px; flex: none; }
.banner .grow { flex: 1; }

.log .e { display: flex; gap: 10px; padding: 6px 0; border-top: 1px solid var(--divider-color); font-size: .88em; }
.log .e:first-of-type { border-top: 0; }
.log .e b { font-weight: 400; color: var(--secondary-text-color); width: 100px; flex: none; }
.empty { padding: 20px; text-align: center; color: var(--secondary-text-color); font-size: .9em; }
.err { color: var(--error-color, #db4437); font-size: .88em; }

/* history */
.stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }
.stat { padding: 12px; border-radius: 12px; background: var(--secondary-background-color, rgba(127,127,127,.08)); }
.stat .v { font-size: 1.4em; font-weight: 600; }
.stat .l { font-size: .78em; color: var(--secondary-text-color); }
canvas.chart { width: 100%; height: 140px; display: block; }
.etools { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin-bottom: 8px; }
.etool.on { background: var(--vc-accent); color: var(--vc-dark); }
.efurn { padding: 7px 10px; border-radius: 10px; border: 1px solid var(--divider-color); background: var(--card-background-color); color: var(--primary-text-color); }
.ehint { font-size: .8em; color: var(--secondary-text-color); margin-bottom: 8px; }
.estage { background: #1b1b1b; border-radius: 10px; overflow: hidden; line-height: 0; }
.ecanvas { width: 100%; height: auto; display: block; touch-action: none; cursor: crosshair; }
.erooms { margin-top: 10px; } .erooms h5 { margin: 6px 0; }
.ebtns { display: flex; gap: 8px; margin-top: 12px; align-items: center; flex-wrap: wrap; }
.estatus { margin-top: 8px; min-height: 1.2em; }
.bkgrid { display: grid; grid-template-columns: repeat(auto-fill,minmax(220px,1fr)); gap: 10px; }
.bkcard { border-radius: 12px; overflow: hidden; background: var(--secondary-background-color); border: 1px solid var(--divider-color); }
.bkcard .thumb { display: block; width: 100%; aspect-ratio: 1; object-fit: contain; background: var(--primary-background-color); cursor: pointer; }
.bkcard .thumb.none { display: flex; align-items: center; justify-content: center; color: var(--secondary-text-color); font-size: .8em; }
.bkcard .meta { padding: 9px 11px; } .bkcard .meta .t { font-weight: 600; }
.bkcard .meta .s { font-size: .8em; color: var(--secondary-text-color); margin-top: 2px; }
.bkcard .meta .acts { display: flex; gap: 6px; margin-top: 9px; }
.bkcard .meta .acts .btn { flex: 1; justify-content: center; padding: 7px 6px; }
.src { font-size: .68em; text-transform: uppercase; letter-spacing: .04em; padding: 2px 6px; border-radius: 6px; background: var(--secondary-background-color); color: var(--secondary-text-color); }
.lightbox { position: fixed; inset: 0; background: rgba(0,0,0,.72); display: flex; align-items: center; justify-content: center; z-index: 9; padding: 20px; }
.lightbox img { max-width: 92vw; max-height: 78vh; border-radius: 10px; background: #1b1b1b; }
.lightbox .lb-info { position: absolute; bottom: 16px; left: 0; right: 0; text-align: center; color: #fff; font-size: .86em; }
/* a rotated preview (history map): lb-wrap holds the final on-screen box, lb-stage is the
   same image pre-rotation (width/height swapped for 90/270) so it lands exactly on it. */
.lightbox .lb-wrap { position: relative; }
.lightbox .lb-stage { position: absolute; top: 50%; left: 50%; display: flex; }
.lightbox .lb-stage img { width: 100%; height: 100%; max-width: none; max-height: none; }
/* rooms and freshness, drive, maintenance */
.bar-row { display: grid; grid-template-columns: 110px 1fr 70px; gap: 10px; align-items: center; font-size: .86em; padding: 5px 0; }
.bar-row .track { height: 8px; border-radius: 4px; background: var(--secondary-background-color, rgba(127,127,127,.18)); overflow: hidden; }
.bar-row .track > div { height: 100%; border-radius: 4px; background: var(--vc-accent); }
.bar-row.warn .track > div { background: var(--warning-color, #ffa600); }
.bar-row.bad .track > div { background: var(--error-color, #db4437); }
.bar-row .r { text-align: right; color: var(--secondary-text-color); }
.bar-row.consumable-row { grid-template-columns: minmax(85px, 125px) minmax(36px, 1fr) 38px auto; gap: 6px; }
.consumable-row .minibtn { padding: 4px 9px; }
.drv-status { display: flex; align-items: center; gap: 8px; padding: 10px 12px; border-radius: 10px;
              margin-bottom: 8px; font-size: .9em; background: var(--secondary-background-color, rgba(127,127,127,.1)); }
.drv-status.live { border: 1px solid var(--vc-accent); color: var(--vc-accent);
                   background: var(--secondary-background-color, rgba(127,127,127,.05)); }
.drv-status ha-icon { --mdc-icon-size: 20px; flex: none; }
.dpad { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; max-width: 280px; margin: 14px auto;
        touch-action: none; user-select: none; -webkit-user-select: none; }
.dpad button { aspect-ratio: 1; border: 1px solid var(--divider-color); border-radius: 14px; cursor: pointer;
               display: grid; place-items: center; background: var(--secondary-background-color, rgba(127,127,127,.1));
               color: var(--primary-text-color); touch-action: none; -webkit-touch-callout: none; }
.dpad button ha-icon { --mdc-icon-size: 30px; pointer-events: none; }
.dpad button.held { background: var(--vc-accent); border-color: var(--vc-accent); color: var(--vc-dark); }
.dpad button.halt { background: var(--secondary-background-color, rgba(219,68,55,.14));
                    color: var(--error-color, #db4437); border-color: var(--error-color, #db4437); }
.dpad[aria-disabled="true"] button { opacity: .35; pointer-events: none; }
/* vacuum home tab */
.vac-ctrl { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 12px; }
.vac-ctrl .btn { flex: 1 1 92px; justify-content: center; padding: 10px 12px; }
.presets { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 10px; }
.mapwrap { position: relative; border-radius: 12px; overflow: hidden;
           background: var(--secondary-background-color, rgba(127,127,127,.06)); }
.mapwrap { max-height: 58vh; aspect-ratio: var(--map-ratio, 1); margin-inline: auto; }
.mapstage { position: absolute; top: 50%; left: 50%; transform-origin: center; }
.mapstage img { display: block; width: 100%; height: 100%; object-fit: contain; }
.mapstage svg { position: absolute; inset: 0; width: 100%; height: 100%; }
.mapwrap rect.room { cursor: pointer; fill: var(--vc-accent); fill-opacity: 0;
                     stroke: transparent; stroke-width: 2; }
.mapwrap rect.room:hover { fill-opacity: .18; }
.mapwrap rect.room.sel { fill-opacity: .32; stroke: var(--vc-accent); stroke-opacity: .9; }
.mapwrap rect.room.sel:hover { fill-opacity: .42; }
.mapwrap rect.room:focus { outline: none; }
.mapwrap rect.room:focus-visible { stroke: var(--vc-accent); stroke-opacity: 1; stroke-width: 3; }
.mapwrap rect.zone-preset { cursor: pointer; fill: #8e70d6; fill-opacity: .14; stroke: #8e70d6; stroke-width: 3; stroke-dasharray: 8 5; }
.mapwrap rect.zone-preset:hover, .mapwrap rect.zone-preset.sel { fill-opacity: .38; stroke-width: 5; }
.zone-menu-wrap { position: relative; }
.zone-picker { position: absolute; z-index: 5; top: calc(100% + 6px); left: 0; width: min(320px, calc(100vw - 48px));
  border: 1px solid var(--divider-color); border-radius: 10px; padding: 10px;
  background: var(--ha-card-background, var(--card-background-color, var(--primary-background-color)));
  box-shadow: 0 6px 20px rgba(0,0,0,.25); }
.zone-picker .actions { margin-top: 8px; }
.map-tools { display: flex; flex-wrap: wrap; gap: 6px; margin: 6px 0 10px; }
.map-tools .minibtn.on { background: var(--vc-accent); border-color: var(--vc-accent); color: var(--vc-dark); }
.mapwrap rect.hit { cursor: crosshair; fill: transparent; touch-action: none; }
.mapwrap rect.zone-draft { fill: var(--vc-accent); fill-opacity: .28; stroke: var(--vc-accent); stroke-width: 2; pointer-events: none; }
`;

class TapoPlannerPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._tab = "vacuum";
    this._cleanSel = new Set();
    this._selMapId = null;
    this._zonePickerOpen = false;
    this._selectedZonePreset = null;
    this._zonePresets = [];
    this._zonePresetsKey = null;
    this._zonePresetsLoading = null;
    this._mapPic = null;
    this._mapUrl = null;
    this._mapRotation = 0;
    this._chartObserver = null;
    this._robot = null;
    this._editing = null;   // schedule being edited (object) or {} for new, or null
    this._records = null;   // get_clean_records response of the History tab
    this._recordsFor = null;
    this._open = null;      // room key whose sensor editor is open
    this._planRev = 0;      // re-render counter for planner updates
    this._planDirty = false; // an input is being edited: skip the live re-render
    this._autoEmptyUnsub = null; this._autoEmptyFor = null; this._autoEmpty = null;
  }

  set panel(p) { this._panel = p; }
  set narrow(n) { this._narrow = n; this._layout(); }
  set route(r) { this._route = r; }
  connectedCallback() {
    if (!this._outsideZoneClick) {
      this._outsideZoneClick = (e) => {
        const path = e.composedPath();
        queueMicrotask(() => {
          if (!this._zonePickerOpen) return;
          const wrap = this.shadowRoot.querySelector(".zone-menu-wrap");
          if (wrap && !path.includes(wrap)) {
            this._zonePickerOpen = false;
            this._update(true);
          }
        });
      };
    }
    document.addEventListener("click", this._outsideZoneClick, true);
  }
  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (first) { this._boot(); return; }
    if (this._booted) this._update();
  }

  async _boot() {
    this.shadowRoot.innerHTML = `<style>${STYLE}</style>
      <div class="wrap">
        <div class="head"></div>
        <div class="main">
          <div class="left"></div>
          <div class="right">
            <div class="tabs">${TABS.map(([k, i, l]) => `<button data-tab="${k}"><ha-icon icon="${i}"></ha-icon>${l}</button>`).join("")}</div>
            <div class="pane"></div>
          </div>
        </div>
      </div>`;
    this.shadowRoot.querySelectorAll(".tabs button").forEach((b) => b.onclick = () => {
      if (this._stopDrive) this._stopDrive();
      if (this._chartObserver) { this._chartObserver.disconnect(); this._chartObserver = null; }
      this._tab = b.dataset.tab;
      this._mapAction = "select";
      this._editing = null;
      this._update(true);
    });
    this._booted = true;
    this._layout();
    this._update(true);
  }

  _layout() {
    const w = this.shadowRoot && this.shadowRoot.querySelector(".wrap");
    if (w) w.classList.toggle("narrow", !!this._narrow);
  }

  disconnectedCallback() {
    if (this._outsideZoneClick) document.removeEventListener("click", this._outsideZoneClick, true);
    this._dropSub();
    if (this._chartObserver) { this._chartObserver.disconnect(); this._chartObserver = null; }
    if (this._stopDrive) this._stopDrive();
  }

  // ---- data ------------------------------------------------------------------------
  _robots() {
    const reg = (this._hass && this._hass.entities) || {};
    return Object.values(this._hass.states).filter((s) =>
      s.entity_id.startsWith("vacuum.") && reg[s.entity_id] && reg[s.entity_id].platform === DOMAIN);
  }
  _st(id) { return id ? this._hass.states[id] : undefined; }
  _related(vac) {
    const reg = this._hass.entities || {}, dev = reg[vac] && reg[vac].device_id;
    let ids = dev ? Object.keys(reg).filter((id) => reg[id].device_id === dev) : [];
    if (!ids.length) { const base = vac.split(".")[1]; ids = Object.keys(this._hass.states).filter((id) => id.split(".")[1].startsWith(base)); }
    const find = (prefix, needle) => ids.find((id) => id.startsWith(prefix) && (!needle || id.includes(needle)));
    const all = (prefix) => ids.filter((id) => id.startsWith(prefix)).sort();
    return {
      ids, camera: find("camera."), schedules: find("sensor.", "schedules"), status: find("sensor.", "status"),
      cleanArea: find("sensor.", "clean_area"),
      mapImage: find("image.", "map_image"),
      presets: all("button.").filter((id) => id.includes("preset")),
      switches: all("switch."), selects: all("select."), numbers: all("number."), times: all("time."),
      buttons: all("button.").filter((id) => !id.includes("preset")),
    };
  }

  // Map rotation is a Map Rotation select entity (an integration option, so it is
  // global and shared across every browser/device, not per-session like before).
  _loadMapRotation(robot) {
    const id = this._related(robot).selects.find((i) => i.includes("map_rotation"));
    this._mapRotationEntity = id;
    const st = id ? this._st(id) : null;
    const value = Number(st && st.state);
    this._mapRotation = [0, 90, 180, 270].includes(value) ? value : 0;
  }

  _saveMapRotation() {
    if (!this._mapRotationEntity) return;
    this._call("select", "select_option", { option: String(this._mapRotation) },
               { entity_id: this._mapRotationEntity });
  }
  _schedules(r) { const s = this._st(r.schedules); return (s && s.attributes.schedules) || []; }
  _dnd(r) { const s = this._st(r.schedules); return (s && s.attributes.dnd) || null; }
  _rooms(vac) {
    const s = this._st(vac);
    if (s && s.attributes.rooms && s.attributes.rooms.length) return s.attributes.rooms;
    const cam = this._st(this._related(vac).camera);
    return (cam && cam.attributes.rooms) || [];
  }
  _presets(r) {
    return r.presets.map((id) => { const s = this._st(id);
      return { id: s.attributes.preset_id, name: s.attributes.preset_name || s.attributes.friendly_name, rooms: s.attributes.rooms };
    }).filter((p) => p.id != null);
  }

  async _call(domain, service, data, target) {
    try { await this._hass.callService(domain, service, data, target); return true; }
    catch (e) {
      const message = (e && (e.message || (e.body && e.body.message))) || "The robot rejected that";
      this._notify(message);
      return false;
    }
  }

  // ---- planner websocket ---------------------------------------------------------------
  async _ensurePlanSub() {
    if (this._for === this._robot || this._pending || !this._robot) return;
    this._dropSub();
    this._for = this._robot; this._pending = true; this._plan = null; this._planErr = null;
    try {
      this._unsub = await this._hass.connection.subscribeMessage((view) => {
        this._plan = view;
        this._planRev++;
        const a = this.shadowRoot.activeElement;
        if (a && (a.tagName === "SELECT" || a.tagName === "INPUT" || a.tagName === "HA-ENTITY-PICKER")) {
          this._planDirty = true; return;
        }
        this._update();
      }, { type: `${DOMAIN}/planner/subscribe`, entity_id: this._robot });
    } catch (e) {
      this._planErr = (e && e.message) || "The planner needs the v4.0 integration or newer.";
      this._update();
    } finally { this._pending = false; }
  }

  _dropSub() {
    if (this._unsub) { try { this._unsub(); } catch (e) { /* closed */ } }
    this._unsub = null; this._for = null;
  }

  async _ws(msg) {
    try {
      const res = await this._hass.callWS({ entity_id: this._robot, ...msg });
      const view = res && (res.view || (res.rooms ? res : null));
      if (view) { this._plan = view; this._planDirty = false; this._update(); }
      return res;
    } catch (e) {
      this._notify((e && e.message) || "The planner refused that");
      return null;
    }
  }
  _set(config) { return this._ws({ type: `${DOMAIN}/planner/set`, config }); }
  _act(action, extra) { return this._ws({ type: `${DOMAIN}/planner/action`, action, ...(extra || {}) }); }

  _notify(message) {
    this.dispatchEvent(new CustomEvent("hass-notification", { detail: { message }, bubbles: true, composed: true }));
  }

  // ---- render ------------------------------------------------------------------------
  _update(first) {
    const robots = this._robots();
    const wrap = this.shadowRoot.querySelector(".wrap");
    const head = wrap.querySelector(".head");
    const pane = wrap.querySelector(".pane");
    if (!robots.length) {
      head.innerHTML = "";
      wrap.querySelector(".left").innerHTML = "";
      pane.innerHTML = `<ha-card><div class="card"><div class="empty">No Tapo robot vacuum is set up yet.</div></div></ha-card>`;
      return;
    }
    if (!this._robot || !robots.some((r) => r.entity_id === this._robot)) {
      this._robot = robots[0].entity_id;
      this._loadMapRotation(this._robot);
    }
    const st = this._st(this._robot);
    const name = (st && st.attributes.friendly_name) || this._robot;
    const v = this._tab === "planner" ? this._plan : null;
    head.innerHTML = `
      <div class="disc"><ha-icon icon="mdi:robot-vacuum"></ha-icon></div>
      <div class="txt">
        <div class="name">${esc(name)}</div>
        <div class="status">${v ? esc(v.status) : esc((st && st.state) || "")}</div>
      </div>
      ${robots.length > 1 ? `<div class="robots">${robots.map((r) =>
        `<button class="minibtn ${r.entity_id === this._robot ? "on" : ""}" data-robot="${esc(r.entity_id)}">${esc((this._hass.states[r.entity_id].attributes.friendly_name) || r.entity_id)}</button>`).join("")}</div>` : ""}`;
    head.querySelectorAll("[data-robot]").forEach((b) => b.onclick = () => {
      this._robot = b.dataset.robot;
      this._loadMapRotation(this._robot);
      this._open = null; this._editing = null; this._records = null; this._plan = null;
      this._cleanSel = new Set(); this._mapPic = null; this._mapUrl = null;
      this._dropSub(); this._dropAutoEmptySub();
      this._update(true);
    });
    this._renderLeft();
    // The edit tab deliberately does not reload (and so does not re-read rotation) on every
    // poll, to keep unsaved edits - but a rotation change from elsewhere still has to reach
    // the open canvas, so pick it up here without touching this._edit's areas/furniture/rooms.
    if (this._tab === "edit" && this._edit && this._edit.img) {
      const prevRot = this._mapRotation;
      this._loadMapRotation(this._robot);
      if (this._mapRotation !== prevRot) this._editApplyRotation();
    }
    this.shadowRoot.querySelectorAll(".tabs button").forEach((b) => b.classList.toggle("on", b.dataset.tab === this._tab));
    if (this._tab === "planner") this._ensurePlanSub(); else this._dropSub();
    if (this._tab === "autoempty") this._ensureAutoEmptySub(); else this._dropAutoEmptySub();
    const sig = JSON.stringify([this._tab, this._robot,
      this._editing ? String(this._editing.id != null ? this._editing.id : "new") : "",
      this._tab === "planner" ? [this._planRev, this._open] : this._relatedSig()]);
    if (!first && sig === this._paneSig) return;
    this._paneSig = sig;
    ({ vacuum: this._paneVacuum, zones: this._paneZones, schedules: this._paneSchedules, planner: this._panePlanner, autoempty: this._paneAutoEmpty, history: this._paneHistory,
       rooms: this._paneRooms, drive: this._paneDrive, edit: this._paneEdit, backups: this._paneBackups,
       maintenance: this._paneMaintenance, settings: this._paneSettings, log: this._paneLog }[this._tab]).call(this, pane);
  }


  _isAdmin() { const u = this._hass && this._hass.user; return !u || u.is_admin !== false; }

  _relatedSig() {
    const r = this._related(this._robot);
    if (this._tab === "backups" || this._tab === "log") return this._robot;
    if (this._tab === "edit") {
      const cam = this._st(r.camera), a = cam && cam.attributes || {};
      // The canvas owns local unsaved edits. Keep it mounted through all polling;
      // map_id changes only when the robot switches maps, while Discard reloads on demand.
      return JSON.stringify([this._robot, a.map_id]);
    }
    const pick = (ids) => ids.map((id) => {
      const s = this._st(id); if (!s) return "";
      const attrs = Object.fromEntries(Object.entries(s.attributes || {}).filter(([k]) => !VOLATILE.has(k)));
      // Keep only the live coordinate in the vacuum pane signature so its marker moves;
      // rapid path/battery telemetry must not tear down editor canvases or forms.
      if (this._tab === "vacuum" && id === this._robot) attrs.position_mm = s.attributes.position_mm;
      if (this._tab === "vacuum" && id === r.camera) {
        attrs.entity_picture = s.attributes.entity_picture;
        attrs.access_token = s.attributes.access_token;
      }
      return s.state + JSON.stringify(attrs);
    }).join("|");
    return pick([this._robot, r.camera, r.schedules, r.status, r.mapImage, ...r.switches, ...r.selects, ...r.numbers, ...r.times, ...r.presets]);
  }

  _renderLeft() {
    const left = this.shadowRoot.querySelector(".left");
    const vac = this._st(this._robot);
    if (!vac) { left.innerHTML = ""; return; }
    // Keep the optional Lovelace card, or provide the compact controls ourselves.
    const el = customElements.get("tapo-vacuum-card") ? "tapo-vacuum-card"
      : (customElements.get("vacuum-card") ? "vacuum-card" : null);
    if (el) {
      let card = left.querySelector(el);
      if (!card || card._tapoEntity !== this._robot) {
        left.innerHTML = "";
        card = document.createElement(el);
        try { card.setConfig({ entity: this._robot }); } catch (e) { card = null; }
        if (card) { card._tapoEntity = this._robot; left.appendChild(card); }
      }
      if (card) card.hass = this._hass;
    }
    if ((!el || !left.querySelector(el)) && !left.querySelector("[data-left-controls]")) {
      left.innerHTML = `<ha-card><div class="card" data-left-controls>
        <h3><span>Vacuum controls</span></h3>
        <div class="actions" style="margin-top:8px">
          <button class="btn primary" data-q="start"><ha-icon icon="mdi:play"></ha-icon>Clean</button>
          <button class="btn" data-q="pause"><ha-icon icon="mdi:pause"></ha-icon>Pause</button>
          <button class="btn" data-q="return_to_base"><ha-icon icon="mdi:home-import-outline"></ha-icon>Dock</button>
        </div>
      </div></ha-card>`;
      left.querySelectorAll("[data-q]").forEach((b) => b.onclick = () => this._call("vacuum", b.dataset.q, {}, { entity_id: this._robot }));
    }
    let live = left.querySelector("[data-left-live]");
    if (!live) {
      const card = document.createElement("ha-card");
      card.innerHTML = `<div class="card"><h3><span>Live status</span></h3><div class="vac-live" data-left-live></div></div>`;
      left.appendChild(card);
      live = card.querySelector("[data-left-live]");
    }
    const a = vac.attributes || {}, r = this._related(this._robot);
    const status = this._st(r.status), room = a.current_room || "—";
    const hasMop = r.ids.some((id) => id.startsWith("binary_sensor.") && id.includes("mop_attached"));
    const mop = a.mop_attached == null ? "Unknown" : (a.mop_attached ? "Attached" : "Not attached");
    const battery = Number(a.battery_level), percent = Number(a.clean_percent);
    const active = ["cleaning", "returning", "paused"].includes(vac.state);
    const progress = Number.isFinite(percent) && (active || percent > 0)
      ? Math.max(0, Math.min(100, percent)) : null;
    const area = Number(a.clean_area), minutes = Number(a.clean_time_min);
    const areaUnit = this._st(r.cleanArea)?.attributes?.unit_of_measurement || "m²";
    live.innerHTML = `<div class="stat"><div class="l">Status</div><div class="v">${esc(status ? status.state : vac.state)}</div></div>
      ${Number.isFinite(battery) ? `<div class="stat"><div class="l">Battery</div><div class="v">${Math.round(battery)}%</div><div class="bar ${battery <= 20 ? "due" : ""}"><div style="width:${Math.max(0, Math.min(100, battery))}%"></div></div></div>` : ""}
      <div class="stat"><div class="l">Current room</div><div class="v">${esc(room)}</div></div>
      ${hasMop ? `<div class="stat"><div class="l">Mop</div><div class="v">${esc(mop)}</div></div>` : ""}
      ${progress == null ? "" : `<div class="stat vac-live-progress"><div class="l">Cleaning progress</div><div class="v">${Math.round(progress)}%</div><div class="bar"><div style="width:${progress}%"></div></div></div>`}
      ${Number.isFinite(area) && area > 0 ? `<div class="stat"><div class="l">Area cleaned</div><div class="v">${esc(area)} ${esc(areaUnit)}</div></div>` : ""}
      ${Number.isFinite(minutes) && minutes > 0 ? `<div class="stat"><div class="l">Cleaning time</div><div class="v">${esc(minutes)} min</div></div>` : ""}`;
  }

  // ---- vacuum home tab ----------------------------------------------------------------
  _paneZones(pane) {
    const r = this._related(this._robot), cam = this._st(r.camera), attrs = (cam && cam.attributes) || {};
    const name = attrs.map_name || "current map", isAdmin = this._isAdmin();
    pane.innerHTML = `<ha-card><div class="card">
      <h3><span>Zones</span><span class="note map-note">${esc(name)}</span>
        <button class="icon-btn" data-map-rotate title="Rotate map 90°" aria-label="Rotate map 90 degrees"><ha-icon icon="mdi:rotate-right"></ha-icon></button></h3>
      <p class="sub">Draw a rectangle to save a zone preset for this map. Saved presets stay in Home Assistant and do not use the robot's shared map-zone slots.</p>
      <div class="map-tools">
        <button class="minibtn" data-map-save-zone ${isAdmin ? "" : "disabled title=\"Only admins can save zone presets\""}><ha-icon icon="mdi:content-save-outline"></ha-icon> Draw a zone</button>
        <button class="minibtn" data-map-cancel hidden>Cancel</button>
      </div>
      ${isAdmin ? "" : `<p class="sub">Only administrators can create or change saved zones.</p>`}
      <div class="mapwrap" hidden><div class="mapstage"><img alt="Current vacuum map"><svg></svg></div></div>
      <div class="zone-presets" data-zone-presets></div>
    </div></ha-card>`;
    const save = pane.querySelector("[data-map-save-zone]");
    if (save) save.onclick = () => { this._mapAction = this._mapAction === "save_zone" ? "select" : "save_zone"; this._update(true); };
    const cancel = pane.querySelector("[data-map-cancel]");
    if (cancel) cancel.onclick = () => { this._mapAction = "select"; this._update(true); };
    const mode = this._mapAction || "select";
    if (save) save.classList.toggle("on", mode === "save_zone");
    if (cancel) cancel.hidden = mode === "select";
    pane.querySelector(".map-note").textContent = mode === "save_zone" ? "drag a rectangle on the map, then name it" : name;
    this._wireVacMap(pane, []);
    this._loadZonePresets(pane);
  }

  _paneVacuum(pane) {
    const vac = this._st(this._robot), r = this._related(this._robot);
    const st = this._st(r.status), dnd = this._dnd(r), presets = this._presets(r);
    const cam = this._st(r.camera), geom = (cam && cam.attributes.room_geometry) || [];
    const mapName = cam ? cam.attributes.map_name : null;
    const mapId = cam ? cam.attributes.map_id : null;
    if (this._selMapId !== mapId) { this._cleanSel = new Set(); this._selMapId = mapId; this._selectedZonePreset = null; }
    const state = st ? st.state : vac.state;
    pane.innerHTML = `
      <ha-card><div class="card">
        <h3><span>Vacuum</span><span class="note">${esc(state)}${mapName ? ` · map ${esc(mapName)}` : ""}</span></h3>
        ${dnd && dnd.enabled ? `<div class="drv-status live" style="margin-top:8px"><ha-icon icon="mdi:moon-waning-crescent"></ha-icon>Do Not Disturb ${esc(dnd.start)} to ${esc(dnd.end)}</div>` : ""}
        <div class="vac-ctrl">
          <button class="btn primary" data-v="start"><ha-icon icon="mdi:play"></ha-icon>Clean</button>
          <button class="btn" data-v="pause"><ha-icon icon="mdi:pause"></ha-icon>Pause</button>
          <button class="btn" data-v="stop"><ha-icon icon="mdi:stop"></ha-icon>Stop</button>
          <button class="btn" data-v="return_to_base"><ha-icon icon="mdi:home-import-outline"></ha-icon>Dock</button>
          <button class="btn" data-v="locate"><ha-icon icon="mdi:map-marker-radius"></ha-icon>Locate</button>
        </div>
        ${presets.length ? `<div class="presets">${presets.map((p) =>
          `<button class="chip btn" data-preset="${esc(p.id)}">${esc(p.name)}</button>`).join("")}</div>` : ""}
      </div></ha-card>
      <ha-card><div class="card">
        <h3><span>Map</span><span class="note map-note">${geom.length ? "tap rooms to select" : ""}</span><button class="icon-btn" data-map-rotate title="Rotate map 90°" aria-label="Rotate map 90 degrees"><ha-icon icon="mdi:rotate-right"></ha-icon></button></h3>
        <div class="map-tools">
          <button class="minibtn" data-map-goto><ha-icon icon="mdi:crosshairs-gps"></ha-icon> Go to point</button>
          <div class="zone-menu-wrap"><button class="minibtn" data-map-zone aria-haspopup="true" aria-expanded="${this._zonePickerOpen}"><ha-icon icon="mdi:vector-square"></ha-icon> Clean a zone</button>
          ${this._zonePickerOpen && (this._mapAction || "select") === "select" ? `<div class="zone-picker" role="menu">
            <strong>Clean a zone</strong>
            <div class="actions"><button class="btn" data-zone-draw role="menuitem"><ha-icon icon="mdi:draw"></ha-icon> Temporary (draw)</button></div>
            <div class="sub" style="margin-top:8px">Choose a saved zone</div>
            <div class="presets">${this._zonePresets.filter((p) => String(p.map_id) === String(mapId)).map((p) =>
              `<button class="chip btn ${this._selectedZonePreset === p.id ? "primary" : ""}" data-zone-select="${esc(p.id)}" role="menuitem">${esc(p.name)}</button>`).join("") || `<span class="sub">No saved zones for this map.</span>`}</div>
            ${this._selectedZonePreset ? `<div class="actions"><button class="btn primary" data-zone-run-selected>Clean selected zone</button></div>` : ""}
          </div>` : ""}</div>
          <button class="minibtn" data-map-cancel hidden>Cancel</button>
        </div>
        <div class="mapwrap" hidden><div class="mapstage"><img alt="Map"><svg></svg></div></div>
        ${geom.length ? `<div class="actions" style="margin-top:12px">
          <button class="btn primary" data-clean-sel disabled><ha-icon icon="mdi:play"></ha-icon><span>Clean selected</span></button>
          <button class="minibtn" data-clear-sel disabled>Clear</button></div>`
        : `<div class="empty">The vacuum has no rooms on its map yet — divide it into rooms in the Tapo app.</div>`}
      </div></ha-card>`;
    pane.querySelectorAll("[data-v]").forEach((b) => b.onclick = () => this._call("vacuum", b.dataset.v, {}, { entity_id: this._robot }));
    pane.querySelectorAll("[data-preset]").forEach((b) => b.onclick = () =>
      this._call(DOMAIN, "run_preset", { preset: b.dataset.preset }, { entity_id: this._robot }));
    const setMapAction = (mode) => { this._mapAction = mode; this._zoneDraft = null; this._zoneDragStart = null; this._zonePickerOpen = false; this._update(true); };
    pane.querySelector("[data-map-goto]").onclick = () => setMapAction(this._mapAction === "goto" ? "select" : "goto");
    pane.querySelector("[data-map-zone]").onclick = () => {
      this._mapAction = "select"; this._zonePickerOpen = !this._zonePickerOpen; this._update(true);
    };
    const drawZone = pane.querySelector("[data-zone-draw]");
    if (drawZone) drawZone.onclick = () => setMapAction("zone");
    pane.querySelectorAll("[data-zone-select]").forEach((b) => b.onclick = () => {
      this._selectedZonePreset = b.dataset.zoneSelect; this._update(true);
    });
    const runSelected = pane.querySelector("[data-zone-run-selected]");
    if (runSelected) runSelected.onclick = () => {
      this._zonePickerOpen = false;
      this._update(true);
      this._confirmZonePreset(this._selectedZonePreset);
    };
    pane.querySelector("[data-map-cancel]").onclick = () => setMapAction("select");
    const mode = this._mapAction || "select";
    pane.querySelector("[data-map-goto]").classList.toggle("on", mode === "goto");
    pane.querySelector("[data-map-zone]").classList.toggle("on", mode === "zone" || this._zonePickerOpen);
    pane.querySelector("[data-map-cancel]").hidden = mode === "select";
    pane.querySelector(".map-note").textContent = mode === "goto" ? "tap the map to drive there"
      : mode === "zone" ? "drag a rectangle on the map, then release to clean it"
      : mode === "save_zone" ? "drag a rectangle on the map, then name it to save for later"
      : geom.length ? "tap rooms to select" : "";
    this._wireVacMap(pane, geom);
    this._ensureVacZonePresets(pane, mapId);
  }

  _confirmZonePreset(id) {
    const preset = this._zonePresets.find((p) => p.id === id);
    if (!preset) return;
    const confirmed = window.confirm(`Clean saved zone “${preset.name}” now?`);
    if (!confirmed) { this._update(true); return; }
    this._call(DOMAIN, "run_zone_preset", { preset: id }, { entity_id: this._robot });
  }

  async _ensureVacZonePresets(pane, mapId) {
    const key = `${this._robot}|${mapId}`;
    if (this._zonePresetsKey === key || this._zonePresetsLoading) return;
    this._zonePresetsLoading = key;
    try {
      const res = await this._hass.callService(DOMAIN, "get_zone_presets", {}, { entity_id: this._robot }, false, true);
      if (!pane.isConnected || this._tab !== "vacuum" || key !== `${this._robot}|${mapId}`) return;
      const result = (res && res.response) ? res.response : res;
      this._zonePresets = (result && result.presets) || [];
      this._zonePresetsKey = key;
      this._update(true);
    } catch (e) { /* keep the map usable if presets cannot be loaded */ }
    finally {
      if (this._zonePresetsLoading === key) this._zonePresetsLoading = null;
      const currentMap = (this._st(this._related(this._robot).camera) || {}).attributes?.map_id;
      if (pane.isConnected && this._tab === "vacuum" && this._zonePresetsKey !== `${this._robot}|${currentMap}`) this._update(true);
    }
  }

  async _loadZonePresets(pane) {
    const box = pane.querySelector("[data-zone-presets]");
    if (!box) return;
    box.innerHTML = `<div class="sub">Loading saved zones…</div>`;
    try {
      const res = await this._hass.callService(DOMAIN, "get_zone_presets", {}, { entity_id: this._robot }, false, true);
      if (!pane.isConnected || this._tab !== "zones") return;
      const r = (res && res.response) ? res.response : res, presets = (r && r.presets) || [];
      this._zonePresets = presets;
      this._zonePresetsKey = null;
      if (!presets.length) { box.innerHTML = `<div class="sub">No saved zone presets yet. Use “Save a zone” to draw one.</div>`; return; }
      const currentMap = r.map_id;
      box.innerHTML = `<h4>Saved zone presets</h4>` + presets.map((p) => `<div class="row zone-preset">
        <span><strong>${esc(p.name)}</strong><small>${esc(p.map_name || `Map ${p.map_id}`)} · ${p.zones.length} zone${p.zones.length === 1 ? "" : "s"}</small></span>
        <span class="actions"><button class="btn primary" data-zone-run="${esc(p.id)}" ${p.map_id !== currentMap ? "disabled title=\"Switch to this map first\"" : ""}>Run</button>
        ${this._isAdmin() ? `<button class="minibtn" data-zone-rename="${esc(p.id)}">Rename</button><button class="minibtn" data-zone-delete="${esc(p.id)}">Delete</button>` : ""}</span></div>`).join("");
      box.querySelectorAll("[data-zone-run]").forEach((b) => b.onclick = () => this._call(DOMAIN, "run_zone_preset", { preset: b.dataset.zoneRun }, { entity_id: this._robot }));
      box.querySelectorAll("[data-zone-rename]").forEach((b) => b.onclick = async () => {
        const p = presets.find((x) => x.id === b.dataset.zoneRename), name = window.prompt("Rename saved zone", p && p.name);
        if (!p || !name || !name.trim()) return;
        if (await this._zonePresetCall("update_zone_preset", { preset: p.id, name: name.trim() })) { this._zonePresetsKey = null; this._loadZonePresets(pane); }
      });
      box.querySelectorAll("[data-zone-delete]").forEach((b) => b.onclick = async () => {
        const p = presets.find((x) => x.id === b.dataset.zoneDelete);
        if (!p || !window.confirm(`Delete saved zone “${p.name}”?`)) return;
        if (await this._zonePresetCall("delete_zone_preset", { preset: p.id, confirm: true })) { this._zonePresetsKey = null; this._loadZonePresets(pane); }
      });
    } catch (e) {
      if (pane.isConnected) box.innerHTML = `<div class="sub">Could not load saved zones: ${esc(e.message || e)}</div>`;
    }
  }

  async _zonePresetCall(service, data) {
    try {
      await this._hass.callService(DOMAIN, service, data, { entity_id: this._robot }, false, true);
      return true;
    } catch (e) { this._notify((e && (e.message || (e.body && e.body.message))) || "Could not update saved zone"); return false; }
  }

  async _wireVacMap(pane, geom) {
    const wrap = pane.querySelector(".mapwrap");
    if (!wrap) return;
    // Pick up a rotation set from another browser or an automation: this re-reads the Map
    // Rotation select entity's current state every time this pane is wired, not just when
    // the robot is first selected or switched.
    this._loadMapRotation(this._robot);
    const stage = wrap.querySelector(".mapstage"), img = wrap.querySelector("img"), svg = wrap.querySelector("svg");
    const rotate = pane.querySelector("[data-map-rotate]");
    if (rotate) rotate.onclick = () => {
      this._mapRotation = (this._mapRotation + 90) % 360;
      this._saveMapRotation();
      this._fitVacMap(wrap, stage, img, svg, geom, pane);
    };
    const r = this._related(this._robot);
    const imgSt = r.mapImage ? this._st(r.mapImage) : null;
    const camSt = r.camera ? this._st(r.camera) : null;
    const pic = (imgSt && imgSt.attributes.entity_picture)
      || (camSt ? `/api/camera_proxy/${r.camera}` : null);
    if (pic) {
      const url = pic.startsWith("http") ? pic : this._hass.hassUrl(pic);
      // image entity: its state is the last-updated stamp (the proxy URL's token
      // changes with it); camera fallback: the access_token attribute changes
      // when the camera re-renders. Either way the key moves with the picture.
      const key = `${url}|${imgSt ? imgSt.state : (camSt && camSt.attributes.access_token) || ""}`;
      const show = (src) => {
        img.onload = () => this._fitVacMap(wrap, stage, img, svg, geom, pane);
        img.src = src;
        if (img.complete && img.naturalWidth) this._fitVacMap(wrap, stage, img, svg, geom, pane);
      };
      if (this._mapPic === key && this._mapUrl) { show(this._mapUrl); return; }
      try {
        const res = await fetch(url, { headers: { Authorization: `Bearer ${this._hass.auth.data.access_token}` } });
        if (!res.ok) return;
        if (this._mapUrl) URL.revokeObjectURL(this._mapUrl);
        this._mapPic = key;
        this._mapUrl = URL.createObjectURL(await res.blob());
        show(this._mapUrl);
      } catch (e) { /* map image stays hidden */ }
    }
  }

  _fitVacMap(wrap, stage, img, svg, geom, pane) {
    if (!img.naturalWidth) return;
    wrap.hidden = false;
    const rotated = this._mapRotation % 180 !== 0;
    const ratio = rotated ? img.naturalHeight / img.naturalWidth : img.naturalWidth / img.naturalHeight;
    const maxH = Math.max(180, window.innerHeight * 0.58);
    const parentW = Math.max(1, wrap.parentElement.clientWidth);
    const w = Math.min(parentW, maxH * ratio), h = w / ratio;
    wrap.style.width = `${w}px`; wrap.style.height = `${h}px`; wrap.style.aspectRatio = `${ratio}`;
    const sw = rotated ? h : w, sh = rotated ? w : h;
    stage.style.width = `${sw}px`; stage.style.height = `${sh}px`;
    stage.style.transform = `translate(-50%, -50%) rotate(${this._mapRotation}deg)`;
    img.style.width = `${sw}px`; img.style.height = `${sh}px`;
    this._drawRooms(svg, geom, img, pane);
  }

  _drawRooms(svg, geom, img, pane) {
    if (!img.naturalWidth) return;
    svg.setAttribute("viewBox", `0 0 ${img.naturalWidth} ${img.naturalHeight}`);
    const mode = this._mapAction || "select";
    if ((mode === "zone" || mode === "save_zone") && this._zoneDragStart) return;   // don't cut a drag short on a periodic poll
    if (mode !== "select") {
      // Go-to-point / zone clean / save: one full-canvas hit target instead of per-room rects,
      // so a tap/drag anywhere on the map works, not just inside a room's bounding box.
      svg.innerHTML = `<rect class="hit" x="0" y="0" width="${img.naturalWidth}" height="${img.naturalHeight}"></rect>`;
      this._wireMapAction(svg, pane, mode);
      return;
    }
    const mg = (this._st(this._related(this._robot).camera) || {}).attributes?.map_geometry;
    const presets = (this._zonePresets || []).filter((p) => String(p.map_id) === String(this._selMapId));
    const zoneRects = mg ? presets.flatMap((p) => (p.zones || []).map((z) => {
      const [x1, y1, x2, y2] = z;
      const [px1, py1] = this._mmToMapPx(x1, y2, mg), [px2, py2] = this._mmToMapPx(x2, y1, mg);
      return `<rect class="zone-preset ${this._selectedZonePreset === p.id ? "sel" : ""}" data-zone-id="${esc(p.id)}" role="button" tabindex="0" aria-label="Select saved zone ${esc(p.name)}" x="${Math.min(px1, px2)}" y="${Math.min(py1, py2)}" width="${Math.max(2, Math.abs(px2-px1))}" height="${Math.max(2, Math.abs(py2-py1))}"><title>${esc(p.name)}</title></rect>`;
    })).join("") : "";
    svg.innerHTML = geom.map((g) => {
      const b = g.bbox || [0, 0, 0, 0];
      return `<rect class="room ${this._cleanSel.has(g.name) ? "sel" : ""}" data-name="${esc(g.name)}"`
        + ` role="button" tabindex="0" aria-pressed="${this._cleanSel.has(g.name)}"`
        + ` aria-label="Select room ${esc(g.name)}"`
        + ` x="${b[0]}" y="${b[1]}" width="${Math.max(2, b[2] - b[0])}" height="${Math.max(2, b[3] - b[1])}">`
        + `<title>${esc(g.name)}</title></rect>`;
    }).join("") + zoneRects;
    const toggle = (rc) => {
      const name = rc.dataset.name;
      this._cleanSel.has(name) ? this._cleanSel.delete(name) : this._cleanSel.add(name);
      rc.classList.toggle("sel", this._cleanSel.has(name));
      rc.setAttribute("aria-pressed", String(this._cleanSel.has(name)));
      const b = pane.querySelector("[data-clean-sel]"), c = pane.querySelector("[data-clear-sel]");
      if (b) { b.disabled = !this._cleanSel.size;
               b.querySelector("span").textContent = `Clean selected${this._cleanSel.size ? ` (${this._cleanSel.size})` : ""}`; }
      if (c) c.disabled = !this._cleanSel.size;
    };
    svg.querySelectorAll("rect.room").forEach((rc) => {
      rc.onclick = () => toggle(rc);
      rc.onkeydown = (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggle(rc); } };
    });
    svg.querySelectorAll("rect.zone-preset").forEach((rc) => {
      const run = () => { this._zonePickerOpen = false; this._update(true); this._confirmZonePreset(rc.dataset.zoneId); };
      rc.onclick = run;
      rc.onkeydown = (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); run(); } };
    });
    const cb = pane.querySelector("[data-clean-sel]");
    if (cb) cb.onclick = async () => {
      const rooms = [...this._cleanSel];
      if (!rooms.length) return;
      const ok = await this._call(DOMAIN, "clean_rooms", { rooms }, { entity_id: this._robot });
      if (ok) { this._cleanSel = new Set(); this._update(true); }
    };
    const cl = pane.querySelector("[data-clear-sel]");
    if (cl) cl.onclick = () => { this._cleanSel = new Set(); this._update(true); };
  }

  // A pointer event's position in the SVG's own (unrotated) viewBox space - getScreenCTM
  // composes every ancestor CSS transform, Map Rotation's included, so this lands in the
  // same unrotated image-pixel space as room_geometry/map_geometry regardless of rotation.
  _svgPoint(svg, evt) {
    const pt = svg.createSVGPoint();
    pt.x = evt.clientX; pt.y = evt.clientY;
    const loc = pt.matrixTransform(svg.getScreenCTM().inverse());
    return [loc.x, loc.y];
  }

  // Inverse of maprender.py's to_px (see map_geometry's own comment for the forward form).
  _mapPxToMm(px, py, mg) {
    const scale = mg.scale_px_per_cell || 1, res = mg.resolution_mm || 50;
    const [ox, oy] = mg.real_origin_mm || [0, 0];
    const gh = (mg.grid_size || [0, 0])[1] || 1;
    return [Math.round(ox + ((px - scale / 2) / scale) * res),
            Math.round(oy + (gh - 1 - (py - scale / 2) / scale) * res)];
  }

  _mmToMapPx(x, y, mg) {
    const scale = mg.scale_px_per_cell || 1, res = mg.resolution_mm || 50;
    const [ox, oy] = mg.real_origin_mm || [0, 0];
    const gh = (mg.grid_size || [0, 0])[1] || 1;
    return [((x - ox) / res) * scale + scale / 2,
            (gh - 1 - (y - oy) / res) * scale + scale / 2];
  }

  _paintZoneDraft(svg) {
    let r = svg.querySelector("rect.zone-draft");
    if (!this._zoneDraft) { if (r) r.remove(); return; }
    if (!r) { r = document.createElementNS("http://www.w3.org/2000/svg", "rect"); r.setAttribute("class", "zone-draft"); svg.appendChild(r); }
    const [x1, y1, x2, y2] = this._zoneDraft;
    r.setAttribute("x", x1); r.setAttribute("y", y1);
    r.setAttribute("width", Math.max(1, x2 - x1)); r.setAttribute("height", Math.max(1, y2 - y1));
  }

  _wireMapAction(svg, pane, mode) {
    const hit = svg.querySelector("rect.hit");
    const cam = this._st(this._related(this._robot).camera);
    const mg = cam && cam.attributes.map_geometry;
    if (!hit || !mg) return;
    if (mode === "goto") {
      hit.onclick = (e) => {
        const [x, y] = this._mapPxToMm(...this._svgPoint(svg, e), mg);
        this._mapAction = "select"; this._update(true);
        this._call(DOMAIN, "go_to", { x, y }, { entity_id: this._robot });
      };
      return;
    }
    // zone: drag a rectangle, release to clean or save it. A tap with no real drag is ignored,
    // rather than sending a 0x0 zone to the robot. The start point lives on `this`, not a
    // local, so _drawRooms can tell a periodic poll not to cut a drag in progress short.
    hit.onpointerdown = (e) => {
      hit.setPointerCapture(e.pointerId);
      const start = this._svgPoint(svg, e);
      this._zoneDragStart = start;
      this._zoneDraft = [start[0], start[1], start[0], start[1]];
      this._paintZoneDraft(svg);
    };
    hit.onpointermove = (e) => {
      if (!this._zoneDragStart) return;
      const [px, py] = this._svgPoint(svg, e);
      const [sx, sy] = this._zoneDragStart;
      this._zoneDraft = [Math.min(sx, px), Math.min(sy, py), Math.max(sx, px), Math.max(sy, py)];
      this._paintZoneDraft(svg);
    };
    hit.onpointerup = (e) => {
      if (!this._zoneDragStart) return;
      hit.releasePointerCapture(e.pointerId);
      this._zoneDragStart = null;
      const draft = this._zoneDraft; this._zoneDraft = null;
      if (!draft || draft[2] - draft[0] < 4 || draft[3] - draft[1] < 4) { this._paintZoneDraft(svg); return; }
      const [x1, y1] = this._mapPxToMm(draft[0], draft[1], mg), [x2, y2] = this._mapPxToMm(draft[2], draft[3], mg);
      const zones = [[Math.min(x1, x2), Math.min(y1, y2), Math.max(x1, x2), Math.max(y1, y2)]];
      this._mapAction = "select";
      if (mode === "save_zone") {
        this._update(true);
        const name = window.prompt("Name this zone preset");
        if (!name || !name.trim()) return;
        this._zonePresetCall("create_zone_preset", { name: name.trim(), zones, map_id: cam.attributes.map_id })
          .then((ok) => { if (ok) this._loadZonePresets(pane); });
      } else {
        const confirmed = window.confirm("Clean this temporary zone now?");
        // Rebuild the map pane after the modal closes, including on No. Some HA browsers
        // leave the replaced pane's map image hidden after a synchronous confirm dialog.
        this._update(true);
        if (confirmed) this._call(DOMAIN, "clean_zone", { zones }, { entity_id: this._robot });
      }
    };
    // A touch drag can still be claimed by the browser (e.g. as a page gesture) and
    // cancelled before pointerup fires; touch-action: none on the hit rect (see CSS)
    // stops that for an ordinary drag, but clear the draft here too so an interrupted
    // one never leaves the zone tool stuck "drawing" with a stale start point.
    hit.onpointercancel = () => {
      this._zoneDragStart = null; this._zoneDraft = null;
      this._paintZoneDraft(svg);
    };
  }

  // ---- schedules ----------------------------------------------------------------------
  _paneSchedules(pane) {
    const r = this._related(this._robot), list = this._schedules(r), dnd = this._dnd(r);
    if (this._editing) return this._renderEditor(pane, r);
    const rows = list.map((s) => {
      const blocked = s.blocked_by_dnd != null ? s.blocked_by_dnd : inDnd(dnd, s.time);
      const warn = blocked && dnd ? `<div class="warn"><ha-icon icon="mdi:bell-sleep"></ha-icon>Inside ${esc(dndText(dnd))}: the robot will skip it</div>` : "";
      const target = s.preset_id != null ? `Preset ${esc((this._presets(r).find((p) => p.id === s.preset_id) || {}).name || s.preset_id)}`
        : (s.rooms && s.rooms.length ? esc(s.rooms.join(", ")) : "Whole house");
      const days = (s.days || []).length === 7 ? "Daily" : (s.days || []).join(" ");
      const levels = [s.suction != null ? FAN[s.suction - 1] : null,
        s.water_level != null ? `water ${WATER[s.water_level]}` : null,
        s.clean_passes ? `${s.clean_passes}x` : null].filter(Boolean).join(", ");
      return `<div class="row ${s.enabled ? "" : "off"}">
        <button class="switch ${s.enabled ? "on" : ""}" data-toggle="${esc(s.id)}" title="${s.enabled ? "Disable" : "Enable"}"></button>
        <div class="grow"><div class="t">${esc(s.time)} · ${esc(days)}</div>
          <div class="s">${target}${levels ? " · " + esc(levels) : ""}</div>${warn}</div>
        <button class="icon-btn" data-editsc="${esc(s.id)}" title="Edit"><ha-icon icon="mdi:pencil"></ha-icon></button>
        <button class="icon-btn" data-del="${esc(s.id)}" title="Delete"><ha-icon icon="mdi:delete"></ha-icon></button>
      </div>`;
    }).join("");
    pane.innerHTML = `<ha-card><div class="card">
      <h3><span>Schedules on the robot</span><button class="btn primary" data-add><ha-icon icon="mdi:plus"></ha-icon>Add</button></h3>
      ${rows || `<div class="empty">No schedules yet. They run on the robot itself, app or not.</div>`}
    </div></ha-card>`;
    pane.querySelector("[data-add]").onclick = () => { this._editing = {}; this._update(true); };
    pane.querySelectorAll("[data-toggle]").forEach((b) => b.onclick = () => {
      const s = list.find((x) => String(x.id) === b.dataset.toggle);
      const data = { schedule_id: s.id, enabled: !s.enabled };
      if (!s.enabled && inDnd(dnd, s.time)) {
        if (!confirm(`${s.time} is inside ${dndText(dnd)}, so the robot will not run this schedule. Enable it anyway?`)) return;
        data.ignore_dnd = true;
      }
      this._call(DOMAIN, "set_schedule", data, { entity_id: this._robot });
    });
    pane.querySelectorAll("[data-editsc]").forEach((b) => b.onclick = () => {
      this._editing = { ...list.find((x) => String(x.id) === b.dataset.editsc) };
      this._update(true);
    });
    pane.querySelectorAll("[data-del]").forEach((b) => b.onclick = async () => {
      const s = list.find((x) => String(x.id) === b.dataset.del);
      if (!confirm(`Delete the ${s.time} schedule from the robot?`)) return;
      await this._call(DOMAIN, "remove_schedule", { schedule_id: s.id }, { entity_id: this._robot });
    });
  }

  _renderEditor(pane, r) {
    const s = this._editing, isNew = s.id == null;
    const rooms = this._rooms(this._robot), presets = this._presets(r), dnd = this._dnd(r);
    const state = {
      time: s.time || "09:00", days: new Set((s.days || []).map((d) => d.slice(0, 3))),
      mode: s.preset_id != null ? "preset" : (s.rooms && s.rooms.length ? "rooms" : "house"),
      rooms: new Set(s.rooms || []), preset: s.preset_id != null ? String(s.preset_id) : (presets[0] ? String(presets[0].id) : ""),
      suction: s.suction || 0, water: s.water_level == null ? -1 : s.water_level,
      passes: s.clean_passes || 0, enabled: s.enabled !== false,
    };
    const dayChips = () => DAYS.map((d) => `<button class="chip btn ${state.days.has(d) ? "on" : ""}" data-day="${d}">${d}</button>`).join("") +
      `<button class="chip btn" data-quick="daily">Daily</button><button class="chip btn" data-quick="weekdays">Weekdays</button><button class="chip btn" data-quick="weekend">Weekend</button>`;
    const roomChips = () => rooms.map((n) => `<button class="chip btn ${state.rooms.has(n) ? "on" : ""}" data-room="${esc(n)}">${esc(n)}</button>`).join("");
    pane.innerHTML = `<ha-card><div class="card form">
      <h3><span>${isNew ? "New schedule" : `Edit schedule ${esc(s.id)}`}</span></h3>
      <div><label>Start time (robot's time zone)</label><input type="time" value="${esc(state.time)}">
        <div class="warn dnd" hidden><ha-icon icon="mdi:bell-sleep"></ha-icon><span></span></div></div>
      <div><label>Days</label><div class="chips days">${dayChips()}</div></div>
      <div><label>What to clean</label><div class="seg mode">
        <button data-mode="house" class="${state.mode === "house" ? "on" : ""}">Whole house</button>
        <button data-mode="rooms" class="${state.mode === "rooms" ? "on" : ""}">Rooms</button>
        <button data-mode="preset" class="${state.mode === "preset" ? "on" : ""}" ${presets.length ? "" : "disabled"}>Preset</button></div></div>
      <div class="rooms-box" ${state.mode === "rooms" ? "" : "hidden"}><div class="chips rooms">${roomChips()}</div></div>
      <div class="preset-box" ${state.mode === "preset" ? "" : "hidden"}><select class="preset">${presets.map((p) => `<option value="${p.id}" ${String(p.id) === state.preset ? "selected" : ""}>${esc(p.name)}</option>`).join("")}</select></div>
      <div class="grid2">
        <div><label>Suction</label><select class="suction"><option value="0">Robot default</option>${FAN.map((f, i) => `<option value="${i + 1}" ${state.suction === i + 1 ? "selected" : ""}>${f}</option>`).join("")}</select></div>
        <div><label>Water</label><select class="water"><option value="-1">Robot default</option>${WATER.map((w, i) => `<option value="${i}" ${state.water === i ? "selected" : ""}>${w}</option>`).join("")}</select></div>
      </div>
      <div class="grid2">
        <div><label>Passes</label><select class="passes"><option value="0">Robot default</option>${[1, 2, 3].map((n) => `<option value="${n}" ${state.passes === n ? "selected" : ""}>${n}</option>`).join("")}</select></div>
        <div><label>Enabled</label><button class="switch enabled ${state.enabled ? "on" : ""}" style="margin-top:6px"></button></div>
      </div>
      <div class="err" hidden></div>
      <div class="actions"><button class="btn cancel">Cancel</button><button class="btn primary save"><ha-icon icon="mdi:content-save"></ha-icon>${isNew ? "Add to robot" : "Save"}</button></div>
    </div></ha-card>`;
    const q = (sel) => pane.querySelector(sel);
    const redrawDays = () => { q(".days").innerHTML = dayChips(); bindDays(); };
    const bindDays = () => {
      q(".days").querySelectorAll("[data-day]").forEach((b) => b.onclick = () => { state.days.has(b.dataset.day) ? state.days.delete(b.dataset.day) : state.days.add(b.dataset.day); redrawDays(); });
      q(".days").querySelectorAll("[data-quick]").forEach((b) => b.onclick = () => {
        const sets = { daily: DAYS, weekdays: DAYS.slice(0, 5), weekend: DAYS.slice(5) };
        state.days = new Set(sets[b.dataset.quick]); redrawDays();
      });
    };
    const dndCheck = () => {
      const w = q(".warn.dnd"), t = q("input[type=time]").value;
      const hit = dnd && dnd.enabled && inDnd(dnd, t);
      w.hidden = !hit;
      if (hit) w.querySelector("span").textContent = `${t} is inside ${dndText(dnd)}: the robot will not run it. Pick another time or change the window in Settings.`;
      return hit;
    };
    q("input[type=time]").oninput = dndCheck; dndCheck();
    bindDays();
    q(".rooms").querySelectorAll("[data-room]").forEach((b) => b.onclick = () => { const n = b.dataset.room; state.rooms.has(n) ? state.rooms.delete(n) : state.rooms.add(n); b.classList.toggle("on"); });
    q(".mode").querySelectorAll("button").forEach((b) => b.onclick = () => {
      state.mode = b.dataset.mode; q(".mode").querySelectorAll("button").forEach((o) => o.classList.toggle("on", o === b));
      q(".rooms-box").hidden = state.mode !== "rooms"; q(".preset-box").hidden = state.mode !== "preset";
    });
    q(".enabled").onclick = () => { state.enabled = !state.enabled; q(".enabled").classList.toggle("on", state.enabled); };
    q(".cancel").onclick = () => { this._editing = null; this._update(true); };
    q(".save").onclick = async () => {
      const err = q(".err"); err.hidden = true;
      const time = q("input[type=time]").value;
      if (!time) { err.textContent = "Pick a start time."; err.hidden = false; return; }
      if (!state.days.size) { err.textContent = "Pick at least one day (the robot only keeps repeating schedules)."; err.hidden = false; return; }
      if (state.mode === "rooms" && !state.rooms.size) { err.textContent = "Pick at least one room."; err.hidden = false; return; }
      const data = { time, days: [...state.days], enabled: state.enabled };
      if (state.mode === "rooms") data.rooms = [...state.rooms];
      else if (state.mode === "preset") data.preset = q(".preset").value;
      else data.rooms = [];
      const su = Number(q(".suction").value), wa = Number(q(".water").value), pa = Number(q(".passes").value);
      if (su) data.suction = FAN[su - 1];
      if (wa >= 0) data.water = WATER[wa];
      if (pa) data.passes = pa;
      if (!isNew) data.schedule_id = s.id;
      if (state.enabled && dndCheck()) {
        if (!confirm(`${time} is inside ${dndText(dnd)}. The robot will keep the schedule but never run it until the time or the window changes. Save anyway?`)) return;
        data.ignore_dnd = true;
      }
      const ok = await this._call(DOMAIN, isNew ? "add_schedule" : "set_schedule", data, { entity_id: this._robot });
      if (ok) { this._editing = null; this._update(true); }
    };
  }

  // ---- history and stats --------------------------------------------------------------
  async _paneHistory(pane) {
    pane.innerHTML = `<ha-card><div class="card"><h3><span>Statistics</span></h3><div class="empty">Loading…</div></div></ha-card>
      <ha-card><div class="card"><h3><span>Recent runs</span></h3><div class="runs"><div class="empty">Loading…</div></div></div></ha-card>`;
    if (!this._records || this._recordsFor !== this._robot) {
      try {
        const resp = await this._hass.connection.sendMessagePromise({ type: "call_service", domain: DOMAIN, service: "get_clean_records",
          service_data: { entity_id: this._robot, limit: 100 }, return_response: true });
        const body = (resp && resp.response) || {};
        this._records = { recs: body.records || [], runs: body.total_runs, area: body.total_area, minutes: body.total_minutes };
      } catch (e) { this._records = { recs: [], runs: null, area: null, minutes: null }; }
      this._recordsFor = this._robot;
    }
    if (!this._historyMeta || this._historyMetaFor !== this._robot) {
      try { this._historyMeta = await this._hass.callWS({ type: "tapo_rv30/history/list", entity_id: this._robot }); }
      catch (e) { this._historyMeta = { runs: [], usage: null }; }
      this._historyMetaFor = this._robot;
    }
    if (this._tab !== "history") return;   // the user moved on while it loaded
    const d = this._records, hm = this._historyMeta;
    const kept = new Set((hm.runs || []).filter((r) => r.kept).map((r) => r.started));
    const num = (x) => (x == null ? "–" : esc(x));
    const r = this._related(this._robot);
    const retentionId = r.selects.find((i) => i.includes("clean_map_history") && !i.includes("limit"));
    const limitId = r.numbers.find((i) => i.includes("clean_map_history_limit"));
    const retentionSt = retentionId ? this._st(retentionId) : null;
    const limitSt = limitId ? this._st(limitId) : null;
    const usage = hm.usage || {};
    pane.innerHTML = `<ha-card><div class="card">
      <h3><span>Statistics</span></h3>
      <div class="stats">
        <div class="stat"><div class="v">${num(d.runs)}</div><div class="l">cleans</div></div>
        <div class="stat"><div class="v">${num(d.area)}</div><div class="l">m² cleaned</div></div>
        <div class="stat"><div class="v">${d.minutes == null ? "–" : esc((d.minutes / 60).toFixed(1))}</div><div class="l">hours</div></div>
      </div>
      <h5>Cleans per day, last 30 days</h5><canvas class="chart"></canvas>
      <h5>Minutes per week, last 8 weeks</h5><canvas class="chart weeks"></canvas>
    </div></ha-card>
    <ha-card><div class="card"><h3><span>Clean map history</span>
      <span class="note">${num(usage.runs)} kept, ${usage.bytes != null ? Math.round(usage.bytes / 1024) : "–"} KB</span></h3>
      <div class="row"><div class="grow"><div class="t">Keep maps for</div><div class="s">Off deletes everything already kept</div></div>
        <div class="ctl"><select data-histkeep>${(retentionSt && retentionSt.attributes.options || []).map((o) =>
          `<option ${retentionSt && o === retentionSt.state ? "selected" : ""}>${esc(o)}</option>`).join("")}</select></div></div>
      <div class="row"><div class="grow"><div class="t">At most</div></div>
        <div class="ctl"><input type="number" data-histlimit min="${limitSt ? limitSt.attributes.min : 10}"
          max="${limitSt ? limitSt.attributes.max : 1000}" step="10" value="${limitSt ? esc(limitSt.state) : 200}"></div></div>
    </div></ha-card>
    <ha-card><div class="card"><h3><span>Recent runs</span></h3><div class="runs"></div></div></ha-card>`;
    if (retentionId) pane.querySelector("[data-histkeep]").onchange = (e) =>
      this._call("select", "select_option", { option: e.target.value }, { entity_id: retentionId })
        .then(() => { this._historyMeta = null; });
    if (limitId) pane.querySelector("[data-histlimit]").onchange = (e) =>
      this._call("number", "set_value", { value: Number(e.target.value) }, { entity_id: limitId })
        .then(() => { this._historyMeta = null; });
    const recs = d.recs;
    // The robot only keeps a short list of its own records; a run that was kept here but
    // has since dropped off that list (or the robot is offline) is still in hm.runs - add
    // it as its own row so it can still be viewed or forgotten, not just the live ones.
    const recIds = new Set(recs.map((x) => x.started).filter((v) => v != null));
    const archived = (hm.runs || []).filter((x) => x.kept && !recIds.has(x.started));
    const rows = [...recs, ...archived].sort((a, b) => (b.started || 0) - (a.started || 0));
    const runs = pane.querySelector(".runs");
    runs.innerHTML = rows.length ? rows.map((x) => {
      const dt = x.started ? new Date(x.started * 1000) : null;
      const when = dt ? dt.toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" }) + " " +
        dt.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" }) : "";
      const meta = [x.area != null ? `${x.area} m²` : null, x.minutes != null ? `${x.minutes} min` : null,
        START[x.start_type] || null, x.rule_name || null, x.emptied_bin ? "bin emptied" : null].filter(Boolean).join(" · ");
      const isKept = x.started != null && kept.has(x.started);
      return `<div class="row"><ha-icon icon="${x.error ? "mdi:alert-circle" : "mdi:robot-vacuum"}" style="color:${x.error ? "var(--error-color,#db4437)" : "var(--vc-accent)"}"></ha-icon>
        <div class="grow"><div class="t">${esc(when)}${isKept ? ` <span class="sub">· kept</span>` : ""}</div><div class="s">${esc(meta)}${x.error ? ` · error ${x.error}` : ""}</div></div>
        ${x.started != null ? `<button class="btn" data-history-view="${esc(x.started)}" title="View this clean's map"><ha-icon icon="mdi:eye"></ha-icon>View</button>` : ""}
        ${x.record_index != null ? `<button class="btn" data-record-map="${esc(x.record_index)}" data-started="${esc(x.started || x.record_index)}" title="Save this clean's map"><ha-icon icon="mdi:download"></ha-icon>Save map</button>` : ""}
        ${isKept ? `<button class="btn" data-history-forget="${esc(x.started)}" title="Forget the kept map"><ha-icon icon="mdi:delete-outline"></ha-icon>Forget</button>` : ""}</div>`;
    }).join("") : `<div class="empty">No runs recorded yet.</div>`;
    runs.querySelectorAll("[data-history-view]").forEach((b) => b.onclick = () => this._historyView(Number(b.dataset.historyView)));
    runs.querySelectorAll("[data-history-forget]").forEach((b) => b.onclick = () => this._historyForget(Number(b.dataset.historyForget), pane));
    runs.querySelectorAll("[data-record-map]").forEach((b) => b.onclick = () => this._downloadRecordMap(b));
    if (this._chartObserver) this._chartObserver.disconnect();
    const redraw = () => {
      if (this._tab !== "history" || !pane.isConnected) return;
      this._chart(pane.querySelector("canvas.chart"), this._perDay(recs, 30), (i) => (i % 7 === 0 ? `${29 - i}d` : ""));
      this._chart(pane.querySelector("canvas.weeks"), this._perWeek(recs, 8), (i) => (i === 7 ? "this wk" : `-${7 - i}`));
    };
    this._chartObserver = new ResizeObserver(redraw);
    pane.querySelectorAll("canvas.chart").forEach((canvas) => this._chartObserver.observe(canvas));
    requestAnimationFrame(redraw);
  }

  async _downloadRecordMap(button) {
    button.disabled = true;
    try {
      const url = this._hass.hassUrl(`/api/${DOMAIN}/${encodeURIComponent(this._robot)}/clean/${encodeURIComponent(button.dataset.recordMap)}`);
      const res = await fetch(url, { headers: { Authorization: `Bearer ${this._hass.auth.data.access_token}` } });
      if (!res.ok) throw new Error(`Map request failed (${res.status})`);
      const href = URL.createObjectURL(await res.blob()), link = document.createElement("a");
      link.href = href; link.download = `tapo-clean-${button.dataset.started}.png`;
      document.body.appendChild(link); link.click(); link.remove();
      setTimeout(() => URL.revokeObjectURL(href), 1000);
    } catch (err) { this._notify((err && err.message) || "Could not save this clean's map"); }
    finally { button.disabled = false; }
  }

  async _historyView(started) {
    this._loadMapRotation(this._robot);   // the Map Rotation setting applies here too
    const box = document.createElement("div");
    box.className = "lightbox";
    box.innerHTML = `<div class="lb-wrap"><div class="lb-stage"><img alt="clean map"></div></div><div class="lb-info">Loading map...</div>`;
    box.onclick = (e) => { if (e.target === box) box.remove(); };
    this.shadowRoot.appendChild(box);
    const img = box.querySelector("img");
    img.onload = () => this._fitRotatedPreview(box.querySelector(".lb-wrap"), box.querySelector(".lb-stage"), img);
    try {
      const res = await this._hass.callWS({ type: "tapo_rv30/history/image", entity_id: this._robot, started });
      img.src = res.image;
      box.querySelector(".lb-info").textContent = new Date(started * 1000).toLocaleString();
    } catch (e) {
      box.querySelector(".lb-info").textContent = "Could not load this clean's map: " + ((e && e.message) || e);
    }
  }

  // Fit an image rotated by this._mapRotation into its final on-screen box: `wrap` gets the
  // correct-aspect-ratio box (honouring a max size), `stage` is sized pre-rotation (swapped
  // for 90/270) and centred on it, exactly like the vacuum tab's own map view.
  _fitRotatedPreview(wrap, stage, img) {
    if (!img.naturalWidth) return;
    const rot = this._mapRotation || 0, rotated = rot % 180 !== 0;
    const maxW = window.innerWidth * 0.84, maxH = window.innerHeight * 0.7;
    const ratio = rotated ? img.naturalHeight / img.naturalWidth : img.naturalWidth / img.naturalHeight;
    const boxW = Math.min(maxW, maxH * ratio), boxH = boxW / ratio;
    wrap.style.width = `${boxW}px`; wrap.style.height = `${boxH}px`;
    const sw = rotated ? boxH : boxW, sh = rotated ? boxW : boxH;
    stage.style.width = `${sw}px`; stage.style.height = `${sh}px`;
    stage.style.transform = `translate(-50%, -50%) rotate(${rot}deg)`;
  }

  async _historyForget(started, pane) {
    if (!window.confirm("Forget this clean's kept map? It stays listed, but its map is read from the robot again next time (if it still has it).")) return;
    try {
      await this._hass.callWS({ type: "tapo_rv30/history/delete", entity_id: this._robot, started });
      this._historyMeta = null;
      if (this._tab === "history") this._paneHistory(pane);
    } catch (e) { this._notify((e && e.message) || "Could not forget this clean's map"); }
  }

  _perDay(recs, n) {
    const out = new Array(n).fill(0), now = Math.floor(Date.now() / 86400000);
    for (const x of recs) { if (!x.started) continue; const d = now - Math.floor(x.started / 86400); if (d >= 0 && d < n) out[n - 1 - d] += 1; }
    return out;
  }
  _perWeek(recs, n) {
    const out = new Array(n).fill(0), now = Math.floor(Date.now() / 604800000);
    for (const x of recs) { if (!x.started) continue; const w = now - Math.floor(x.started / 604800); if (w >= 0 && w < n) out[n - 1 - w] += x.minutes || 0; }
    return out;
  }
  _chart(canvas, values, label) {
    if (!canvas) return;
    const dpr = window.devicePixelRatio || 1, W = Math.max(1, canvas.getBoundingClientRect().width), H = Math.max(1, canvas.getBoundingClientRect().height);
    canvas.width = W * dpr; canvas.height = H * dpr;
    const ctx = canvas.getContext("2d"); ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const cs = getComputedStyle(this);
    const primary = cs.getPropertyValue("--vc-accent").trim() || cs.getPropertyValue("--primary-color").trim() || "#34e0d6";
    const text = cs.getPropertyValue("--secondary-text-color").trim() || "#888";
    const max = Math.max(1, ...values), n = values.length, gap = 3, bw = (W - gap * (n - 1)) / n, base = H - 18;
    ctx.font = "11px sans-serif"; ctx.textAlign = "center";
    values.forEach((v, i) => {
      const h = Math.round((base - 14) * v / max), x = i * (bw + gap);
      ctx.fillStyle = v ? primary : text; ctx.globalAlpha = v ? 1 : .18;
      ctx.beginPath(); ctx.roundRect(x, base - Math.max(h, 2), bw, Math.max(h, 2), 2); ctx.fill(); ctx.globalAlpha = 1;
      if (v) { ctx.fillStyle = text; ctx.fillText(String(v), x + bw / 2, base - h - 3); }
      const l = label(i); if (l) { ctx.fillStyle = text; ctx.fillText(l, x + bw / 2, H - 4); }
    });
  }

  // ---- rooms and freshness ------------------------------------------------------------
  _paneRooms(pane) {
    const r = this._related(this._robot), cam = this._st(r.camera), geom = (cam && cam.attributes.room_geometry) || [];
    const fresh = (cam && cam.attributes.rooms_last_cleaned) || {};
    const rows = geom.map((g) => {
      const f = fresh[g.name] || {}, cov = f.coverage || 0, d = f.last_cleaned ? (Date.now() / 1000 - f.last_cleaned) / 86400 : null;
      const cls = d == null ? "bad" : d > 7 ? "warn" : "";
      return `<div class="bar-row ${cls}"><span>${esc(g.name)}</span><div class="track"><div style="width:${cov}%"></div></div><span class="r">${esc(ago(f.last_cleaned))}</span></div>
        <div class="actions" style="justify-content:flex-start;margin:-2px 0 6px"><button class="btn" data-room="${esc(g.name)}"><ha-icon icon="mdi:play"></ha-icon>Clean ${esc(g.name)}</button>
        <span class="sub" style="align-self:center">${f.coverage != null ? `${f.coverage}% covered last time` : "not cleaned since the map was made"}${g.suction ? ` · ${FAN[g.suction - 1]}` : ""}${g.passes ? ` · ${g.passes}x` : ""}</span></div>`;
    }).join("");
    pane.innerHTML = `<ha-card><div class="card"><h3><span>Rooms and freshness</span></h3>${rows || `<div class="empty">No rooms on the current map.</div>`}</div></ha-card>`;
    pane.querySelectorAll("[data-room]").forEach((b) => b.onclick = () => this._call(DOMAIN, "clean_rooms", { rooms: [b.dataset.room] }, { entity_id: this._robot }));
  }

  // ---- drive (the app's remote control) ------------------------------------------------
  _paneDrive(pane) {
    const r = this._related(this._robot), vac = this._st(this._robot), st = this._st(r.status);
    const supported = vac.attributes.remote_control !== false;
    const text = st ? st.state : vac.state, remote = text === "Remote Control";
    const sweep = r.switches.find((id) => /sweep_walk|clean_while/.test(id)), sw = sweep ? this._st(sweep) : null;
    if (!pane.querySelector(".dpad")) {
      if (!supported) { pane.innerHTML = `<ha-card><div class="card"><div class="empty">This robot has no remote control.</div></div></ha-card>`; return; }
      pane.innerHTML = `<ha-card><div class="card" tabindex="0">
        <h3><span>Drive</span><span class="actions"><button class="btn primary take"><ha-icon icon="mdi:gamepad-variant"></ha-icon>Take control</button><button class="btn give" hidden><ha-icon icon="mdi:hand-back-left"></ha-icon>Hand back</button></span></h3>
        <div class="drv-status"><ha-icon icon="mdi:robot-vacuum"></ha-icon><span></span></div>
        <div class="dpad" aria-disabled="true">
          <span></span><button data-dir="forward" title="Forward (up arrow)"><ha-icon icon="mdi:arrow-up-bold"></ha-icon></button><span></span>
          <button data-dir="left" title="Turn left (left arrow)"><ha-icon icon="mdi:arrow-left-bold"></ha-icon></button>
          <button class="halt" data-dir="stop" title="Stop (space)"><ha-icon icon="mdi:stop"></ha-icon></button>
          <button data-dir="right" title="Turn right (right arrow)"><ha-icon icon="mdi:arrow-right-bold"></ha-icon></button>
          <span></span><button data-dir="backward" title="Backward (down arrow)"><ha-icon icon="mdi:arrow-down-bold"></ha-icon></button><span></span>
        </div>
        <div class="actions" style="justify-content:center">
          ${sweep ? `<button class="btn sweep"><ha-icon icon="mdi:broom"></ha-icon><span>Vacuum while driving</span></button>` : ""}
          <button class="btn spot"><ha-icon icon="mdi:target"></ha-icon>Spot clean here</button>
          <button class="btn locate"><ha-icon icon="mdi:map-marker-radius"></ha-icon>Locate</button>
          <button class="btn dock"><ha-icon icon="mdi:home-import-outline"></ha-icon>Send home</button>
        </div>
        <p class="sub" style="margin:10px 0 0">Take control and the robot drives off the dock. It moves while you hold a button or an arrow key and stops when you let go. Hand back control, or send it home, when you are done.</p>
      </div></ha-card>`;
      const q = (s) => pane.querySelector(s), dpad = q(".dpad");
      const send = (command, wantResponse) => wantResponse
        ? this._hass.callService(DOMAIN, "remote_drive", { command }, { entity_id: this._robot }, true)
        : this._hass.callService(DOMAIN, "remote_drive", { command }, { entity_id: this._robot });
      const fail = (e) => this._notify((e && (e.message || (e.body && e.body.message))) || "The robot rejected that");
      let held = null;
      const paint = () => dpad.querySelectorAll("[data-dir]").forEach((b) => b.classList.toggle("held", b.dataset.dir === held));
      const loop = async (dir) => {
        // like the app: send, wait for the answer, pause 300 ms, repeat while still held
        while (held === dir) {
          try { await send(dir); } catch (e) { held = null; paint(); fail(e); return; }
          await new Promise((res) => setTimeout(res, 300));
        }
      };
      const start = (dir) => { if (dpad.getAttribute("aria-disabled") === "true" || held === dir) return; held = dir; paint(); loop(dir); };
      const stop = () => { if (held == null) return; held = null; paint(); send("stop").catch(fail); };
      dpad.querySelectorAll("[data-dir]").forEach((b) => {
        if (b.dataset.dir === "stop") { b.onclick = () => { held = null; paint(); send("stop").catch(fail); }; return; }
        b.onpointerdown = (e) => { e.preventDefault(); b.setPointerCapture(e.pointerId); start(b.dataset.dir); };
        b.onpointerup = b.onpointercancel = b.onlostpointercapture = () => stop();
        b.oncontextmenu = (e) => e.preventDefault();
      });
      const keys = { ArrowUp: "forward", ArrowDown: "backward", ArrowLeft: "left", ArrowRight: "right" };
      q(".card").onkeydown = (e) => { if (e.repeat) return; if (keys[e.key]) { e.preventDefault(); start(keys[e.key]); } else if (e.key === " ") { e.preventDefault(); stop(); } };
      q(".card").onkeyup = (e) => { if (keys[e.key] && held === keys[e.key]) stop(); };
      window.addEventListener("blur", stop);
      this._stopDrive = stop;
      q(".take").onclick = async () => {
        try {
          const res = await send("enter", true);
          const ms = (res && res.response && res.response.leaving_dock_ms) || 4000;
          this._entered = true; dpad.setAttribute("aria-disabled", "false"); q(".take").hidden = true; q(".give").hidden = false;
          q(".drv-status").classList.add("live");
          q(".drv-status span").textContent = "Remote control: leaving the dock";
          this._notify(`You have the controls. Give it ${Math.round(ms / 1000)} s to leave the dock.`);
        } catch (e) { fail(e); }
      };
      q(".give").onclick = () => { stop(); this._entered = false; send("exit").catch(fail); };
      q(".spot").onclick = () => { stop(); this._call("vacuum", "clean_spot", {}, { entity_id: this._robot }); };
      q(".locate").onclick = () => this._call("vacuum", "locate", {}, { entity_id: this._robot });
      q(".dock").onclick = async () => { stop(); this._entered = false; try { await send("exit"); } catch (e) { /* not in control */ } this._call("vacuum", "return_to_base", {}, { entity_id: this._robot }); };
      if (sweep) q(".sweep").onclick = () => this._call("switch", (this._st(sweep).state === "on") ? "turn_off" : "turn_on", {}, { entity_id: sweep });
    }
    const live = remote || !!this._entered;
    const s = pane.querySelector(".drv-status");
    s.classList.toggle("live", live);
    s.querySelector("span").textContent = !live ? `Robot is ${String(text).toLowerCase()}. Take control to drive it.`
      : remote ? "You have the controls. Hold an arrow to drive." : `Remote control requested, robot reports ${String(text).toLowerCase()}`;
    pane.querySelector(".dpad").setAttribute("aria-disabled", live ? "false" : "true");
    pane.querySelector(".take").hidden = live; pane.querySelector(".give").hidden = !live;
    if (sw) { const b = pane.querySelector(".sweep"); b.classList.toggle("primary", sw.state === "on"); b.querySelector("span").textContent = sw.state === "on" ? "Vacuuming while driving" : "Vacuum while driving"; }
  }

  // ---- maintenance --------------------------------------------------------------------
  _paneEdit(pane) {
    // Carpets and room renaming are read-only for now: carpet writes do not persist
    // standalone, and setAreaInfo "room" can disturb room geometry; both pending safe testing.
    const tools = [["select", "mdi:cursor-move", "Select"], ["forbid", "mdi:cancel", "No-go"],
      ["virtual_wall", "mdi:wall", "Wall"], ["furniture", "mdi:sofa", "Furniture"]];
    pane.innerHTML = `<ha-card><div class="card">
      <div class="etools">${tools.map(([k, i, l]) => `<button class="btn etool" data-tool="${k}"><ha-icon icon="${i}"></ha-icon>${l}</button>`).join("")}
        <select class="efurn" title="Furniture type"></select>
        <button class="btn edel" title="Delete selected"><ha-icon icon="mdi:delete"></ha-icon></button></div>
      <div class="ehint">Pick a tool, then draw on the map. Select a wall and drag either endpoint to change its length; select furniture and drag its round handle to rotate it. Changes are saved to the robot only when you press Save.${this._isAdmin() ? "" : " Only an administrator can save map changes."}</div>
      <div class="estage"><canvas class="ecanvas"></canvas></div>
      <div class="erooms"></div>
      <div class="ebtns">
        <button class="btn eundo"><ha-icon icon="mdi:undo"></ha-icon>Undo</button>
        <button class="btn ecancel"><ha-icon icon="mdi:refresh"></ha-icon>Discard</button>
        <button class="btn primary esave"><ha-icon icon="mdi:content-save"></ha-icon>Save to robot</button>
      </div>
      <div class="s estatus"></div>
    </div></ha-card>`;
    const q = (s) => pane.querySelector(s);
    this._editEl = { canvas: q(".ecanvas"), rooms: q(".erooms"), status: q(".estatus"), furn: q(".efurn") };
    this._edit = { tool: "select", sel: null, areas: null, furniture: [], rooms: [], undo: [], img: null, geom: null, mapId: null };
    this._editFurnTypes(null);
    pane.querySelectorAll(".etool").forEach((b) => b.onclick = () => {
      this._edit.tool = b.dataset.tool; this._edit.sel = null;
      pane.querySelectorAll(".etool").forEach((x) => x.classList.toggle("on", x === b)); this._editDraw();
    });
    q(".etool").classList.add("on");
    q(".edel").onclick = () => this._editDelete();
    q(".eundo").onclick = () => this._editUndo();
    q(".ecancel").onclick = () => this._editLoad();
    q(".esave").onclick = () => this._editSave();
    if (!this._isAdmin()) { q(".esave").disabled = true; q(".esave").title = "Only an administrator can save map changes"; }
    const c = this._editEl.canvas;
    c.onpointerdown = (e) => this._editDown(e);
    c.onpointermove = (e) => this._editMove(e);
    c.onpointerup = (e) => this._editUp(e);
    // With the pointer captured, a drag released outside the canvas still ends in _editUp; a
    // cancelled pointer (or a capture lost any other way) drops the drag instead of leaving it open.
    c.onpointercancel = c.onlostpointercapture = () => this._editCancel();
    this._editLoad();
  }

  // The type list and names from the edit_get reply ({"<code>": "<label>"}), else the built-in list.
  _editFurnTypes(types) {
    const list = types && typeof types === "object" && Object.keys(types).length
      ? Object.entries(types).map(([c, n]) => [Number(c), String(n)]).filter(([c]) => Number.isInteger(c)) : FURN_FALLBACK;
    this._furnNames = Object.fromEntries(list);
    const sel = this._editEl && this._editEl.furn; if (!sel) return;
    const was = sel.value;
    sel.innerHTML = list.map(([c, n]) => `<option value="${c}">${esc(n)}</option>`).join("");
    if (list.some(([c]) => String(c) === was)) sel.value = was;
  }

  _editGeom() { return this._edit.geom; }
  // Map cell (gx, gy) covers ox + gx * res to ox + (gx + 1) * res (the robot rounds mm down into
  // cells), so ox, oy is a cell corner: the bottom left corner of the picture.
  _editMm2Px(x, y) { const g = this._edit.geom, s = g.scale_px_per_cell, r = g.resolution_mm, [ox, oy] = g.real_origin_mm, gh = g.grid_size[1]; return [((x - ox) / r) * s, (gh - (y - oy) / r) * s]; }
  _editPx2Mm(x, y) { const g = this._edit.geom, s = g.scale_px_per_cell, r = g.resolution_mm, [ox, oy] = g.real_origin_mm, gh = g.grid_size[1]; return [Math.round(ox + (x / s) * r), Math.round(oy + (gh - y / s) * r)]; }
  // The canvas buffer itself is drawn rotated (see _editDraw); a pointer event lands in that
  // rotated buffer space, so it is rotated back to the map's own (unrotated) pixel space
  // here, once, before anything downstream - _editMm2Px/_editPx2Mm and all the hit-testing
  // that compares against them - ever sees it.
  _editPoint(e) {
    const c = this._editEl.canvas, b = c.getBoundingClientRect(), clamp = (v, max) => Math.max(0, Math.min(max, v));
    const bx = clamp((e.clientX - b.left) / b.width * c.width, c.width);
    const by = clamp((e.clientY - b.top) / b.height * c.height, c.height);
    const rot = ((this._mapRotation || 0) * Math.PI) / 180;
    if (!rot || !this._edit.img) return [bx, by];
    const W = this._edit.img.naturalWidth, H = this._edit.img.naturalHeight;
    const u = bx - c.width / 2, v = by - c.height / 2, cos = Math.cos(rot), sin = Math.sin(rot);
    return [W / 2 + u * cos + v * sin, H / 2 - u * sin + v * cos];
  }

  async _editLoad() {
    this._loadMapRotation(this._robot);   // the Map Rotation setting applies to the editor too
    const r = this._related(this._robot), cam = this._st(r.camera);
    const geom = cam && cam.attributes.map_geometry, src = cam && cam.attributes.entity_picture;
    const tok = this._editTok = {}, el = this._editEl;    // a newer load (or pane) wins
    el.status.textContent = "Loading map...";
    if (!geom || !src) { el.status.textContent = "No map available yet."; return; }
    let res;
    try { res = await this._hass.callWS({ type: "tapo_rv30/map/edit_get", entity_id: this._robot }); }
    catch (err) { if (this._editTok === tok) el.status.textContent = "Could not read the map: " + (err.message || err); return; }
    if (this._editTok !== tok) return;
    const img = new Image();
    img.onerror = () => { if (this._editTok === tok) el.status.textContent = "Could not load the map picture."; };
    img.onload = () => {
      if (this._editTok !== tok) return;
      this._edit.img = img; this._edit.geom = geom; this._edit.mapId = res.map_id;
      this._edit.areas = res.areas || {}; this._edit.furniture = res.furniture || []; this._edit.rooms = res.rooms || [];
      this._edit.originalAreas = JSON.parse(JSON.stringify(this._edit.areas));
      this._edit.originalFurniture = JSON.parse(JSON.stringify(this._edit.furniture));
      this._edit.originalRooms = JSON.parse(JSON.stringify(this._edit.rooms));
      this._editFurnTypes(res.furniture_types);
      this._edit.sel = null; this._edit.undo = [];
      this._editApplyRotation();   // sizes the canvas for the current rotation, then draws
      this._editRenderRooms();
      this._editEl.status.textContent = "";
    };
    img.src = src.startsWith("http") ? src : this._hass.hassUrl(src);
  }

  // Resize the canvas buffer for the current this._mapRotation (swapped for 90/270) and
  // redraw - called after a fresh load, and whenever the Map Rotation setting changes while
  // the editor stays open, without touching the in-progress areas/furniture/rooms/undo.
  _editApplyRotation() {
    if (!this._edit || !this._edit.img) return;
    const c = this._editEl.canvas, img = this._edit.img, swapped = (this._mapRotation || 0) % 180 !== 0;
    c.width = swapped ? img.naturalHeight : img.naturalWidth;
    c.height = swapped ? img.naturalWidth : img.naturalHeight;
    this._editDraw();
  }

  _editRenderRooms() {
    const el = this._editEl.rooms;
    if (!this._edit.rooms.length) { el.innerHTML = ""; return; }
    const admin = this._isAdmin();
    el.innerHTML = `<h5>Rooms</h5>` + this._edit.rooms.map((rm, i) =>
      `<div class="row"><div class="main"><input class="room-name" type="text" data-room-i="${i}" ` +
      `value="${esc(rm.name || ("Room " + rm.id))}" placeholder="Room ${rm.id}" ${admin ? "" : "disabled"}></div></div>`).join("") +
      `<div class="ehint">Carpets are view-only for now.</div>`;
    if (!admin) return;
    el.querySelectorAll(".room-name").forEach((inp) => {
      inp.addEventListener("focus", () => {
        if (this._edit.renamingRoom) return;
        this._edit.renamingRoom = true;
        this._editSnapshot();
      });
      inp.addEventListener("blur", () => { this._edit.renamingRoom = false; });
      inp.addEventListener("input", () => {
        const i = Number(inp.dataset.roomI);
        this._edit.rooms[i] = { ...this._edit.rooms[i], name: inp.value };
      });
    });
  }

  _editDraw() {
    const c = this._editEl.canvas, ctx = c.getContext("2d"); if (!this._edit.img) return;
    ctx.save();
    ctx.clearRect(0, 0, c.width, c.height);
    // Rotate the whole canvas space by the Map Rotation setting: the map image and every
    // overlay below (all drawn from _editMm2Px, in the map's own unrotated pixel space)
    // come out rotated together, like the vacuum tab's own map view.
    ctx.translate(c.width / 2, c.height / 2);
    ctx.rotate(((this._mapRotation || 0) * Math.PI) / 180);
    ctx.translate(-this._edit.img.naturalWidth / 2, -this._edit.img.naturalHeight / 2);
    ctx.drawImage(this._edit.img, 0, 0);
    const poly = (verts) => { ctx.beginPath(); verts.forEach((p, i) => { const [x, y] = this._editMm2Px(p[0], p[1]); i ? ctx.lineTo(x, y) : ctx.moveTo(x, y); }); };
    const styles = { forbid: ["rgba(219,68,55,.22)", "rgba(219,68,55,.95)"], carpet_rectangle: ["rgba(186,140,90,.30)", "rgba(150,100,55,.95)"], carpet_round: ["rgba(186,140,90,.30)", "rgba(150,100,55,.95)"] };
    for (const [i, f] of (this._edit.furniture || []).entries()) {
      // The robot bakes the furniture picture into the map render, which only refreshes on
      // Save. Shade and label the box so the furniture reads as moved straight away; drawn
      // first and see-through, so no-go zones and walls on top of it stay visible.
      poly(f.vertexs); ctx.closePath(); ctx.fillStyle = "rgba(60,90,150,.35)"; ctx.fill();
      ctx.strokeStyle = "rgba(230,238,250,.95)"; ctx.lineWidth = this._editSelMatch("furniture", i) ? 4 : 2; ctx.stroke();
      const cx = f.vertexs.reduce((s, p) => s + p[0], 0) / f.vertexs.length, cy = f.vertexs.reduce((s, p) => s + p[1], 0) / f.vertexs.length;
      const [px, py] = this._editMm2Px(cx, cy);
      // Counter-rotate just the label around its own point, so it reads upright on screen
      // even though the canvas underneath it is rotated by the Map Rotation setting.
      ctx.save(); ctx.translate(px, py); ctx.rotate(-((this._mapRotation || 0) * Math.PI) / 180); ctx.translate(-px, -py);
      ctx.fillStyle = "#fff"; ctx.strokeStyle = "rgba(0,0,0,.6)"; ctx.lineWidth = 3; ctx.font = "11px system-ui, sans-serif"; ctx.textAlign = "center"; ctx.textBaseline = "middle";
      const name = this._furnNames?.[f.type] || "Furniture"; ctx.strokeText(name, px, py); ctx.fillText(name, px, py);
      ctx.restore();
    }
    for (const t of ["forbid", "carpet_rectangle", "carpet_round"]) for (const [i, a] of (this._edit.areas[t] || []).entries()) {
      poly(a.vertexs); ctx.closePath(); ctx.fillStyle = styles[t][0]; ctx.fill();
      ctx.strokeStyle = styles[t][1]; ctx.lineWidth = this._editSelMatch(t, i) ? 4 : 2; ctx.setLineDash(t === "forbid" ? [] : [6, 4]); ctx.stroke(); ctx.setLineDash([]);
    }
    for (const [i, a] of (this._edit.areas.virtual_wall || []).entries()) {
      poly(a.vertexs); ctx.strokeStyle = "rgba(150,70,210,.95)"; ctx.lineWidth = this._editSelMatch("virtual_wall", i) ? 6 : 4; ctx.stroke();
    }
    const r = this._editHandleR() / 2;
    for (const hd of this._editHandles()) {
      ctx.fillStyle = "#fff"; ctx.strokeStyle = "rgba(40,110,220,.95)"; ctx.lineWidth = 2;
      if (hd.kind === "rotate") { ctx.beginPath(); ctx.arc(hd.point[0], hd.point[1], r, 0, 2 * Math.PI); ctx.fill(); ctx.stroke(); }
      else { ctx.fillRect(hd.point[0] - r, hd.point[1] - r, 2 * r, 2 * r); ctx.strokeRect(hd.point[0] - r, hd.point[1] - r, 2 * r, 2 * r); }
    }
    if (this._edit.drag) { const d = this._edit.drag; ctx.strokeStyle = "rgba(40,110,220,.95)"; ctx.lineWidth = 2; ctx.setLineDash([5, 4]); if (d.line) { ctx.beginPath(); ctx.moveTo(d.x0, d.y0); ctx.lineTo(d.x1, d.y1); ctx.stroke(); } else { ctx.strokeRect(Math.min(d.x0, d.x1), Math.min(d.y0, d.y1), Math.abs(d.x1 - d.x0), Math.abs(d.y1 - d.y0)); } ctx.setLineDash([]); }
    ctx.restore();
  }

  _editSelMatch(kind, i) { const s = this._edit.sel; return s && s.kind === kind && s.i === i; }
  _editSnapshot() { this._edit.undo.push(JSON.stringify({ areas: this._edit.areas, furniture: this._edit.furniture, rooms: this._edit.rooms })); if (this._edit.undo.length > 30) this._edit.undo.shift(); }

  _editReady() { return !!(this._edit && this._edit.img && this._edit.geom && this._edit.areas); }
  _editDown(e) {
    if (!this._editReady() || this._edit.saving || (this._edit.pointerId != null && this._edit.pointerId !== e.pointerId)) return;
    this._edit.pointerId = e.pointerId;
    try { this._editEl.canvas.setPointerCapture(e.pointerId); } catch (err) { /* the pointer is already gone */ }
    const [x, y] = this._editPoint(e); const t = this._edit.tool;
    if (t === "select") {
      // Selected furniture and virtual-wall handles can be dragged to resize them; furniture
      // also gets a round handle to rotate it freely around its own centre.
      const hd = this._editHandles().find((h) => Math.hypot(x - h.point[0], y - h.point[1]) <= this._editHandleR());
      if (hd && hd.kind === "resize") { this._edit.resizing = { vertex: hd.vertex }; return; }
      if (hd && hd.kind === "rotate") {
        const it = this._editSelItem(); if (!it) return;
        const cx = it.vertexs.reduce((s, p) => s + p[0], 0) / it.vertexs.length;
        const cy = it.vertexs.reduce((s, p) => s + p[1], 0) / it.vertexs.length;
        const [mx, my] = this._editPx2Mm(x, y);
        this._edit.rotating = { center: [cx, cy], startVertexs: it.vertexs.map((p) => [...p]),
                                startAngle: Number(it.angle) || 0, startPointerAngle: Math.atan2(my - cy, mx - cx) };
        return;
      }
      this._edit.sel = this._editHit(x, y); if (this._edit.sel) this._edit.moveFrom = this._editPx2Mm(x, y); this._editDraw(); return;
    }
    if (t === "furniture") {
      this._editSnapshot(); const [mx, my] = this._editPx2Mm(x, y); const type = Number(this._editEl.furn.value);
      const [w, d] = FURN_SIZE[type] || [700, 500], hw = w / 2, hh = d / 2;
      // A fresh id: the robot keys furniture by id, so a second id 0 would clash with the first.
      const id = Math.max(-1, ...this._edit.furniture.map((f) => Number(f.id)).filter(Number.isFinite)) + 1;
      this._edit.furniture.push({ type, id, angle: 0, vertexs: mmBox(mx - hw, my + hh, mx + hw, my - hh) });
      this._edit.sel = { kind: "furniture", i: this._edit.furniture.length - 1 }; this._editDraw(); return;
    }
    this._edit.drag = { x0: x, y0: y, x1: x, y1: y, line: t === "virtual_wall" };
  }
  _editMove(e) {
    if (!this._editReady()) return;
    const [x, y] = this._editPoint(e);
    if (this._edit.drag) { this._edit.drag.x1 = x; this._edit.drag.y1 = y; this._editDraw(); return; }
    if (this._edit.resizing && (e.buttons & 1)) {
      const it = this._editSelItem(); if (!it) return;
      if (!this._edit.moving) { this._editSnapshot(); this._edit.moving = true; }
      const [mx, my] = this._editPx2Mm(x, y);
      if (this._edit.sel.kind === "virtual_wall") it.vertexs[this._edit.resizing.vertex] = [mx, my];
      else {
        const l = Math.min(...it.vertexs.map((p) => p[0])), t = Math.max(...it.vertexs.map((p) => p[1]));
        it.vertexs = mmBox(l, t, Math.max(mx, l + FURN_MIN), Math.min(my, t - FURN_MIN));
      }
      this._editDraw(); return;
    }
    if (this._edit.rotating && (e.buttons & 1)) {
      const it = this._editSelItem(); if (!it) return;
      if (!this._edit.moving) { this._editSnapshot(); this._edit.moving = true; }
      const { center, startVertexs, startAngle, startPointerAngle } = this._edit.rotating;
      const [mx, my] = this._editPx2Mm(x, y);
      const deltaRad = Math.atan2(my - center[1], mx - center[0]) - startPointerAngle;
      const cos = Math.cos(deltaRad), sin = Math.sin(deltaRad);
      it.vertexs = startVertexs.map(([px, py]) => {
        const dx = px - center[0], dy = py - center[1];
        return [center[0] + dx * cos - dy * sin, center[1] + dx * sin + dy * cos];
      });
      it.angle = Math.round((((startAngle + (deltaRad * 180) / Math.PI) % 360) + 360) % 360);
      this._editDraw(); return;
    }
    if (this._edit.tool === "select" && this._edit.sel && this._edit.moveFrom && (e.buttons & 1)) {
      const [mx, my] = this._editPx2Mm(x, y); const dx = mx - this._edit.moveFrom[0], dy = my - this._edit.moveFrom[1];
      if (!this._edit.moving) { this._editSnapshot(); this._edit.moving = true; }
      this._edit.moveFrom = [mx, my]; const it = this._editSelItem(); if (it) it.vertexs = it.vertexs.map(([a, b]) => [a + dx, b + dy]); this._editDraw();
    }
  }
  _editUp(e) {
    if (this._edit.pointerId != null && this._edit.pointerId !== e.pointerId) return;
    this._edit.pointerId = null;
    this._edit.moving = false; this._edit.moveFrom = null; this._edit.resizing = false; this._edit.rotating = null;
    if (!this._editReady()) { this._edit.drag = null; return; }
    const d = this._edit.drag; if (!d) return; this._edit.drag = null;
    const moved = Math.hypot(d.x1 - d.x0, d.y1 - d.y0); if (moved < 6) { this._editDraw(); return; }
    const [ax, ay] = this._editPx2Mm(d.x0, d.y0), [bx, by] = this._editPx2Mm(d.x1, d.y1); this._editSnapshot();
    // The same corner order whichever way the drag went: zones as mmBox, walls from their left
    // end (the top one when upright).
    const existingIds = Object.values(this._edit.areas).flat().map((a) => Number(a.id)).filter(Number.isInteger);
    const id = Math.max(-1, ...existingIds) + 1;
    if (this._edit.tool === "virtual_wall") { const ends = (ax < bx || (ax === bx && ay >= by)) ? [[ax, ay], [bx, by]] : [[bx, by], [ax, ay]]; (this._edit.areas.virtual_wall ||= []).push({ id, vertexs: ends }); }
    else { const t = this._edit.tool; (this._edit.areas[t] ||= []).push({ id, vertexs: mmBox(ax, ay, bx, by) }); }
    this._editDraw();
  }

  _editCancel() {
    if (!this._edit) return;
    this._edit.pointerId = null;
    this._edit.moving = false; this._edit.moveFrom = null; this._edit.resizing = false; this._edit.rotating = null;
    if (this._edit.drag) { this._edit.drag = null; this._editDraw(); }
  }

  _editHit(x, y) {
    const inside = (verts) => { let hit = false; const pts = verts.map((p) => this._editMm2Px(p[0], p[1])); for (let i = 0, j = pts.length - 1; i < pts.length; j = i++) { const [xi, yi] = pts[i], [xj, yj] = pts[j]; if ((yi > y) !== (yj > y) && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) hit = !hit; } return hit; };
    const near = (verts) => { const [x0, y0] = this._editMm2Px(verts[0][0], verts[0][1]), [x1, y1] = this._editMm2Px(verts[1][0], verts[1][1]); const L = Math.hypot(x1 - x0, y1 - y0) || 1; return Math.abs((y1 - y0) * x - (x1 - x0) * y + x1 * y0 - y1 * x0) / L < 8; };
    // The smallest item under the pointer wins, so a zone inside a furniture box stays selectable
    // (a wall counts as no area: it is hit only near its line).
    const area = (verts) => { let s = 0; for (let i = 0, j = verts.length - 1; i < verts.length; j = i++) s += verts[j][0] * verts[i][1] - verts[i][0] * verts[j][1]; return Math.abs(s) / 2; };
    let best = null, bestArea = Infinity;
    const take = (kind, i, a) => { if (a < bestArea) { best = { kind, i }; bestArea = a; } };
    for (const [i, f] of (this._edit.furniture || []).entries()) if (inside(f.vertexs)) take("furniture", i, area(f.vertexs));
    for (const [i, a] of (this._edit.areas.forbid || []).entries()) if (inside(a.vertexs)) take("forbid", i, area(a.vertexs));
    for (const [i, a] of (this._edit.areas.virtual_wall || []).entries()) if (near(a.vertexs)) take("virtual_wall", i, 0);
    return best;
  }
  // Resize handles in canvas pixels: furniture's bottom-right corner, or both wall endpoints.
  // Turned furniture has no resize handle because resizing keeps its box square to the map,
  // but it always gets a round handle beyond its top edge to rotate it freely.
  _editHandles() {
    const s = this._edit.sel; if (this._edit.tool !== "select" || !s) return [];
    if (s.kind === "virtual_wall") {
      const wall = this._edit.areas.virtual_wall[s.i];
      return wall && wall.vertexs
        ? wall.vertexs.slice(0, 2).map((p, vertex) => ({ point: this._editMm2Px(p[0], p[1]), vertex, kind: "resize" })) : [];
    }
    if (s.kind !== "furniture") return [];
    const f = this._edit.furniture[s.i]; if (!f || !f.vertexs || f.vertexs.length < 4) return [];
    const handles = [];
    if (!Number(f.angle)) {
      handles.push({ point: this._editMm2Px(Math.max(...f.vertexs.map((p) => p[0])), Math.min(...f.vertexs.map((p) => p[1]))),
                    vertex: null, kind: "resize" });
    }
    const [p0, p1] = f.vertexs;
    const cx = f.vertexs.reduce((sum, p) => sum + p[0], 0) / f.vertexs.length;
    const cy = f.vertexs.reduce((sum, p) => sum + p[1], 0) / f.vertexs.length;
    const mx = (p0[0] + p1[0]) / 2, my = (p0[1] + p1[1]) / 2;
    const dx = mx - cx, dy = my - cy, len = Math.hypot(dx, dy) || 1;
    handles.push({ point: this._editMm2Px(mx + (dx / len) * FURN_ROTATE_OFFSET, my + (dy / len) * FURN_ROTATE_OFFSET),
                  vertex: null, kind: "rotate" });
    return handles;
  }
  // The handle's size in canvas px: about 14 screen px however the canvas is scaled.
  _editHandleR() { const c = this._editEl.canvas, w = c.getBoundingClientRect().width; return 14 * (w ? c.width / w : 1); }
  _editSelItem() { const s = this._edit.sel; if (!s) return null; return s.kind === "furniture" ? this._edit.furniture[s.i] : this._edit.areas[s.kind][s.i]; }
  _editDelete() { const s = this._edit.sel; if (!s || !this._editReady()) return; this._editSnapshot(); if (s.kind === "furniture") this._edit.furniture.splice(s.i, 1); else this._edit.areas[s.kind].splice(s.i, 1); this._edit.sel = null; this._editDraw(); }
  _editUndo() { const u = this._edit.undo.pop(); if (!u) return; const o = JSON.parse(u); this._edit.areas = o.areas; this._edit.furniture = o.furniture; this._edit.rooms = o.rooms; this._edit.sel = null; this._editRenderRooms(); this._editDraw(); }

  async _editSave() {
    // Only the verified-safe layers are written: no-go zones, virtual walls, furniture and
    // room names. Carpets are left untouched (not sent), so they are preserved as-is.
    if (this._edit.saving) return;
    if (!this._editReady() || this._edit.mapId == null) { this._editEl.status.textContent = "The map has not loaded yet, so there is nothing to save."; return; }
    if (!this._isAdmin()) { this._editEl.status.textContent = "Only an administrator can save map changes."; return; }
    // Defend against repeated copies returned by a robot or a repeated pointer event.
    const uniqueFurniture = [], seenFurniture = new Set();
    for (const f of this._edit.furniture) {
      const key = JSON.stringify([f.type, f.angle, f.vertexs]);
      if (!seenFurniture.has(key)) { seenFurniture.add(key); uniqueFurniture.push(f); }
    }
    const areas = {};
    for (const type of ["forbid", "virtual_wall"]) {
      const current = this._edit.areas[type] || [], original = this._edit.originalAreas[type] || [];
      if (JSON.stringify(current) !== JSON.stringify(original)) areas[type] = current;
    }
    const furnitureChanged = JSON.stringify(uniqueFurniture) !== JSON.stringify(this._edit.originalFurniture || []);
    const originalRooms = this._edit.originalRooms || [];
    const roomsRenamed = this._edit.rooms.some((rm, i) => rm.name !== (originalRooms[i] || {}).name);
    if (!Object.keys(areas).length && !furnitureChanged && !roomsRenamed) {
      this._editEl.status.textContent = "No map changes to save."; return;
    }
    const payload = { type: "tapo_rv30/map/edit_apply", entity_id: this._robot, map_id: this._edit.mapId };
    if (Object.keys(areas).length) payload.areas = areas;
    if (furnitureChanged) payload.furniture = uniqueFurniture;
    // set_areas replaces every room, not just the renamed one - send the whole list (with its
    // other rooms' names unchanged) or an unrenamed room would be dropped from the map.
    if (roomsRenamed) payload.rooms = this._edit.rooms;
    this._edit.saving = true;
    const save = this._editEl.canvas.closest("ha-card").querySelector(".esave");
    save.disabled = true;
    this._editEl.status.textContent = "Saving to robot...";
    try {
      const response = await this._hass.callWS(payload);
      const failed = Object.entries((response && response.result) || {}).filter(([, code]) => Number(code) !== 0);
      if (failed.length) throw new Error(`Robot rejected ${failed.map(([kind]) => kind).join(", ")} (${failed.map(([, code]) => code).join(", ")})`);
      this._editEl.status.textContent = "Saved."; this._edit.furniture = uniqueFurniture; await this._editLoad();
    }
    catch (err) {
      const detail = err && (err.message || (err.body && err.body.message) || (err.data && err.data.message) || err.code);
      this._editEl.status.textContent = "Save failed: " + (detail || String(err));
    }
    finally { this._edit.saving = false; save.disabled = false; }
  }

  // ---- backups -------------------------------------------------------------------------
  _paneBackups(pane) {
    pane.innerHTML = `<ha-card><div class="card">
      <h3><span>Map backups</span>
        <button class="btn bkfetch"><ha-icon icon="mdi:cloud-download"></ha-icon>Fetch from cloud</button></h3>
      <div class="s">Backups held under <code>config/tapo_rv30/map_backups</code>. Tap a map to see it full size, or restore it to the robot (docked and idle). Fetching downloads your latest TP-Link cloud backups so you keep your own copies.</div>
      <div class="s bkstatus" style="margin-top:8px"></div>
      <div class="bkgrid" style="margin-top:12px"><div class="empty">Loading backups...</div></div>
    </div></ha-card>`;
    const grid = pane.querySelector(".bkgrid"), status = pane.querySelector(".bkstatus");
    pane.querySelector(".bkfetch").onclick = () => this._backupFetch(status, grid);
    if (!this._isAdmin()) { pane.querySelector(".bkfetch").disabled = true; status.textContent = "Only an administrator can fetch or restore backups."; }
    this._backupLoad(grid, status);
  }

  async _backupLoad(grid, status) {
    let res;
    try { res = await this._hass.callWS({ type: "tapo_rv30/backups/list", entity_id: this._robot }); }
    catch (e) { grid.innerHTML = `<div class="err">Could not list backups: ${esc(e.message || e)}</div>`; return; }
    const list = res.backups || [];
    this._backups = list;
    if (!list.length) { grid.innerHTML = `<div class="empty">No backups yet. Press "Fetch from cloud" to download your TP-Link map backups.</div>`; return; }
    grid.innerHTML = list.map((b, i) => {
      const f = b.facts || {};
      const sub = [f.extent ? `${f.extent.area_m2} m2` : "", f.room_count ? `${f.room_count} room${f.room_count > 1 ? "s" : ""}` : ""].filter(Boolean).join(" · ");
      const kb = Math.round(b.size / 1024);
      const thumb = b.thumb ? `<img class="thumb" data-i="${i}" src="${esc(b.thumb)}" alt="map preview">` : `<div class="thumb none">No preview</div>`;
      return `<div class="bkcard">${thumb}
        <div class="meta"><div class="t">${esc(b.map_name)} <span class="src">${esc(b.source)}</span></div>
          <div class="s">${esc(b.when)} · ${kb} KB${sub ? " · " + esc(sub) : ""}</div>
          <div class="acts">
            <button class="btn bkview" data-i="${i}"><ha-icon icon="mdi:eye"></ha-icon>View</button>
            <button class="btn primary bkrestore" data-i="${i}"><ha-icon icon="mdi:backup-restore"></ha-icon>Restore</button>
          </div></div></div>`;
    }).join("");
    grid.querySelectorAll(".thumb[data-i], .bkview").forEach((el) => el.onclick = () => this._backupView(list[+el.dataset.i]));
    grid.querySelectorAll(".bkrestore").forEach((el) => { el.onclick = () => this._backupRestore(list[+el.dataset.i], status); el.disabled = !this._isAdmin(); });
  }

  async _backupView(b) {
    const box = document.createElement("div");
    box.className = "lightbox";
    box.innerHTML = `<img src="${esc(b.thumb || "")}"><div class="lb-info">Loading full image...</div>`;
    box.onclick = () => box.remove();
    this.shadowRoot.appendChild(box);
    try {
      const res = await this._hass.callWS({ type: "tapo_rv30/backups/image", entity_id: this._robot, file: b.file });
      if (res.image) box.querySelector("img").src = res.image;
      const f = res.facts || {};
      const bits = [b.map_name, b.when];
      if (f.extent) bits.push(`${f.extent.width_m} × ${f.extent.height_m} m (${f.extent.area_m2} m2)`);
      if (f.room_count) bits.push(`${f.room_count} rooms`);
      box.querySelector(".lb-info").textContent = bits.filter(Boolean).join("   ·   ");
    } catch (e) { box.querySelector(".lb-info").textContent = "Could not load image: " + (e.message || e); }
  }

  _backupRestore(b, status) {
    const asNew = window.confirm(`Restore "${b.map_name}" from ${b.when} as a new map instead of replacing it?\n\nOK = new map (keeps the original as it is). Cancel = ask about replacing it.`);
    let newName = null;
    if (asNew) {
      newName = (window.prompt(`Name for the new map:`, `${b.map_name} (restored)`) || "").trim();
      if (!newName) return;
    } else if (!window.confirm(`Replace "${b.map_name}" on the robot with this backup from ${b.when}?\n\nThis replaces that map's shape and layout on the robot. The robot must be docked and idle.`)) {
      return;
    }
    status.textContent = `Restoring "${b.map_name}"...`;
    const data = { map: String(b.map_id), file: b.file, confirm: true };
    if (newName) data.new_name = newName;
    this._hass.callService(DOMAIN, "restore_map_backup", data, { entity_id: this._robot }, false, true)
      .then((res) => {
        const r = (res && res.response) ? res.response : res;
        if (r && r.applied) status.textContent = `Restored "${b.map_name}". ${r.next_steps || ""}`;
        else status.textContent = `Restore ended without confirmation: ${r && r.note ? r.note : "check the robot"}.`;
      })
      .catch((e) => { status.textContent = "Restore failed: " + (e.message || e); });
  }

  async _backupFetch(status, grid) {
    status.textContent = "Fetching cloud backups (this can take a moment)...";
    try {
      const res = await this._hass.callService(DOMAIN, "fetch_cloud_map_backups", {}, { entity_id: this._robot }, false, true);
      const r = (res && res.response) ? res.response : res;
      if (r && r.status === "code_sent") {
        status.innerHTML = `TP-Link emailed a verification code. Run the <code>fetch_cloud_map_backups</code> action once with that code, then fetch again.`;
        return;
      }
      const n = (r && r.backups) ? r.backups.length : 0;
      status.textContent = `Fetched ${n} backup${n === 1 ? "" : "s"}.`;
      this._backupLoad(grid, status);
    } catch (e) { status.textContent = "Fetch failed: " + (e.message || e); }
  }

  // ---- log ----------------------------------------------------------------------------
  _paneLog(pane) {
    pane.innerHTML = `<ha-card><div class="card">
      <h3><span>Integration log</span>
        <button class="btn logrefresh"><ha-icon icon="mdi:refresh"></ha-icon>Refresh</button>
        <button class="btn logclear"><ha-icon icon="mdi:delete-outline"></ha-icon>Clear</button></h3>
      <div class="s">Recent log records from this integration (<code>custom_components.tapo_rv30</code> and its
        modules), newest first. The buffer is shared by every configured robot and holds a few hundred
        records; turning on debug logging for this integration shows more here.</div>
      <div class="s logstatus" style="margin-top:8px"></div>
      <div class="logrows" style="margin-top:12px"><div class="empty">Loading…</div></div>
    </div></ha-card>`;
    const rows = pane.querySelector(".logrows"), status = pane.querySelector(".logstatus");
    pane.querySelector(".logrefresh").onclick = () => this._logLoad(rows, status);
    const clearBtn = pane.querySelector(".logclear");
    clearBtn.onclick = () => this._logClear(rows, status);
    if (!this._isAdmin()) { clearBtn.disabled = true; clearBtn.title = "Only an administrator can clear the log."; }
    this._logLoad(rows, status);
  }

  async _logLoad(rows, status) {
    status.textContent = "";
    let res;
    try { res = await this._hass.callWS({ type: "tapo_rv30/log/list", entity_id: this._robot, limit: 300 }); }
    catch (e) { rows.innerHTML = `<div class="err">Could not load the log: ${esc((e && e.message) || e)}</div>`; return; }
    const recs = res.records || [];
    if (!recs.length) { rows.innerHTML = `<div class="empty">Nothing logged yet.</div>`; return; }
    rows.innerHTML = recs.map((r) => {
      const color = LOG_COLORS[r.level] || LOG_COLORS.INFO;
      return `<div class="row" style="border-left:3px solid ${color};padding-left:8px">
        <div class="grow"><div class="t"><span style="color:${color};font-weight:600">${esc(r.level)}</span>
          <span class="sub">${esc(r.when)} · ${esc(r.logger)}</span></div>
          <div class="s" style="white-space:pre-wrap;word-break:break-word">${esc(r.message)}</div></div></div>`;
    }).join("");
  }

  _logClear(rows, status) {
    if (!window.confirm("Clear the integration log buffer? This only clears what the sidebar page shows, not Home Assistant's own log.")) return;
    this._hass.callWS({ type: "tapo_rv30/log/clear", entity_id: this._robot })
      .then(() => { status.textContent = "Cleared."; this._logLoad(rows, status); })
      .catch((e) => { status.textContent = "Could not clear the log: " + ((e && e.message) || e); });
  }

  _paneMaintenance(pane) {
    const r = this._related(this._robot), vac = this._st(this._robot), cons = vac.attributes.consumables || {};
    const strip = (n) => String(n || "").replace(vac.attributes.friendly_name + " ", "");
    const resetByName = new Map();
    r.buttons.forEach((id) => {
      const s = this._st(id), label = strip(s && s.attributes.friendly_name);
      const match = label.match(/^Reset\s+(.+)$/i);
      if (match) resetByName.set(match[1].trim().toLowerCase(), id);
    });
    const paired = new Set();
    const bars = Object.entries(cons).map(([k, v]) => {
      const resetId = resetByName.get(String(k).trim().toLowerCase());
      if (resetId) paired.add(resetId);
      return `<div class="bar-row consumable-row ${v <= 10 ? "bad" : v <= 30 ? "warn" : ""}"><span>${esc(k)}</span><div class="track"><div style="width:${v}%"></div></div><span class="r">${v}%</span>${resetId ? `<button class="minibtn" data-btn="${esc(resetId)}" title="Reset ${esc(k)}" aria-label="Reset ${esc(k)}"><ha-icon icon="mdi:restore"></ha-icon>Reset</button>` : ""}</div>`;
    }).join("");
    const btns = r.buttons.filter((id) => !paired.has(id)).map((id) => { const s = this._st(id);
      return `<button class="btn" data-btn="${esc(id)}"><ha-icon icon="${esc(s.attributes.icon || "mdi:gesture-tap-button")}"></ha-icon>${esc(strip(s.attributes.friendly_name))}</button>`; }).join(" ");
    pane.innerHTML = `<ha-card><div class="card"><h3><span>Consumables</span></h3>${bars || `<div class="empty">No consumable data.</div>`}</div></ha-card>
      ${btns ? `<ha-card><div class="card"><h3><span>Other actions</span></h3><div class="chips">${btns}</div></div></ha-card>` : ""}`;
    pane.querySelectorAll("[data-btn]").forEach((b) => b.onclick = () => this._call("button", "press", {}, { entity_id: b.dataset.btn }));
  }

  // ---- settings -----------------------------------------------------------------------
  _paneSettings(pane) {
    const r = this._related(this._robot), vac = this._st(this._robot), strip = (n) => String(n || "").replace(vac.attributes.friendly_name + " ", "");
    const sw = r.switches.map((id) => { const s = this._st(id);
      return `<div class="row"><div class="grow"><div class="t">${esc(strip(s.attributes.friendly_name))}</div></div><button class="switch ${s.state === "on" ? "on" : ""}" data-sw="${esc(id)}"></button></div>`; }).join("");
    const sel = r.selects.map((id) => { const s = this._st(id);
      return `<div class="row"><div class="grow"><div class="t">${esc(strip(s.attributes.friendly_name))}</div></div><select data-sel="${esc(id)}">${(s.attributes.options || []).map((o) => `<option ${o === s.state ? "selected" : ""}>${esc(o)}</option>`).join("")}</select></div>`; }).join("");
    const num = r.numbers.map((id) => { const s = this._st(id);
      return `<div class="row"><div class="grow"><div class="t">${esc(strip(s.attributes.friendly_name))}</div><div class="s">${esc(s.state)} ${esc(s.attributes.unit_of_measurement || "")}</div></div><input type="range" data-num="${esc(id)}" min="${s.attributes.min}" max="${s.attributes.max}" step="${s.attributes.step || 1}" value="${esc(s.state)}"></div>`; }).join("");
    const tim = r.times.map((id) => { const s = this._st(id);
      return `<div class="row"><div class="grow"><div class="t">${esc(strip(s.attributes.friendly_name))}</div></div><input type="time" data-time="${esc(id)}" value="${esc(String(s.state).slice(0, 5))}"></div>`; }).join("");
    const admin = this._isAdmin();
    pane.innerHTML = `<ha-card><div class="card"><h3><span>Settings</span></h3>${sw}${sel}${tim}${num}${(sw || sel || num || tim) ? "" : `<div class="empty">No settings entities.</div>`}</div></ha-card>
      <ha-card><div class="card"><h3><span>Maps</span></h3>
        <div class="s">Name a saved map (full name or id) to rename, lock or delete it, or make a copy of it to edit or try things on. The robot must be docked and idle; copy and delete need the TP-Link cloud / confirmation respectively.${admin ? "" : " Only an administrator can change maps."}</div>
        <div class="row" style="margin-top:8px"><div class="grow"><div class="t">Map</div></div>
          <div class="ctl"><input type="text" class="mapref" placeholder="name or id" ${admin ? "" : "disabled"}></div></div>
        <div class="row"><div class="grow"><div class="t">New name</div><div class="s">for rename or copy</div></div>
          <div class="ctl"><input type="text" class="mapnewname" placeholder="new name" ${admin ? "" : "disabled"}></div></div>
        <div class="actions" style="margin-top:8px">
          <button class="btn maprename" ${admin ? "" : "disabled"}><ha-icon icon="mdi:rename-box"></ha-icon>Rename</button>
          <button class="btn mapcopy" ${admin ? "" : "disabled"}><ha-icon icon="mdi:content-copy"></ha-icon>Copy</button>
          <button class="btn maplock" ${admin ? "" : "disabled"}><ha-icon icon="mdi:lock-outline"></ha-icon>Lock</button>
          <button class="btn mapunlock" ${admin ? "" : "disabled"}><ha-icon icon="mdi:lock-open-variant-outline"></ha-icon>Unlock</button>
          <button class="btn mapdelete" ${admin ? "" : "disabled"}><ha-icon icon="mdi:delete-outline"></ha-icon>Delete</button>
        </div>
        <div class="s mapstatus" style="margin-top:8px"></div>
      </div></ha-card>`;
    pane.querySelectorAll("[data-sw]").forEach((b) => b.onclick = () => this._call("switch", b.classList.contains("on") ? "turn_off" : "turn_on", {}, { entity_id: b.dataset.sw }));
    pane.querySelectorAll("[data-sel]").forEach((e) => e.onchange = () => this._call("select", "select_option", { option: e.value }, { entity_id: e.dataset.sel }));
    pane.querySelectorAll("[data-num]").forEach((e) => e.onchange = () => this._call("number", "set_value", { value: Number(e.value) }, { entity_id: e.dataset.num }));
    pane.querySelectorAll("[data-time]").forEach((e) => e.onchange = () => { if (e.value) this._call("time", "set_value", { time: e.value + ":00" }, { entity_id: e.dataset.time }); });
    this._wireMapsCard(pane);
  }

  // ---- auto-empty -------------------------------------------------------------------
  _dropAutoEmptySub() {
    if (this._autoEmptyUnsub) { try { this._autoEmptyUnsub(); } catch (e) { /* closed */ } }
    this._autoEmptyUnsub = null; this._autoEmptyFor = null;
  }

  async _ensureAutoEmptySub() {
    if (this._autoEmptyFor === this._robot || !this._robot) return;
    this._dropAutoEmptySub(); this._autoEmptyFor = this._robot;
    try {
      this._autoEmptyUnsub = await this._hass.connection.subscribeMessage((view) => {
        this._autoEmpty = view;
        this._update(true);
      }, { type: `${DOMAIN}/auto_empty/subscribe`, entity_id: this._robot });
    } catch (e) {
      this._autoEmpty = { error: (e && e.message) || "Planner unavailable" };
      this._update(true);
    }
  }

  _paneAutoEmpty(pane) {
    const v = this._autoEmpty;
    const next = v && v.next_run ? new Date(v.next_run * 1000).toLocaleString() : "—";
    const last = v && v.last_run ? new Date(v.last_run * 1000).toLocaleString() : "Never";
    const supported = !!(v && v.supported);
    const status = !v ? "Loading schedule…" : v.error || (!supported ? "Empty Bin is not supported by this vacuum" : v.last_error || (v.enabled ? (v.status_code != null && ![5, 6].includes(v.status_code) ? "Waiting for the vacuum to dock" : "Schedule active") : "Schedule off"));
    pane.innerHTML = `<ha-card><div class="card">
      <h3><span>Auto-empty planner</span></h3>
      <p class="sub">Home Assistant will run the vacuum’s Empty Bin command at the saved frequency and time. It waits until the vacuum is docked. No presence conditions are used.</p>
      <div class="row"><div class="grow"><div class="t">Schedule</div><div class="s">${esc(status)}</div></div><button class="switch ${v && v.enabled ? "on" : ""}" data-ae-enabled ${supported ? "" : "disabled"}></button></div>
      <div class="row"><div class="grow"><div class="t">Frequency</div></div><select data-ae-days ${supported ? "" : "disabled"}>${[1,2,3,4,5,7,14,30].map((d) => `<option value="${d}" ${v && v.interval_days === d ? "selected" : ""}>Every ${d} day${d === 1 ? "" : "s"}</option>`).join("")}</select></div>
      <div class="row"><div class="grow"><div class="t">Time</div></div><input type="time" data-ae-time value="${esc(v && v.run_time || "10:00")}" ${supported ? "" : "disabled"}></div>
      <div class="stat"><div class="l">Next empty</div><div class="v">${esc(next)}</div></div>
      <div class="stat"><div class="l">Last empty</div><div class="v">${esc(last)}</div></div>
      ${v && v.last_error ? `<div class="err">${esc(v.last_error)}</div>` : ""}
      <div class="actions" style="margin-top:12px"><button class="btn" data-ae-now ${supported ? "" : "disabled"}><ha-icon icon="mdi:delete-empty"></ha-icon>Empty now</button></div>
    </div></ha-card>`;
    const save = () => this._hass.callWS({ type: `${DOMAIN}/auto_empty/set`, entity_id: this._robot,
      config: { enabled: pane.querySelector("[data-ae-enabled]").classList.contains("on"),
        interval_days: Number(pane.querySelector("[data-ae-days]").value), run_time: pane.querySelector("[data-ae-time]").value } });
    const toggle = pane.querySelector("[data-ae-enabled]");
    if (toggle) toggle.onclick = () => { toggle.classList.toggle("on"); save().catch((e) => this._notify(e.message)); };
    pane.querySelector("[data-ae-days]").onchange = () => save().catch((e) => this._notify(e.message));
    pane.querySelector("[data-ae-time]").onchange = () => save().catch((e) => this._notify(e.message));
    pane.querySelector("[data-ae-now]").onclick = () => this._hass.callWS({ type: `${DOMAIN}/auto_empty/empty`, entity_id: this._robot }).catch((e) => this._notify(e.message));
  }

  _wireMapsCard(pane) {
    const status = pane.querySelector(".mapstatus");
    const mapVal = () => pane.querySelector(".mapref").value.trim();
    const newNameVal = () => pane.querySelector(".mapnewname").value.trim();
    const run = (label, service, data) => {
      status.textContent = `${label}...`;
      return this._hass.callService(DOMAIN, service, data, { entity_id: this._robot }, false, true)
        .then((res) => { const r = (res && res.response) ? res.response : res; status.textContent = `${label}: done.`; return r; })
        .catch((e) => { status.textContent = `${label} failed: ${(e && e.message) || e}`; throw e; });
    };
    pane.querySelector(".maprename").onclick = () => {
      const map = mapVal(), name = newNameVal();
      if (!map || !name) { status.textContent = "Give the map and its new name."; return; }
      run("Rename", "rename_map", { map, name });
    };
    pane.querySelector(".mapcopy").onclick = () => {
      const map = mapVal(), name = newNameVal();
      if (!name) { status.textContent = "Give a name for the copy."; return; }
      run("Copy", "copy_map", { map: map || undefined, name });
    };
    pane.querySelector(".maplock").onclick = () => {
      const map = mapVal();
      if (!map) { status.textContent = "Give the map."; return; }
      run("Lock", "set_map_lock", { map, locked: true });
    };
    pane.querySelector(".mapunlock").onclick = () => {
      const map = mapVal();
      if (!map) { status.textContent = "Give the map."; return; }
      run("Unlock", "set_map_lock", { map, locked: false });
    };
    pane.querySelector(".mapdelete").onclick = () => {
      const map = mapVal();
      if (!map) { status.textContent = "Give the map."; return; }
      if (!window.confirm(`Delete map "${map}" from the robot? This cannot be undone, and is never allowed for the current or only saved map.`)) return;
      run("Delete", "delete_map", { map, confirm: true });
    };
  }

  // ---- planner --------------------------------------------------------------------------
  _panePlanner(pane) {
    const v = this._plan;
    if (this._planErr) { pane.innerHTML = `<ha-card><div class="card"><div class="err">${esc(this._planErr)}</div></div></ha-card>`; return; }
    if (!v) { pane.innerHTML = `<ha-card><div class="card"><div class="empty">Loading the planner…</div></div></ha-card>`; return; }
    pane.innerHTML = this._statusCard(v) + this._unmappedCard(v) + this._previewCard(v) + this._timelineCard(v)
      + this._roomsCard(v) + this._conditionsCard(v) + this._notifyCard(v) + this._logCard(v);
    this._wirePlanner(pane, v);
  }

  _statusCard(v) {
    const c = v.config, on = !!c.enabled, home = v.away && v.away.home;
    return `<ha-card><div class="card">
      ${c.preview ? `<div class="banner"><ha-icon icon="mdi:eye-outline"></ha-icon><span class="grow">Preview mode: the planner logs what it would do and never starts the robot. Turn preview off when the log looks right.</span><button class="switch on" data-set="preview"></button></div>`
        : `<div class="banner live"><ha-icon icon="mdi:robot-vacuum"></ha-icon><span class="grow">The planner starts the robot when rooms are due. Preview mode only logs instead.</span><button class="switch" data-set="preview"></button></div>`}
      <h3><span>Planner</span>
        <span class="note">keeps each room within its target</span>
        <button class="switch ${on ? "on" : ""}" data-set="enabled"></button></h3>
      <div class="line">${esc(v.status)}</div>
      <div class="chips">
        ${(v.chips || []).map((t) => `<span class="chip warn">${esc(t)}</span>`).join("")}
        ${v.battery != null ? `<span class="chip info">Battery ${esc(v.battery)}%</span>` : ""}
        <span class="chip info">${home ? esc((v.away.who || []).join(", ") || "somebody") + " home" : "Nobody home"}</span>
        ${c.runs_per_window === "repeat" ? `<span class="chip info">repeat runs</span>` : ""}
      </div>
      <div class="actions" style="margin-top:12px">
        <button class="btn primary" data-act="clean_now" ${v.due.length ? "" : "disabled"}><ha-icon icon="mdi:play"></ha-icon>Clean due rooms now</button>
        <button class="btn" data-act="skip_today" data-on="${v.skip_today ? "0" : "1"}"><ha-icon icon="mdi:calendar-remove"></ha-icon>${v.skip_today ? "Back on today" : "Skip today"}</button>
        ${c.preview ? `<button class="btn" data-set="preview"><ha-icon icon="mdi:robot-vacuum"></ha-icon>Turn preview off</button>` : ""}
      </div>
    </div></ha-card>`;
  }

  _unmappedCard(v) {
    if (!v.unmapped.length) return "";
    return `<ha-card><div class="card">
      <div class="banner"><ha-icon icon="mdi:link-variant"></ha-icon>
        <span class="grow">Not linked to a Home Assistant area: ${esc(v.unmapped.join(", "))}. Linked rooms can use the sensors and people in their area.</span></div>
      <div class="actions">
        <button class="btn" data-act="match_areas"><ha-icon icon="mdi:auto-fix"></ha-icon>Match by name</button>
        <button class="btn" data-mapping><ha-icon icon="mdi:cog"></ha-icon>Map rooms to areas</button>
      </div></div></ha-card>`;
  }

  _previewCard(v) {
    if (!v.config.preview) return "";
    return `<ha-card><div class="card">
      <h3><ha-icon icon="mdi:flask-outline"></ha-icon><span>Dry run</span><span class="note">preview mode: this is what would happen, nothing is sent to the robot</span></h3>
      <div class="line">${esc(v.status)}</div>
      ${(v.chips || []).length ? `<div class="chips">${v.chips.map((t) => `<span class="chip warn">${esc(t)}</span>`).join("")}</div>` : ""}
    </div></ha-card>`;
  }

  _timelineCard(v) {
    const rows = (v.timeline || []).map((w) => {
      const d = new Date(w.opens);
      const when = w.today
        ? `Today ${d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`
        : d.toLocaleDateString([], { weekday: "short", day: "numeric", month: "short" }) + " " +
          d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
      const text = w.names.length ? esc(w.names.join(", ")) : `<span class="sub">nothing due</span>`;
      return `<div class="e"><b>${esc(when)}</b><span>${text}</span></div>`;
    }).join("");
    return `<ha-card><div class="card log"><h3><span>Upcoming</span><span class="note">projected forward, assuming each window runs</span></h3>
      ${rows || `<div class="empty">Turn the planner on to see what is coming up.</div>`}</div></ha-card>`;
  }

  _roomsCard(v) {
    const c = v.config, targets = v.target_choices || [0, 1, 2, 3, 4, 5, 7, 14];
    const tname = (n) => (n === 0 ? "Leave out" : n === 1 ? "every day" : n === 7 ? "every week" : n === 14 ? "every 2 weeks" : `every ${n} days`);
    const fresh = (r) => {
      if (!r.target_days) return 0;
      if (!r.last_cleaned) return 100;
      return Math.min(100, Math.round(100 * (Date.now() / 1000 - r.last_cleaned) / 86400 / r.target_days));
    };
    const cls = (s) => (s === "Overdue" ? "over" : s === "Due today" ? "due" : s === "Fresh" ? "fresh" : "out");
    const rooms = v.rooms.map((r) => {
      const areas = r.areas.length ? r.areas.map((a) => a.name).join(", ") : "no area";
      const listen = r.ignore_occupancy ? "ignores occupancy"
        : r.sensors.length ? `listening to ${r.sensors.map((s) => esc(s.name)).join(", ")}` : "no sensors";
      const inuse = r.in_use_by.length ? ` · <span style="color:var(--error-color,#db4437)">in use: ${esc(r.in_use_by.join(", "))}</span>` : "";
      let editor = "";
      if (this._open === r.key) {
        const chosen = new Set(r.sensors.map((s) => s.entity_id));
        const manual = r.sensors.filter((s) => s.source === "manual");
        editor = `<div class="editor">
          <div class="chips">${v.sensors.map((s) =>
            `<button class="chip btn ${chosen.has(s.entity_id) ? "on" : ""}" data-sensor="${esc(s.entity_id)}" data-room="${esc(r.key)}">${esc(s.name)}${s.area ? ` <span style="opacity:.7">(${esc(s.area)})</span>` : ""}</button>`).join("") || `<span class="sub">No motion, occupancy or presence sensors in Home Assistant.</span>`}</div>
          ${manual.length ? `<div class="chips" style="margin-top:8px">${manual.map((s) =>
            `<button class="chip btn on" data-unman="${esc(s.entity_id)}" data-room="${esc(r.key)}" title="Remove">${esc(s.name)} ✕</button>`).join("")}</div>` : ""}
          <div class="row" style="border:0;padding-bottom:0">
            <div class="grow"><div class="t">Add any entity as “in use”</div>
              <div class="s">a contact sensor, a person, an input_boolean — on / not home means the room is busy</div></div>
            <div class="ctl"><ha-entity-picker data-addman="${esc(r.key)}" allow-custom-entity></ha-entity-picker>
              <button class="minibtn" data-addmanbtn="${esc(r.key)}">Add</button></div>
          </div>
          <div class="row" style="border:0">
            <div class="grow"><div class="t">Ignore occupancy for this room</div>
              <div class="s">clean it even when somebody is inside</div></div>
            <button class="switch ${r.ignore_occupancy ? "on" : ""}" data-ignore="${esc(r.key)}"></button>
          </div>
        </div>`;
      }
      return `<div class="room">
        <div class="top">
          <div class="nm">${esc(r.name)}</div>
          <div class="bar ${r.score >= 1 ? "due" : ""}"><div style="width:${fresh(r)}%"></div></div>
          <span class="pillst ${cls(r.skipped_today ? "Skipped today" : r.status)}">${esc(r.skipped_today ? "Skipped today" : r.status)}</span>
          <select data-target="${esc(r.key)}">${targets.map((n) => `<option value="${n}" ${n === r.target_days ? "selected" : ""}>${tname(n)}</option>`).join("")}</select>
        </div>
        <div class="bot">
          <span class="sub">${esc(areas)} · ${listen}${inuse}</span>
          <button class="minibtn" data-open="${esc(r.key)}">${this._open === r.key ? "Done" : "Sensors"}</button>
          <button class="minibtn" data-skiproom="${esc(r.key)}" data-on="${r.skipped_today ? "0" : "1"}">${r.skipped_today ? "Include today" : "Leave out today"}</button>
        </div>
        ${editor}
      </div>`;
    }).join("");
    return `<ha-card><div class="card"><h3><span>Rooms</span><span class="note">how fresh each room is against its target</span></h3>
      ${rooms || `<div class="empty">No rooms on the current map.</div>`}</div></ha-card>`;
  }

  _conditionsCard(v) {
    const c = v.config, w = c.windows, opt = (vals, cur, label) => vals.map((n) => `<option value="${n}" ${Number(cur) === n ? "selected" : ""}>${label(n)}</option>`).join("");
    const src = c.away_source || "persons";
    const dnd = this._dnd(this._related(this._robot));
    const people = v.people.map((p) =>
      `<button class="chip btn ${p.included ? "on" : ""}" data-person="${esc(p.entity_id)}">${esc(p.name)}${p.home ? " (home)" : ""}</button>`).join("");
    return `<ha-card><div class="card"><h3><span>Only clean when</span></h3>
      <div class="row">
        <div class="grow"><div class="t">Nobody is home</div><div class="s">the condition that lets a run start</div></div>
        <div class="ctl"><select data-awaysrc>
            <option value="persons" ${src === "persons" ? "selected" : ""}>person entities</option>
            <option value="entity" ${src === "entity" ? "selected" : ""}>one entity decides</option>
          </select><button class="switch ${c.require_away ? "on" : ""}" data-set="require_away"></button></div>
      </div>
      ${src === "persons" ? (v.people.length ? `<div class="chips" style="padding:4px 0 8px">${people}</div>`
        : `<div class="sub" style="padding:0 0 8px">no people in Home Assistant</div>`) : `
      <div class="row">
        <div class="grow"><div class="t">Entity that knows</div>
          <div class="s">your input_boolean “someone home”, a tracker, a group — states below mean occupied</div></div>
        <div class="ctl"><ha-entity-picker data-awayent allow-custom-entity></ha-entity-picker></div>
      </div>
      <div class="row">
        <div class="grow"><div class="t">States that mean “home”</div><div class="s">comma separated: home, on, …</div></div>
        <div class="ctl"><input type="text" data-awaystates value="${esc((c.away_home_states || []).join(", "))}"></div>
      </div>`}
      <div class="row">
        <div class="grow"><div class="t">Leave out rooms in use</div><div class="s">motion counts for a while after it stops; people in the room's area count too</div></div>
        <div class="ctl"><select data-num="clear_minutes">${opt([0, 5, 10, 15, 30, 60], c.clear_minutes, (n) => `${n} min`)}</select>
          <button class="switch ${c.skip_in_use ? "on" : ""}" data-set="skip_in_use"></button></div>
      </div>
      <div class="row">
        <div class="grow"><div class="t">Occupancy sources</div><div class="s">what the planner listens to per room</div></div>
        <div class="ctl">
          <button class="chip btn ${c.occupancy_sources.area_sensors ? "on" : ""}" data-osrc="area_sensors">motion in area</button>
          <button class="chip btn ${c.occupancy_sources.area_people ? "on" : ""}" data-osrc="area_people">people in area</button>
          <button class="chip btn ${c.occupancy_sources.manual ? "on" : ""}" data-osrc="manual">manual entities</button>
        </div>
      </div>
      <div class="row">
        <div class="grow"><div class="t">Battery at least</div><div class="s">it waits on the dock below this</div></div>
        <select data-num="min_battery">${opt([0, 20, 30, 40, 50, 60, 80], c.min_battery, (n) => (n ? `${n}%` : "any"))}</select>
      </div>
      <div class="row">
        <div class="grow"><div class="t">Runs per window</div><div class="s">once a day like the original, or again while rooms are due</div></div>
        <div class="ctl">
          <select data-runs>
            <option value="once" ${c.runs_per_window !== "repeat" ? "selected" : ""}>once per window</option>
            <option value="repeat" ${c.runs_per_window === "repeat" ? "selected" : ""}>repeat while due</option>
          </select>
          ${c.runs_per_window === "repeat" ? `<input type="number" min="0" max="1440" data-num="min_run_gap_minutes" value="${esc(c.min_run_gap_minutes)}" title="minimum minutes between runs">` : ""}
        </div>
      </div>
      <div class="row">
        <div class="grow"><div class="t">Not near the robot's own schedules</div><div class="s">holds off when one starts within the hour</div></div>
        <button class="switch ${c.avoid_schedules ? "on" : ""}" data-set="avoid_schedules"></button>
      </div>
      <div class="row">
        <div class="grow"><div class="t">Outside Do Not Disturb</div><div class="s">always: the robot would refuse anyway</div></div>
        <span class="sub">${dnd && dnd.enabled ? esc(dndText(dnd)) : "not set"}</span>
      </div>
      <div class="row">
        <div class="grow"><div class="t">Weekdays</div><div class="s">when it may start</div></div>
        <div class="ctl"><input type="time" data-win="weekdays" data-i="0" value="${esc(w.weekdays[0])}"> to <input type="time" data-win="weekdays" data-i="1" value="${esc(w.weekdays[1])}"></div>
      </div>
      <div class="row">
        <div class="grow"><div class="t">Weekends</div></div>
        <div class="ctl"><input type="time" data-win="weekends" data-i="0" value="${esc(w.weekends[0])}"> to <input type="time" data-win="weekends" data-i="1" value="${esc(w.weekends[1])}"></div>
      </div>
      <div class="row">
        <div class="grow"><div class="t">If someone comes home mid-run</div><div class="s">finish_room is not yet tested on a real robot</div></div>
        <div class="seg">
          <button data-ret="finish_room" class="${c.on_return === "finish_room" ? "on" : ""}">Finish room, dock</button>
          <button data-ret="keep_going" class="${c.on_return === "keep_going" ? "on" : ""}">Keep going</button>
        </div>
      </div>
      <div class="row">
        <div class="grow"><div class="t">Target for new rooms</div></div>
        <select data-num="default_target_days">${opt((v.target_choices || []).filter((n) => n), c.default_target_days, (n) => (n === 1 ? "every day" : n === 7 ? "every week" : n === 14 ? "every 2 weeks" : `every ${n} days`))}</select>
      </div>
    </div></ha-card>`;
  }

  _notifyCard(v) {
    const n = (v.config && v.config.notify) || {};
    const services = Object.keys((this._hass.services && this._hass.services.notify) || {}).sort();
    return `<ha-card><div class="card"><h3><span>Notifications</span><span class="note">any combination</span></h3>
      <div class="row">
        <div class="grow"><div class="t">Persistent notification</div><div class="s">a card in HA's notification panel</div></div>
        <button class="switch ${n.persistent ? "on" : ""}" data-notify="persistent"></button>
      </div>
      <div class="row">
        <div class="grow"><div class="t">Write into an input_text</div><div class="s">your own helper, e.g. for Jarvis</div></div>
        <div class="ctl"><ha-entity-picker data-notifyent allow-custom-entity></ha-entity-picker></div>
      </div>
      <div class="row">
        <div class="grow"><div class="t">Write into a text</div><div class="s">a Home Assistant text entity</div></div>
        <div class="ctl"><ha-entity-picker data-textnotifyent allow-custom-entity></ha-entity-picker></div>
      </div>
      <div class="row">
        <div class="grow"><div class="t">Call a notify service</div><div class="s">mobile_app, telegram, …</div></div>
        <div class="ctl"><select data-notifysvc>
          <option value="">— none —</option>
          ${services.map((s) => `<option value="notify.${esc(s)}" ${n.notify_service === `notify.${s}` ? "selected" : ""}>notify.${esc(s)}</option>`).join("")}
          ${n.notify_service && !services.some((s) => `notify.${s}` === n.notify_service) ? `<option value="${esc(n.notify_service)}" selected>${esc(n.notify_service)}</option>` : ""}
        </select></div>
      </div>
      <div class="row">
        <div class="grow"><div class="t">Notify when</div></div>
        <select data-notifywhen>
          <option value="start" ${n.when !== "start_and_blocked" ? "selected" : ""}>a run starts</option>
          <option value="start_and_blocked" ${n.when === "start_and_blocked" ? "selected" : ""}>a run starts or keeps waiting</option>
        </select>
      </div>
    </div></ha-card>`;
  }

  _logCard(v) {
    const log = (v.log || []).map((e) => {
      const d = new Date(e.ts * 1000);
      const today = d.getDate() === new Date().getDate() && (Date.now() - d) / 864e5 < 1;
      const when = today
        ? d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
        : d.toLocaleDateString([], { weekday: "short" }) + " " + d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
      return `<div class="e"><b>${esc(when)}</b><span>${esc(e.text)}</span></div>`;
    }).join("");
    return `<ha-card><div class="card log"><h3><span>Recent decisions</span></h3>
      ${log || `<div class="empty">Nothing yet.</div>`}</div></ha-card>`;
  }

  // ---- planner wiring -------------------------------------------------------------------
  _wirePlanner(pane, v) {
    const c = v.config, q = (sel) => pane.querySelectorAll(sel);
    // ha-entity-picker needs real JS properties — Lit-style .prop= bindings do
    // not survive innerHTML, so they are set here after the markup is in place
    q("ha-entity-picker[data-addman]").forEach((p) => { p.hass = this._hass; });
    q("[data-set]").forEach((b) => b.onclick = () => this._set({ [b.dataset.set]: !c[b.dataset.set] }));
    q("[data-act]").forEach((b) => b.onclick = () => this._act(b.dataset.act, b.dataset.on != null ? { on: b.dataset.on === "1" } : {}));
    q("[data-mapping]").forEach((b) => b.onclick = () =>
      this.dispatchEvent(new CustomEvent("hass-more-info", { detail: { entityId: this._robot, view: "settings" }, bubbles: true, composed: true })));
    q("[data-target]").forEach((s) => s.onchange = () => { this._planDirty = false; this._set({ rooms: { [s.dataset.target]: { target_days: Number(s.value) } } }); });
    q("[data-num]").forEach((s) => s.onchange = () => { this._planDirty = false; this._set({ [s.dataset.num]: Number(s.value) }); });
    q("[data-win]").forEach((i) => i.onchange = () => {
      if (!i.value) return;
      const pair = [...c.windows[i.dataset.win]];
      pair[Number(i.dataset.i)] = i.value;
      this._planDirty = false;
      this._set({ windows: { [i.dataset.win]: pair } });
    });
    q("[data-ret]").forEach((b) => b.onclick = () => this._set({ on_return: b.dataset.ret }));
    q("[data-runs]").forEach((s) => s.onchange = () => { this._planDirty = false; this._set({ runs_per_window: s.value }); });
    q("[data-awaysrc]").forEach((s) => s.onchange = () => { this._planDirty = false; this._set({ away_source: s.value }); });
    q("[data-awaystates]").forEach((i) => i.onchange = () => {
      this._planDirty = false;
      this._set({ away_home_states: i.value.split(",").map((s) => s.trim()).filter(Boolean) });
    });
    const awayent = pane.querySelector("[data-awayent]");
    if (awayent) {
      awayent.hass = this._hass;
      awayent.value = c.away_entity || "";
      awayent.includeDomains = ["input_boolean", "person", "device_tracker", "group", "binary_sensor", "sensor"];
      awayent.addEventListener("value-changed", () => { this._planDirty = false; this._set({ away_entity: awayent.value || null }); });
    }
    q("[data-osrc]").forEach((b) => b.onclick = () => this._set({ occupancy_sources: { [b.dataset.osrc]: !c.occupancy_sources[b.dataset.osrc] } }));
    q("[data-notify]").forEach((b) => b.onclick = () => this._set({ notify: { [b.dataset.notify]: !nOf(c)[b.dataset.notify] } }));
    const nent = pane.querySelector("[data-notifyent]");
    if (nent) {
      nent.hass = this._hass;
      nent.value = nOf(c).input_text || "";
      nent.includeDomains = ["input_text"];
      nent.addEventListener("value-changed", () => { this._planDirty = false; this._set({ notify: { input_text: nent.value || null } }); });
    }
    const textent = pane.querySelector("[data-textnotifyent]");
    if (textent) {
      textent.hass = this._hass;
      textent.value = nOf(c).text_entity || "";
      textent.includeDomains = ["text"];
      textent.addEventListener("value-changed", () => { this._planDirty = false; this._set({ notify: { text_entity: textent.value || null } }); });
    }
    q("[data-notifysvc]").forEach((s) => s.onchange = () => { this._planDirty = false; this._set({ notify: { notify_service: s.value || null } }); });
    q("[data-notifywhen]").forEach((s) => s.onchange = () => { this._planDirty = false; this._set({ notify: { when: s.value } }); });
    q("[data-open]").forEach((b) => b.onclick = () => { this._open = this._open === b.dataset.open ? null : b.dataset.open; this._update(); });
    q("[data-skiproom]").forEach((b) => b.onclick = () => this._act("skip_room", { room: b.dataset.skiproom, on: b.dataset.on === "1" }));
    q("[data-ignore]").forEach((b) => b.onclick = () => {
      const r = v.rooms.find((x) => x.key === b.dataset.ignore);
      this._set({ rooms: { [r.key]: { ignore_occupancy: !r.ignore_occupancy } } });
    });
    q("[data-person]").forEach((b) => b.onclick = () => {
      const now = v.people.filter((p) => p.included).map((p) => p.entity_id), id = b.dataset.person;
      const next = now.includes(id) ? now.filter((x) => x !== id) : [...now, id];
      this._set({ people: next.length === v.people.length ? null : next });
    });
    q("[data-sensor]").forEach((b) => b.onclick = () => {
      const r = v.rooms.find((x) => x.key === b.dataset.room), id = b.dataset.sensor;
      const rc = (c.rooms || {})[r.key] || {}, add = new Set(rc.add_sensors || []), rem = new Set(rc.remove_sensors || []);
      const auto = new Set([...r.sensors.filter((s) => s.source === "area").map((s) => s.entity_id), ...(r.removed || [])]);
      const chosen = r.sensors.some((s) => s.entity_id === id);
      if (chosen) { if (auto.has(id)) rem.add(id); else add.delete(id); }
      else { if (auto.has(id)) rem.delete(id); else add.add(id); }
      this._set({ rooms: { [r.key]: { add_sensors: [...add], remove_sensors: [...rem] } } });
    });
    q("[data-unman]").forEach((b) => b.onclick = () => {
      const rc = (c.rooms || {})[b.dataset.room] || {};
      const add = (rc.add_sensors || []).filter((x) => x !== b.dataset.unman);
      this._set({ rooms: { [b.dataset.room]: { add_sensors: add } } });
    });
    q("[data-addmanbtn]").forEach((b) => b.onclick = () => {
      const pick = pane.querySelector(`ha-entity-picker[data-addman="${CSS.escape(b.dataset.addmanbtn)}"]`);
      if (!pick || !pick.value) { this._notify("Pick an entity first"); return; }
      const rc = (c.rooms || {})[b.dataset.addmanbtn] || {};
      const add = new Set(rc.add_sensors || []);
      add.add(pick.value);
      this._set({ rooms: { [b.dataset.addmanbtn]: { add_sensors: [...add] } } });
    });
    // blur guard: a stale re-render while typing loses focus; re-render once free
    if (this._planDirty) {
      this._planDirty = false;
      this._update();
    }
  }
}

customElements.define("tapo-planner-panel", TapoPlannerPanel);
