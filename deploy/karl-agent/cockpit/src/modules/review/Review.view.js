// views/tickets/Review — la fiche de revue (RM2210/2229/2384/2726/2786/2832/2873/2888). Balisage repris ; gestes en data-*.
import { html, raw } from "../../core/html.js";
import { pillClass } from "../../core/status.js";

export function TagPills(tags) {
  if (!tags.length) return "";
  return html` · 🏷 ${tags.map((t, i) => html`${i ? " " : ""}<span class="pill" style="cursor:pointer" title="Voir les tickets étiquetés « ${t} »" data-action="tag" data-tag="${String(t)}">${t}</span>`)}`;
}

export function TicketSessions(vm) {
  if (vm.loading) return html`<div style="color:var(--muted)">recherche des sessions qui traitent ce ticket…</div>`;
  const hs = vm.handled(), c = vm.candidates(), p = vm.prompt;
  return html`${hs.length ? hs.map(s => html`<div class="kv"><span class="k">${s.alive ? html`<span style="color:var(--ok,#3fb950)">●</span> ` : "◌ "}${s.name}</span><span class="v">${s.title ? s.title + " · " : ""}<span style="color:var(--muted)">${s.reasons}${s.alive ? "" : " · éteinte"}${s.other ? " · " + s.other : ""}</span>${s.alive ? html` <button class="mini" title="Ouvrir cette session" data-action="attach" data-sid="${s.sid}">⇱ ouvrir</button>` : ""}</span></div>`)
    : html`<div style="color:var(--muted)">aucune session ne traite ce ticket — ni ancrage, ni branche, ni worklog.</div>`}<div style="margin-top:10px"><label for="ts-tpl" style="display:block;font-size:11px;color:var(--muted)">Prompt initial</label><select id="ts-tpl" style="width:auto;max-width:340px" data-prompt="tpl">${vm.templates.map(t => html`<option value="${t.value}"${t.value === p.tpl ? " selected" : ""}>${t.label}</option>`)}</select><textarea id="ts-prompt" rows="2" style="margin-top:4px" data-prompt="text" placeholder="traite la tâche RM…">${p.text}</textarea></div><div class="rels" style="margin-top:8px"><button class="chip" data-action="spawn" data-rm="${vm.rm}"${vm.ownAlive ? html` disabled title="la session du ticket tourne déjà — ouvre-la plutôt"` : html` title="Lance karl-RM${vm.rm} avec le moteur et le modèle du lanceur, et la consigne ci-dessus"`}>▶ nouvelle session</button>${(c.mine.length || c.other.length)
    ? html`<select id="ts-target" style="width:auto;max-width:340px">${c.mine.length ? html`<optgroup label="${c.project}">${c.mine.map(o => html`<option value="${o.sid}">${o.label}</option>`)}</optgroup>` : ""}${c.other.length ? html`<optgroup label="autres projets">${c.other.map(o => html`<option value="${o.sid}">${o.label}</option>`)}</optgroup>` : ""}</select><button class="chip" title="Envoie la consigne ci-dessus dans la session choisie" data-action="send" data-rm="${vm.rm}">➜ envoyer dans cette session</button>`
    : html`<span style="color:var(--muted);font-size:11px">aucune autre session vivante où l’envoyer</span>`}</div>`;
}

export function StatusMenu(vm) {
  const items = vm.items();
  if (!items.length) return html`<button disabled>aucune transition depuis « ${vm.status} »</button>`;
  return html`${items.map(t => html`<button data-st="${t.status}"${t.refused ? " disabled" : ""}${t.reason ? html` data-reason="1"` : ""}${t.note ? html` data-note="1"` : ""} title="${t.tip}">${t.reason ? "🔒 " : ""}${t.status}</button>`)}${vm.degraded
    ? html`<div class="sep"></div><button disabled title="Le workflow Redmine n'a pas pu être interrogé : les transitions affichées sont celles des NORMS, sans le contrôle des droits de ce compte">⚠ transitions NORMS seules</button>` : ""}`;
}

const muted = "color:var(--muted)";
/** RM3089 — la réflexion du ticket sur sa fiche : les quatre rubriques, et le geste qui tranche.
 *  Les questions d'abord : ce sont elles qui bloquent la clôture, et le chiffre l'explique AVANT
 *  que le refus ne tombe. L'écriture passe par la route de RM3064 (D022), pas par une seconde. */
