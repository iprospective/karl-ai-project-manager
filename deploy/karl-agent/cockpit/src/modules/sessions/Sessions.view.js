// views/sessions/Sessions — la liste « en cours » : bandeau « à traiter », bannière de contexte, groupes, tuiles vivantes et grises,
// revues ouvertes, compteurs, titres. Gestes en data-action / data-k (délégation posée par le contrôleur), aucun on*. RM2889.
// `titleLink` (lien vers la fiche ℹ) et `pin` (marque d'épinglage RM2795) sont prêtés : ils rendent du HTML déjà sûr.
import { html, raw } from "../../core/html.js";

/** RM2894 : en-tête du panneau de droite — identifiant + libellé (sujet Redmine, sinon titre du transcript, sinon « sans libellé »). Déplacé tel quel. */
export function rTitleHtml(sid, sess, resolved, escFn) {
  const s = sess || {}, r = resolved;
  const id = (s.is_ticket === false) ? String(sid) : "RM" + String(sid);
  const label = (r && r.found && r.title) ? String(r.title) : String(s.title || "");
  return '<span class="rt-id">' + escFn(id) + '</span>'
    + (label ? '<span class="rt-label">' + escFn(label) + '</span>' : '<span class="rt-label none">sans libellé</span>');
}

const attr = (name, v) => v ? html` ${raw(name)}="${v}"` : "";
const Badge = (b) => b ? html`<span class="tbadge"${attr("style", b.style)}${attr("title", b.title)}>${b.text}</span>` : "";
const outline = (vm) => vm.selMode && vm.selected ? raw(' style="outline:1px solid var(--accent)"') : "";

/** Tuile d'une session vivante. `pin`/`titleLink` prêtés par le contrôleur. */
/** RM3082 — la jauge de contexte : une barre (longueur = occupation) et le chiffre. La couleur ne
 * porte JAMAIS l'information seule — jaune et orange ne se distinguent pas pour tout le monde. */
export function CtxGauge(g, pulse) {
  if (!g) return "";
  return html`<span class="tctx ctx-${g.level}${pulse ? " ctx-cross" : ""}" title="${g.title}"><span class="tctxbar"><i style="width:${String(g.width)}%"></i></span><span class="tctxn">${g.label}</span></span>`;
}

export function Tile(vm, { pin, titleLink }) {
  const tc = vm.ticketCount;   // RM3131 : « n ouverts / m » des tickets de la session
  const s = vm.s, tag = vm.setTag, q = vm.quiet;
  return html`<div class="runitem${vm.active ? " active" : ""}${vm.unseen ? " unseen" : ""}" data-action="attach" data-k="${vm.key}" title="${vm.tip}"${outline(vm)}><span class="${vm.dotClass}" data-action="disp" data-k="${vm.key}" title="${vm.dispTip}"></span><span class="tid">${vm.idLabel}</span>${raw(pin("session", s.rm_id))}${tag ? html`<span class="tbadge" style="opacity:${tag.opacity}" title="${tag.title}">${tag.text}</span>` : ""}<span class="rmeta">${raw(titleLink(s.rm_id, vm.title))}${vm.age ? (vm.title ? " · " : "") + vm.age : ""}</span>${q ? html`<span class="tquiet" title="${q.title}">${q.text}</span>` : ""}${Badge(vm.badge)}${vm.autoTitle ? html`<span class="tbadge" style="color:var(--ok)" title="${vm.autoTitle}">⏱✔</span>` : ""}${vm.stale ? html`<span class="tbadge" title="Question posée puis laissée sans réponse — la session a continué (RM2598)">🕓</span>` : ""}${vm.canApprove ? html`<span class="tyes" data-action="approve" data-k="${vm.key}" title="Répondre Oui à la question en attente (sans attacher)">✔</span>` : ""}${vm.canDrop ? html`<span class="tkill tdrop" data-action="drop" data-k="${vm.key}" title="${vm.dropTitle}">⊖</span>` : ""}<span class="tkill" data-action="kill" data-k="${vm.key}" title="Fermer la session (le tmux est tué ; l'entrée reste dans le jeu, en tuile grise)">✕</span>${tc
    ? html`<span class="tcount" title="${tc.open} ticket(s) encore ouvert(s) sur ${tc.total} traité(s) dans cette session — statuts résolus par l'index, pas figés au worklog">${tc.open}/${tc.total}</span>` : ""}${CtxGauge(vm.ctxGauge, vm.ctxPulse)}</div>`;
}

/** RM2427 : tuile grise d'une session enregistrée non démarrée. */
export function Ghost(vm) {
  const g = vm.groupTag;
  return html`<div class="runitem ghost" data-action="relaunch" data-k="${vm.key}" title="${vm.tip}"${outline(vm)}><span class="tdot st-ghost"></span><span class="tid">${vm.idLabel}</span>${g ? html`<span class="tbadge" style="opacity:.65" title="${g.title}">${g.text}</span>` : ""}<span class="rmeta"${vm.faded ? raw(' style="opacity:.55"') : ""}>${vm.title}${vm.age ? (vm.title ? " · " : "") + vm.age : ""}</span>${vm.inSet ? html`<span class="tbadge trestart" style="cursor:pointer" data-action="restart" data-k="${vm.key}" title="${vm.restartTip}">${vm.restartIcon}</span><span class="tkill" data-action="forget" data-k="${vm.key}" title="Retirer du jeu de sessions enregistrées">⊖</span>` : ""}</div>`;
}

