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
const TABS = [["vacuum", "mdi:robot-vacuum", "Vacuum"], ["schedules", "mdi:calendar-clock", "Schedules"],
              ["planner", "mdi:calendar-check", "Planner"],
              ["history", "mdi:history", "History"], ["rooms", "mdi:floor-plan", "Rooms"],
              ["drive", "mdi:gamepad-variant", "Drive"], ["maintenance", "mdi:wrench", "Maintenance"],
              ["settings", "mdi:tune", "Settings"]];
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
const nOf = (c) => Object.assign({ persistent: false, input_text: null, notify_service: null, when: "start" }, c.notify || {});

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
.tabs { display: flex; gap: 6px; overflow-x: auto; scrollbar-width: none; margin-bottom: 12px; }
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

/* rooms and freshness, drive, maintenance */
.bar-row { display: grid; grid-template-columns: 110px 1fr 70px; gap: 10px; align-items: center; font-size: .86em; padding: 5px 0; }
.bar-row .track { height: 8px; border-radius: 4px; background: var(--secondary-background-color, rgba(127,127,127,.18)); overflow: hidden; }
.bar-row .track > div { height: 100%; border-radius: 4px; background: var(--vc-accent); }
.bar-row.warn .track > div { background: var(--warning-color, #ffa600); }
.bar-row.bad .track > div { background: var(--error-color, #db4437); }
.bar-row .r { text-align: right; color: var(--secondary-text-color); }
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
.mapwrap img { display: block; width: 100%; height: auto; }
.mapwrap svg { position: absolute; inset: 0; width: 100%; height: 100%; }
.mapwrap rect.room { cursor: pointer; fill: var(--vc-accent); fill-opacity: 0;
                     stroke: transparent; stroke-width: 2; }
.mapwrap rect.room:hover { fill-opacity: .18; }
.mapwrap rect.room.sel { fill-opacity: .32; stroke: var(--vc-accent); stroke-opacity: .9; }
.mapwrap rect.room.sel:hover { fill-opacity: .42; }
`;

class TapoPlannerPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._tab = "vacuum";
    this._cleanSel = new Set();
    this._mapPic = null;
    this._mapUrl = null;
    this._robot = null;
    this._editing = null;   // schedule being edited (object) or {} for new, or null
    this._records = null;   // get_clean_records response of the History tab
    this._recordsFor = null;
    this._open = null;      // room key whose sensor editor is open
    this._planRev = 0;      // re-render counter for planner updates
    this._planDirty = false; // an input is being edited: skip the live re-render
  }

  set panel(p) { this._panel = p; }
  set narrow(n) { this._narrow = n; this._layout(); }
  set route(r) { this._route = r; }
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
      this._tab = b.dataset.tab;
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
    this._dropSub();
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
      mapImage: find("image.", "map_image"),
      presets: all("button.").filter((id) => id.includes("preset")),
      switches: all("switch."), selects: all("select."), numbers: all("number."), times: all("time."),
      buttons: all("button.").filter((id) => !id.includes("preset")),
    };
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
    if (!this._robot || !robots.some((r) => r.entity_id === this._robot)) this._robot = robots[0].entity_id;
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
      this._open = null; this._editing = null; this._records = null; this._plan = null;
      this._dropSub();
      this._update(true);
    });
    this._renderLeft();
    this.shadowRoot.querySelectorAll(".tabs button").forEach((b) => b.classList.toggle("on", b.dataset.tab === this._tab));
    if (this._tab === "planner") this._ensurePlanSub(); else this._dropSub();
    const sig = JSON.stringify([this._tab, this._robot,
      this._editing ? String(this._editing.id != null ? this._editing.id : "new") : "",
      this._tab === "planner" ? [this._planRev, this._open] : this._relatedSig()]);
    if (!first && sig === this._paneSig) return;
    this._paneSig = sig;
    ({ vacuum: this._paneVacuum, schedules: this._paneSchedules, planner: this._panePlanner, history: this._paneHistory,
       rooms: this._paneRooms, drive: this._paneDrive, maintenance: this._paneMaintenance,
       settings: this._paneSettings }[this._tab]).call(this, pane);
  }

  _relatedSig() {
    const r = this._related(this._robot);
    const pick = (ids) => ids.map((id) => { const s = this._st(id); return s ? s.state + JSON.stringify(s.attributes) : ""; }).join("|");
    return pick([this._robot, r.camera, r.schedules, r.status, r.mapImage, ...r.switches, ...r.selects, ...r.numbers, ...r.times, ...r.presets]);
  }

  _renderLeft() {
    const left = this.shadowRoot.querySelector(".left");
    const vac = this._st(this._robot);
    if (!vac) { left.innerHTML = ""; return; }
    // the Lovelace card, when it is loaded as a resource; a compact status card otherwise
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
      if (card) { card.hass = this._hass; return; }
    }
    const sig = JSON.stringify([this._robot, vac.state, vac.attributes.battery_level]);
    if (sig === this._leftSig) return;
    this._leftSig = sig;
    const batt = vac.attributes.battery_level;
    left.innerHTML = `<ha-card><div class="card">
      <h3><span>Status</span></h3>
      <div class="line">${esc(vac.state)}</div>
      ${batt != null ? `<div class="quick-batt"><div class="bar ${batt <= 20 ? "due" : ""}"><div style="width:${batt}%"></div></div><span class="sub">${batt}%</span></div>` : ""}
      <div class="actions" style="margin-top:12px">
        <button class="btn primary" data-q="start"><ha-icon icon="mdi:play"></ha-icon>Clean</button>
        <button class="btn" data-q="pause"><ha-icon icon="mdi:pause"></ha-icon>Pause</button>
        <button class="btn" data-q="return_to_base"><ha-icon icon="mdi:home-import-outline"></ha-icon>Dock</button>
      </div>
    </div></ha-card>`;
    left.querySelectorAll("[data-q]").forEach((b) => b.onclick = () => this._call("vacuum", b.dataset.q, {}, { entity_id: this._robot }));
  }

  // ---- vacuum home tab ----------------------------------------------------------------
  _paneVacuum(pane) {
    const vac = this._st(this._robot), r = this._related(this._robot);
    const st = this._st(r.status), dnd = this._dnd(r), presets = this._presets(r);
    const cam = this._st(r.camera), geom = (cam && cam.attributes.room_geometry) || [];
    const mapName = cam ? cam.attributes.map_name : null;
    const batt = vac.attributes.battery_level;
    const state = st ? st.state : vac.state;
    pane.innerHTML = `
      <ha-card><div class="card">
        <h3><span>Vacuum</span><span class="note">${esc(state)}${mapName ? ` · map ${esc(mapName)}` : ""}</span></h3>
        ${batt != null ? `<div class="quick-batt"><div class="bar ${batt <= 20 ? "due" : ""}"><div style="width:${batt}%"></div></div><span class="sub">${batt}%</span></div>` : ""}
        ${dnd && dnd.enabled ? `<div class="drv-status live" style="margin-top:8px"><ha-icon icon="mdi:moon-waning-crescent"></ha-icon>Do Not Disturb until ${esc(dnd.end)}</div>` : ""}
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
        <h3><span>Map</span><span class="note">${geom.length ? "tap rooms to select" : ""}</span></h3>
        <div class="mapwrap"><img alt="Map"><svg></svg></div>
        ${geom.length ? `<div class="actions" style="margin-top:12px">
          <button class="btn primary" data-clean-sel disabled><ha-icon icon="mdi:play"></ha-icon><span>Clean selected</span></button>
          <button class="minibtn" data-clear-sel disabled>Clear</button></div>`
        : `<div class="empty">The vacuum has no rooms on its map yet — divide it into rooms in the Tapo app.</div>`}
      </div></ha-card>`;
    pane.querySelectorAll("[data-v]").forEach((b) => b.onclick = () => this._call("vacuum", b.dataset.v, {}, { entity_id: this._robot }));
    pane.querySelectorAll("[data-preset]").forEach((b) => b.onclick = () =>
      this._call(DOMAIN, "run_preset", { preset: b.dataset.preset }, { entity_id: this._robot }));
    this._wireVacMap(pane, geom);
  }

  async _wireVacMap(pane, geom) {
    const wrap = pane.querySelector(".mapwrap");
    if (!wrap) return;
    const img = wrap.querySelector("img"), svg = wrap.querySelector("svg");
    const r = this._related(this._robot);
    const pic = (r.mapImage && (this._st(r.mapImage) || {}).attributes && this._st(r.mapImage).attributes.entity_picture)
      || (r.camera ? `/api/camera_proxy/${r.camera}` : null);
    if (pic) {
      const url = pic.startsWith("http") ? pic : this._hass.hassUrl(pic);
      const show = (src) => {
        img.onload = () => this._drawRooms(svg, geom, img, pane);
        img.src = src;
        if (img.complete && img.naturalWidth) this._drawRooms(svg, geom, img, pane);
      };
      if (this._mapPic === url && this._mapUrl) { show(this._mapUrl); return; }
      try {
        const res = await fetch(url, { headers: { Authorization: `Bearer ${this._hass.auth.data.access_token}` } });
        if (!res.ok) return;
        if (this._mapUrl) URL.revokeObjectURL(this._mapUrl);
        this._mapPic = url;
        this._mapUrl = URL.createObjectURL(await res.blob());
        show(this._mapUrl);
      } catch (e) { /* map image stays hidden */ }
    }
  }

  _drawRooms(svg, geom, img, pane) {
    if (!img.naturalWidth) return;
    svg.setAttribute("viewBox", `0 0 ${img.naturalWidth} ${img.naturalHeight}`);
    svg.innerHTML = geom.map((g) => {
      const b = g.bbox || [0, 0, 0, 0];
      return `<rect class="room${this._cleanSel.has(g.name) ? "sel" : ""}" data-name="${esc(g.name)}"`
        + ` x="${b[0]}" y="${b[1]}" width="${Math.max(2, b[2] - b[0])}" height="${Math.max(2, b[3] - b[1])}">`
        + `<title>${esc(g.name)}</title></rect>`;
    }).join("");
    svg.querySelectorAll("rect.room").forEach((rc) => rc.onclick = () => {
      const name = rc.dataset.name;
      this._cleanSel.has(name) ? this._cleanSel.delete(name) : this._cleanSel.add(name);
      rc.classList.toggle("sel", this._cleanSel.has(name));
      const b = pane.querySelector("[data-clean-sel]"), c = pane.querySelector("[data-clear-sel]");
      if (b) { b.disabled = !this._cleanSel.size;
               b.querySelector("span").textContent = `Clean selected${this._cleanSel.size ? ` (${this._cleanSel.size})` : ""}`; }
      if (c) c.disabled = !this._cleanSel.size;
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
    if (this._tab !== "history") return;   // the user moved on while it loaded
    const d = this._records;
    const num = (x) => (x == null ? "–" : esc(x));
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
    <ha-card><div class="card"><h3><span>Recent runs</span></h3><div class="runs"></div></div></ha-card>`;
    const recs = d.recs;
    const runs = pane.querySelector(".runs");
    runs.innerHTML = recs.length ? recs.slice(0, 20).map((x) => {
      const dt = x.started ? new Date(x.started * 1000) : null;
      const when = dt ? dt.toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" }) + " " +
        dt.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" }) : "";
      const meta = [x.area != null ? `${x.area} m²` : null, x.minutes != null ? `${x.minutes} min` : null,
        START[x.start_type] || null, x.rule_name || null, x.emptied_bin ? "bin emptied" : null].filter(Boolean).join(" · ");
      return `<div class="row"><ha-icon icon="${x.error ? "mdi:alert-circle" : "mdi:robot-vacuum"}" style="color:${x.error ? "var(--error-color,#db4437)" : "var(--vc-accent)"}"></ha-icon>
        <div class="grow"><div class="t">${esc(when)}</div><div class="s">${esc(meta)}${x.error ? ` · error ${x.error}` : ""}</div></div></div>`;
    }).join("") : `<div class="empty">No runs recorded yet.</div>`;
    this._chart(pane.querySelector("canvas.chart"), this._perDay(recs, 30), (i) => (i % 7 === 0 ? `${29 - i}d` : ""));
    this._chart(pane.querySelector("canvas.weeks"), this._perWeek(recs, 8), (i) => (i === 7 ? "this wk" : `-${7 - i}`));
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
    const dpr = window.devicePixelRatio || 1, W = canvas.clientWidth || 400, H = 140;
    canvas.width = W * dpr; canvas.height = H * dpr;
    const ctx = canvas.getContext("2d"); ctx.scale(dpr, dpr);
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
  _paneMaintenance(pane) {
    const r = this._related(this._robot), vac = this._st(this._robot), cons = vac.attributes.consumables || {};
    const strip = (n) => String(n || "").replace(vac.attributes.friendly_name + " ", "");
    const bars = Object.entries(cons).map(([k, v]) =>
      `<div class="bar-row ${v <= 10 ? "bad" : v <= 30 ? "warn" : ""}"><span>${esc(k)}</span><div class="track"><div style="width:${v}%"></div></div><span class="r">${v}%</span></div>`).join("");
    const btns = r.buttons.map((id) => { const s = this._st(id);
      return `<button class="btn" data-btn="${esc(id)}"><ha-icon icon="${esc(s.attributes.icon || "mdi:gesture-tap-button")}"></ha-icon>${esc(strip(s.attributes.friendly_name))}</button>`; }).join(" ");
    pane.innerHTML = `<ha-card><div class="card"><h3><span>Consumables</span></h3>${bars || `<div class="empty">No consumable data.</div>`}</div></ha-card>
      <ha-card><div class="card"><h3><span>Actions</span></h3><div class="chips">${btns}</div></div></ha-card>`;
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
    pane.innerHTML = `<ha-card><div class="card"><h3><span>Settings</span></h3>${sw}${sel}${tim}${num}${(sw || sel || num || tim) ? "" : `<div class="empty">No settings entities.</div>`}</div></ha-card>`;
    pane.querySelectorAll("[data-sw]").forEach((b) => b.onclick = () => this._call("switch", b.classList.contains("on") ? "turn_off" : "turn_on", {}, { entity_id: b.dataset.sw }));
    pane.querySelectorAll("[data-sel]").forEach((e) => e.onchange = () => this._call("select", "select_option", { option: e.value }, { entity_id: e.dataset.sel }));
    pane.querySelectorAll("[data-num]").forEach((e) => e.onchange = () => this._call("number", "set_value", { value: Number(e.value) }, { entity_id: e.dataset.num }));
    pane.querySelectorAll("[data-time]").forEach((e) => e.onchange = () => { if (e.value) this._call("time", "set_value", { time: e.value + ":00" }, { entity_id: e.dataset.time }); });
  }

  // ---- planner --------------------------------------------------------------------------
  _panePlanner(pane) {
    const v = this._plan;
    if (this._planErr) { pane.innerHTML = `<ha-card><div class="card"><div class="err">${esc(this._planErr)}</div></div></ha-card>`; return; }
    if (!v) { pane.innerHTML = `<ha-card><div class="card"><div class="empty">Loading the planner…</div></div></ha-card>`; return; }
    pane.innerHTML = this._statusCard(v) + this._unmappedCard(v) + this._roomsCard(v) + this._conditionsCard(v) + this._notifyCard(v) + this._logCard(v);
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