export function ThinkPane(th) {
  if (!th) return "";
  const ligne = (e, rub) => html`<div class="oline${e.open ? " oq" : ""}" style="white-space:normal">${e.icon} <b>${e.id}</b> ${e.closed
    ? html`<span style="opacity:.6;text-decoration:line-through">${e.text}</span>` : e.text}${e.open
    ? html` <span class="thk-acts"><button class="mini" title="Trancher : validé (réponse facultative pour une question)" data-action="think-state" data-id="${e.id}" data-rub="${rub}" data-state="valide">✅</button><button class="mini" title="Écarter : invalidé (le motif reste au carnet ; motif facultatif pour une question)" data-action="think-state" data-id="${e.id}" data-rub="${rub}" data-state="invalide">❌</button></span>` : ""}</div>`;
  const bloc = (titre, rows, rub) => (rows.length
    ? html`<div class="ms"><h4>${titre} (${String(rows.length)})</h4>${rows.map(e => ligne(e, rub))}</div>` : "");
  const c = th.counts || {};
  return html`<div class="ms"><h4>🧠 Réflexion <span style="${muted};font-weight:normal;font-size:12px">(${th.file})</span></h4><div style="${muted};font-size:11.5px">${String(c.questions_open || 0)} question(s) ouverte(s) · ${String(c.decisions || 0)} décision(s) · ${String(c.features || 0)} fonctionnalité(s) · ${String(c.notes_pending || 0)} note(s) à trier${th.blocking
    ? html` — <b>la clôture est refusée tant qu'il en reste</b>` : ""}</div></div>${bloc("❓ questions", th.questions, "question")}${bloc("⚖ décisions et conseils", th.decisions, "decision")}${bloc("✳ fonctionnalités", th.features, "feature")}${bloc("📝 notes", th.notes, "note")}`;
}

/** RM3225 : la mise en production du ticket. Les actions au déploiement, puis le script de MEP
 *  conservé à côté de la fiche : ses deux commandes de lancement (contrôle, puis --apply) et son
 *  texte. Déplié d'office quand le ticket est à mettre en prod — c'est le moment où il sert. */
export function MepPane(m) {
  if (!m) return "";
  // bloc de code aligné à gauche, coupé où il faut (un chemin de script est long) ; le clic
  // sélectionne toute la commande, 📋 la copie
  const cmd = (label, c) => (c ? html`<div style="margin:4px 0 6px"><div style="${muted};font-size:12px">${label} <button class="mini" title="Copier la commande" data-action="copy" data-text="${c}">📋</button></div><code style="display:block;text-align:left;font-size:12px;line-height:1.4;white-space:pre-wrap;word-break:break-all;user-select:all;background:rgba(127,127,127,.12);padding:4px 8px;border-radius:6px">${c}</code></div>` : "");
  const s = m.script;
  return html`<div class="ms"><h4>🚀 Mise en production</h4>${m.actions.length
    ? html`<div style="${muted};font-size:12px;margin-bottom:4px">actions au déploiement, dans l'ordre :</div><ol style="margin:0 0 8px 18px;padding:0;font-size:13px;line-height:1.45">${m.actions.map(a => html`<li>${a}</li>`)}</ol>` : ""}${s
    ? html`<details${m.focus ? " open" : ""}><summary style="cursor:pointer"><b>📜 Script de MEP</b> <span style="${muted};font-size:12px">(${s.file} · ${String(s.lines)} lignes)</span></summary><div style="margin-top:6px">${cmd("contrôle", s.check)}${cmd("exécution", s.apply)}${s.aliasKnown ? "" : html`<div style="${muted};font-size:11.5px">alias ssh inconnu : à remplacer dans la commande (champ <code>ssh_alias</code> de l'environnement prod).</div>`}${s.lint.length
      ? html`<div style="color:var(--warn,#d29922);font-size:12px;margin:4px 0">⚠ contrat du script : manque ${s.lint.join(", ")}</div>` : ""}<pre style="font-size:12px;line-height:1.4;max-height:420px;overflow:auto;background:rgba(127,127,127,.08);padding:8px 10px;border-radius:8px">${s.text}</pre>${s.truncated
      ? html`<div style="${muted};font-size:11.5px">texte tronqué — le fichier complet est à côté de la fiche.</div>` : ""}</div></details>` : ""}</div>`;
}

