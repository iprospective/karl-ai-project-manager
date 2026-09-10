// modules/clientnotify/clientnotify.service — l'état du compte-rendu client : la file, le client ouvert,
// les tickets cochés, l'aperçu de l'email correspondant. RM3052.
//
// Une règle tient tout : **ce qui est coché est ce qui part**. La sélection ne survit donc jamais à un
// rafraîchissement de la file — un ticket disparu (envoyé ailleurs, écarté) ne doit pas rester coché en
// mémoire et repartir au prochain clic.
import { ClientNotifyRepository } from "./ClientNotifyRepository.js";

/** Pur : les ids réellement en file pour ce client (toutes ses projets confondus). */
export function idsOf(data, client) {
  const c = ((data || {}).clients || []).find(x => x.client === client);
  return c ? c.projects.reduce((acc, p) => acc.concat(p.tickets.map(t => String(t.id))), []) : [];
}

/** Pur : la sélection nettoyée de ce qui n'est plus en file. */
export function prune(sel, ids) {
  const keep = new Set(ids);
  return new Set([...(sel || [])].filter(id => keep.has(id)));
}

export class ClientNotifyService {
  constructor({ repo = new ClientNotifyRepository(), storage = null } = {}) {
    this.repo = repo; this.storage = storage;
    this.data = null; this.client = null; this.sel = new Set();
    this.protocole = true; this.preview = null; this.error = null;
    this.testTo = "";           // destinataire du dernier envoi de test (mémorisé)
    this.dem = new Set();       // RM3092 : tickets dont le DEMANDEUR doit être prévenu
  }
  /** Le protocole de test dans l'email est un choix qui se garde d'une fois sur l'autre (RM3052). */
  loadProto() { try { return this.storage ? this.storage.getItem("karlCnProto") !== "0" : true; } catch (e) { return true; } }
  saveProto(on) { try { if (this.storage) this.storage.setItem("karlCnProto", on ? "1" : "0"); } catch (e) { /* stockage indisponible */ } }
  /** On teste presque toujours vers la même adresse : elle survit au rechargement. */
  loadTestTo() { try { return (this.storage && this.storage.getItem("karlCnTestTo")) || ""; } catch (e) { return ""; } }
  saveTestTo(v) { try { if (this.storage) this.storage.setItem("karlCnTestTo", v || ""); } catch (e) { /* stockage indisponible */ } }
  setTestTo(v) { this.testTo = String(v || "").trim(); this.saveTestTo(this.testTo); }
  /** L'annuaire, une entrée par email — pour choisir sans retaper. */
  get contacts() { return ((this.data || {}).contacts) || []; }

  async load() {
    try { this.data = await this.repo.pending(); this.error = null; } catch (e) { this.data = { clients: [], total: 0 }; this.error = e.message; }
    if (this.client) this.sel = prune(this.sel, idsOf(this.data, this.client));
    return this.data;
  }
  get total() { return ((this.data || {}).total) || 0; }
  get clients() { return ((this.data || {}).clients) || []; }
  current() { return this.clients.find(c => c.client === this.client) || null; }

  /** Ouvre un client : par défaut TOUT est coché — le cas courant est « j'annonce ce qui vient de sortir ». */
  open(client) {
    this.client = client;
    this.protocole = this.loadProto();
    if (!this.testTo) this.testTo = this.loadTestTo();
    this.sel = new Set(idsOf(this.data, client));
    this.dem = new Set();
    this.preview = null;
    return this.current();
  }
  toggle(id) { const s = String(id); if (this.sel.has(s)) this.sel.delete(s); else this.sel.add(s); this.preview = null; }
  /** RM3092 — prévenir aussi le demandeur de CE ticket. */
  toggleDem(id) { const s = String(id); if (this.dem.has(s)) this.dem.delete(s); else this.dem.add(s); this.preview = null; }
  /** …ou de tous ceux qui sont cochés, d'un coup. */
  allDem(on) { this.dem = on ? new Set(this.selected()) : new Set(); this.preview = null; }
  /** Ne prévenir que pour des tickets RÉELLEMENT envoyés : cocher un demandeur puis
   *  décocher son ticket ne doit pas lui expédier un email sur un ticket absent du lot. */
  demSelected() { return this.selected().filter(id => this.dem.has(id)); }
  all(on) { this.sel = on ? new Set(idsOf(this.data, this.client)) : new Set(); if (!on) { this.dem = new Set(); } this.preview = null; }
  setProto(on) { this.protocole = !!on; this.saveProto(this.protocole); this.preview = null; }
  /** Ordre stable (celui de la file), pour que l'email ne dépende pas de l'ordre des clics. */
  selected() { return idsOf(this.data, this.client).filter(id => this.sel.has(id)); }

  async refreshPreview() {
    const rm = this.selected();
    if (!this.client || !rm.length) { this.preview = null; return null; }
    try { this.preview = await this.repo.preview({ client: this.client, rm, protocole: this.protocole }); this.error = null; } catch (e) { this.preview = null; this.error = e.message; }
    return this.preview;
  }
  async send() {
    const rm = this.selected();
    const r = await this.repo.send({ client: this.client, rm, protocole: this.protocole, requesters: this.demSelected() });
    await this.load();
    return r;
  }
  /** Envoi de TEST : même email, adresse choisie, la file ne bouge pas (donc pas de reload). */
  async sendTest() {
    return await this.repo.test({ client: this.client, rm: this.selected(), to: [this.testTo], protocole: this.protocole });
  }
  async dismiss() {
    const rm = this.selected();
    const r = await this.repo.dismiss({ client: this.client, rm });
    await this.load();
    return r;
  }
}
