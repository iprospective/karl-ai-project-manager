// views/tickets/Meta — l'encart ℹ : onglet « infos » (session) et onglet « tickets » (facettes). Balisage repris ; gestes en data-*. RM2889.
import { html, raw } from "../../core/html.js";
import { pillClass } from "../../core/status.js";
import { renderEntity } from "../../core/entities.js";   // RM3256
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
    ? kv("dépôt", html`${vm.repo}${vm.branch ? html` <span class="pill">${vm.branch}</span>` : ""}`) : ""}${vm.provider
    ? kv("provider", html`<span class="pill" title="instance de gestion des tickets (${vm.provider.type}) — ${vm.provider.url}">${vm.provider.name}</span>${vm.provider.secondaries.map(s => html` <span class="pill" style="opacity:.75" title="secondaire déclaré du projet : un ticket peut y être rattaché, il n'est jamais source de vérité">+ ${s}</span>`)}`) : ""}</div>`;
}

export function TicketDetail(vm, { tip }) {
  const d = vm.detail(), rm = d.rm;
  return html`<div class="ms"><h4>Ticket</h4><div class="kv"><span class="k">id</span><span class="v">${d.redmineUrl ? html`<a href="${d.redmineUrl}" target="_blank">RM${rm} ↗</a>` : "RM" + rm} <span class="pill" style="cursor:pointer" title="Pré-remplir le lanceur avec ce ticket" data-action="launcher" data-rm="${rm}">→ lanceur</span> <span class="pill" style="cursor:pointer" title="(Re)chiffrer : prépare le lanceur avec ce ticket et la consigne « étudie et chiffre » — rien ne part avant ▶ Lancer" data-action="estimate" data-rm="${rm}">💰 chiffrer</span> <span class="pill" style="cursor:pointer" title="Ouvrir la fiche complète du ticket (protocole de test, description, env, verdict)" data-action="review" data-rm="${rm}">🗂 fiche</span> <span class="pill" style="cursor:pointer" title="Recharger ce ticket depuis le disque (description, statut, chiffrage)" data-action="reload" data-rm="${rm}">↻</span></span></div>${d.freshness
    ? html`<div class="kv"><span class="k" style="${muted}">version</span><span class="v" style="${muted}" title="dernière écriture du ticket : ${d.freshness.stamp}">${d.freshness.stamp}${d.freshness.since ? html` <span style="opacity:.75">(${d.freshness.since})</span>` : ""}</span></div>` : ""}<div style="margin:4px 0">${d.title}</div>${kv("type", d.type)}<div class="kv"><span class="k">phase</span><span class="v"><span class="${pillClass(d.status)}" style="cursor:pointer" title="Changer le statut — transitions du workflow depuis « ${d.status || "?"} »" data-action="status" data-rm="${rm}">${d.status || "—"} ⇄</span>${d.closed
    ? html` <span class="pill" style="cursor:pointer" title="Rouvrir le ticket (ferme → a_faire, motif requis)" data-action="reopen" data-rm="${rm}">↻ rouvrir</span>` : ""}</span></div>${kv("priorité", d.priority)}${kv("avancement", d.pct)}</div>${ProjectBrief(vm.brief())}${renderEntity(vm.entityVm(), "panel")}${d.rels.length ? html`<div class="ms"><h4>Relations</h4>${d.rels.map(p => html`<div style="margin-bottom:4px"><span style="${muted}">${p.label} :</span> <span class="rels">${p.ids.map((id, i) => html`${i ? " " : ""}${rmLink(id, tip)}`)}</span></div>`)}</div>` : ""}<div class="ms"><h4>Contenu</h4><div class="rels"><button class="chip" data-action="facet" data-facet="desc">${d.hasDesc ? "📄 description" : "📄 description (vide)"}</button><button class="chip" data-action="facet" data-facet="log">${d.hasLog ? "🕘 historique" : "🕘 historique (vide)"}</button></div></div>`;
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

/** RM3164 — les sessions qui traitent ce ticket, dans le panneau. L'information existait
 *  dans la fiche de revue (RM2726) ; elle manquait là où l'on regarde le ticket au quotidien.
 *  Un clic attache la session : le but est d'y RETOURNER, pas seulement de savoir. */
export function TicketSessionsBlock(ts) {
  if (ts.kind === "none") return "";                     // jamais demandé : pas de bloc vide
  if (ts.kind === "loading") return html`<div class="ms"><h4>Sessions</h4><span style="${muted}">…</span></div>`;
  if (ts.kind === "error") return html`<div class="ms"><h4>Sessions</h4><span style="${muted}">indisponible</span></div>`;
  if (ts.kind === "empty") {
    return html`<div class="ms"><h4>Sessions</h4><span style="${muted}">aucune session ne traite ce ticket${ts.candidates ? html` — ${ts.candidates} candidate(s) possible(s), voir la fiche de revue` : ""}.</span></div>`;
  }
  return html`<div class="ms"><h4>Sessions (${ts.rows.length})</h4>${ts.rows.map(s =>
    html`<div class="kv" style="cursor:pointer" data-action="attach-session" data-sid="${s.sid}" title="Attacher la session ${s.name}"><span class="k">${s.alive
      ? html`<span style="color:var(--ok)">●</span> ` : "◌ "}${s.name}</span><span class="v">${s.title}</span></div>`)}</div>`;
}

/** RM3175 — les critères d'acceptation, avec ce qui est coché et OÙ cocher.
 *  La provenance n'est pas un détail d'implémentation : sur un ticket migré, cocher la description
 *  ne change rien pour la livraison (RM2882) — l'onglet le dit plutôt que de le laisser découvrir. */
export function TicketCriteria(c) {
  if (!c.total) return html`<div class="ms"><h4>Critères d'acceptation</h4><span style="${muted}">aucun critère posé sur ce ticket.</span></div>`;
  const ou = c.source === "acceptance"
    ? html`champ dédié (CF 33) — cocher : <code>mmi-pm task-acceptance ${c.rm} --check N</code>`
    : html`section de la description (ticket non migré) — cocher : <code>mmi-pm task-description-update ${c.rm} --check N</code>`;
  return html`<div class="ms"><h4>Critères d'acceptation <span style="text-transform:none;${muted}">(${String(c.done)}/${String(c.total)})</span></h4><div style="${muted};font-size:11px;margin-bottom:6px">${ou}</div><ol class="crit">${c.items.map(i =>
    html`<li class="${i.done ? "done" : ""}"><span class="cbox">${i.done ? "☑" : "☐"}</span> ${i.label}</li>`)}</ol></div>`;
}