export function ReviewPane(vm, { md, titleLink, mcBanner }) {
  const r = vm.r, rm = vm.rm, env = vm.env, envs = vm.environments, v = vm.version;
  return html`<div style="max-width:720px"><h3 style="margin:0 0 4px">🧪 RM${rm}${vm.found ? html` — ${raw(titleLink(rm, r.title))}` : ""}</h3>${vm.found
    ? html`<div style="${muted};margin-bottom:6px">${r.client + "/" + r.project} · <span class="${pillClass(r.status)}">${r.status || "?"}</span>${r.priority ? html` · <span class="pill">${r.priority}</span>` : ""}${TagPills(vm.tags)}${vm.q && vm.q.branch ? html` · branche <span class="pill" title="${vm.q.branch}">${vm.q.branch}</span>` : ""}${v ? html` · <span title="dernière écriture du ticket : ${v.iso}">version ${v.label}</span>` : ""} <span class="pill" style="cursor:pointer" title="Recharger ce ticket depuis le disque" data-action="reload">↻</span></div>${vm.links.length ? html`<div style="margin-bottom:12px">${vm.links.map((l, i) => html`${i ? " · " : ""}<a href="${l.href}" target="_blank">${l.label}</a>`)}</div>` : ""}<div class="ms"><h4>Sessions</h4>${TicketSessions(vm.sessions())}</div>${ThinkPane(vm.think)}${vm.protocol
      ? html`<div class="ms"><h4>📋 Protocole de test <span style="${muted};font-weight:normal;font-size:12px">(${vm.protocol.source})</span></h4><div style="font-size:13.5px;line-height:1.5;background:rgba(127,127,127,.08);padding:10px 12px;border-radius:8px;max-height:340px;overflow:auto">${raw(md(vm.protocol.text))}</div></div>`
      : html`<div class="ms"><h4>📋 Protocole de test</h4><div style="${muted}">aucune section « À tester » dans la note de livraison ni la description — voir la description ci-dessous. (Norme RM2229 : toute livraison devrait en inclure une.)</div></div>`}${MepPane(vm.mep)}${r.description
      ? html`<div class="ms"><details><summary style="cursor:pointer"><b>📝 Description du ticket</b></summary><div style="font-size:13px;line-height:1.45;margin-top:8px;max-height:380px;overflow:auto">${raw(md(r.description))}</div></details></div>` : ""}${r.log_tail
      ? html`<div class="ms"><details><summary style="cursor:pointer"><b>🕘 Dernière activité (log)</b></summary><div style="white-space:pre-wrap;font-size:12.5px;${muted};margin-top:8px;max-height:300px;overflow:auto">${r.log_tail}</div></details></div>` : ""}` : ""}<div class="ms"><h4>Env de test du ticket</h4>${env.kind === "live"
    ? html`<div style="margin:6px 0 10px;font-size:15px">🔗 <a href="http://${env.host}/" target="_blank"><b>${env.host}</b> ↗</a> <span style="color:var(--ok,#3fb950)">●</span></div><div class="rels"><button class="chip" data-action="env-teardown" data-rm="${rm}">🧹 démonter cet env</button></div>`
    : env.kind === "broken" ? html`<div style="margin:6px 0 4px;font-size:15px">⚠ <b>${env.host}</b> — env présent mais indisponible</div><div style="${muted};margin:0 0 8px">${env.reason}</div><div class="rels"><button class="chip" data-action="env-deploy" data-rm="${rm}">🔁 re-déployer (répare l’env)</button><button class="chip" data-action="env-teardown" data-rm="${rm}">🧹 démonter</button></div>`
    : env.kind === "deployable" ? html`<div style="${muted};margin:4px 0 8px">aucun env monté pour ce ticket — déployer sa branche :</div><div class="rels"><button class="chip" data-action="env-deploy" data-rm="${rm}">🚀 env dédié au ticket (choix BDD)</button><button class="chip" data-action="env-shared" data-rm="${rm}">📤 env test PARTAGÉ du projet</button></div>`
    : env.kind === "nolayout" ? html`<div style="${muted}">workspace hors layout repos/+envs/ — normaliser d’abord (mmi-pm env migrate) pour déployer ici.</div>`
    : env.kind === "left" ? html`<div style="${muted}">Ce ticket n’est plus dans la file de test (statut : <span class="${pillClass(env.status)}">${env.status}</span>) — clôturé ou renvoyé.</div><div class="rels"><button class="chip" data-action="close">✖ fermer ce panneau</button></div>`
    : env.kind === "outside" ? html`<div style="${muted}">ticket hors file de test — env de session non géré depuis cette fiche.</div>`
    : html`<div style="${muted}">chargement de l’état…</div>`}</div>${envs && (envs.list.length || envs.test_url)
    ? html`<div class="ms"><h4>Environnements du projet</h4>${envs.test_url ? html`<div class="kv"><span class="k">test_url ticket</span><span class="v"><a href="${envs.test_url}" target="_blank">↗</a></span></div>` : ""}${envs.list.map(e => html`<div class="kv"><span class="k">${e.name}</span><span class="v"><a href="${e.url}" target="_blank">${e.url} ↗</a></span></div>`)}</div>` : ""}${vm.found
    ? html`<div class="ms"><h4>Cohérence git</h4>${vm.e.mc ? raw(mcBanner(vm.e.mc)) : html`<div style="${muted}">vérification de la mergeabilité en cours…</div>`}</div>` : ""}${(vm.pmActions.length || vm.verdicts.length)
    ? html`<div class="ms"><h4>Actions</h4>${vm.verdicts.length ? html`<div class="rels">${vm.verdicts.map(x => html`<button class="chip" data-action="verdict" data-kind="${x.kind}" data-rm="${rm}">${x.label}</button>`)}</div>` : ""}${vm.pmActions.length
      ? html`<div class="rels" style="margin-top:6px">${vm.pmActions.map(a => html`<button class="chip"${vm.pmTarget.sid ? "" : " disabled"} title="${a.title}" data-action="pm" data-i="${a.i}" data-rm="${rm}">${a.label}</button>`)}</div><div style="${muted};font-size:11px;margin-top:4px">${vm.pmTarget.why}</div>` : ""}${!vm.verdicts.length
      ? html`<div style="${muted};font-size:11px;margin-top:4px">Aucun verdict à rendre sur un ticket « ${vm.status || "?"} » — un verdict porte sur du travail livré.</div>` : ""}</div>` : ""}</div>`;
}
