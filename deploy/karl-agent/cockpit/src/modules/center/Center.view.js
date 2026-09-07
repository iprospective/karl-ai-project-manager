// views/center — onglets, historique, titre, contenus génériques. RM2889, cluster centre.
// Balisage repris de renderCenterTabs, histListHtml, renderCurTitle, fileViewHtml,
// dirViewHtml, mailViewHtml, clientViewHtml, confViewHtml, viewErrorHtml ; gestes en data-*.
import { html, raw } from "../../core/html.js";

export function Tabs(vm) {
  return html`${vm.entries().map(t => html`<span class="${t.cls}" data-action="activate" data-id="${t.id}" title="${t.tooltip}"><span>${t.icon}</span><span class="lbl">${t.label}</span>${t.fixed ? "" : html`<span class="pin" data-action="pin" data-id="${t.id}" title="${t.pinTitle}">${t.pinned ? "📌" : "⇧"}</span><span class="x" data-action="close" data-id="${t.id}" title="Fermer">✕</span>`}</span>`)}`;
}

export function History(vm) {
  const rows = vm.rows();
  if (!rows.length) return html`<div class="empty">aucune vue visitée pour l'instant</div>`;
  return html`${rows.map(r => html`<div class="histrow${r.cur ? " cur" : ""}${r.ouvert ? "" : " gone"}"${r.ouvert ? html` data-action="goto" data-id="${r.id}"` : ""} title="${r.title}"><span>${r.icon}</span> ${r.label}${r.cur ? html` <span class="pill">ici</span>` : ""}${r.ouvert ? "" : html` <span class="pill">fermée</span>`}</div>`)}`;
}

export function CenterTitle(vm) {
  switch (vm.mode) {
    case "view":  return html`${vm.icon} <span class="ttitle">${vm.viewLabel}</span>`;
    case "panel": return html`${vm.icon} <span class="ttitle">${vm.panelLabel}</span>`;
    case "home":  return html`📊 <span class="ttitle">tableau de bord</span>`;
    default:      return html`<span class="notabs">aucune vue — choisis une session dans « en cours »</span>`;
  }
}

/** Le CORPS d'un fichier — un seul rendu pour les trois vues (RM2861). Pas `.desc` : plafonné (RM2806). */
export function FileBody(vm) {
  return vm.markdown
    ? html`<div class="facetfull descfull mdview">${raw(vm.rendered)}</div>`
    : html`<pre class="logtail" style="white-space:pre-wrap;max-height:none">${vm.content}</pre>`;
}
export function FileView(vm) {
  return html`<div class="ms"><h4 style="font-family:var(--mono);word-break:break-all">${vm.title}<span style="color:var(--muted);font-weight:normal">${vm.sizeKo}</span></h4></div>${FileBody(vm)}`;
}

export function DirView(vm) {
  const cs = vm.crumbs();
  const link = (kind, path, label) => html`<a href="#" data-action="${kind}" data-src="${vm.src}" data-wt="${vm.wt}" data-path="${path}" data-tag="${vm.tag}">${label}</a>`;
  let h = html`<div class="ms"><h4>${cs.map((c, i) => html`${i ? html` <span style="color:var(--muted)">/</span> ` : ""}${i < cs.length - 1 ? link("open-dir", c.path, c.name) : html`<b>${c.name}</b>`}`)}</h4></div>`;
  if (!vm.entries.length) return html`${h}<div class="empty">dossier vide</div>`;
  return html`${h}${vm.entries.map(e => e.dir
    ? html`<div class="oline" style="white-space:normal;cursor:pointer" data-action="open-dir" data-src="${vm.src}" data-wt="${vm.wt}" data-path="${vm.child(e.name)}" data-tag="${vm.tag}">🗂 ${e.name}</div>`
    : html`<div class="oline" style="white-space:normal;cursor:pointer" data-action="open-file" data-src="${vm.src}" data-wt="${vm.wt}" data-path="${vm.child(e.name)}" data-tag="${vm.tag}">📄 ${e.name}${e.size != null ? html` <span style="color:var(--muted);font-size:10px">${Math.round(e.size / 102.4) / 10} Ko</span>` : ""}</div>`)}`;
}

