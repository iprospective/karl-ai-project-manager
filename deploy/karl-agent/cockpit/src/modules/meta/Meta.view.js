// views/tickets/Meta — l'encart ℹ : onglet « infos » (session) et onglet « tickets » (facettes). Balisage repris ; gestes en data-*. RM2889.
import { html, raw } from "../../core/html.js";
import { pillClass } from "../../core/status.js";
const muted = "color:var(--muted)";
const kv = (k, v, kStyle) => html`<div class="kv"><span class="k"${kStyle ? html` style="${kStyle}"` : ""}>${k}</span><span class="v">${v}</span></div>`;

export function Usage(vm, sid) {
  const h = vm.head(), st = vm.stats();
  return html`<div class="ms"><h4>Session en direct <span class="pill" style="cursor:pointer" title="Rafraîchir la conso de la session" data-action="refresh-usage" data-rm="${sid}">↻</span> <span class="pill" style="cursor:pointer" title="Copier le récap dans le presse-papier" data-action="copy-infos" data-rm="${sid}">⧉ copier</span></h4>${h
    ? html`${kv("outil", h.engine)}${h.model ? kv("modèle", h.model) : ""}${h.cost ? html`<div class="kv"><span class="k">coût actuel</span><span class="v"${h.ratesKnown ? html` title="${h.ratesTip}"` : ""}>${h.cost}${h.ratesKnown ? "" : html` <span style="${muted}">(tarif inconnu)</span>`}</span></div>` : ""}` : ""}${vm.kind === "loading" ? html`<span style="${muted}">…</span>`
    : vm.kind === "unavailable" ? html`<span style="${muted}">indisponible</span>`
    : vm.kind === "notranscript" ? html`<span style="${muted}">transcript claude indisponible${vm.engineNote}</span>`
    : html`<div class="kv"><span class="k">tokens</span><span class="v" title="entrée + sortie (le cache n'est pas compté dans le total — RM2519)">${st.total}</span></div><div class="kv"><span class="k">↳ entrée<span style="${muted}"> (hors cache)</span></span><span class="v" title="entrée NON cachée seulement. Tout ce qui est relu à chaque tour (NORMS, historique, résultats d'outils) est compté sur la ligne « cache lu / écrit » — RM2628">${st.input}</span></div><div class="kv"><span class="k">↳ sortie</span><span class="v" title="tokens générés par l'agent, raisonnement compris — une réponse est comptée une fois, pas une fois par bloc de contenu (RM2628)">${st.output}</span></div><div class="kv"><span class="k" style="${muted}">cache lu / écrit</span><span class="v" style="${muted}" title="information complémentaire, hors total (facturé à d'autres taux)">${st.cache}</span></div><div class="kv"><span class="k">contexte courant</span><span class="v" title="occupation de la fenêtre de contexte au dernier tour (entrée + cache)">${st.context}${st.contextPct ? html` <span style="${muted}">(${st.contextPct})</span>` : ""}</span></div>${kv("tours IA", st.turns)}${st.rate ? html`<div class="kv"><span class="k">débit</span><span class="v" title="moyenne depuis la création">${st.rate}</span></div>` : ""}`}${vm.dates().map(d => html`<div class="kv"><span class="k">${d.k}</span><span class="v" title="${d.v}">${d.v}</span></div>`)}</div>`;
}

export function SessionInfos(vm) {
  if (!vm.attached) return html`<div class="empty">attache une session pour voir ses infos.</div>`;
  const reg = vm.registry;
  return html`<div class="ms"><h4>Session</h4>${kv("libellé", vm.label ? vm.label : html`<span style="${muted}">—</span>`)}${kv("tmux", vm.tmux)}${reg
    ? kv("session PM", html`#${reg.seq}${reg.machine ? " · m" + reg.machine : ""}${reg.created ? " · " + reg.created : ""}`) : ""}${vm.conflicts.map(c => html`<div style="margin-top:4px"><span class="pill dang">⚠ RM${c.rm} aussi ouvert en session ${c.seqs}</span></div>`)}</div>${Usage(vm.usage(), vm.sid)}`;
}

/** Un RM-id cliquable → détail de CE ticket dans l'encart (RM2173). `tip` = attributs d'infobulle prêtés par le monolithe (RM2619). */
const rmLink = (id, tip) => html`<span class="pill" style="cursor:pointer"${raw(tip(id))} data-action="ticket" data-rm="${id}">RM${id}</span>`;

