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
    const cur = parMinute.get(k.heure) || { heure: k.heure, tours: 0, minutes: 0, tokens: 0, tickets: [], clients: new Map(), left: pct(x, from, span) };
    cur.tours += 1;
    cur.minutes += Number(k.minutes) || 0;
    cur.tokens += Number(k.tokens) || 0;
    if (k.ticket && !cur.tickets.includes(k.ticket)) cur.tickets.push(k.ticket);
    if (k.client) cur.clients.set(k.client, (cur.clients.get(k.client) || 0) + (Number(k.minutes) || 0));
    parMinute.set(k.heure, cur);
  }
  // Le repère porte la couleur de SON client : la voie IA se lit alors comme la voie
  // humaine, et on voit d'un coup d'œil pour qui l'agent a travaillé.
  const ia = [...parMinute.values()].map(g => {
    const dom = [...g.clients.entries()].sort((a, b) => b[1] - a[1])[0];
    return { ...g, client: dom ? dom[0] : null, couleur: couleurClient(dom ? dom[0] : null) };
  }).sort((a, b) => (a.left - b.left));
  const a0 = minOf(start), a1 = minOf(end);
  const normal = (!isNaN(a0) && !isNaN(a1) && a1 > a0)
    ? { left: pct(a0, from, span), width: pct(a1, from, span) - pct(a0, from, span), debut: start, fin: end }
    : null;
  // Une journée large (24 h) ne tient pas 25 étiquettes : elles se chevauchent et la
  // règle devient illisible. On garde toutes les graduations, on espace les ÉTIQUETTES.
  const pas = span > 18 * 60 ? 180 : span > 12 * 60 ? 120 : 60;
  const heures = [];
  for (let h = from; h <= to; h += 60) {
    heures.push({ label: (h % pas === 0) ? hhmm(h) : "", left: pct(h, from, span) });
  }
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
  // Le temps IA est celui que les tours DÉCLARENT. On ne le rabote pas : deux agents en
  // parallèle produisent bien deux fois du travail, même si l'horloge n'avance qu'une fois
  // (arbitrage Mathieu 2026-09-22, après un premier essai de bornage qu'il a retiré).
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
    merge: !!c.merge, rm: c.rm || null, branche: c.branche || "", cible: c.cible || "",
  }));
  // Une LIVRAISON (MR fusionnée) ne se range pas avec les commits ordinaires : c'est
  // du travail qui est sorti, et c'est ce qu'on montre en premier à un client.
  return { travail: tous.filter(c => !c.auto && !c.merge),
           fusions: tous.filter(c => c.merge),
           plomberie: tous.filter(c => c.auto && !c.merge), total: tous.length };
}

