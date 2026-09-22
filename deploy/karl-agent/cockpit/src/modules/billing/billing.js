// modules/billing/billing — la matière d'une journée de facturation, en fonctions PURES (RM3229, lot L3).
//
// Une journée se valide en la REGARDANT : les plages où l'on a effectivement travaillé, le travail de l'IA
// en face (c'est lui qui justifie une plage), ce qui est déjà noté dans Redmine, et ce que la proposition
// ajouterait. Tout ce qui se calcule ici se teste sans navigateur — la vue n'a plus qu'à peindre.

/** Minutes → « 3 h 45 » / « 45 min ». La lecture d'un temps de travail, pas une durée machine. */
export function fmtMin(m) {
  const n = Math.round(Number(m) || 0);
  if (!n) return "0";
  const h = Math.floor(n / 60), r = n % 60;
  return h ? (r ? `${h} h ${String(r).padStart(2, "0")}` : `${h} h`) : `${r} min`;
}

/** « 08:51 » → minutes depuis minuit. Rend NaN sur une entrée qui n'est pas une heure. */
export function minOf(hhmm) {
  const m = /^(\d{1,2}):(\d{2})$/.exec(String(hhmm || "").trim());
  return m ? Number(m[1]) * 60 + Number(m[2]) : NaN;
}

/** Minutes depuis minuit → « 08:51 ». */
export function hhmm(min) {
  const n = Math.max(0, Math.round(Number(min) || 0));
  return `${String(Math.floor(n / 60) % 24).padStart(2, "0")}:${String(n % 60).padStart(2, "0")}`;
}

/** Jour ± n, en AAAA-MM-JJ (UTC : la date est une étiquette, pas un instant). */
export function shiftDay(day, n) {
  const d = new Date(String(day) + "T12:00:00Z");
  if (isNaN(d.getTime())) return day;
  d.setUTCDate(d.getUTCDate() + Number(n || 0));
  return d.toISOString().slice(0, 10);
}

/** Le lundi de la semaine d'une journée, puis les 7 jours — l'ossature de la vue semaine (L4). */
export function weekOf(day) {
  const d = new Date(String(day) + "T12:00:00Z");
  if (isNaN(d.getTime())) return [];
  const lundi = shiftDay(day, -((d.getUTCDay() + 6) % 7));
  return Array.from({ length: 7 }, (_, i) => shiftDay(lundi, i));
}

const DOW = ["dimanche", "lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi"];
const MOIS = ["janvier", "février", "mars", "avril", "mai", "juin",
              "juillet", "août", "septembre", "octobre", "novembre", "décembre"];

/** « 2026-09-18 » → « vendredi 18 septembre 2026 ». */
export function longDate(day) {
  const d = new Date(String(day) + "T12:00:00Z");
  if (isNaN(d.getTime())) return String(day || "");
  return `${DOW[d.getUTCDay()]} ${d.getUTCDate()} ${MOIS[d.getUTCMonth()]} ${d.getUTCFullYear()}`;
}

/** Vrai pour un samedi ou un dimanche — le transversal y reste à la charge de Mathieu (arbitrage RM2890). */
export function isWeekend(day) {
  const d = new Date(String(day) + "T12:00:00Z");
  return !isNaN(d.getTime()) && (d.getUTCDay() === 0 || d.getUTCDay() === 6);
}

/**
 * Les bornes de la frise : la plage réellement observée, élargie aux heures proposées,
 * arrondie à l'heure et jamais plus étroite qu'une heure. Sans rien à montrer : 8 h → 19 h.
 */
export function bounds(jour, { start, end } = {}) {
  const pts = [];
  for (const [a, b] of (jour && jour.periodes) || []) { pts.push(minOf(a), minOf(b)); }
  for (const k of (jour && jour.ia) || []) pts.push(minOf(k.heure));
  for (const v of [start, end]) { const m = minOf(v); if (!isNaN(m)) pts.push(m); }
  const ok = pts.filter(n => !isNaN(n));
  if (!ok.length) return { from: 8 * 60, to: 19 * 60 };
  let from = Math.floor(Math.min(...ok) / 60) * 60;
  let to = Math.ceil(Math.max(...ok) / 60) * 60;
  if (to - from < 60) to = from + 60;
  return { from, to };
}

const pct = (v, from, span) => Math.max(0, Math.min(100, ((v - from) / span) * 100));