export function ProjectBrief(vm) {
  if (!vm.shown) return "";      // ticket non résolu : pas de bloc vide
  return html`<div class="ms"><h4>Client / projet</h4>${kv("client", html`${vm.clientName}${vm.clientId ? html` <span class="pill" style="opacity:.7">${vm.clientId}</span>` : ""}`)}${kv("projet", html`${vm.name} <span class="pill" style="cursor:pointer" title="Ouvrir la fiche du projet" data-action="project" data-key="${vm.key}">🗂 fiche</span>${vm.redmineUrl ? html` <a href="${vm.redmineUrl}" target="_blank" rel="noopener">Redmine ↗</a>` : ""}`)}${vm.open !== null
    ? kv("tickets", html`${vm.open} ouvert${vm.open > 1 ? "s" : ""}${vm.total ? " / " + vm.total : ""}`) : ""}${vm.repo
    ? kv("dépôt", html`${vm.repo}${vm.branch ? html` <span class="pill">${vm.branch}</span>` : ""}`) : ""}</div>`;
}

export function TicketDetail(vm, { tip }) {
  const d = vm.detail(), rm = d.rm;
  return html`<div class="ms"><h4>Ticket</h4><div class="kv"><span class="k">id</span><span class="v">${d.redmineUrl ? html`<a href="${d.redmineUrl}" target="_blank">RM${rm} ↗</a>` : "RM" + rm} <span class="pill" style="cursor:pointer" title="Pré-remplir le lanceur avec ce ticket" data-action="launcher" data-rm="${rm}">→ lanceur</span> <span class="pill" style="cursor:pointer" title="Ouvrir la fiche complète du ticket (protocole de test, description, env, verdict)" data-action="review" data-rm="${rm}">🗂 fiche</span> <span class="pill" style="cursor:pointer" title="Recharger ce ticket depuis le disque (description, statut, chiffrage)" data-action="reload" data-rm="${rm}">↻</span></span></div>${d.freshness
    ? html`<div class="kv"><span class="k" style="${muted}">version</span><span class="v" style="${muted}" title="dernière écriture du ticket : ${d.freshness.stamp}">${d.freshness.stamp}${d.freshness.since ? html` <span style="opacity:.75">(${d.freshness.since})</span>` : ""}</span></div>` : ""}<div style="margin:4px 0">${d.title}</div>${kv("type", d.type)}<div class="kv"><span class="k">phase</span><span class="v"><span class="${pillClass(d.status)}" style="cursor:pointer" title="Changer le statut — transitions du workflow depuis « ${d.status || "?"} »" data-action="status" data-rm="${rm}">${d.status || "—"} ⇄</span>${d.closed
    ? html` <span class="pill" style="cursor:pointer" title="Rouvrir le ticket (ferme → a_faire, motif requis)" data-action="reopen" data-rm="${rm}">↻ rouvrir</span>` : ""}</span></div>${kv("priorité", d.priority)}${kv("avancement", d.pct)}</div>${ProjectBrief(vm.brief())}${d.envs.length
    ? html`<div class="ms"><h4>Environnement (selon phase)</h4>${d.envs.map(e => e.kind === "active"
        ? html`<div class="kv"><span class="k"><span class="pill ok">${e.name}</span></span><span class="v">${e.url ? html`<a href="${e.url}" target="_blank">ouvrir ↗</a>` : "—"}</span></div>`
        : html`<div class="kv"><span class="k"${e.kind === "other" ? html` style="${muted}"` : ""}>${e.name}</span><span class="v"><a href="${e.url}" target="_blank">↗</a></span></div>`)}</div>` : ""}${d.git
    ? html`<div class="ms"><h4>Git ticket</h4>${d.git.branch ? kv("branche", d.git.branch) : ""}${d.git.mrUrl ? kv("MR", html`<a href="${d.git.mrUrl}" target="_blank">↗</a>`) : ""}</div>` : ""}${d.rels.length
    ? html`<div class="ms"><h4>Relations</h4>${d.rels.map(p => html`<div style="margin-bottom:4px"><span style="${muted}">${p.label} :</span> <span class="rels">${p.ids.map((id, i) => html`${i ? " " : ""}${rmLink(id, tip)}`)}</span></div>`)}</div>` : ""}<div class="ms"><h4>Contenu</h4><div class="rels"><button class="chip" data-action="facet" data-facet="desc">${d.hasDesc ? "📄 description" : "📄 description (vide)"}</button><button class="chip" data-action="facet" data-facet="log">${d.hasLog ? "🕘 historique" : "🕘 historique (vide)"}</button></div></div>`;
}

/** RM2797/RM2806 : la description occupe la zone — ni cadre ni bride, c'est la colonne qui défile. */
export function TicketDesc(text, { md }) {
  if (!text) return html`<div class="empty">ce ticket n'a pas de description</div>`;
  return html`<div class="facetfull descfull mdview">${raw(md(text))}</div>`;
}

