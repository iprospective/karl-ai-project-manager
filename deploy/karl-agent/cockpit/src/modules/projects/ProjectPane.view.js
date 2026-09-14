// views/projects/ProjectPane — la fiche projet au centre (RM2353/2590/2531/2696). Balisage repris ; data-action partout.
import { html, raw } from "../../core/html.js";
import { pillClass } from "../../core/status.js";

export function SessionPills(vm) {
  const ss = vm.sessions(); if (!ss.length) return "";
  return html`<div class="ms"><h4>Sessions en cours</h4><div class="rels">${ss.map(s => html`<span class="pill" style="cursor:pointer" data-action="attach" data-sid="${s.sid}"><span class="tdot st-${s.state}" style="margin-right:4px"></span>${s.label}</span>`)}</div></div>`;
}
const TkRow = (t, titleLink) => html`<div class="oline" style="white-space:normal" data-action="ticket" data-rm="${t.rm_id}" title="Détail dans l’encart ℹ"><span class="r-id">RM${t.rm_id}</span> <span class="${pillClass(t.status)}">${t.status}</span> ${raw(titleLink(t.rm_id, t.title))}${t.when ? html` <span style="color:var(--muted)">· ${t.when}</span>` : ""}</div>`;

export function ProjectHeader(vm) {
  return html`<div style="display:flex;align-items:baseline;gap:12px;flex-wrap:wrap"><h2 style="font-size:16px;text-transform:none;letter-spacing:0;color:var(--fg)">📁 ${vm.key}</h2>${vm.e.name ? html`<span style="color:var(--muted)">${vm.e.name}</span>` : ""}<span style="flex:1"></span><button class="mini" data-action="conf" data-scope="project" title="Modifier la conf du projet (meta.yml)">✎ conf projet</button><button class="mini" data-action="conf" data-scope="client" title="Modifier la conf du client ${vm.clientKey} (meta.yml)">✎ conf client</button><button class="mini" data-action="close">✕ fermer</button></div><div class="rsub" style="margin:8px 0 4px"><button class="${vm.tab === "worklog" ? "" : "active"}" data-action="tab" data-tab="fiche">📋 fiche</button><button class="${vm.tab === "worklog" ? "active" : ""}" data-action="tab" data-tab="worklog">🗒 worklog</button></div>`;
}

export function ProjectSheet(vm, titleLink, files) {
  const d = vm.e;
  return html`${ProjectHeader(vm)}<div class="rels" style="margin:10px 0 14px">${vm.links.map(l => l.kind === "a" ? html`<a class="pill" href="${l.href}" target="_blank">${l.label}</a>` : html`<span class="pill" title="${l.title || ""}">${l.label}</span>`)}</div>${SessionPills(vm)}${vm.environments.length
    ? html`<div class="ms"><h4>Environnements</h4>${vm.environments.map(e => html`<div class="kv"><span class="k">${e.name || "?"}</span><span class="v">${e.url ? html`<a href="${e.url}" target="_blank">${e.url} ↗</a>` : "—"}</span></div>`)}</div>` : ""}${vm.docs.length
    ? html`<div class="ms"><h4>Docs projet</h4><ul class="doclist">${vm.docs.map(doc => html`<li data-action="doc" data-path="${doc.path}" data-name="${doc.name}">📄 ${doc.name}</li>`)}</ul></div>` : ""}${vm.byStatus.length
    ? html`<div class="ms"><h4>Tickets ouverts</h4><div class="rels" style="margin-bottom:8px">${vm.byStatus.map(s => html`<span class="${pillClass(s.status)}">${s.status} : ${s.n}</span>`)}</div>${vm.openRecent.map(t => TkRow(t, titleLink))}</div>` : ""}${vm.closedRecent.length
    ? html`<div class="ms"><h4>Derniers tickets traités</h4>${vm.closedRecent.map(t => TkRow(t, titleLink))}</div>` : ""}<div class="ms"><h4>🗂 Fichiers / worktrees du projet</h4><div id="projfiles">${files !== undefined ? files : html`<div class="empty">chargement…</div>`}</div></div>`;
}

