// services/layout.service — les préférences de disposition (ce navigateur) : démarrage de la colonne de droite, repli gauche, largeur. RM2889.
import { defaultTabOf, clampWidth, clampCenterH } from "./panels.js";

export class LayoutService {
  constructor({ storage = null } = {}) { this.storage = storage; }
  _get(k) { try { return this.storage ? this.storage.getItem(k) : null; } catch (e) { return null; } }
  _set(k, v) { try { if (this.storage) this.storage.setItem(k, v); } catch (e) { /* mode privé */ } }
  _del(k) { try { if (this.storage) this.storage.removeItem(k); } catch (e) { /* mode privé */ } }
  startOpen() { return this._get("karlRightStartOpen") === "1"; }
  defaultTab() { return defaultTabOf(this._get("karlRightDefaultTab")); }
  setStartOpen(on) { this._set("karlRightStartOpen", on ? "1" : "0"); }
  setDefaultTab(tab) { this._set("karlRightDefaultTab", tab); }
  leftCollapsed() { return this._get("karlLeftCollapsed") === "1"; }
  saveLeft(collapsed) { this._set("karlLeftCollapsed", collapsed ? "1" : "0"); }
  saveRight(state) { this._set("karlRight", JSON.stringify(state)); }
  /** La largeur réglée, bornée ; null si aucune (le CSS garde son défaut, 460 px sur l'onglet conversation — RM2952). */
  width() { const v = parseInt(this._get("karlRightWidth") || "", 10); return v ? clampWidth(v) : null; }
  saveWidth(px) { this._set("karlRightWidth", String(clampWidth(px))); }
  resetWidth() { this._del("karlRightWidth"); }
  /** RM3003 : forçage de la disposition (mobile|desktop) pour ce navigateur ; null = automatique. */
  layoutPref() { const v = this._get("karlLayout"); return v === "mobile" || v === "desktop" ? v : null; }
  setLayoutPref(v) { if (v === "mobile" || v === "desktop") this._set("karlLayout", v); else this._del("karlLayout"); }
  /** RM3051 — split de la zone centrale : afficher un ticket/document SOUS la session
   *  attachée, plutôt qu'à sa place. **Désactivé par défaut** : la valeur absente vaut
   *  « non » (personne ne l'a demandé, ça ne s'active qu'exprès). */
  centerSplit() { return this._get("karlCenterSplit") === "1"; }
  setCenterSplit(on) { this._set("karlCenterSplit", on ? "1" : "0"); }
  /** Hauteur du volet bas quand le split est actif ; null = laisser le défaut CSS. */
  centerH() { const v = parseInt(this._get("karlCenterH") || "", 10); return v ? clampCenterH(v) : null; }
  saveCenterH(px) { this._set("karlCenterH", String(clampCenterH(px))); }
  resetCenterH() { this._del("karlCenterH"); }
  /** RM2283 : panneau gauche actif, persisté. */
  panel() { return this._get("karlPanel"); }
  savePanel(name) { this._set("karlPanel", name); }
}