export function MailView(vm) {
  return html`<div class="ms"><h4>${vm.subject}</h4>${vm.lines().map(([k, v]) => html`<div style="font-size:11.5px"><span style="color:var(--muted)">${k} </span>${v}</div>`)}</div>${vm.e.body
    ? html`<pre class="logtail" style="white-space:pre-wrap;max-height:none">${vm.e.body}${vm.e.body_truncated ? "\n\n…(tronqué à la relève)" : ""}</pre>`
    : html`<div class="empty">corps non disponible</div>`}`;
}

export function CommitView(short, message, patch) {
  return html`<div class="ms"><h4 style="font-family:var(--mono)">${short}</h4><div style="white-space:pre-wrap;font-size:12px">${message}</div></div>${patch}`;
}

export function ClientView(vm) {
  const kv = (k, v) => v ? html`<div class="kv"><span class="k">${k}</span><span class="v">${v}</span></div>` : "";
  const c = vm.e, contacts = vm.contacts();
  return html`<div class="ms"><h4>${vm.name}</h4>${vm.identity().map(([k, v]) => kv(k, v))}${kv("Redmine", c.redmine_project_url ? html`<a href="${c.redmine_project_url}" target="_blank">${c.redmine_project_id} ↗</a>` : (c.redmine_project_id || ""))}</div>${contacts.length
    ? html`<div class="ms"><h4>Contacts (${contacts.length})</h4>${contacts.map(p => html`<div class="kv"><span class="k">${p.nom}${p.internal ? html` <span class="pill">interne</span>` : ""}</span><span class="v">${p.det}</span></div>`)}</div>` : ""}${(vm.priority || vm.team.length)
    ? html`<div class="ms"><h4>Valeurs par défaut</h4>${kv("priorité", vm.priority)}${kv("équipe", vm.team.join(" · "))}</div>` : ""}<div class="ms"><h4>Projets (${vm.projects.length})</h4>${vm.projects.length
    ? vm.projects.map(p => html`<div class="oline" style="white-space:normal;cursor:pointer" data-action="open-project" data-value="${p.value}" title="Ouvrir la fiche de ${p.value}">📄 ${p.project}</div>`)
    : html`<div style="color:var(--muted);font-size:11.5px">aucun projet</div>`}</div>${vm.used.length
    ? html`<div class="ms"><h4>Projets utilisés (${vm.used.length})</h4><div style="font-size:11.5px">${vm.used.join(" · ")}</div><div style="color:var(--muted);font-size:11px;margin-top:4px">Projets d'un autre client, partagés avec celui-ci.</div></div>` : ""}${vm.docs.length
    ? html`<div class="ms"><h4>Docs client</h4><ul class="doclist">${vm.docs.map(d => html`<li data-action="open-file" data-src="doc" data-wt="" data-path="${d.path}" data-tag="">📄 ${d.name}</li>`)}</ul></div>` : ""}`;
}

/** La conf est rendue TELLE QUELLE : la reformater masquerait ce qu'on vient vérifier. */
export function ConfView(c) {
  c = c || {};
  return html`<div class="ms"><h4>⚙ ${c.label || c.client || "conf"} <span style="color:var(--muted);font-weight:normal;font-family:var(--mono)">${c.name || "meta.yml"}</span></h4><div style="color:var(--muted);font-size:11px">Lecture seule — les mutations passent par l'outillage PM (<code>mmi-pm</code>), jamais par une édition à la main.</div></div><pre class="logtail" style="white-space:pre-wrap;max-height:none">${c.content || ""}</pre>`;
}

/** Une source disparue DOIT se dire : un onglet épinglé survit à ce qu'il montrait. */
export function ViewError(quoi, message) {
  return html`<div class="ms"><h4>${quoi}</h4><div style="color:var(--warn);font-size:12px">${message || "contenu indisponible"}</div><div style="color:var(--muted);font-size:11.5px;margin-top:6px">La source a pu disparaître depuis l'ouverture de cet onglet (session fermée, fichier déplacé, email traité). Ferme l'onglet ou rouvre depuis son panneau.</div></div>`;
}

/** Bouton « ⤢ au centre » posé dans une vue historique (chaîne onclick prêtée au monolithe). */
export function centerBtnHtml(call, quoi) {
  return '<button class="mini" onclick="' + call + '" title="Afficher ' + quoi + ' dans un onglet du panneau central">⤢ au centre</button>';
}
