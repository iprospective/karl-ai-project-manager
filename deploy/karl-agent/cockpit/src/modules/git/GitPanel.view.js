// views/git/GitPanel — l'onglet git du panneau droit. RM2889, L4.
// Balisage repris de #rp-git, gitRender, gitPatchHtml, gitBranchesHtml ;
// gestes en data-action, plus aucun onclick ni createElement.

import { html } from "../../core/html.js";

export function GitBranches(branches, courante) {
  const list = (branches || []).filter(Boolean);
  if (!list.length) return "";
  return html`<div class="kv"><span class="k">branches</span><span class="v rels">${list.map((b, i) =>
    html`${i ? " " : ""}<span class="pill${b === courante ? " ok" : ""}" title="${b}${b === courante ? " (branche courante)" : ""}">${b}</span>`)}</span></div>`;
}

/** Le patch d'un commit ou d'un diff, depuis son GitPatchViewModel. */
export function GitPatch(pvm) {
  return html`<div class="ms"><h4>${pvm.label}</h4>${pvm.files.map(f =>
      html`<div class="gmeta">${f.path} +${f.added} −${f.removed}${f.binary ? " (binaire)" : ""}</div>`)}${pvm.truncatedKb !== null
      ? html`<div class="gtrunc">⚠ diff tronqué à ${pvm.truncatedKb} Ko — la suite n'est pas affichée. Ouvre le dépôt pour le diff complet.</div>` : ""}<div class="gdiff">${pvm.lines().map(l =>
      l.cls ? html`<span class="${l.cls}">${l.text}</span>\n` : html`${l.text}\n`)}</div></div>`;
}

/** Un détail ouvert au-dessus du journal (commit ou diff), fermable. */
export function GitDetail(title, patch) {
  return html`<div class="ms"><h4>${title} <button class="mini" data-action="close">✕</button></h4></div>${patch}`;
}

export function GitBody(vm, detail) {
  if (vm.mode === "not_git") return html`<div class="empty">pas un dépôt git</div>`;
  if (vm.mode === "pm_data") return html`<div class="empty">Ce ticket n'a pas de worktree de code.<br><br>Le dépôt trouvé ne porte que les données PM (<code>.mmi-pm/</code>) et ses commits automatiques — sans intérêt ici.<br><br>Prends le ticket (<code>pm-task-take</code>) pour créer son worktree, ou attache une session qui en a un.</div>`;
  const entete = GitBranches(vm.branches, vm.branch);
  if (vm.mode === "empty") return html`${entete}<div class="empty">aucun commit</div>`;
  return html`${detail || ""}${entete}${vm.commits().map(c =>
    html`<div class="gcommit${c.pushed ? "" : " local"}${c.cur ? " cur" : ""}" data-action="show" data-sha="${c.sha}" title="${c.title}">${c.pushed ? "○" : "●"} <span class="gsha">${c.short}</span> ${c.subject}${c.merge ? html` <span class="pill">merge</span>` : ""}<div class="gmeta">${c.when} · ${c.author}${c.pushed ? "" : " · pas encore poussé"}</div><button class="mini" data-action="center" data-sha="${c.sha}" title="Afficher ce commit dans un onglet du panneau central" style="margin-left:6px">⤢</button></div>`)}`;
}

export function GitPanel({ vm, detail, body }) {
  return html`<div class="outnav">
    <button class="mini" data-action="refresh" title="Rafraîchir">⟳</button>
    <button class="mini" data-action="diff-branch" title="Ce que la branche apporte à sa cible d'intégration">Δ branche</button>
    <button class="mini" data-action="diff-worktree" title="Modifications pas encore commitées">Δ non commité</button>
    <span class="cnt" id="gitcnt" title="${vm ? vm.countTitle : ""}">${vm ? vm.count : ""}</span>
  </div>
  <div class="outbody" id="gitbody">${body !== undefined ? body : (vm ? GitBody(vm, detail) : html`<div class="empty">attache une session…</div>`)}</div>`;
}
