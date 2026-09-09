// modules/clientnotify/ClientNotifyRepository — la file de compte-rendu client : ce qui attend d'être annoncé, l'aperçu de l'email, l'envoi, la mise à l'écart. RM3052.
import { Repository } from "../../core/Repository.js";
import { Factory } from "../../core/Factory.js";
import { get, post } from "../../core/api.js";

export class ClientNotifyRepository extends Repository {
  constructor() {
    super({
      name: "clientnotify", ttl: 15000, max: 10, factory: new Factory({ type: "clientnotify" }),
      routes: { pending: "clientnotify.pending", preview: "clientnotify.preview", send: "clientnotify.send", dismiss: "clientnotify.dismiss" },
    });
  }
  /** La file entière, groupée par client (compteurs du menu). Jamais mise en cache : elle bouge à chaque MEP et à chaque envoi. */
  async pending() { return await get(this.path("pending")); }
  /** Aperçu de l'email pour une sélection — n'écrit rien, n'envoie rien. */
  async preview(body) { return await post(this.path("preview"), body); }
  /** Envoi RÉEL au client, puis sent_at/sent_to sur les tickets envoyés. */
  async send(body) { return await post(this.path("send"), body); }
  /** Sortie de file SANS email : ce que le client n'a pas besoin de savoir. */
  async dismiss(body) { return await post(this.path("dismiss"), body); }
}
