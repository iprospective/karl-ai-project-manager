// models/git/gitDiff — lecture d'un patch : pur, repris tel quel. RM2889, L4.

/** Classe d'une ligne de patch. `+++`/`---` sont des EN-TÊTES de fichier, pas des
 *  ajouts/retraits : les colorer en vert/rouge ferait lire un en-tête comme du
 *  contenu modifié. */
export function gitDiffLine(line) {
  const l = String(line == null ? "" : line);
  if (l.startsWith("+++") || l.startsWith("---")) return "fh";
  if (l.startsWith("diff --git") || l.startsWith("index ")) return "fh";
  if (l.startsWith("@@")) return "hunk";
  if (l.startsWith("+")) return "add";
  if (l.startsWith("-")) return "del";
  return "";
}

/** Un fichier binaire ne rend pas de compte de lignes : afficher « +0 −0 »
 *  laisserait croire qu'il n'a pas changé. */
export function gitStatLabel(stats) {
  const s = stats || {};
  const n = s.count || 0;
  const bin = (s.files || []).filter(f => f.binary).length;
  return n + " fichier" + (n > 1 ? "s" : "")
    + " · +" + (s.added || 0) + " −" + (s.removed || 0)
    + (bin ? " · " + bin + " binaire" + (bin > 1 ? "s" : "") : "");
}
