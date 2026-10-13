// modules/billing/BillingRepository — la lecture du temps d'une journée (GET /api/timesheet/day) et d'un mois. RM3229.
//
// L'ÉCRITURE ne passe pas par ici : ajuster et valider sont des commandes du catalogue PM (`/pm/run`),
// comme tout ce qui mute — même allowlist, même journal d'exécution, même parité avec la CLI (RM3208).
import { Repository } from "../../core/Repository.js";
import { Factory } from "../../core/Factory.js";
import { get } from "../../core/api.js";

export class BillingRepository extends Repository {
  constructor() {
    super({ name: "timesheet", ttl: 60000, max: 40,
            factory: new Factory({ type: "timesheet_day" }),
            routes: { day: "timesheet.day", month: "timesheet.month",
                      projects: "project.projects" } });
  }

  /** Une journée. `refresh` rejoue les traces au lieu de lire le cache du jour (~20 s). */
  day(jour, refresh) {
    const p = new URLSearchParams({ day: String(jour) });
    if (refresh) p.set("refresh", "1");
    return get(this.path("day") + "?" + p.toString());
  }

  /** Le mois entier, une entrée par journée — vues semaine et mois.
   *  `resume` ne rend que les totaux : 9 Ko au lieu de 3 Mo, la grille n'a pas besoin
   *  des commits ni des traces de trente journées. */
  month(mois, resume = true) {
    const p = new URLSearchParams({ month: String(mois) });
    if (resume) p.set("resume", "1");
    return get(this.path("month") + "?" + p.toString());
  }

  /** Les clients et projets PM — ce que les menus du formulaire proposent. */
  projects() { return get(this.path("projects")); }
}
