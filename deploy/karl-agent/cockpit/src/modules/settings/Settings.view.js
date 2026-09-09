// views/settings — la carte « 🔧 Réglages » et la carte thème. RM2889, L5.
// Balisage repris de loadSettings (createElement → gabarit) ; gestes en data-*.
import { html } from "../../core/html.js";

export function SettingsBody(vm) {
  return html`${vm.groups().map(g => html`<details${g.open ? " open" : ""}><summary style="cursor:pointer;font-size:11px;text-transform:uppercase;color:var(--muted);margin:6px 0">${g.name} (${g.entries.length})</summary>${g.entries.map(e =>
    html`<div style="display:flex;align-items:center;gap:8px;margin:5px 0" data-key="${e.key}">${e.type === "bool"
      ? html`<input type="checkbox" style="width:auto" data-setting="bool"${e.value ? " checked" : ""}><span style="font-size:12px;flex:1">${e.label}</span>`
      : e.type === "enum"
      ? html`<span style="font-size:12px;flex:1">${e.label}</span><select style="width:110px" data-setting="enum">${e.options.map(o => html`<option value="${o}"${o === e.value ? " selected" : ""}>${o}</option>`)}</select>`
      : html`<span style="font-size:12px;flex:1">${e.label}${e.pinned ? html` <span style="color:var(--muted)">🔒</span>` : ""}</span><input type="number" step="0.01" value="${e.value != null ? e.value : ""}" style="width:90px"${e.pinned ? html` disabled title="figé par ${e.pinned} (.env)"` : ""}><button class="mini" data-action="save"${e.pinned ? html` disabled title="figé par ${e.pinned} (.env)"` : ""}>💾</button>`}</div>`)}</details>`)}`;
}

export function SettingsCard(body) {
  return html`<h2>🔧 Réglages <span style="color:var(--muted);font-weight:normal">(whitelist RM2213)</span> <button class="helpq" data-action="help" title="Aide sur ce panneau">?</button></h2><div id="reglages-body" style="margin-top:8px">${body === undefined ? html`<div style="color:var(--muted)">chargement…</div>` : body}</div>`;
}

export function ThemeCard({ local, hint, showClientCtx }) {
  const opt = (v, l) => html`<option value="${v}"${v === (local || "server") ? " selected" : ""}>${l}</option>`;
  return html`<h2>🎨 Thème &amp; affichage <span style="color:var(--muted);font-weight:normal">(ce navigateur)</span></h2><label for="th-local">Apparence</label><select id="th-local" data-theme-local>${opt("server", "suivre la conf serveur")}${opt("auto", "auto (thème système)")}${opt("dark", "sombre")}${opt("light", "clair")}</select><div id="th-hint" style="color:var(--muted);font-size:11.5px;margin-top:6px">${hint}</div><label style="display:flex;align-items:center;gap:7px;cursor:pointer;margin-top:10px" title="Le contexte client (pré-filtre global, RM2639) reste appliqué même masqué (RM3063)"><input type="checkbox" data-show-clientctx${showClientCtx ? " checked" : ""}><span>Afficher le filtre « Clients » dans l'en-tête</span></label>`;
}