/** Les tours d'agent de la journée, groupés par ticket — où l'IA a réellement travaillé. */
export function toursIA(jour) {
  const parTicket = new Map();
  for (const k of (jour && jour.ia) || []) {
    const cle = k.ticket ? `RM${k.ticket}` : [k.client, k.projet].filter(Boolean).join("/") || "—";
    const g = parTicket.get(cle) || { cle, rm: k.ticket || null, cible: [k.client, k.projet].filter(Boolean).join("/"),
                                      tours: 0, minutes: 0, chevauche: 0,
                                      tokens: 0, modeles: new Set(),
                                      premier: k.heure, dernier: k.heure };
    g.tours += 1;
    g.minutes += Number(k.minutes) || 0;
    g.tokens += Number(k.tokens) || 0;
    if (k.borne) g.chevauche += 1;
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

// ── La pause de midi (RM3229) ─────────────────────────────────────────────────

/**
 * Ce que l'écran dit de la pause : est-elle déclarée, apparaît-elle dans les traces,
 * et que proposer si elle manque.
 *
 * Elle ne se devine pas. Une journée sans trou à midi peut être une journée sans pause
 * (sandwich devant l'écran) ou une pause que rien n'a tracée : c'est à l'humain de dire
 * laquelle. L'écran se contente de signaler qu'elle n'apparaît pas.
 */
export function pause(jour) {
  const p = (jour && jour.pause) || null;
  const cible = (p && p.cible) || {};
  const declaree = Number(p && p.declaree_h) || 0;
  // Les bornes POSÉES à la main l'emportent sur le trou mesuré : c'est le geste par
  // lequel on corrige une détection, il ne doit pas être réécrit par elle.
  const posee = (p && p.debut && p.fin) ? { debut: p.debut, fin: p.fin } : null;
  const trou = posee || ((p && p.trou) || null);
  return {
    declaree, trou, posee,
    // D'où vient cette pause : notée sur la journée, ou héritée des horaires
    // habituels de la présence. Sans le dire, elle paraîtrait sortie de nulle part.
    heritee: !!p && p.origine === "presence",
    debut: posee ? posee.debut : "", fin: posee ? posee.fin : "",
    visible: !!trou,
    // Sans bloc `pause` du serveur, on ne SAIT pas : une journée d'avant cette
    // fonctionnalité ne doit pas réclamer une pause qu'on n'a pas cherchée.
    manquante: !!p && !declaree && !trou,
    proposition: Number(cible.heures) || 1,
    ou: [cible.client, cible.projet].filter(Boolean).join("/") || "",
    commentaire: cible.commentaire || "",
    texte: declaree
      ? `pause déclarée : ${posee ? `${posee.debut}–${posee.fin} · ` : ""}${fmtMin(declaree * 60)}${cible.client ? ` sur ${cible.client}` : ""}`
      : trou
        ? `pause visible dans les traces : ${trou.debut}–${trou.fin} (${fmtMin(trou.minutes)})`
        : p ? "aucune pause visible ce jour-là" : "",
  };
}

/** Les lignes que la journée ne facturera à personne — son propre temps (entités `self`). */
export function nonFacturable(jour) {
  const lignes = ((jour && jour.proposition) || []).filter(l => l.facturable === false);
  return { count: lignes.length, minutes: Math.round(lignes.reduce((n, l) => n + (Number(l.minutes) || 0), 0)) };
}

// ── Couleurs par client, bandes de la frise, fil unique des actions (RM3229) ──

/**
 * Une teinte stable par client, dérivée de son nom.
 *
 * Pas de palette fixe : les clients vont et viennent, et une table à maintenir
 * finirait par attribuer deux fois la même couleur sans qu'on le voie. Le nom donne
 * la teinte ; la même partout, d'une journée à l'autre et d'un écran à l'autre.
 */
export function couleurClient(nom) {
  const s = String(nom || "");
  if (!s || s === "null") return "var(--muted)";
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) % 360;
  return `hsl(${h} 62% 56%)`;
}

/** « null » / vide → ce que l'écran doit lire : du temps qu'on n'a pas su rattacher. */
export function nomClient(c) {
  return (!c || c === "null") ? "non attribué" : String(c);
}

/**
 * Les bandes colorées de la frise, positionnées et légendées.
 *
 * Chaque bande porte sa répartition complète : la couleur ne montre que le client
 * dominant, le survol dit le détail — sans quoi une bande « pisceen » cacherait
 * les 4 minutes de calicote qu'elle contient.
 */
export function bandes(jour, { from, span }) {
  return ((jour && jour.bandes) || []).map(b => {
    const x0 = minOf(b.debut), x1 = minOf(b.fin);
    const detail = Object.entries(b.parts || {})
      .map(([c, m]) => `${nomClient(c)} ${fmtMin(m)}`).join(" · ");
    return {
      debut: b.debut, fin: b.fin, client: nomClient(b.client),
      couleur: couleurClient(b.client), minutes: b.minutes,
      left: Math.max(0, ((x0 - from) / span) * 100),
      width: Math.max(0.4, ((x1 - x0) / span) * 100),
      titre: `${b.debut}–${b.fin} · ${fmtMin(b.minutes)}\n${detail}`,
    };
  }).filter(b => !isNaN(b.left));
}

/** La légende : un client, sa couleur, son cumul de la journée. */
export function legende(jour) {
  const cumul = new Map();
  for (const b of (jour && jour.bandes) || []) {
    for (const [c, m] of Object.entries(b.parts || {})) {
      cumul.set(c, (cumul.get(c) || 0) + (Number(m) || 0));
    }
  }
  return [...cumul.entries()]
    .sort((a, b) => b[1] - a[1])
    .map(([c, m]) => ({ client: nomClient(c), couleur: couleurClient(c),
                        minutes: Math.round(m), duree: fmtMin(m) }));
}

/** La bande neutre de la pause : déclarée si elle l'est, sinon le trou mesuré. */
export function bandePause(jour, { from, span }) {
  const p = pause(jour);
  const t = p.posee || p.trou;
  if (!t) return null;
  const x0 = minOf(t.debut), x1 = minOf(t.fin);
  if (isNaN(x0) || isNaN(x1)) return null;
  return {
    debut: t.debut, fin: t.fin, minutes: t.minutes,
    left: Math.max(0, ((x0 - from) / span) * 100),
    width: Math.max(0.4, ((x1 - x0) / span) * 100),
    declaree: !!p.declaree,
    titre: `pause ${t.debut}–${t.fin}`
           + (p.posee ? ` · posée à la main (${fmtMin(p.declaree * 60)})`
                      : ` (${fmtMin(t.minutes)}) · vue dans les traces`),
  };
}

/** Le cumul de temps transversal reçu par chaque client ce jour-là. */
export function transversalParClient(jour) {
  const t = (jour && jour.transversal_par_client) || {};
  return Object.entries(t)
    .sort((a, b) => b[1] - a[1])
    .map(([c, m]) => ({ client: nomClient(c), couleur: couleurClient(c),
                        minutes: m, duree: fmtMin(m) }));
}

/**
 * TOUT ce qui s'est passé dans la journée, en un seul fil chronologique.
 *
 * Trois listes séparées obligeaient à faire la couture dans sa tête pour savoir ce qui
 * précède quoi. Ici, une trace, un commit et un tour d'agent se lisent dans l'ordre
 * où ils sont arrivés — c'est comme ça qu'on reconstitue une journée.
 */
export function fil(jour) {
  const out = [];
  for (const t of traces(jour)) {
    out.push({ heure: t.heure, genre: "trace", source: t.source, humain: t.humain,
               cible: t.cible, rm: t.rm, texte: t.extrait });
  }
  for (const c of commits(jour).travail) {
    out.push({ heure: c.heure, genre: "commit", source: c.depot, humain: true,
               cible: c.client || "", rm: null, texte: c.sujet, sha: c.sha });
  }
  for (const c of commits(jour).fusions) {
    out.push({ heure: c.heure, genre: "livraison", source: c.depot, humain: true,
               cible: c.client || "", rm: c.rm, sha: c.sha,
               texte: `${c.branche || c.sujet}${c.cible ? " → " + c.cible : ""}` });
  }
  for (const c of commits(jour).plomberie) {
    out.push({ heure: c.heure, genre: "plomberie", source: c.depot, humain: false,
               cible: c.client || "", rm: null, texte: c.sujet, sha: c.sha });
  }
  for (const k of (jour && jour.ia) || []) {
    out.push({ heure: k.heure, genre: "ia", source: k.modele || "agent", humain: false,
               cible: [k.client, k.projet].filter(Boolean).join("/"), rm: k.ticket,
               texte: `${fmtMin(k.minutes)}${k.borne ? " (en parallèle du tour suivant)" : ""}`
                      + ` · ${fmtTokens(k.tokens)} tokens`, chevauche: !!k.borne });
  }
  return out.sort((a, b) => (a.heure < b.heure ? -1 : a.heure > b.heure ? 1 : 0));
}

/**
 * Le temps IA de la journée : ce que les tours déclarent, sans rabot.
 *
 * Le recouvrement entre tours est SIGNALÉ, jamais retranché : quand deux agents
 * tournent en parallèle, le travail produit dépasse légitimement l'horloge.
 */
export function totauxIA(jour) {
  const ia = (jour && jour.ia) || [];
  const declare = ia.reduce((n, k) => n + (Number(k.minutes) || 0), 0);
  const horloge = ia.reduce((n, k) => n + (Number(k.minutes_reelles != null ? k.minutes_reelles : k.minutes) || 0), 0);
  return { tours: ia.length, minutes: Math.round(declare),
           paralleles: ia.filter(k => k.borne).length,
           horloge: Math.round(horloge) };
}

// ── Relier le temps IA au temps humain (RM3229) ───────────────────────────────
//
// Une plage humaine facturée doit pouvoir se justifier : ce qui s'y est passé, et ce
// qui en est sorti. Ces fonctions font la couture — chaque tour d'agent, chaque commit,
// chaque livraison est rattaché à l'intervalle humain qui le contient.

const dedans = (x, a, b) => !isNaN(x) && x >= a && x <= b;

/**
 * Les intervalles humains de la journée, chacun avec ce qu'il contient.
 *
 * `orphelins` recueille ce qui ne tombe dans AUCUN intervalle : c'est le cas qui
 * intéresse: un tour d'agent sans trace humaine autour veut dire soit qu'on a oublié
 * une plage, soit que l'agent a tourné seul — et les deux se traitent différemment.
 */
export function correspondances(jour) {
  const periodes = ((jour && jour.periodes) || []).map(([a, b], i) => ({
    i, debut: a, fin: b, min: minOf(a), max: minOf(b),
    minutes: Math.max(0, minOf(b) - minOf(a)),
    ia: [], commits: [], fusions: [], prompts: [], redmine: [], clients: new Map(),
  }));
  const orphelins = { ia: [], commits: [], fusions: [], prompts: [], redmine: [] };
  const loge = (x, genre, item) => {
    const p = periodes.find(q => dedans(x, q.min, q.max));
    (p ? p[genre] : orphelins[genre]).push(item);
    return p || null;
  };

  for (const k of (jour && jour.ia) || []) {
    const p = loge(minOf(k.heure), "ia", {
      heure: k.heure, minutes: Number(k.minutes) || 0, modele: k.modele || "",
      rm: k.ticket || null, client: k.client || null,
      cible: [k.client, k.projet].filter(Boolean).join("/"),
    });
    if (p && k.client) p.clients.set(k.client, (p.clients.get(k.client) || 0) + (Number(k.minutes) || 0));
  }
  for (const t of traces(jour)) {
    // Seules les traces HUMAINES font preuve ici : une trace d'agent est déjà comptée
    // comme tour d'IA, la reprendre comme « ce que l'humain a écrit » serait mentir.
    if (!t.humain) continue;
    const item = { heure: t.heure, source: t.source, cible: t.cible, rm: t.rm, texte: t.extrait };
    loge(minOf(t.heure), t.source.includes("redmine") ? "redmine" : "prompts", item);
  }
  for (const c of ((jour && jour.commits) || [])) {
    const heure = String(c.ts || "").slice(11, 16);
    const item = { heure, sha: c.sha, depot: c.depot, client: c.client, sujet: c.sujet,
                   rm: c.rm || null, branche: c.branche || "", cible: c.cible || "" };
    if (c.merge) loge(minOf(heure), "fusions", item);
    else if (!c.auto) loge(minOf(heure), "commits", item);
  }

  for (const p of periodes) {
    // Les bandes colorées donnent le client de la plage ; à défaut, les tours d'agent.
    for (const b of (jour && jour.bandes) || []) {
      if (dedans(minOf(b.debut), p.min, p.max) || dedans(minOf(b.fin), p.min, p.max)) {
        for (const [c, m] of Object.entries(b.parts || {})) {
          if (c && c !== "null") p.clients.set(c, (p.clients.get(c) || 0) + (Number(m) || 0));
        }
      }
    }
    p.clients = [...p.clients.entries()].sort((a, b) => b[1] - a[1])
      .map(([c, m]) => ({ client: nomClient(c), couleur: couleurClient(c), minutes: Math.round(m) }));
    p.preuves = p.ia.length + p.commits.length + p.fusions.length + p.prompts.length + p.redmine.length;
  }
  return { periodes, orphelins };
}

/**
 * Les traits qui relient un tour d'agent à sa plage humaine.
 *
 * Un tour rattaché pointe vers le MILIEU de sa plage : plusieurs tours convergent
 * alors visiblement vers la même plage. Un tour orphelin n'est relié à rien et le
 * montre — c'est l'information, pas un défaut d'affichage.
 */
export function liens(jour, { from, span }) {
  const pos = (m) => ((m - from) / span) * 100;
  const periodes = ((jour && jour.periodes) || []).map(([a, b]) => ({ min: minOf(a), max: minOf(b), debut: a, fin: b }));
  const out = [];
  for (const k of (jour && jour.ia) || []) {
    const x = minOf(k.heure);
    if (isNaN(x)) continue;
    const p = periodes.find(q => dedans(x, q.min, q.max));
    out.push({
      x1: pos(x),
      x2: p ? pos((p.min + p.max) / 2) : pos(x),
      couleur: couleurClient(k.client),
      orphelin: !p,
      titre: p
        ? `${k.heure} · ${fmtMin(k.minutes)}${k.ticket ? " · RM" + k.ticket : ""} → plage ${p.debut}–${p.fin}`
        : `${k.heure} · ${fmtMin(k.minutes)} — AUCUNE trace humaine à cette heure`,
    });
  }
  return out.filter(l => l.x1 >= -1 && l.x1 <= 101);
}

/** Le compte rendu d'une mise en correspondance : ce qui tient, et ce qui ne tient pas. */
export function bilanCorrespondance(jour) {
  const { periodes, orphelins } = correspondances(jour);
  const sansPreuve = periodes.filter(p => !p.preuves);
  return {
    periodes: periodes.length,
    sansPreuve: sansPreuve.length,
    iaOrphelins: orphelins.ia.length,
    minutesOrphelines: Math.round(orphelins.ia.reduce((n, k) => n + k.minutes, 0)),
    commitsOrphelins: orphelins.commits.length + orphelins.fusions.length,
  };
}

// ── Les blocs destinés à Redmine, et ce qui les justifie (RM3229) ─────────────
//
// L'UNITÉ de ce qui sera inséré dans Redmine est le BLOC : du temps, une activité, UN
// projet, si possible un ticket. Une plage de travail humain n'en est pas un — elle peut
// nourrir plusieurs blocs si on a changé de client pendant. C'est le bloc qu'on valide,
// c'est donc lui qu'il faut pouvoir justifier.

/** Le nom lisible d'une activité Redmine, ou son numéro à défaut. */
export function nomActivite(jour, id) {
  const t = (jour && jour.activites) || {};
  return t[String(id)] || (id ? `activité ${id}` : "");
}

/**
 * Les blocs de la journée, chacun avec les preuves qui le soutiennent.
 *
 * Une preuve rejoint un bloc quand elle porte le MÊME ticket, ou à défaut le même
 * client/projet. Un bloc sans la moindre preuve est signalé : c'est du temps réparti
 * par la clé de refacturation, pas du travail directement observé — légitime, mais à
 * regarder avant de le facturer.
 */
export function blocsRedmine(jour) {
  const prompts = traces(jour).filter(t => t.humain);
  const cm = commits(jour);
  const ia = (jour && jour.ia) || [];

  return ((jour && jour.proposition) || []).map(l => {
    const cible = [l.client, l.projet].filter(Boolean).join("/");
    const memeCible = (c, p) => c === l.client && (!l.projet || !p || p === l.projet);
    const parTicket = (rm) => l.ticket && String(rm) === String(l.ticket);

    const sesIa = ia.filter(k => parTicket(k.ticket) || (!l.ticket && memeCible(k.client, k.projet)));
    const sesPrompts = prompts.filter(t => parTicket(t.rm) || (!l.ticket && t.cible === cible));
    const sesCommits = cm.travail.filter(c => c.client === l.client);
    const sesFusions = cm.fusions.filter(c => parTicket(c.rm) || c.client === l.client);

    const heures = [...sesIa.map(k => k.heure), ...sesPrompts.map(t => t.heure)].sort();
    return {
      jour: l.jour, client: l.client, projet: l.projet || "", ticket: l.ticket || null,
      minutes: l.minutes, duree: fmtMin(l.minutes),
      activite: l.activite, activiteNom: nomActivite(jour, l.activite),
      facturable: l.facturable !== false,
      outillage: l.outillage_min || 0,
      couleur: couleurClient(l.client),
      ia: sesIa.map(k => ({ heure: k.heure, minutes: Number(k.minutes) || 0, modele: k.modele || "" })),
      iaDuree: fmtMin(sesIa.reduce((n, k) => n + (Number(k.minutes) || 0), 0)),
      prompts: sesPrompts, commits: sesCommits, fusions: sesFusions,
      plage: heures.length ? `${heures[0]}–${heures[heures.length - 1]}` : "",
      preuves: sesIa.length + sesPrompts.length + sesCommits.length + sesFusions.length,
    };
  }).sort((a, b) => b.minutes - a.minutes);
}

/** Les tours d'agent qui ne tombent dans aucune plage humaine — informatif, jamais facturé. */
export function iaHorsPlage(jour) {
  const periodes = ((jour && jour.periodes) || []).map(([a, b]) => [minOf(a), minOf(b)]);
  return ((jour && jour.ia) || [])
    .filter(k => { const x = minOf(k.heure); return !isNaN(x) && !periodes.some(([a, b]) => x >= a && x <= b); })
    .map(k => ({ heure: k.heure, minutes: Number(k.minutes) || 0, duree: fmtMin(k.minutes),
                 rm: k.ticket || null, cible: [k.client, k.projet].filter(Boolean).join("/"),
                 couleur: couleurClient(k.client), modele: k.modele || "" }))
    .sort((a, b) => (a.heure < b.heure ? -1 : 1));
}

/** Le bilan des blocs : ce qui tient, ce qui est à regarder. */
export function bilanBlocs(jour) {
  const b = blocsRedmine(jour);
  const hors = iaHorsPlage(jour);
  return {
    blocs: b.length,
    minutes: b.reduce((n, x) => n + x.minutes, 0),
    sansPreuve: b.filter(x => !x.preuves).length,
    sansTicket: b.filter(x => !x.ticket).length,
    clients: [...new Set(b.map(x => x.client))].length,
    iaHorsPlage: hors.length,
    minutesHorsPlage: Math.round(hors.reduce((n, k) => n + k.minutes, 0)),
  };
}

// ── La note de la journée (RM3229) ────────────────────────────────────────────

/**
 * Ce que Mathieu a écrit de sa main ce jour-là, lu sur le Nextcloud.
 *
 * C'est la source la plus directe qui soit : une note dit les horaires et les clients
 * que les traces ne sauront jamais. Elle est en TEXTE LIBRE — on l'affiche, on ne
 * l'interprète pas. Les horaires ne sont proposés que quand une ligne ne contient
 * QUE la plage ; sinon « Pause 2h repas 12h30-14h30 » passerait pour une journée.
 */
export function note(jour) {
  const n = (jour && jour.note) || null;
  if (!n) return null;
  const h = n.heures && n.heures.length === 2 ? { debut: n.heures[0], fin: n.heures[1] } : null;
  const lignes = String(n.texte || "").split("\n");
  return {
    chemin: n.chemin || "", fichier: (n.chemin || "").split("/").pop(),
    texte: String(n.texte || "").trim(),
    lignes: lignes.length,
    heures: h,
    resume: lignes.map(l => l.trim()).filter(Boolean).slice(1, 4).join(" · ").slice(0, 90),
  };
}

/**
 * La notice de la voie IA : pour qui les agents ont travaillé, et combien.
 *
 * La voie humaine a sa légende ; la voie IA était colorée sans rien pour la lire. Or
 * un agent travaille souvent sur un client où l'humain n'a presque pas de trace — ce
 * sont justement ces couleurs-là qu'on ne savait pas nommer.
 */
export function legendeIA(jour) {
  const parClient = new Map();
  for (const k of (jour && jour.ia) || []) {
    const c = k.client || null;
    const g = parClient.get(c) || { client: nomClient(c), couleur: couleurClient(c),
                                    tours: 0, minutes: 0, tickets: new Set() };
    g.tours += 1;
    g.minutes += Number(k.minutes) || 0;
    if (k.ticket) g.tickets.add(k.ticket);
    parClient.set(c, g);
  }
  return [...parClient.values()]
    .map(g => ({ ...g, minutes: Math.round(g.minutes), duree: fmtMin(g.minutes),
                 tickets: [...g.tickets].sort((a, b) => a - b) }))
    .sort((a, b) => b.minutes - a.minutes);
}

// ── Vues semaine et mois (RM3229, lot L4) ─────────────────────────────────────
//
// Valider cent journées une par une, sans jamais voir où l'on en est, décourage avant
// d'avoir fini. Ces grilles donnent la vue d'ensemble : ce qui est validé, ce qui
// attend, et ce qui n'a rien.

/** L'état d'une journée résumée, en un mot — il pilote la couleur de sa case. */
export function etatResume(r) {
  if (!r) return "hors";
  if (r.absence) return "absence";
  if (r.valide) return "validee";
  if (r.propose_min > 0) return "a_valider";
  if (r.deja_min > 0) return "manuelle";
  return "vide";
}

const MOIS_NOMS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
                   "août", "septembre", "octobre", "novembre", "décembre"];