export function ProjectWorklog(vm, mrLine) {
  if (vm.empty) return html`<div class="empty">rien en cours sur ce projet.</div>`;
  const row = t => html`<div class="oline" style="white-space:normal" data-action="ticket" data-rm="${t.rm_id}" title="Ouvrir la fiche du ticket"><span class="r-id">RM${t.rm_id}</span> <span class="${pillClass(t.status)}">${t.status}</span>${t.prog ? html` <span class="pill${t.prog.ok ? " ok" : ""}">${t.prog.done}/${t.prog.total} ✓</span>` : ""}${t.cold ? html` <span class="pill warn" title="ticket en cours, mais aucune session vivante ne le traite">💤 à reprendre</span>` : ""} ${t.title}<div style="margin-top:2px">${t.sessions.length ? t.sessions.map((s, i) => html`${i ? " " : ""}<span class="pill" title="session qui traite ce ticket">${s}</span>`) : html`<span class="pill warn" title="aucune session, vivante ou éteinte, ne parle de ce ticket">sans session</span>`}</div></div>`;
  const listing = (l, empty) => l.total ? html`${l.shown.map(row)}${l.more ? html`<div style="color:var(--muted);font-size:11px;margin-top:4px">… et ${l.more} autre(s) — la liste complète est dans la fiche du projet</div>` : ""}` : html`<div class="empty">${empty}</div>`;
  const active = vm.list("active"), waiting = vm.list("waiting");
  return html`<div class="rels" style="margin-bottom:10px">${vm.counts.map(c => html`<span class="pill ${c.cls}">${c.n} ${c.txt}</span>`)}</div>${vm.mrs.length
    ? html`<div class="ms"><h4>🔀 MR à merger (${vm.mrs.length})</h4>${vm.mrs.map(m => raw(mrLine(m)))}</div>` : ""}${vm.requests.length
    ? html`<div class="ms"><h4>📥 demandes non ticketées (${vm.requests.length})</h4>${vm.requests.map(r => html`<div class="oline" style="white-space:normal">📥 ${String(r.text || "")}</div>`)}</div>` : ""}<div class="ms"><h4>🔨 en cours (${active.total})</h4>${listing(active, "rien en cours")}</div><div class="ms"><h4>⏳ en attente d’un geste (${waiting.total})</h4>${waiting.total ? html`<div class="rels" style="margin-bottom:6px">${vm.waitingByStatus.map(s => html`<span class="${pillClass(s.status)}">${s.status} : ${s.n}</span>`)}</div>` : ""}${listing(waiting, "rien en attente")}</div>${vm.sessions.length
    ? html`<div class="ms"><h4>🖥 sessions du projet (${vm.live}/${vm.sessions.length})</h4><div class="rels">${vm.sessions.map(s => html`<span class="pill${s.alive ? " ok" : ""}" style="cursor:pointer" title="${s.title}${s.alive ? " — ouverte" : " — éteinte"}" data-action="attach" data-sid="${s.sid}">${s.sid}</span>`)}</div></div>` : ""}`;
}

export function ProjectFiles(vm, fileBody) {
  const wts = vm.worktrees;
  if (!vm.wt) {
    if (!wts.length) return html`<div class="empty">aucun worktree pour ce projet.</div>`;
    return html`<div style="max-height:340px;overflow-y:auto">${wts.map(w => html`<div class="oline" style="white-space:normal;cursor:pointer" title="${w.path}" data-action="wt" data-path="${w.path}">📂 ${w.name}${w.is_git ? html` <span class="pill">⎇ ${w.branch}</span><span class="pill ${w.clean ? "ok" : "warn"}">${w.clean ? "clean" : w.dirty + " modifs"}</span>` : ""}</div>`)}</div>`;
  }
  const cur = vm.current, f = vm.e.file;
  return html`<div style="margin-bottom:6px"><button class="mini" data-action="wts">‹ worktrees</button> <b style="font-family:var(--mono);font-size:12px">${cur.name || ""}</b>${cur.is_git ? html` <span class="pill">⎇ ${cur.branch}</span>` : ""}</div>${f
    ? html`<div style="display:flex;align-items:center;gap:8px;margin:4px 0"><button class="mini" data-action="browse" data-path="${vm.e.path || ""}">‹ retour</button><b style="font-family:var(--mono);font-size:12px;word-break:break-all">${f.name}</b></div>${raw(fileBody(f))}`
    : html`<div style="font-size:11px;margin:2px 0 6px">${vm.crumbs.map((c, i, a) => html`${i ? html` <span style="color:var(--muted)">/</span> ` : ""}${i < a.length - 1 ? html`<a href="#" data-action="browse" data-path="${c.path}">${c.name}</a>` : html`<b>${c.name}</b>`}`)}</div><div style="max-height:340px;overflow-y:auto">${vm.entries.length ? vm.entries.map(e => e.dir ? html`<div class="oline" style="white-space:normal;cursor:pointer" data-action="browse" data-path="${vm.child(e.name)}">📁 ${e.name}</div>` : html`<div class="oline" style="white-space:normal;cursor:pointer" data-action="open" data-name="${e.name}">📄 ${e.name}</div>`) : html`<div class="empty">dossier vide</div>`}</div>`}`;
}

export function ConfigForm(vm) {
  const row = (r) => html`<label for="${r.id}" style="display:block;margin-top:10px;font-size:12px;color:var(--muted)">${r.label}</label><input id="${r.id}" data-cfg="${r.field}" type="text" value="${r.value == null ? "" : r.value}" style="width:100%;box-sizing:border-box;padding:7px 9px;border:1px solid var(--line);border-radius:6px;background:var(--bg);color:var(--fg);font-family:var(--mono);font-size:13px">`;
  return html`<div style="display:flex;align-items:baseline;gap:12px"><h2 style="font-size:16px;text-transform:none;letter-spacing:0;color:var(--fg)">${vm.title}</h2><span class="pill warn">mutation meta.yml</span><span style="flex:1"></span><button class="mini" data-action="cancel">✕ annuler</button></div><div style="max-width:560px">${vm.rows().map(row)}<div style="margin-top:14px;display:flex;gap:8px"><button class="primary" data-action="save" data-scope="${vm.ctx.scope}">✓ Enregistrer</button><button class="mini" data-action="cancel">Annuler</button></div><div style="margin-top:8px;color:var(--muted);font-size:11px">Laisser un champ vide = ne pas y toucher. Écrit meta.yml (édition ciblée) + commit auto.</div></div>`;
}
