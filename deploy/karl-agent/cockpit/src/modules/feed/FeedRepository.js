// modules/feed/FeedRepository — le fil de notifications de l'instance. RM2792.
// Le fil vit côté serveur (fichier d'état, partagé par tous les outils PM) : le cockpit ne fait que
// le lire et marquer ce qu'il a traité. Il est lu AU NOM de l'utilisateur authentifié — les entrées
// privées d'autrui n'arrivent jamais jusqu'ici.
import { Repository } from "../../core/Repository.js";
import { Factory } from "../../core/Factory.js";
import { get, post } from "../../core/api.js";

export class FeedRepository extends Repository {
  constructor() { super({ name: "feed", ttl: 15000, max: 5, factory: new Factory({ type: "notification" }),
    routes: { feed: "dashboard.notifications", mark: "dashboard.notifications_mark" } }); }
  async feed({ etat = "ouvert", user = "", limit = 100 } = {}) {
    return await get(this.path("feed") + `?etat=${encodeURIComponent(etat)}&limit=${limit}`
                     + (user ? `&user=${encodeURIComponent(user)}` : ""));
  }
  /** `etat` vaut « lu » ou « traite » ; `all` marque tout ce qui est ouvert DANS LA VUE du lecteur. */
  async mark(body) { return await post(this.path("mark"), body); }
}