/**
 * La frise d'une journée : deux voies alignées sur la même échelle.
 *
 *  - `humain` : les plages mesurées (union déjà faite côté serveur — rien n'est compté deux fois) ;
 *  - `ia`     : un repère par tour d'agent, groupé à la minute pour ne pas empiler 30 traits ;
 *  - `normal` : la plage « heures normales » déclarée (début/fin), qui sert de cadre de lecture.
 *
 * Les positions sont en POURCENTAGE de la plage affichée : la vue n'a aucun calcul à refaire.
 */
export function timeline(jour, { start, end } = {}) {
  const { from, to } = bounds(jour, { start, end });
  const span = Math.max(1, to - from);
  const humain = ((jour && jour.periodes) || []).map(([a, b]) => {
    const x0 = minOf(a), x1 = minOf(b);
    return {
      debut: a, fin: b, minutes: Math.max(0, x1 - x0),
      left: pct(x0, from, span), width: Math.max(0.4, pct(x1, from, span) - pct(x0, from, span)),
    };
  }).filter(s => !isNaN(s.minutes));
  const parMinute = new Map();
  for (const k of (jour && jour.ia) || []) {
    const x = minOf(k.heure);
    if (isNaN(x)) continue;
    const cur = parMinute.get(k.heure) || { heure: k.heure, tours: 0, minutes: 0, tokens: 0, tickets: [], left: pct(x, from, span) };
    cur.tours += 1;
    cur.minutes += Number(k.minutes) || 0;
    cur.tokens += Number(k.tokens) || 0;
    if (k.ticket && !cur.tickets.includes(k.ticket)) cur.tickets.push(k.ticket);
    parMinute.set(k.heure, cur);
  }
  const ia = [...parMinute.values()].sort((a, b) => (a.left - b.left));
  const a0 = minOf(start), a1 = minOf(end);
  const normal = (!isNaN(a0) && !isNaN(a1) && a1 > a0)
    ? { left: pct(a0, from, span), width: pct(a1, from, span) - pct(a0, from, span), debut: start, fin: end }
    : null;
  const heures = [];
  for (let h = from; h <= to; h += 60) heures.push({ label: hhmm(h), left: pct(h, from, span) });
  return { from, to, span, humain, ia, normal, heures };
}

/** La plage ouvrée de référence (arbitrage RM2890) : au-delà, c'est du soir ou de la nuit. */
export const OUVRE = { debut: 8 * 60, fin: 19 * 60 };

/**
 * Les heures « normales » proposées pour la journée : l'ajustement s'il existe, sinon la
 * première et la dernière trace, arrondies au quart d'heure vers l'extérieur et RAMENÉES
 * à la plage ouvrée.
 *
 * Le bornage n'est pas cosmétique : une journée dont la dernière trace est à 23h44 proposerait
 * sinon « 08:45–23:45 = 14 h », et ces 14 h serviraient de plancher de régie. Une soirée n'est
 * pas une journée de travail facturable (arbitrage RM2890) — elle se rajoute à la main si elle
 * doit compter. `hors` dit ce qui a été laissé dehors, pour que le bornage se voie.
 *
 * C'est une PROPOSITION : ce que la machine a vu. Mathieu la corrige, et c'est sa correction
 * qui fait foi — d'où `source`, qui dit à l'écran d'où vient ce qu'il affiche.
 */
export function heuresNormales(jour) {
  const s = (jour && jour.surcharge) || {};
  if (s.debut && s.fin) return { debut: s.debut, fin: s.fin, pause: s.pause_h, source: "ajuste", hors: null };
  const pers = (jour && jour.periodes) || [];
  const deb0 = Math.min(...pers.map(p => minOf(p[0])).filter(n => !isNaN(n)));
  const fin0 = Math.max(...pers.map(p => minOf(p[1])).filter(n => !isNaN(n)));
  if (!pers.length || !isFinite(deb0) || !isFinite(fin0)) {
    return { debut: "", fin: "", pause: null, source: "vide", hors: null };
  }
  const brutDeb = Math.floor(deb0 / 15) * 15, brutFin = Math.ceil(fin0 / 15) * 15;
  let deb = Math.max(brutDeb, OUVRE.debut), fin = Math.min(brutFin, OUVRE.fin);
  // Journée entièrement hors plage ouvrée (une nuit, un dimanche soir) : on ne la réécrit pas,
  // on la montre telle quelle — c'est à l'humain de dire ce qu'il en fait.
  if (fin <= deb) { deb = brutDeb; fin = brutFin; }
  const hors = (brutDeb < deb || brutFin > fin)
    ? { premiere: hhmm(deb0), derniere: hhmm(fin0) } : null;
  return { debut: hhmm(deb), fin: hhmm(fin), pause: null, source: "mesure", hors };
}