/** RM3175 — la proposition d'implémentation (CF 31) : le COMMENT, là où la description porte le quoi. */
export function TicketImpl(text, { md }) {
  if (!text) return html`<div class="ms"><h4>Implémentation</h4><span style="${muted}">aucune proposition d'implémentation — elle se rédige en fin d'étude : <code>mmi-pm task-implementation</code>.</span></div>`;
  return html`<div class="facetfull descfull mdview">${raw(md(text))}</div>`;
}

/** RM3175 — le déploiement : les gestes de MEP dans leur ordre (CF 8), puis la recette (CF 30). */
export function TicketDeploy(d, { md }) {
  const gestes = d.actions.length
    ? html`<ol class="crit">${d.actions.map(a => html`<li>${a}</li>`)}</ol>`
    : html`<span style="${muted}">aucune action au déploiement — rien de particulier à faire à la MEP.</span>`;
  return html`<div class="ms"><h4>Actions au déploiement <span style="text-transform:none;${muted}">(${String(d.actions.length)})</span></h4>${gestes}</div><div class="ms"><h4>Protocole de test</h4>${d.protocol
    ? html`<div class="mdview">${raw(md(d.protocol.text))}</div>`
    : html`<span style="${muted}">pas de protocole de test : <code>mmi-pm task-protocol</code>.</span>`}</div>`;
}

export function TicketConso(c) {
  if (!c) return html`<div class="ms" style="${muted}">Aucune consommation enregistrée pour ce ticket.</div>`;
  return html`<div class="ms"><h4>Consommation <span style="text-transform:none;${muted}">(enregistrée)</span></h4><div class="kv"><span class="k">tokens</span><span class="v" title="entrée + sortie (cache hors total — RM2519)">${c.total}</span></div>${c.breakdown
    ? html`${kv("↳ entrée", c.breakdown.input)}${kv("↳ sortie", c.breakdown.output)}<div class="kv"><span class="k" style="${muted}">cache lu / écrit</span><span class="v" style="${muted}" title="information complémentaire, hors total">${c.breakdown.cache}</span></div>` : ""}${kv("coût", c.cost)}${kv("temps IA", c.ai)}${kv("temps humain", c.human)}${kv("dernière activité", c.updated)}</div>`;
}

