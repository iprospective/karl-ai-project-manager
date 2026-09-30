// models/health/HealthRepository — santé du système PM : la page et le badge (RM3369).
import { Repository } from "../../core/Repository.js";
import { Factory } from "../../core/Factory.js";
import { get } from "../../core/api.js";

export class HealthRepository extends Repository {
  constructor() {
    super({ name: "health", ttl: 30000, max: 4, factory: new Factory({ type: "health-report" }),
            routes: { status: "health.pm_health", check: "health.pm_health_check" } });
  }
  status() { return get(this.path("status")); }
  check()  { return get(this.path("check")); }
}
