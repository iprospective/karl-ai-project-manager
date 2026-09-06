// views/common/Links — les références cliquables partagées par toutes les vues : titre de ticket → fiche ℹ + lien Redmine (RM2585),
// `linkify` d'un texte libre (RM2596 : RM<id> → fiche, chemin → onglet Fichiers, URL → lien ; RM2623 : jargon souligné), pastille de statut
// (RM2718). Gestes en `data-link` — le contrôleur `links` les capte au niveau du document, sans jamais laisser le clic remonter à la tuile. RM2889.
import { html, raw } from "../../core/html.js";

/** RM2718 : pastille du statut de session — trois statuts, rien d'inventé (une clé héritée d'Object ne compte pas). */
export function markPillHtml(mark) {
  const PILL = { wip: ["warn", "WIP"], test: ["test", "À TESTER"], done: ["ok", "DONE"] };
  const p = Object.hasOwn(PILL, mark) ? PILL[mark] : null;
  return p ? String(html`<span class="pill ${p[0]}">${p[1]}</span> `) : "";
}

/** RM2596 : URL → <a>, RM<id> → fiche, chemin/fichier.ext → onglet Fichiers ; le reste est échappé puis passé au glossaire (RM2623). */
export function linkify(text, glossify) {
  const g = glossify || ((s) => s);
  const s = String(text == null ? "" : text);
  const re = /(https?:\/\/[^\s<)]+)|(\bRM\d+\b)|([\w.-]+\/[\w./-]+\.\w{1,6})/g;
  const parts = []; let last = 0, m;
  const plain = (chunk) => raw(g(String(html`${chunk}`)));   // texte échappé par le gabarit, puis souligné par le glossaire
  while ((m = re.exec(s))) {
    parts.push(plain(s.slice(last, m.index)));
    if (m[1]) parts.push(html`<a href="${m[1]}" target="_blank" rel="noopener">${m[1]}</a>`);
    else if (m[2]) parts.push(html`<span class="olink" title="Ouvrir la fiche ${m[2]}" data-link="ticket" data-rm="${m[2].slice(2)}">${m[2]}</span>`);
    else if (m[3]) parts.push(html`<span class="olink omono" title="Ouvrir dans l'onglet Fichiers" data-link="file" data-path="${m[3]}">${m[3]}</span>`);
    last = m.index + m[0].length;
  }
  parts.push(plain(s.slice(last)));
  return String(html`${parts}`);
}

/** RM2585 : titre cliquable → fiche ℹ, suivi d'un ↗ vers Redmine si la base est connue ; une référence non numérique (slug) reste du texte. */
export function titleLink(rmId, title, redmineBase) {
  const t = title == null ? "" : title;
  if (rmId == null || !/^\d+$/.test(String(rmId))) return String(html`${t}`);
  const id = String(rmId);
  const base = redmineBase || "";
  return String(html`<span class="tlink" title="Voir la fiche du ticket RM${id}" data-link="ticket" data-rm="${id}">${t}</span>${base ? html` <a class="rmext" href="${base + "/issues/" + id}" target="_blank" rel="noopener" title="Ouvrir RM${id} dans Redmine" data-link="ext">↗</a>` : ""}`);
}
