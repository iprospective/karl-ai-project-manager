// views/worklog/Worklog — le worklog de la session, la ligne de MR partagée, les écrans de lot. Gestes en data-*. RM2889.
import { html, raw } from "../../core/html.js";
const muted = "color:var(--muted)";

/** RM2723 : rendu UNIQUE session + projet (la fiche projet le reçoit en prêt). */
export function MrLine(m) {
  return html`<div class="oline oq" style="white-space:normal">🔀 <b>!${m.iid}</b> ${m.ref ? m.ref + " " : ""}${m.target ? html`→ <span class="pill">${m.target}</span> ` : ""}${m.url ? html`<a href="${m.url}" target="_blank" rel="noopener">ouvrir ↗</a> ` : ""}${m.dead ? html`<span class="pill warn" title="la session qui l’a ouverte est éteinte">session éteinte</span> ` : ""}${m.url ? html`<button class="mini" title="Merger cette MR maintenant (pm-mr merge)" data-action="merge-one" data-url="${m.url}" data-iid="${m.iid}" data-target="${m.target}">⇥ merger</button>` : ""}</div>`;
}
/** RM3074 — une MR dans l'onglet : le ticket, le dépôt, le trajet, l'état, l'âge, et le geste. */
export function MrRow(m, { tip }) {
  return html`<div class="mrrow${m.mergeable ? " oq" : ""}"><div class="mrhead">🔀 <b>!${m.iid}</b>${m.ref
    ? (m.rm ? html` <span class="rmref"${raw(tip ? tip(m.rm) : "")} data-action="ticket" data-rm="${m.rm}">${m.ref}</span>` : html` <b>${m.ref}</b>`) : ""}${m.repo
    ? html` <span class="pill" title="dépôt">${m.repo}</span>` : ""}${m.source || m.target
    ? html` <span class="mrpath" title="branche source → cible">${m.source || "?"} → <b>${m.target || "?"}</b></span>` : ""}${m.age
    ? html` <span class="mrage" title="dernier mouvement connu">${m.age}</span>` : ""}</div><div class="mrfoot"><span class="pill ${m.mergeable ? "warn" : "ok"}" title="état sur la forge">${m.state}</span>${m.dead
    ? html`<span class="pill warn" title="la session qui l’a ouverte est éteinte">session éteinte</span>` : ""}${m.url
    ? html`<a href="${m.url}" target="_blank" rel="noopener">ouvrir ↗</a>` : ""}${m.url && m.mergeable
    ? html`<button class="mini" title="Merger cette MR maintenant (pm-mr merge)" data-action="merge-one" data-url="${m.url}" data-iid="${m.iid}" data-target="${m.target}">⇥ merger</button>` : ""}</div></div>`;
}

export function MrPane(groups, deps) {
  if (!groups.length) return html`<div class="empty">aucune MR dans cette session</div>`;
  return html`${groups.map(g => html`<div class="mrgroup"><div class="mrghead" title="${g.hint}">${g.icon} ${g.label} <span class="gcnt">${String(g.rows.length)}</span></div>${g.rows.map(m => MrRow(m, deps))}</div>`)}`;
}

export function Progress(p) {
  if (!p) return "";
  return html`${p.check ? html`<div class="wl-prog"><span class="pill ${p.check.cls}" title="critères d’acceptation cochés">${p.check.done}/${p.check.total} ✓</span>${p.check.items.map(t => html`<span class="wl-crit" title="critère restant">☐ ${t}</span>`)}${p.check.truncated ? html`<span class="wl-crit" style="opacity:.6">…</span>` : ""}</div>` : ""}${p.subs.length
    ? html`<div class="wl-prog">${p.subs.map((s, i) => html`${i ? " " : ""}<span class="pill" title="sous-tâche${s.title ? " — " + s.title : ""}">RM${s.rm}${s.status ? " · " + s.status : ""}</span>`)}</div>` : ""}`;
}
export function StatusPill(s) { return s.drifted ? html`<span class="pill warn" title="${s.tip}">${s.status}</span>` : html`<span class="pill">${s.status}</span>`; }
export function Stage(st) { if (!st) return ""; return st.url ? html` <span class="pill ${st.cls}" style="cursor:pointer" title="${st.tip}" data-action="mr-stage" data-url="${st.url}">${st.txt}</span>` : html` <span class="pill ${st.cls}" title="${st.tip}">${st.txt}</span>`; }

