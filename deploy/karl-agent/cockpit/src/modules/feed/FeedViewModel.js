// modules/feed/FeedViewModel — le fil, décidé : ce qui attend, d'où ça vient, depuis quand, et à
// qui ça s'adresse. RM2792. Une FILE, pas une trace : ce qui est traité sort de la vue.
import { EntityViewModel } from "../../core/EntityViewModel.js";

const ICONE = { info: "ℹ️", warn: "⚠️", critical: "🔴" };
const CLS = { info: "", warn: "wait", critical: "due" };
const MARQUE = { neuf: "●", lu: "○", traite: "✓" };

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
      traite: n.etat === "traite",
    }));
  }
}