/** En-tête de groupe (RM2353 : clic = fiche projet ; RM2448 : le chevron replie sans ouvrir la fiche). */
export function GroupHead(vm) {
  return html`<div class="rghead" data-action="group" data-key="${vm.key}" title="${vm.tip}"><span class="gfold" style="cursor:pointer;opacity:.6;margin-right:4px" data-action="fold" data-key="${vm.key}" title="${vm.foldTitle}">${vm.chevron}</span><span>${vm.key}</span><span class="gcnt">${String(vm.count)}${vm.unseen ? html` <span class="gunseen" title="${String(vm.unseen)} session(s) ont fini leur tour et attendent qu'on aille les voir">👁${String(vm.unseen)}</span>` : ""}${vm.att ? html` <span style="color:var(--danger)">⚠${String(vm.att)}</span>` : ""}${vm.cho ? html` <span style="color:var(--warn)">❓${String(vm.cho)}</span>` : ""}</span></div>`;
}

/** Un groupe : en-tête + tuiles (aucune si replié). */
export function Group(gvm, tiles) { return html`<div class="rgroup">${GroupHead(gvm)}${gvm.folded ? "" : tiles}</div>`; }

/** RM2346 : bandeau « à traiter » — attention/choix à place fixe, en tête. */
export function AttnBand(chips, { titleLink }) {
  if (!chips.length) return "";
  return html`<div class="attnband"><div class="attnband-h">à traiter (${String(chips.length)})</div>${chips.map(c => html`<div class="attnchip" data-action="attach" data-k="s:${c.s.rm_id}"><span class="tdot st-${c.s.state}"></span><span class="tid">${c.idLabel}</span><span class="rmeta">${c.hasTitle ? raw(titleLink(c.s.rm_id, c.r.title)) : c.fallback}</span>${c.canApprove ? html`<span class="tyes" data-action="approve" data-k="s:${c.s.rm_id}" title="Répondre Oui (sans attacher)">✔</span>` : ""}${c.ctxGauge ? html`<span class="tctxn ctx-crit" title="${c.ctxGauge.title}">🧠 ${c.ctxGauge.label}</span>` : ""}</div>`)}</div>`;
}

/** RM2639 : bannière du contexte client, avec le nombre de groupes masqués et le retour à « tous ». */
export function CtxBanner(clientContext, hidden) {
  return html`<div class="ctxbanner">Contexte client : <b>${clientContext}</b>${hidden > 0 ? html` <span style="opacity:.7">· ${String(hidden)} groupe(s) hors client masqué(s)</span>` : ""} <button class="mini" data-action="ctx-clear" title="Revenir à tous les clients">tous ✕</button></div>`;
}

/** RM2210 : revues « à tester » ouvertes (pas des sessions tmux). */
export function ReviewGroup(vms, { pin, titleLink }) {
  if (!vms.length) return "";
  return html`<div class="rgroup"><div class="rghead"><span>🧪 revues ouvertes</span><span class="gcnt">${String(vms.length)}</span></div>${vms.map(v => html`<div class="runitem${v.active ? " active" : ""}" data-action="review" data-rm="${v.rm}" title="${v.tip}"><span class="tdot" style="background:var(--warn)"></span><span class="tid">RM${v.rm}</span>${raw(pin("review", v.rm))}<span class="rmeta">${raw(titleLink(v.rm, v.title))}</span><span class="tkill" data-action="review-close" data-rm="${v.rm}" title="Fermer la revue">✕</span></div>`)}</div>`;
}

export const Empty = () => html`<div class="empty">Aucune session — lances-en une depuis le panneau « 🚀 sessions »</div>`;

/** RM2283 : compteurs du panneau (ouvertes · enregistrées · ⚠ · ❓ · repos). */
export function Counters(vm) {
  const c = vm.c;
  return html`<span class="pill" title="sessions ouvertes">● ${String(c.total)}</span>${vm.unseen ? html`<span class="pill unseen" title="sessions qui ont fini leur tour pendant que tu regardais ailleurs — le compteur descend dès que tu vas les voir">👁 ${String(vm.unseen)} à voir</span>` : ""}${c.ghost ? html`<span class="pill" style="opacity:.6" title="sessions enregistrées, non démarrées — clic sur la tuile pour relancer">⏸ ${String(c.ghost)}</span>` : ""}<span class="pill${c.attention ? " att" : ""}" title="questions OUI/NON en attente">⚠ ${String(c.attention)}</span>${c.choice ? html`<span class="pill" style="color:var(--warn);border-color:var(--warn)" title="questions à choix multiple en attente (réponse dans le terminal)">❓ ${String(c.choice)}</span>` : ""}<span class="pill" title="au repos">💤 ${String(c.idle)}</span>`;
}

/** RM2283/RM2332/RM2327 : titre de la session attachée dans la barre du centre, avec « ✔ Oui » quand elle attend. */
export function SessionTitle(vm, { titleLink }) {
  if (!vm.shown) return "";
  return html`<span class="tdot st-${vm.state}"></span><span class="tid">${vm.idLabel}</span><span class="ttitle">${vm.hasTitle ? raw(titleLink(vm.attached, vm.r.title)) : vm.fallback}</span>${vm.state === "attention" ? html`<span class="tbadge">⚠</span><button class="mini" style="margin-left:8px" data-action="approve" title="Répondre Oui à la question en attente de cette session">✔ Oui</button>` : vm.state === "choice" ? html`<span class="tbadge" style="color:var(--warn)">❓</span>` : ""}`;
}

/** RM2894 : en-tête du panneau de droite. */
const escFn = (s) => String(html`${s}`);   // RM3001 : l'échappement vient du gabarit, pas d'un esc() appelé par la vue
export function RTitle(vm) { return raw(rTitleHtml(vm.attached, vm.s, vm.r, escFn)); }
