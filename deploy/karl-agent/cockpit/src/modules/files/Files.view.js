// views/files/Files — l'onglet fichiers de la colonne de droite. Balisage repris ; gestes en data-*. RM2889.
import { html, raw } from "../../core/html.js";
const muted = "color:var(--muted)";

export function Vocab(vm) {
  if (vm.loading) return html`<div class="empty">chargement du glossaire…</div>`;
  const head = html`<div style="margin:2px 0 6px"><input id="vocab-q" placeholder="filtrer un terme, une définition, un alias…" value="${vm.q}" style="width:100%;box-sizing:border-box;font-size:12px;padding:4px 6px"></div><div style="font-size:11px;${muted};margin-bottom:4px">${vm.count}</div>`;
  const rows = vm.list();
  if (!rows.length) return html`${head}<div class="empty">aucun terme ne correspond.</div>`;
  return html`${head}<table style="width:100%;font-size:12px"><thead><tr><th>Terme</th><th>Définition</th><th>Contexte</th></tr></thead><tbody>${rows.map(r => html`<tr><td><b>${r.terme}</b>${r.alias ? html`<div style="${muted};font-size:11px">alias : ${r.alias}</div>` : ""}</td><td>${r.definition}</td><td style="${muted}">${r.contexte}</td></tr>`)}</tbody></table>`;
}
const centerBtn = (action, wt, path, tag, quoi) => html`<button class="mini" data-action="${action}" data-wt="${wt}" data-path="${path}" data-tag="${tag}" title="Afficher ${quoi} dans un onglet du panneau central">⤢ au centre</button>`;

export function FilesPane(vm, { fileBody, vocab }) {
  const h = vm.header, git = vm.git, f = vm.file(), wt = vm.nav.wt || "", tag = vm.scopeTag;
  return html`${h ? html`<div class="rels" style="margin-bottom:6px"><span class="pill" title="Aucune session attachée : le panneau montre le projet courant">📁 ${h.project}</span><span class="pill" style="opacity:.75">${h.from}</span></div>` : ""}${vm.projectTabs.length
    ? html`<div class="rsub">${vm.projectTabs.map(t => html`<button class="${t.active ? "active" : ""}" title="${t.tip}" data-action="dir" data-wt="${t.wt}" data-path="">${t.label}</button>`)}</div>` : ""}${vm.rootTabs.length
    ? html`<div class="rsub">${vm.rootTabs.map(t => html`<button class="${t.active ? "active" : ""}${t.doc ? " doc" : ""}" title="${t.tip}" data-action="dir" data-wt="${t.wt}" data-path="">${t.icon ? t.icon + " " : ""}${t.name}</button>`)}</div>` : ""}${vm.isDoc
    ? html`<div class="rels" style="margin-bottom:6px"><span class="pill">📄 ${vm.docLabel}</span><span class="pill" title="Hors dépôt de code : ni branche ni commits">PM</span></div>${vm.hasGloss
        ? html`<div class="rsub"><button class="${vm.vocab ? "" : "active"}" data-action="vocab" data-on="0">fichiers</button><button class="${vm.vocab ? "active" : ""}" title="Vocabulaire métier du projet — ce qu'il faut savoir pour le comprendre (RM2675)" data-action="vocab" data-on="1">📖 vocabulaire</button></div>` : ""}` : ""}${vm.vocab
    ? Vocab(vocab())
    : html`${git ? html`<div class="rels" style="margin-bottom:6px"><span class="pill">⎇ ${git.branch}</span><span class="pill ${git.clean ? "ok" : "warn"}">${git.clean ? "clean" : git.dirty + " modifs"}</span>${git.untracked ? html`<span class="pill warn">${git.untracked} untracked</span>` : ""}${git.ahead ? html`<span class="pill">↑${git.ahead}</span>` : ""}${git.behind ? html`<span class="pill dang">↓${git.behind}</span>` : ""}<span class="pill" style="cursor:pointer" data-action="commits">${git.open ? "▾" : "▸"} commits</span></div>${git.open
        ? html`<div class="ms">${vm.commits().length ? vm.commits().map(c => c.clickable
            ? html`<div class="oline" style="white-space:normal;cursor:pointer" title="${c.author} — ⤢ ouvrir au centre" data-action="commit" data-hash="${c.hash}"><span class="r-id">${c.hash}</span> ${c.subject} <span style="${muted}">· ${c.date}</span></div>`
            : html`<div class="oline" style="white-space:normal" title="${c.author} — attache la session pour ouvrir le patch"><span class="r-id">${c.hash}</span> ${c.subject} <span style="${muted}">· ${c.date}</span></div>`)
          : html`<div style="${muted};font-size:11.5px">aucun commit</div>`}</div>` : ""}` : ""}${f
      ? html`<div style="display:flex;align-items:center;gap:8px;margin:4px 0"><button class="mini" data-action="back">‹ retour</button>${centerBtn("center-file", wt, f.path, tag, "ce fichier")}<b style="font-family:var(--mono);font-size:12px;word-break:break-all">${f.name}</b><span style="${muted};font-size:11px">${f.size}</span></div>${raw(fileBody(f.raw))}`
      : html`<div style="margin:2px 0 4px">${centerBtn("center-dir", wt, vm.nav.path || "", tag, "ce dossier")}</div><div style="font-size:11px;margin:2px 0 6px">${vm.crumbs.map((c, i) => html`${i ? html` <span style="${muted}">/</span> ` : ""}${c.last ? html`<b>${c.name}</b>` : html`<a href="#" data-action="dir" data-wt="${wt}" data-path="${c.path}">${c.name}</a>`}`)}</div>${vm.entries().length
        ? vm.entries().map(e => e.dir ? html`<div class="oline" style="white-space:normal;cursor:pointer" data-action="dir" data-wt="${wt}" data-path="${e.child}">📁 ${e.name}</div>`
                                        : html`<div class="oline" style="white-space:normal;cursor:pointer" data-action="open" data-name="${e.name}">📄 ${e.name}${e.size ? html` <span style="${muted};font-size:10px">${e.size}</span>` : ""}</div>`)
        : html`<div class="empty">dossier vide</div>`}`}`}`;
}
