// views/common/Links — les références cliquables partagées par toutes les vues : titre de ticket → fiche ℹ + lien Redmine (RM2585),
// `linkify` d'un texte libre (RM2596 : RM<id> → fiche, chemin → onglet Fichiers, URL → lien ; RM2623 : jargon souligné), pastille de statut
// (RM2718). Gestes en `data-link` — le contrôleur `links` les capte au niveau du document, sans jamais laisser le clic remonter à la tuile. RM2889.
import { esc } from "../../core/html.js";

/** RM2718 : pastille du statut de session — trois statuts, rien d'inventé (une clé héritée d'Object ne compte pas). */
export function markPillHtml(mark) {
  const PILL = { wip: ["warn", "WIP"], test: ["test", "À TESTER"], done: ["ok", "DONE"] };
  const p = Object.hasOwn(PILL, mark) ? PILL[mark] : null;
  return p ? '<span class="pill ' + p[0] + '">' + p[1] + "</span> " : "";
}

/** RM2596 : URL → <a>, RM<id> → fiche, chemin/fichier.ext → onglet Fichiers ; le reste est échappé puis passé au glossaire (RM2623). */
export function linkify(text, glossify) {
  const g = glossify || ((s) => s);
  const s = String(text == null ? "" : text);
  const re = /(https?:\/\/[^\s<)]+)|(\bRM\d+\b)|([\w.-]+\/[\w./-]+\.\w{1,6})/g;
  let out = "", last = 0, m;
  while ((m = re.exec(s))) {
    out += g(esc(s.slice(last, m.index)));
    if (m[1]) out += '<a href="' + esc(m[1]) + '" target="_blank" rel="noopener">' + esc(m[1]) + "</a>";
    else if (m[2]) out += '<span class="olink" title="Ouvrir la fiche ' + esc(m[2]) + '" data-link="ticket" data-rm="' + esc(m[2].slice(2)) + '">' + esc(m[2]) + "</span>";
    else if (m[3]) out += '<span class="olink omono" title="Ouvrir dans l\'onglet Fichiers" data-link="file" data-path="' + esc(m[3]) + '">' + esc(m[3]) + "</span>";
    last = m.index + m[0].length;
  }
  return out + g(esc(s.slice(last)));
}

/** RM2585 : titre cliquable → fiche ℹ, suivi d'un ↗ vers Redmine si la base est connue ; une référence non numérique (slug) reste du texte. */
export function titleLink(rmId, title, redmineBase) {
  const t = esc(title == null ? "" : title);
  if (rmId == null || !/^\d+$/.test(String(rmId))) return t;
  const id = String(rmId);
  const lbl = '<span class="tlink" title="Voir la fiche du ticket RM' + id + '" data-link="ticket" data-rm="' + id + '">' + t + "</span>";
  const base = redmineBase || "";
  const ext = base ? ' <a class="rmext" href="' + esc(base) + "/issues/" + id + '" target="_blank" rel="noopener" title="Ouvrir RM' + id + ' dans Redmine" data-link="ext">↗</a>' : "";
  return lbl + ext;
}
