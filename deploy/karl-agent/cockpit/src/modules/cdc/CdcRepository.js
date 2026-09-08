// modules/cdc/CdcRepository — les CDC vivants (sommaires par projet), le registre des fonctionnalités d'un CDC, le texte d'un chapitre. RM3044.
import { Repository } from "../../core/Repository.js";
import { Factory } from "../../core/Factory.js";
import { get, raw } from "../../core/api.js";
const enc = encodeURIComponent;

export class CdcRepository extends Repository {
  constructor() { super({ name: "cdc", ttl: 60000, max: 40, factory: new Factory({ type: "cdc" }), routes: { cdc: "doc.cdc", features: "doc.cdc_features", file: "file.file" } }); }
  async cdcs() { const r = await get(this.path("cdc")); return (r && r.cdcs) || []; }
  async features(client, project, prefix) { return await get(this.path("features") + "/" + enc(client) + "/" + enc(project) + "/" + enc(prefix)); }
  async file(path) { const r = await raw(this.path("file") + "?path=" + enc(path)); return r.text(); }
}