/** RM2797 : la plus RÉCENTE en tête — on ouvre l'historique pour savoir ce qui vient de se passer. */
export function TicketLog(entries, { md }) {
  const list = entries || [];
  if (!list.length) return html`<div class="empty">aucune activité enregistrée pour ce ticket</div>`;
  return html`<div class="logfeed">${list.slice().reverse().map(e => { const quand = String(e.ts || "").replace("T", " ");
    return html`<div class="logent">${quand || e.title ? html`<div class="logent-h">${quand ? html`<span class="logent-ts">${quand}</span>` : ""}${e.title ? html`<span>${e.title}</span>` : ""}</div>` : ""}${e.body ? html`<div class="logent-b">${raw(md(e.body))}</div>` : ""}</div>`; })}</div>`;
}

export function TicketConso(c) {
  if (!c) return html`<div class="ms" style="${muted}">Aucune consommation enregistrée pour ce ticket.</div>`;
  return html`<div class="ms"><h4>Consommation <span style="text-transform:none;${muted}">(enregistrée)</span></h4><div class="kv"><span class="k">tokens</span><span class="v" title="entrée + sortie (cache hors total — RM2519)">${c.total}</span></div>${c.breakdown
    ? html`${kv("↳ entrée", c.breakdown.input)}${kv("↳ sortie", c.breakdown.output)}<div class="kv"><span class="k" style="${muted}">cache lu / écrit</span><span class="v" style="${muted}" title="information complémentaire, hors total">${c.breakdown.cache}</span></div>` : ""}${kv("coût", c.cost)}${kv("temps IA", c.ai)}${kv("temps humain", c.human)}${kv("dernière activité", c.updated)}</div>`;
}

export function TicketWorkspace(w, rm) {
  const refresh = html`<span class="pill" data-action="refresh-ws" data-rm="${rm}">↻</span>`;
  return html`<div class="ms"><h4>Workspace <span style="text-transform:none;${muted}">(git · intérim RM1883)</span></h4>${w.kind === "loading" ? html`<span style="${muted}">…</span> ${refresh}`
    : w.kind === "nogit" ? html`<span style="${muted}">pas un dépôt git</span>`
    : html`${kv("branche", w.branch)}<div class="rels" style="margin-top:4px"><span class="pill ${w.clean ? "ok" : "warn"}">${w.clean ? "clean" : w.dirty + " modifs"}</span>${w.untracked ? html`<span class="pill warn">${w.untracked} untracked</span>` : ""}${w.ahead ? html`<span class="pill">↑${w.ahead}</span>` : ""}${w.behind ? html`<span class="pill dang">↓${w.behind}</span>` : ""} ${refresh}</div>`}</div>`;
}

export function TicketsPane(vm, deps) {
  const k = vm.kind;
  if (k === "empty") {
    const e = vm.emptyKind;
    return e === "none" ? html`<div class="empty">aucun ticket — attache une session ou ouvre une fiche.</div>`
      : html`<div class="ms" style="${muted}">${e === "untracked" ? "ticket non PM-tracké" : e === "slug-empty" ? "session slug — aucun ticket dans son worklog" : "session slug (sans ticket d’ancrage) — lecture du worklog…"}</div>`;
  }
  const sel = vm.sel;
  // RM3126 : le TITRE du ticket courant entre la liste des tickets et ses onglets. Sans lui, on
  // navigue entre des numéros : « RM3126 » ne dit pas de quoi il s'agit, et le titre n'apparaissait
  // qu'une fois l'onglet « détail » ouvert — donc jamais sur les autres facettes.
  const titre = vm.currentTitle;
  return html`<div class="rsub">${vm.tabs.map(t => html`<button class="${t.active ? "active" : ""}" data-action="tab" data-rm="${t.rm}">RM${t.rm}</button>`)}</div>${titre
    ? html`<div class="rtitle" title="${titre}">${titre}</div>` : ""}<div class="rsub facets">${vm.facets.map(f => html`<button class="${f.active ? "active" : ""}" data-action="facet" data-facet="${f.key}">${f.label}</button>`)}</div>${k === "loading" ? html`<div class="ms">chargement…</div>`
    : k === "notfound" ? html`<div class="ms"><h4>Ticket</h4>RM${sel} <span style="${muted}">non trouvé en local</span></div>`
    : k === "desc" ? TicketDesc(vm.desc(), deps)
    : k === "log" ? html`<div class="facetfull">${TicketLog(vm.log(), deps)}</div>`
    : k === "conso" ? TicketConso(vm.conso())
    : k === "workspace" ? TicketWorkspace(vm.workspace(), sel)
    : TicketDetail(vm, deps)}`;
}
