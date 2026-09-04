// models/settings/SettingsRepository — la whitelist serveur (RM2213). RM2889, L5.
import { Repository } from "../Repository.js";
import { Factory } from "../Factory.js";
import { get, post } from "../../core/api.js";

export class SettingsRepository extends Repository {
  constructor() {
    super({ name: "settings", ttl: 5000, max: 2, routes: { list: "pm.settings" },
            factory: new Factory({ type: "setting", required: ["key"], defaults: { group: "autres", type: "number", options: [] } }) });
  }
  all() { return this.store.ensure("all", async () => this.factory.many((await get(this.path("list"))).settings || [])); }
  async set(key, value) { const r = await post(this.path("list"), { key, value, confirm: true }); this.store.invalidate(); return r; }
}

/** Le thème (RM2386) : défaut serveur, surcharge « ce navigateur ». Pure : le stockage est injecté. */
export const theme = {
  read(store) { let loc = "", srv = "auto"; try { loc = store.getItem("karlThemeLocal") || ""; srv = store.getItem("karlThemeServer") || "auto"; } catch (e) {} return { local: loc, server: srv }; },
  setServer(store, v) { try { store.setItem("karlThemeServer", v || "auto"); } catch (e) {} },
  setLocal(store, v) { try { if (v === "server") store.removeItem("karlThemeLocal"); else store.setItem("karlThemeLocal", v); } catch (e) {} },
  hint({ local, server }, effective) {
    return local ? "Surcharge locale active (effectif : " + effective + "). Conf serveur : " + server + "."
                 : "Suit la conf serveur « " + server + " » (effectif : " + effective + ").";
  },
};
