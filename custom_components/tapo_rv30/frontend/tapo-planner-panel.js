/* Tapo Planner sidebar page.
 *
 * The smart cleaning planner's home: which rooms are due, the conditions it waits for,
 * per-room sensors and targets, notifications and the decision log. Plain JavaScript,
 * no build step, in the same visual language as the VacuumCard-ADV card (pill buttons,
 * accent colour, robot disc header). Registered by the integration; toggle it in the
 * integration's options (Options -> Show planner page).
 *
 * Talks to the integration over three websocket commands:
 *   tapo_rv30/planner/subscribe | set | action
 */
const DOMAIN = "tapo_rv30";

const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const ago = (ts) => {
  if (!ts) return "never";
  const d = Math.max(0, Date.now() / 1000 - ts);
  if (d < 120) return "just now";
  if (d < 3600) return `${Math.round(d / 60)} min ago`;
  if (d < 86400 * 2) return `${Math.round(d / 3600)} h ago`;
  return `${Math.round(d / 86400)} days ago`;
};

const STYLE = `
:host { display: block; color: var(--primary-text-color); }
--vc-accent: var(--primary-color, #34e0d6);
--vc-dark: #0b0f14;
.wrap { max-width: 940px; margin: 0 auto; padding: 16px 16px 48px; display: grid; gap: 14px; }
@media (max-width: 700px) { .wrap { padding: 10px 10px 40px; } }

/* header, like the card's */
.head { display: flex; align-items: center; gap: 14px; padding: 4px 2px 0; }
.disc { width: 54px; height: 54px; border-radius: 50%; flex: none; display: grid; place-items: center;
        background: var(--vc-accent); color: var(--vc-dark); }
.disc ha-icon { --mdc-icon-size: 28px; }
.head .txt { min-width: 0; }
.head .name { font-size: 1.18em; font-weight: 700; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.head .status { color: var(--secondary-text-color); font-size: .92em; }
.robots { display: flex; gap: 6px; margin-left: auto; flex-wrap: wrap; }

ha-card, .card { background: var(--card-background-color); border: 1px solid var(--divider-color);
                 border-radius: 14px; padding: 14px 16px; }
h3 { margin: 0 0 10px; font-size: .95em; font-weight: 700; display: flex; align-items: center; gap: 8px; }
h3 .note { font-weight: 400; color: var(--secondary-text-color); font-size: .92em; margin-left: auto; }

/* pill buttons, exactly like the card */
.btn { border: 1px solid var(--vc-accent); color: var(--vc-accent); background: transparent;
       border-radius: 999px; padding: 8px 16px; font: inherit; font-size: .9em; font-weight: 600;
       cursor: pointer; display: inline-flex; align-items: center; gap: 6px; }
.btn:hover { background: var(--secondary-background-color, rgba(127,127,127,.12)); }
.btn.primary, .btn.on { background: var(--vc-accent); color: var(--vc-dark); }
.btn:disabled { opacity: .45; cursor: default; }
.btn ha-icon { --mdc-icon-size: 16px; }
.actions { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }

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
.chip.warn { border-color: var(--error-color, #db4437); color: var(--error-color, #db4437); }
.chip.info { border-color: var(--divider-color); }
.chip.btn { cursor: pointer; }
.chip.preview { border-color: var(--vc-accent); background: var(--vc-accent); color: var(--vc-dark); font-weight: 700; }

.line { font-size: 1.05em; font-weight: 600; margin: 2px 0 8px; }
.sub { color: var(--secondary-text-color); font-size: .88em; }

/* conditions / settings rows */
.row { display: flex; align-items: center; gap: 10px; padding: 9px 0; border-top: 1px solid var(--divider-color); }
.row:first-of-type { border-top: 0; }
.row .grow { flex: 1; min-width: 0; }
.row .t { font-size: .93em; }
.row .s { color: var(--secondary-text-color); font-size: .82em; }
.ctl { display: flex; align-items: center; gap: 8px; flex: none; }
.seg { display: flex; border: 1px solid var(--divider-color); border-radius: 999px; overflow: hidden; }
.seg button { border: 0; background: transparent; color: var(--secondary-text-color); padding: 6px 12px;
              font: inherit; font-size: .84em; cursor: pointer; }
.seg button.on { background: var(--vc-accent); color: var(--vc-dark); font-weight: 700; }

select, input[type=time], input[type=number], input[type=text] {
  color: var(--primary-text-color); background: var(--card-background-color);
  border: 1px solid var(--divider-color); border-radius: 6px; padding: 6px 8px; font: inherit; font-size: .86em; }
input[type=number] { width: 74px; }
ha-entity-picker { max-width: 300px; --ha-switch-checked-color: var(--vc-accent); }

/* rooms */
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
.minibtn:hover { border-color: var(--vc-accent); color: var(--vc-accent); }
.minibtn.danger:hover { border-color: var(--error-color, #db4437); color: var(--error-color, #db4437); }

.banner { display: flex; align-items: center; gap: 10px; padding: 10px 12px; border-radius: 10px;
          border: 1px solid var(--vc-accent); color: var(--vc-accent); font-size: .88em; margin-bottom: 10px; }
.banner .grow { flex: 1; }

.log .e { display: flex; gap: 10px; padding: 6px 0; border-top: 1px solid var(--divider-color); font-size: .88em; }
.log .e:first-of-type { border-top: 0; }
.log .e b { font-weight: 400; color: var(--secondary-text-color); width: 100px; flex: none; }
.empty { padding: 20px; text-align: center; color: var(--secondary-text-color); font-size: .9em; }
.err { color: var(--error-color, #db4437); font-size: .88em; }
`;

class TapoPlannerPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._robot = null;
    this._open = null;      // room key whose sensor editor is open
    this._rev = 0;          // re-render counter (keeps focus handling simple)
    this._dirty = false;    // an input is being edited: skip live re-render
  }

  set panel(p) { this._panel = p; }
  set narrow(n) { this._narrow = n; }
  set route(r) { this._route = r; }
  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (first) this._boot();
    else if (this._booted) this._render();
  }

  async _boot() {
    this.shadowRoot.innerHTML = `<style>${STYLE}</style>
      <div class="wrap"><div class="head"></div><div class="body"><div class="empty">Loading…</div></div></div>`;
    this._booted = true;
    this._render();
  }

  disconnectedCallback() { this._dropSub(); }

  // ---- data ------------------------------------------------------------------------
  _robots() {
    const reg = (this._hass && this._hass.entities) || {};
    return Object.values(this._hass.states).filter((s) =>
      s.entity_id.startsWith("vacuum.") && reg[s.entity_id] && reg[s.entity_id].platform === DOMAIN);
  }

  async _ensureSub() {
    if (this._for === this._robot || this._pending || !this._robot) return;
    this._dropSub();
    this._for = this._robot; this._pending = true; this._plan = null; this._planErr = null;
    try {
      this._unsub = await this._hass.connection.subscribeMessage((view) => {
        this._plan = view;
        this._rev++;
        const a = this.shadowRoot.activeElement;
        if (a && (a.tagName === "SELECT" || a.tagName === "INPUT" || a.tagName === "HA-ENTITY-PICKER")) {
          this._dirty = true; return;
        }
        this._render();
      }, { type: `${DOMAIN}_planner/subscribe`, entity_id: this._robot });
    } catch (e) {
      this._planErr = (e && e.message) || "The planner needs the v3.3 integration or newer.";
      this._render();
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
      if (view) { this._plan = view; this._dirty = false; this._render(); }
      return res;
    } catch (e) {
      this._notify((e && e.message) || "The planner refused that");
      return null;
    }
  }
  _set(config) { return this._ws({ type: `${DOMAIN}_planner/set`, config }); }
  _act(action, extra) { return this._ws({ type: `${DOMAIN}_planner/action`, action, ...(extra || {}) }); }

  _notify(message) {
    this.dispatchEvent(new CustomEvent("hass-notification", { detail: { message }, bubbles: true, composed: true }));
  }

  // ---- render ------------------------------------------------------------------------
  _render() {
    const robots = this._robots();
    const wrap = this.shadowRoot.querySelector(".wrap");
    if (!robots.length) {
      wrap.querySelector(".head").innerHTML = "";
      wrap.querySelector(".body").innerHTML = `<ha-card><div class="card"><div class="empty">No Tapo robot vacuum is set up yet.</div></div></ha-card>`;
      return;
    }
    if (!this._robot || !robots.some((r) => r.entity_id === this._robot)) this._robot = robots[0].entity_id;
    this._ensureSub();

    const st = this._hass.states[this._robot];
    const name = (st && st.attributes.friendly_name) || this._robot;
    const v = this._plan;
    const head = wrap.querySelector(".head");
    head.innerHTML = `
      <div class="disc"><ha-icon icon="mdi:robot-vacuum"></ha-icon></div>
      <div class="txt">
        <div class="name">${esc(name)}</div>
        <div class="status">${v ? esc(v.status) : "Loading the planner…"}</div>
      </div>
      ${robots.length > 1 ? `<div class="robots">${robots.map((r) =>
        `<button class="minibtn ${r.entity_id === this._robot ? "danger" : ""}" data-robot="${esc(r.entity_id)}"
           style="${r.entity_id === this._robot ? "border-color:var(--primary-color,#34e0d6);color:var(--primary-color,#34e0d6)" : ""}">${esc((this._hass.states[r.entity_id].attributes.friendly_name || r.entity_id))}</button>`).join("")}</div>` : ""}
    `;
    head.querySelectorAll("[data-robot]").forEach((b) => b.onclick = () => {
      this._robot = b.dataset.robot; this._open = null; this._dropSub(); this._render(); this._ensureSub();
    });

    const body = wrap.querySelector(".body");
    if (this._planErr) { body.innerHTML = `<ha-card><div class="card"><div class="err">${esc(this._planErr)}</div></div></ha-card>`; return; }
    if (!v) { body.innerHTML = `<ha-card><div class="card"><div class="empty">Loading the planner…</div></div></ha-card>`; return; }
    body.innerHTML = this._statusCard(v) + this._unmappedCard(v) + this._roomsCard(v) + this._conditionsCard(v) + this._notifyCard(v) + this._logCard(v);
    this._wire(body, v);
  }

  _statusCard(v) {
    const c = v.config, on = !!c.enabled, home = v.away && v.away.home;
    return `<ha-card><div class="card">
      ${c.preview ? `<div class="banner"><ha-icon icon="mdi:eye-outline"></ha-icon><span class="grow">Preview mode: the planner logs what it would do and never starts the robot.</span><button class="switch on" data-set="preview"></button></div>` : ""}
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
        ${c.preview ? "" : `<button class="btn" data-set="preview"><ha-icon icon="mdi:eye-off-outline"></ha-icon>Preview only</button>`}
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
            <div class="ctl"><ha-entity-picker data-addman="${esc(r.key)}" .hass=${this._hass} allow-custom-entity></ha-entity-picker>
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
        : `<div class="s" style="padding:0 0 8px">no people in Home Assistant</div>`) : `
      <div class="row">
        <div class="grow"><div class="t">Entity that knows</div>
          <div class="s">your input_boolean “someone home”, a tracker, a group — states below mean occupied</div></div>
        <div class="ctl"><ha-entity-picker data-awayent .hass=${this._hass} .value=${c.away_entity || null}
            .includeDomains=${["input_boolean", "person", "device_tracker", "group", "binary_sensor", "sensor"]}
            allow-custom-entity></ha-entity-picker></div>
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
        <div class="ctl"><ha-entity-picker data-notifyent .hass=${this._hass} .value=${n.input_text || null}
            .includeDomains=${["input_text"]} allow-custom-entity></ha-entity-picker></div>
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

  // ---- wiring ------------------------------------------------------------------------
  _wire(body, v) {
    const c = v.config, q = (sel) => body.querySelectorAll(sel);
    q("[data-set]").forEach((b) => b.onclick = () => this._set({ [b.dataset.set]: !c[b.dataset.set] }));
    q("[data-act]").forEach((b) => b.onclick = () => this._act(b.dataset.act, b.dataset.on != null ? { on: b.dataset.on === "1" } : {}));
    q("[data-mapping]").forEach((b) => b.onclick = () =>
      this.dispatchEvent(new CustomEvent("hass-more-info", { detail: { entityId: this._robot, view: "settings" }, bubbles: true, composed: true })));
    q("[data-target]").forEach((s) => s.onchange = () => { this._dirty = false; this._set({ rooms: { [s.dataset.target]: { target_days: Number(s.value) } } }); });
    q("[data-num]").forEach((s) => s.onchange = () => { this._dirty = false; this._set({ [s.dataset.num]: Number(s.value) }); });
    q("[data-win]").forEach((i) => i.onchange = () => {
      if (!i.value) return;
      const pair = [...c.windows[i.dataset.win]];
      pair[Number(i.dataset.i)] = i.value;
      this._dirty = false;
      this._set({ windows: { [i.dataset.win]: pair } });
    });
    q("[data-ret]").forEach((b) => b.onclick = () => this._set({ on_return: b.dataset.ret }));
    q("[data-runs]").forEach((s) => s.onchange = () => { this._dirty = false; this._set({ runs_per_window: s.value }); });
    q("[data-awaysrc]").forEach((s) => s.onchange = () => { this._dirty = false; this._set({ away_source: s.value }); });
    q("[data-awaystates]").forEach((i) => i.onchange = () => {
      this._dirty = false;
      this._set({ away_home_states: i.value.split(",").map((s) => s.trim()).filter(Boolean) });
    });
    const awayent = body.querySelector("[data-awayent]");
    if (awayent) {
      awayent.hass = this._hass;
      awayent.addEventListener("value-changed", () => { this._dirty = false; this._set({ away_entity: awayent.value || null }); });
    }
    q("[data-osrc]").forEach((b) => b.onclick = () => this._set({ occupancy_sources: { [b.dataset.osrc]: !c.occupancy_sources[b.dataset.osrc] } }));
    q("[data-notify]").forEach((b) => b.onclick = () => this._set({ notify: { [b.dataset.notify]: !nOf(c)[b.dataset.notify] } }));
    const nent = body.querySelector("[data-notifyent]");
    if (nent) {
      nent.hass = this._hass;
      nent.addEventListener("value-changed", () => { this._dirty = false; this._set({ notify: { input_text: nent.value || null } }); });
    }
    q("[data-notifysvc]").forEach((s) => s.onchange = () => { this._dirty = false; this._set({ notify: { notify_service: s.value || null } }); });
    q("[data-notifywhen]").forEach((s) => s.onchange = () => { this._dirty = false; this._set({ notify: { when: s.value } }); });
    q("[data-open]").forEach((b) => b.onclick = () => { this._open = this._open === b.dataset.open ? null : b.dataset.open; this._render(); });
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
      const pick = body.querySelector(`ha-entity-picker[data-addman="${CSS.escape(b.dataset.addmanbtn)}"]`);
      if (!pick || !pick.value) { this._notify("Pick an entity first"); return; }
      const rc = (c.rooms || {})[b.dataset.addmanbtn] || {};
      const add = new Set(rc.add_sensors || []);
      add.add(pick.value);
      this._set({ rooms: { [b.dataset.addmanbtn]: { add_sensors: [...add] } } });
    });
    // blur guard: a stale re-render while typing loses focus; re-render once free
    if (this._dirty) {
      this._dirty = false;
      this._render();
    }
  }
}

const nOf = (c) => Object.assign({ persistent: false, input_text: null, notify_service: null, when: "start" }, c.notify || {});

customElements.define("tapo-planner-panel", TapoPlannerPanel);
