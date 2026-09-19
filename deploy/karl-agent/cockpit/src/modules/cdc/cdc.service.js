// modules/cdc/cdc.service — l'état des pages CDC : quel CDC est en contexte, son registre, ses chapitres. RM3044.
//
// Le CDC en contexte : celui mémorisé (karlCdc) s'il existe encore, sinon le premier CDC d'un projet de la session attachée,
// sinon le premier de la liste. Un projet peut porter plusieurs CDC (pm-ai-agents : « pm » et « karl »).
import { CdcRepository } from "./CdcRepository.js";

/** Pur : le CDC à montrer parmi `cdcs`, selon la préférence mémorisée et les projets de la session (["client/project"]). */
export function pickCdc(cdcs, pref, sessionProjects) {
  if (!cdcs || !cdcs.length) return null;
  if (pref) { const hit = cdcs.find(c => c.key === pref); if (hit) return hit; }
  for (const cp of (sessionProjects || [])) { const hit = cdcs.find(c => c.client + "/" + c.project === cp); if (hit) return hit; }
  return cdcs[0];
}

export class CdcService {
  constructor({ repo = new CdcRepository(), storage = null } = {}) { this.repo = repo; this.storage = storage; this.cdcs = null; this.current = null; this._feat = {}; this._chap = {}; this.error = null; }
  pref() { try { return this.storage ? (this.storage.getItem("karlCdc") || "") : ""; } catch (e) { return ""; } }
  remember(key) { try { if (this.storage) this.storage.setItem("karlCdc", key || ""); } catch (e) { /* stockage indisponible */ } }
  /** (Re)charge la liste et choisit le CDC en contexte ; `sessionProjects` = ["client/project"] de la session attachée. */
  async load(sessionProjects, force) {
    if (!this.cdcs || force) { try { this.cdcs = await this.repo.cdcs(); this.error = null; } catch (e) { this.cdcs = []; this.error = e.message; } }
    if (!this.current || !this.cdcs.some(c => c.key === this.current.key)) this.current = pickCdc(this.cdcs, this.pref(), sessionProjects);
    return this.current;
  }
  select(key) { const hit = (this.cdcs || []).find(c => c.key === key); if (hit) { this.current = hit; this.remember(key); } return this.current; }
  async features(force) {
    const c = this.current; if (!c) return null;
    if (!this._feat[c.key] || force) this._feat[c.key] = c.registry ? await this.repo.features(c.client, c.project, c.prefix) : { entrees: [], domaines: [], jalons: [], missing: true };
    return this._feat[c.key];
  }
  /** RM3064 : édition d'une entrée de think ; invalide les chapitres en cache (les registres sont régénérés). */
  /** RM3258 : `to` porte le ticket destinataire d'un déplacement ; les champs vides ne partent pas. */
  async thinkEdit({ rm, id, action, state, comment, to }) {
    const body = { rm, id, action };
    if (state) body.state = state;
    if (comment) body.comment = comment;
    if (to) body.to = to;
    const r = await this.repo.thinkEdit(body); this._chap = {}; return r;
  }
  async featureEdit({ id, etat }) { const c = this.current; if (!c) return null; const r = await this.repo.featureEdit({ client: c.client, project: c.project, prefix: c.prefix, id, etat }); delete this._feat[c.key]; this._chap = {}; return r; }
  /** RM3060 : versions de la feuille de route. Le registre ET les chapitres changent : on vide les deux. */
  async versionEdit(body) {
    const c = this.current; if (!c) return null;
    const r = await this.repo.versionEdit(Object.assign({ client: c.client, project: c.project }, body));
    delete this._feat[c.key]; this._chap = {};
    return r;
  }
  async chapter(path, force) { if (!this._chap[path] || force) this._chap[path] = await this.repo.file(path); return this._chap[path]; }
}