/** Heures travaillées entre deux bornes, pause déduite (défaut : 1 h au-delà de 6 h — la règle du serveur). */
export function heuresTravaillees(debut, fin, pause) {
  const a = minOf(debut), b = minOf(fin);
  if (isNaN(a) || isNaN(b) || b <= a) return 0;
  const brut = (b - a) / 60;
  const p = (pause === null || pause === undefined || pause === "") ? (brut > 6 ? 1 : 0) : Number(pause) || 0;
  return Math.max(0, brut - p);
}

/** Les totaux d'une journée, tels que l'en-tête les annonce. */
export function totaux(jour) {
  const somme = (arr, f) => (arr || []).reduce((n, x) => n + (Number(f(x)) || 0), 0);
  const prop = somme(jour && jour.proposition, l => l.minutes);
  const deja = somme(jour && jour.deja_saisi, s => s.minutes);
  const regie = somme(jour && jour.regie, r => r.minutes);
  const ia = somme(jour && jour.ia, k => k.minutes);
  return {
    mesure: Math.round(Number(jour && jour.mesure_min) || 0),
    propose: Math.round(prop), deja: Math.round(deja), regie: Math.round(regie),
    total: Math.round(prop + deja),
    ia: Math.round(ia), tours: ((jour && jour.ia) || []).length,
    tokens: somme(jour && jour.ia, k => k.tokens),
  };
}

/** La marque que l'outil pose dans le commentaire d'une saisie qu'il a créée. */
export const MARQUE = "[timesheet:";

/** Une saisie déjà notée vient-elle de l'outil, ou de la main de Mathieu ? */
export function estAutomatique(saisie) {
  return String((saisie && saisie.libelle) || "").includes(MARQUE);
}

/** Où la journée a été travaillée. Vide = non renseigné ; on ne devine pas. */
export const LIEUX = [
  { value: "", label: "—" },
  { value: "presentiel", label: "présentiel" },
  { value: "distanciel", label: "distanciel (maison)" },
];
export function libelleLieu(v) {
  const t = LIEUX.find(x => x.value === String(v || ""));
  return t && t.value ? t.label : "";
}

/** Le commentaire sans sa marque technique — ce qu'on montre à l'écran. */
export function libelleLisible(saisie) {
  const s = String((saisie && saisie.libelle) || "");
  const i = s.indexOf(MARQUE);
  return (i < 0 ? s : s.slice(0, i)).trim() || "—";
}

/**
 * Ce que l'outil a posé sur cette journée, et qui peut donc être repris.
 *
 * Les saisies notées à la main n'en font jamais partie : c'est la frontière qui rend le
 * geste « Reprendre » sûr — il ne peut pas emporter le travail de quelqu'un.
 */
export function poseParOutil(jour) {
  const auto = ((jour && jour.deja_saisi) || []).filter(estAutomatique);
  return { count: auto.length, minutes: Math.round(auto.reduce((n, s) => n + (Number(s.minutes) || 0), 0)) };
}

/** Les lignes de la proposition, groupées par client puis projet — l'ordre dans lequel on les relit. */
export function parClient(jour) {
  const groupes = new Map();
  for (const l of (jour && jour.proposition) || []) {
    const g = groupes.get(l.client) || { client: l.client, minutes: 0, lignes: [] };
    g.minutes += Number(l.minutes) || 0;
    g.lignes.push(l);
    groupes.set(l.client, g);
  }
  for (const g of groupes.values()) {
    g.lignes.sort((a, b) => (b.minutes - a.minutes) || String(a.projet).localeCompare(String(b.projet)));
  }
  return [...groupes.values()].sort((a, b) => b.minutes - a.minutes);
}