/** RM3164 — ce que le ticket a touché : les fichiers, agrégés sur sa branche.
 *
 *  Pas une seconde vue git : RM2602 donne déjà les commits un par un. Ici on répond à la
 *  question inverse, celle qu'on se pose en reprenant un ticket froid — « qu'est-ce que ça a
 *  remué ? » — qu'aucune vue de commits ne dit sans les lire toutes.
 */
export function TicketImpact(im, rm) {
  if (im.kind === "none") return html`<div class="ms" style="${muted}">impact non chargé.</div>`;
  if (im.kind === "loading") return html`<div class="ms"><h4>Impact</h4><span style="${muted}">…</span></div>`;
  if (im.kind === "error") return html`<div class="ms"><h4>Impact</h4><span style="${muted}">indisponible</span></div>`;
  if (im.kind === "nogit") return html`<div class="ms"><h4>Impact</h4><span style="${muted}">pas un dépôt git</span></div>`;
  if (im.kind === "pmdata") return html`<div class="ms"><h4>Impact</h4><span style="${muted}">dépôt de DONNÉES PM — ses commits sont des auto-commits, les lister ferait passer du bruit pour du travail.</span></div>`;
  const tete = html`<h4>Impact <span style="text-transform:none;${muted}">(${im.commits} commit(s)${im.base ? " depuis " + im.base : ""})</span></h4>`;
  if (im.kind === "empty") return html`<div class="ms">${tete}<span style="${muted}">aucun fichier touché sur cette branche.</span></div>`;
  return html`<div class="ms">${tete}${im.files.map(f => html`<div class="kv"><span class="k" title="${f.path}">${f.path}</span><span class="v">${f.n}</span></div>`)}${im.total > im.files.length
    ? html`<div style="${muted};font-size:11px">… ${im.total - im.files.length} autre(s) fichier(s)</div>` : ""}</div>`;
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
  // RM3164 : le filtre par projet — absent quand tous les tickets sont dans le même, puisqu'il
  // n'aurait rien à trier. Positionné par défaut sur le projet de la session attachée.
  const projets = vm.ticketProjects;
  const filtre = vm.ticketFilter;
  return html`${projets.length
    ? html`<div class="cmpbar" style="flex-wrap:wrap;margin-bottom:4px"><button class="mini${filtre ? "" : " primary"}" data-action="tfilter" data-value="" title="Tous les projets">tous (${vm.list.length})</button>${projets.map(p => html`<button class="mini${p.key === filtre ? " primary" : ""}" data-action="tfilter" data-value="${p.key}" title="${p.key}">${p.key} (${p.n})</button>`)}</div>` : ""}<div class="rsub">${vm.tabs.map(t => html`<button class="${t.active ? "active" : ""}" data-action="tab" data-rm="${t.rm}" title="${t.project || ""}">RM${t.rm}</button>`)}</div>${titre
    ? html`<div class="rtitle" title="${titre}">${titre}</div>` : ""}<div class="rsub facets">${vm.facets.map(f => html`<button class="${f.active ? "active" : ""}" data-action="facet" data-facet="${f.key}">${f.label}</button>`)}</div>${k === "loading" ? html`<div class="ms">chargement…</div>`
    : k === "notfound" ? html`<div class="ms"><h4>Ticket</h4>RM${sel} <span style="${muted}">non trouvé en local</span></div>`
    : k === "criteria" ? TicketCriteria(vm.criteria())
    : k === "impl" ? TicketImpl(vm.impl(), deps)
    : k === "deploy" ? TicketDeploy(vm.deploy(), deps)
    : k === "desc" ? TicketDesc(vm.desc(), deps)
    : k === "log" ? html`<div class="facetfull">${TicketLog(vm.log(), deps)}</div>`
    : k === "conso" ? TicketConso(vm.conso())
    : k === "impact" ? TicketImpact(vm.impact(), sel)
    : k === "workspace" ? TicketWorkspace(vm.workspace(), sel)
    : TicketDetail(vm, deps)}`;
}
