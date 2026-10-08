// modules/feed/FeedViewModel — le fil, décidé : ce qui attend, d'où ça vient, depuis quand, et à
// qui ça s'adresse. RM2792. Une FILE, pas une trace : ce qui est traité sort de la vue.
import { EntityViewModel } from "../../core/EntityViewModel.js";

const ICONE = { info: "ℹ️", warn: "⚠️", critical: "🔴" };
const CLS = { info: "", warn: "wait", critical: "due" };
const MARQUE = { neuf: "●", lu: "○", traite: "✓" };

/** Depuis combien de temps cette notification se répète (RM3206).
 *  « ×12 » ne se lit pas : ×12 en dix minutes et ×12 sur trois jours appellent des réactions
 *  opposées. On rend la FENÊTRE entre la première et la dernière, pas seulement le compte. */
export function fenetre(ts, last) {
  const a = Date.parse(ts || ""), b = Date.parse(last || "");
  if (!a || !b || b <= a) return "";
  const min = Math.round((b - a) / 60000);
  if (min < 60) return `${min} min`;
  const h = Math.round(min / 60);
  return h < 48 ? `${h} h` : `${Math.round(h / 24)} j`;
}

/** La mesure qui a déclenché l'alerte, quand il y en a une (RM3206).
 *  `pm-context-budget` passe déjà tokens/budget/pct et le rendu les jetait : « la précharge a
 *  entamé sa marge » ne situe rien, « 28 048 / 29 000 (97 %) » se lit d'un coup d'œil. */
export function mesure(n) {
  const v = n.tokens, max = n.budget, pct = n.pct;
  if (v == null && pct == null) return "";
  const nb = (x) => Number(x).toLocaleString("fr-FR");
  const base = (v != null && max != null) ? `${nb(v)} / ${nb(max)}${pct != null ? ` (${nb(pct)} %)` : ""}`
    : (pct != null ? `${nb(pct)} %` : nb(v));
  return base + tendance(n);
}

/** RM3177 — la TENDANCE : « 98 % » dit où l'on est, « +5,3 pts en 21 j » dit ce qu'il faut faire.
 *  Une valeur seule ne distingue pas un plateau d'une dérive. */
export function tendance(n) {
  const d = n.tendance, j = n.tendance_jours;
  if (d == null || !j) return "";
  const signe = d > 0 ? "+" : "";
  return `, ${signe}${Number(d).toLocaleString("fr-FR")} pts en ${j} j`;
}

/** e = { data: {feed, counts, viewer, users, origins, levels}, error, etat, user } */
export class FeedViewModel extends EntityViewModel {
  constructor(e, ctx) { super(e || {}, ctx); this.d = this.e.data || {}; }
  get error() { return this.e.error || ""; }
  get counts() { return this.d.counts || { open: 0, neuf: 0, worst: null }; }
  get viewer() { return this.d.viewer || ""; }
  get empty() { return !this.error && !(this.d.feed || []).length; }
  get etat() { return this.e.etat || "ouvert"; }
  get user() { return this.e.user || ""; }
  /** Deux vues, et c'est tout : ce qui attend, et l'historique. Un fil qui s'ouvre sur le traité
   *  n'est plus une file. */
  get vues() {
    return [["ouvert", "ce qui attend"], ["tout", "tout, y compris traité"]]
      .map(([v, l]) => ({ key: v, label: l, on: v === this.etat }));
  }
  /** Le filtre par personne : « tout le monde » d'abord, puis les destinataires réellement présents. */
  get users() {
    return [{ key: "", label: "tout le monde", on: !this.user }]
      .concat((this.d.users || []).map(u => ({ key: u, label: u, on: u === this.user })));
  }
  rows() {
    return (this.d.feed || []).map(n => ({
      id: n.id, icone: ICONE[n.level] || "•", cls: CLS[n.level] || "", niveau: n.level || "info",
      marque: MARQUE[n.etat] || "·", etat: n.etat || "neuf", origine: n.origin || "",
      msg: n.msg || "", quand: String(n.last || n.ts || "").slice(0, 16).replace("T", " "),
      repeats: Number(n.repeats || 1),
      // Un privé se VOIT : sinon on ne sait pas qu'on regarde quelque chose que les autres n'ont pas.
      user: n.user || "", prive: !!n.private,
      rm: n.rm ? String(n.rm) : "", ref: n.ref ? String(n.ref) : "",
      // RM3206 — le CONTEXTE : de quoi ça parle, et où. Ces champs arrivaient déjà pour
      // certains (`job` de l'ordonnanceur, `sid` des sessions) et étaient jetés ici.
      job: n.job ? String(n.job) : "",
      sid: n.sid ? String(n.sid) : "",
      client: n.client ? String(n.client) : "",
      projet: n.projet ? String(n.projet) : "",
      mesure: mesure(n),
      // RM3177 — les invariants rouges du doctor : la notification est stable, la LISTE dit lesquels
      invariants: Array.isArray(n.invariants) ? n.invariants.map(String) : [],
      fenetre: fenetre(n.ts, n.last),
      traite: n.etat === "traite",
    }));
  }
}