/** Tokens → « 180,2 M », « 43 k ». Les ordres de grandeur seuls comptent. */
export function fmtTokens(n) {
  const v = Number(n) || 0;
  if (v >= 1e6) return (v / 1e6).toFixed(1).replace(".", ",") + " M";
  if (v >= 1e3) return Math.round(v / 1e3) + " k";
  return String(Math.round(v));
}

/**
 * L'état d'une journée, en un mot — c'est lui qui pilote la couleur de la pastille et
 * ce que le bouton propose.
 *
 *  `validee`  : des saisies portent la marque du timesheet, ou la journée a été validée sans ajout ;
 *  `a_valider`: une proposition attend ;
 *  `manuelle` : rien à ajouter, mais du temps est déjà noté à la main ;
 *  `vide`     : aucune trace.
 */
export function etat(jour) {
  if (!jour) return "vide";
  if (jour.valide) return "validee";
  const t = totaux(jour);
  if (t.propose > 0) return "a_valider";
  if (t.deja > 0) return "manuelle";
  return t.mesure > 0 ? "a_valider" : "vide";
}

export const ETAT_LABEL = {
  validee: "validée", a_valider: "à valider", manuelle: "saisie à la main", vide: "rien ce jour-là",
};

// ── La pièce à conviction d'une journée (RM3229 / L3b) ────────────────────────
// Un chiffre sans ses preuves demande qu'on le croie. Ces trois listes — les traces,
// les commits, les tours d'agent — donnent la journée à VÉRIFIER, à la minute près.

/** Les traces horodatées, dans l'ordre. `humain` distingue ce qui crée du temps de ce qui l'attribue. */
export function traces(jour) {
  return ((jour && jour.traces) || []).map(t => ({
    heure: t.heure, source: String(t.source || "").replace(/^claude-/, ""),
    humain: !!t.humain, extrait: t.extrait || "",
    cible: [t.client, t.projet].filter(Boolean).join("/"),
    rm: t.ticket || null, chars: t.chars || 0,
  }));
}

/**
 * Les commits de la journée, le travail d'abord.
 *
 * La plomberie PM (`pm(tick)`, merges) date l'activité sans la décrire : elle est
 * comptée à part et repliée, pour ne pas noyer les quelques commits qui disent
 * vraiment ce qui a été fait.
 */
export function commits(jour) {
  const tous = ((jour && jour.commits) || []).map(c => ({
    heure: String(c.ts || "").slice(11, 16), sha: c.sha, depot: c.depot,
    client: c.client, sujet: c.sujet || "", auto: !!c.auto,
  }));
  return { travail: tous.filter(c => !c.auto), plomberie: tous.filter(c => c.auto), total: tous.length };
}

/** Les tours d'agent de la journée, groupés par ticket — où l'IA a réellement travaillé. */
export function toursIA(jour) {
  const parTicket = new Map();
  for (const k of (jour && jour.ia) || []) {
    const cle = k.ticket ? `RM${k.ticket}` : [k.client, k.projet].filter(Boolean).join("/") || "—";
    const g = parTicket.get(cle) || { cle, rm: k.ticket || null, cible: [k.client, k.projet].filter(Boolean).join("/"),
                                      tours: 0, minutes: 0, tokens: 0, modeles: new Set(),
                                      premier: k.heure, dernier: k.heure };
    g.tours += 1;
    g.minutes += Number(k.minutes) || 0;
    g.tokens += Number(k.tokens) || 0;
    if (k.modele) g.modeles.add(k.modele);
    if (k.heure < g.premier) g.premier = k.heure;
    if (k.heure > g.dernier) g.dernier = k.heure;
    parTicket.set(cle, g);
  }
  return [...parTicket.values()]
    .map(g => ({ ...g, modeles: [...g.modeles].join(", "), minutes: Math.round(g.minutes) }))
    .sort((a, b) => b.minutes - a.minutes || b.tours - a.tours);
}

/** Les clients d'une liste `{client, project}`, puis les projets d'un client — la matière des deux menus. */
export function clientsEtProjets(liste) {
  const parClient = new Map();
  for (const p of liste || []) {
    if (!p || !p.client) continue;
    if (!parClient.has(p.client)) parClient.set(p.client, []);
    if (p.project) parClient.get(p.client).push(p.project);
  }
  for (const v of parClient.values()) v.sort();
  return { clients: [...parClient.keys()].sort(), projets: (c) => (parClient.get(c) || []).slice() };
}