export function WorklogItem(it, { tip, pin }) {
  return html`<div class="oline" style="white-space:normal" title="${it.label || it.ref} — clic : ouvrir la fiche" data-action="open" data-ref="${it.ref}">${it.ticket
    ? html`<input type="checkbox" style="width:auto;margin-right:5px" title="Sélectionner pour un traitement en série" data-action="toggle" data-ref="${it.ref}" data-status="${it.status.status}" data-label="${it.label}"${it.selected ? " checked" : ""}>` : ""}${raw(pin("review", it.rm))}${it.ticket
    ? html`<span class="rmref"${raw(tip(it.rm))} data-action="ticket" data-rm="${it.rm}">${it.ref}</span>` : html`<b>${it.ref}</b>`} ${it.ticket
    ? html`<span style="cursor:pointer" title="Changer le statut (workflow)" data-action="status" data-ref="${it.ref}">${StatusPill(it.status)}</span>` : StatusPill(it.status)}${Stage(it.stage)}${it.label ? " " + it.label : ""}${it.branches.map(b => html` <span class="pill" title="branche du ticket">⎇ ${b}</span>`)}${it.next ? html`<div style="${muted};font-size:11px">→ ${it.next}</div>` : ""}${it.note ? html`<div style="${muted};font-size:11px">↳ ${it.note}</div>` : ""}${Progress(it.progress)}</div>`;
}
export function WorklogPane(vm, deps) {
  if (!vm.attached) return "";
  const notes = vm.notifications(), mrs = vm.mrs(), reqs = vm.requests(), qs = vm.questions();
  const head = html`${notes.length ? html`<div class="ms"><h4>🔔 notifications de la session (${notes.length})${vm.notificationsDone ? html` <span class="otag" title="traitées, gardées au worklog">${vm.notificationsDone} traitée${vm.notificationsDone > 1 ? "s" : ""}</span>` : ""}</h4>${notes.map(n => html`<div class="oline ${n.cls}" style="white-space:normal" title="${n.ts}">${n.icon} <span class="otag">${n.label}</span>${n.kind ? html`<span class="pill">${n.kind}</span> ` : ""}${n.ref ? html`<b>${n.ref}</b> ` : ""}${n.message}</div>`)}</div>` : ""}${mrs.length
    ? html`<div class="ms mrnudge" title="Le détail (dépôt, trajet, état, âge) est dans l’onglet MR" data-action="sub" data-key="mrs">🔀 <b>${String(mrs.length)}</b> MR à merger — voir l’onglet <b>MR</b> →</div>` : ""}${qs.length
    ? html`<div class="ms"><h4>❓ à trancher (${qs.reduce((a, q) => a + q.n, 0)})</h4>${qs.map(q => html`<div class="oline oq" style="white-space:normal">❓ <span class="rmref" data-action="review" data-rm="${q.rm}" title="Ouvrir la fiche du ticket à sa réflexion — c'est là que les questions se lisent et se tranchent">${q.ref}</span> <span class="otag">${String(q.n)}</span> question${q.n > 1 ? "s" : ""} sans réponse <button class="mini soft" data-action="review" data-rm="${q.rm}" title="Lire et trancher ces questions">→ trancher</button></div>`)}</div>` : ""}${reqs.length
    ? html`<div class="ms"><h4>📥 demandes à traiter (${reqs.length})</h4>${reqs.map(r => html`<div class="oline oq oreq" style="white-space:normal" title="${r.ts}">📥 <span class="otag">#${r.n}</span> ${r.text}${r.ticket ? html` <span class="rmref" data-action="ticket" data-rm="${r.ticket}" title="Le ticket qui la porte">RM${r.ticket}</span>` : ""}${r.note ? html` <span class="oreq-note">${r.note}</span>` : ""}<span class="oreq-acts">${r.suites.map(su => html`<button class="mini soft" data-action="request" data-n="${r.n}" data-status="${su.status}" title="${su.tip}">${su.icon} ${su.label}</button>`)}</span></div>`)}</div>` : ""}`;
  if (vm.empty) return html`${head}<div class="ms"><h4>worklog</h4><div style="${muted};font-size:11.5px">${vm.emptyText}</div></div>`;
  const buckets = vm.buckets(), orphan = vm.orphans(), { tabs, sub } = vm.tabs(orphan.length);
  const bucket = (key) => { const gs = buckets[key]; if (!gs) return html`<div class="empty">rien dans ce statut</div>`; return gs.map(g => g.key === null ? html`${g.items.map(it => WorklogItem(it, deps))}` : html`<div class="wlgroup"><div class="wlghead">${g.key} <span class="gcnt">${g.items.length}</span></div>${g.items.map(it => WorklogItem(it, deps))}</div>`); };
  const docsG = vm.docGroups();
  const docs = docsG.length ? docsG.map(g => html`<div style="margin:4px 0 1px"><b>${g.rm ? html`<span class="olink" title="Ouvrir la fiche ${g.ref}" data-action="ticket" data-rm="${g.rm}">${g.ref}</span>` : g.ref}</b></div>${g.docs.map(d => html`<div class="oline" style="white-space:normal">📄 ${raw(deps.linkify(d.name))}${d.kind ? html` <span class="pill">${d.kind}</span>` : ""}</div>`)}`) : html`<div class="empty">aucun document lié aux tickets de la session</div>`;
  const orphans = orphan.length ? html`<div style="margin:8px 0 2px;${muted};font-size:10.5px">🌿 autres branches (${orphan.length})</div><div class="rels">${orphan.map((b, i) => html`${i ? " " : ""}<span class="pill" title="branche ouverte par la session">⎇ ${b}</span>`)}</div>` : "";
  return html`${head}<div class="rsub">${tabs.map(t => html`<button class="${t.active ? "active" : ""}" data-action="sub" data-key="${t.key}">${t.label} (${t.n})</button>`)}</div><div class="ms">${sub === "mrs" ? MrPane(vm.mrGroups(), deps) : sub === "documents" ? docs : html`${buckets[sub] ? bucket(sub) : (sub === "todo" && orphan.length ? "" : html`<div class="empty">rien dans ce statut</div>`)}${sub === "todo" ? orphans : ""}`}</div>`;
}
// ── écrans de lot (dans la modale doc) ────────────────────────────────────────
export function BatchPlan(vm, { envoi }) {
  return html`<div class="ms"><h4>▶ à traiter (${vm.todo.length})</h4>${vm.todo.length ? vm.todo.map(t => html`<div class="oline" style="white-space:normal"><b>${t.n}.</b> <span class="r-id">RM${t.rm}</span> <span class="pill">${t.status}</span> ${t.title}<div style="${muted};font-size:11px">→ ${t.instruction}</div>${t.points.length
      ? html`<div class="bp-points">${t.points.map(p => html`<label class="bp-point"><input type="checkbox" checked data-ref="${t.rm}" data-i="${p.j}" value="${p.text}"> ${p.text}</label>`)}<div class="bp-hint">tous cochés = ticket entier · aucun coché = ticket écarté${t.truncated ? " · ⚠ liste de critères incomplète (le ticket en porte d’autres)" : ""}</div></div>` : ""}</div>`)
    : html`<div class="empty">aucun ticket actionnable dans la sélection</div>`}</div>${vm.skipped.length ? html`<div class="ms"><h4>⊘ écartés (${vm.skipped.length})</h4>${vm.skipped.map(s => html`<div class="oline" style="white-space:normal;opacity:.75"><span class="r-id">RM${s.rm}</span> ${s.title}<div style="${muted};font-size:11px">${s.reason}</div></div>`)}</div>` : ""}${vm.big
    ? html`<div class="ms" style="color:var(--warn)">⚠ ${vm.todo.length} tickets : au-delà de 10, la file déborde le contexte de l’agent — confirme seulement si tu sais pourquoi.</div>` : ""}<div style="display:flex;gap:8px;margin-top:12px"><button class="primary" data-action="send-batch">${envoi}</button><button class="mini" data-action="close">annuler</button></div><details style="margin-top:10px"><summary style="cursor:pointer;font-size:11.5px;${muted}">voir la consigne exacte</summary><pre class="logtail" style="white-space:pre-wrap">${vm.prompt}</pre></details>`;
}
export function MrBatch(vm) {
  return html`<div class="ms"><h4>${vm.title}</h4>${vm.runs.length ? vm.runs.map(r => html`<div class="oline" style="white-space:normal">${r.rms.map((i, k) => html`${k ? " " : ""}<span class="r-id">RM${i}</span>`)} <span class="pill">${r.source} → ${r.target}</span></div>`) : html`<div class="empty">rien à merger</div>`}</div>${vm.prod
    ? html`<div class="ms" style="color:var(--warn)">⚠ une promotion emporte TOUT ce que « ${vm.source} » contient et qui n’est pas encore en production — pas seulement les tickets cochés. Une MR par dépôt.</div>` : ""}${vm.live.length
    ? html`<div class="ms" style="color:var(--warn)">⚠ session encore vivante pour ${vm.live.map(i => "RM" + i).join(", ")} — merger maintenant, c’est merger sous les pieds d’un agent au travail.</div>` : ""}${vm.skipped.length
    ? html`<div class="ms"><h4>⊘ écartés (${vm.skipped.length})</h4>${vm.skipped.map(k => html`<div class="oline" style="white-space:normal;opacity:.75"><span class="r-id">RM${k.rm}</span><div style="${muted};font-size:11px">${k.reason}</div></div>`)}</div>` : ""}<div style="display:flex;gap:8px;margin-top:12px"><button class="primary" data-action="send-mr">⇥ merger maintenant</button><button class="mini" data-action="close">annuler</button></div>`;
}
export function ClosePlan(p) {
  return html`<div class="bp">${p.todo.length ? html`<h4>Seront fermés (${p.todo.length})</h4>${p.todo.map(t => html`<div class="bp-row"><b>RM${t.rm_id}</b> ${t.title} <span class="pill">${t.status}</span></div>`)}` : html`<div class="empty">aucun ticket fermable dans la sélection</div>`}${p.skipped.length
    ? html`<h4>Écartés (${p.skipped.length})</h4>${p.skipped.map(t => html`<div class="bp-row" style="opacity:.75"><b>RM${t.rm_id}</b> ${t.title} <span style="color:var(--warn)">— ${t.why}</span></div>`)}` : ""}<div class="bp-hint" style="margin-top:8px">Chaque fermeture passe par <code>pm-task-status-update</code>. Un ticket refusé (checklist non cochée, branche non mergée) reste ouvert et sera listé : il se traite depuis sa fiche, où le forçage se demande explicitement.</div></div><div style="display:flex;gap:8px;margin-top:12px">${p.count ? html`<button class="primary" data-action="send-close">✅ fermer maintenant</button>` : ""}<button class="mini" data-action="close">annuler</button></div>`;
}
export function CloseRefused(ko) {
  return html`<div class="bp">${ko.map(k => html`<div class="bp-row"><b>RM${k.rm_id}</b> <span style="color:var(--warn)">${k.why}</span></div>`)}<div class="bp-hint" style="margin-top:8px">À reprendre depuis la fiche de chaque ticket : le forçage (checklist, branche) s'y demande explicitement.</div></div>`;
}