/** « 2026-09 » → « septembre 2026 ». */
export function nomMois(mois) {
  const [a, m] = String(mois || "").split("-");
  return MOIS_NOMS[Number(m) - 1] ? `${MOIS_NOMS[Number(m) - 1]} ${a}` : String(mois || "");
}

/** Le mois d'une journée, et le mois voisin. */
export function moisDe(day) { return String(day || "").slice(0, 7); }
export function decalerMois(mois, n) {
  const [a, m] = String(mois).split("-").map(Number);
  const d = new Date(Date.UTC(a, m - 1 + Number(n || 0), 1));
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}`;
}

/** Une case de grille : la journée résumée, mise en forme. Jamais de calcul dans la vue. */
export function caseJour(jour, resumes, { courant = "" } = {}) {
  const r = (resumes || {})[jour] || null;
  const d = new Date(jour + "T12:00:00Z");
  // Triés du plus lourd au plus léger, avec leur part : la barre dit QUI, sa longueur dit
  // COMBIEN. Des segments égaux laisseraient croire à un partage à parts égales.
  const brut = Object.entries((r && r.par_client) || {}).sort((a, z) => z[1] - a[1]);
  const totalCl = brut.reduce((n, [, m]) => n + m, 0) || 1;
  const clients = brut.map(([c, m]) => ({ client: nomClient(c), couleur: couleurClient(c),
                                          minutes: m, duree: fmtMin(m),
                                          part: Math.round((m / totalCl) * 1000) / 1000 }));
  return {
    date: jour, jourDuMois: isNaN(d.getTime()) ? "" : String(d.getUTCDate()),
    weekend: isWeekend(jour), courant: jour === courant,
    etat: etatResume(r), vide: !r,
    mesure: r ? fmtMin(r.mesure_min) : "", propose: r ? fmtMin(r.propose_min) : "",
    deja: r ? fmtMin(r.deja_min) : "",
    proposeMin: r ? r.propose_min : 0,
    clients,
    ia: r ? r.ia_tours : 0, commits: r ? r.commits : 0,
    note: !!(r && r.note), ajuste: !!(r && r.ajuste), lieu: (r && r.lieu) || "",
    titre: r
      ? `${longDate(jour)}\n${fmtMin(r.mesure_min)} mesurées · ${fmtMin(r.propose_min)} à valider`
        + (r.deja_min ? ` · ${fmtMin(r.deja_min)} déjà noté` : "")
        + (clients.length ? `\n${clients.map(c => `${c.client} ${c.duree}`).join(" · ")}` : "")
      : longDate(jour),
  };
}

/** Les sept jours de la semaine d'une journée. */
export function grilleSemaine(day, resumes, courant) {
  return weekOf(day).map(j => caseJour(j, resumes, { courant: courant || day }));
}

/** Le mois en semaines complètes — lundi à dimanche, débords inclus pour l'alignement. */
export function grilleMois(mois, resumes, courant) {
  const [a, m] = String(mois).split("-").map(Number);
  if (!a || !m) return [];
  const premier = `${mois}-01`;
  const dernier = new Date(Date.UTC(a, m, 0)).toISOString().slice(0, 10);
  const semaines = [];
  let curseur = weekOf(premier)[0];
  while (curseur <= dernier) {
    semaines.push({
      lundi: curseur,
      jours: weekOf(curseur).map(j => ({ ...caseJour(j, resumes, { courant }),
                                         horsMois: moisDe(j) !== mois })),
    });
    curseur = shiftDay(curseur, 7);
  }
  return semaines;
}

/**
 * Où en est la validation du mois — l'indicateur qui manquait.
 *
 * On ne compte QUE les journées qui ont quelque chose : une journée vide n'est pas du
 * travail en retard, et la faire figurer au dénominateur ferait croire à un retard qui
 * n'existe pas.
 */
export function avancement(resumes) {
    const tous = Object.values(resumes || {});
  const actives = tous.filter(r => r.propose_min > 0 || r.deja_min > 0 || r.valide);
  const validees = actives.filter(r => r.valide);
  const attente = actives.filter(r => !r.valide && r.propose_min > 0);
  const minutes = attente.reduce((n, r) => n + r.propose_min, 0);
  return {
    actives: actives.length, validees: validees.length, attente: attente.length,
    minutes, duree: fmtMin(minutes),
    pct: actives.length ? Math.round((validees.length / actives.length) * 100) : 0,
    vides: tous.length - actives.length,
  };
}

/** Le cumul par client sur un ensemble de journées — ce que la semaine ou le mois pèse. */
export function cumulClients(resumes) {
  const par = new Map();
  for (const r of Object.values(resumes || {})) {
    for (const [c, m] of Object.entries(r.par_client || {})) {
      par.set(c, (par.get(c) || 0) + m);
    }
  }
  return [...par.entries()].sort((a, b) => b[1] - a[1])
    .map(([c, m]) => ({ client: nomClient(c), couleur: couleurClient(c),
                        minutes: m, duree: fmtMin(m) }));
}
