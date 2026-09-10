// modules/refresh/push.service — le canal de push du cockpit (RM3006) : un EventSource sur /api/session/events qui porte les MÊMES specs
// `bloc:hash` que le composite /refresh ; le serveur pousse les blocs changés quand un script PM publie (statut, note, worklog, mail).
// La pile /refresh reste : le tick est le repli (période allongée quand le canal est vivant), et il réconcilie. Aucun DOM.
// `open` = fabrique d'EventSource prêtée (boot : (u) => new EventSource(u)) — jamais une référence détachée au natif (garde core § 13).
import { route } from "../../core/endpoints.js";

export class PushService {
  constructor({ open = null, url = () => route("session.events"), token = null } = {}) {
    this.open = open; this.url = url; this.token = token;
    this.es = null; this.alive = false; this.key = "";
    this.stats = { opened: 0, blocks: 0, topics: 0, errors: 0 };
    this.onBlocks = null; this.onTopics = null; this.onState = null;
  }
  /** La signature d'un jeu de specs : les NOMS de blocs (le sid du worklog compris), pas les hashs — et la présence d'un jeton. */
  keyOf(specs) { return (specs || []).map(s => (s.startsWith("worklog:") ? s.split(":").slice(0, -1).join(":") : s.split(":")[0])).join(",") + "|" + (this.token && this.token() ? "1" : "0"); }
  /** (Re)connecte avec ces specs ; rend false si aucune fabrique (node, navigateur sans EventSource). */
  connect(specs) {
    this.disconnect();
    if (!this.open) return false;
    this.key = this.keyOf(specs);
    const tok = this.token ? this.token() : "";
    const u = this.url() + "?blocks=" + encodeURIComponent((specs || []).join(",")) + (tok ? "&token=" + encodeURIComponent(tok) : "");
    let es; try { es = this.open(u); } catch (e) { this.stats.errors++; return false; }
    if (!es || !es.addEventListener) return false;
    this.es = es; this.stats.opened++;
    es.addEventListener("open", () => this._state(true));
    es.addEventListener("hello", () => this._state(true));
    es.addEventListener("error", () => { this.stats.errors++; this._state(false); });   // EventSource se reconnecte seul ; entre-temps le tick reprend sa cadence
    es.addEventListener("topics", (ev) => { const d = this._json(ev); if (d && this.onTopics) { this.stats.topics++; this.onTopics(d.topics || [], d); } });
    es.addEventListener("blocks", (ev) => { const d = this._json(ev); if (d && this.onBlocks) { this.stats.blocks++; this.onBlocks(d); } });
    return true;
  }
  /** À chaque tick : reconnecte seulement si l'ensemble des blocs (ou le jeton) a changé — une session attachée, un onglet ouvert. */
  sync(specs) { if (!this.open) return false; if (!this.es || this.keyOf(specs) !== this.key) return this.connect(specs); return true; }
  disconnect() { if (this.es) { try { this.es.close(); } catch (e) { /* déjà fermé */ } this.es = null; } this._state(false); }
  _json(ev) { try { return JSON.parse(ev && ev.data); } catch (e) { return null; } }
  _state(on) { if (on !== this.alive) { this.alive = on; if (this.onState) this.onState(on); } }
  state() { return Object.assign({ alive: this.alive, connected: !!this.es, names: this.key.split("|")[0] }, this.stats); }
}
