// modules/cdc/CdcRepository — les CDC vivants (sommaires par projet), le registre des fonctionnalités d'un CDC, le texte d'un chapitre. RM3044.
import { Repository } from "../../core/Repository.js";
import { Factory } from "../../core/Factory.js";
import { get, post, raw } from "../../core/api.js";
const enc = encodeURIComponent;

export class CdcRepository extends Repository {
  constructor() { super({ name: "cdc", ttl: 60000, max: 40, factory: new Factory({ type: "cdc" }), routes: { cdc: "doc.cdc", features: "doc.cdc_features", file: "file.file", think: "doc.cdc_think", feature: "doc.cdc_feature", version: "doc.cdc_version" } }); }
  async cdcs() { const r = await get(this.path("cdc")); return (r && r.cdcs) || []; }
  async features(client, project, prefix) { return await get(this.path("features") + "/" + enc(client) + "/" + enc(project) + "/" + enc(prefix)); }
  /** RM3064 : état ou suppression d'une entrée de think (ids RM<id>-Xnnn), puis refusion côté serveur. */
  async thinkEdit(body) { return await post(this.path("think"), body); }
  /** RM3064 : état d'une entrée du registre des fonctionnalités (figée en manuel), chapitre régénéré. */
  async featureEdit(body) { return await post(this.path("feature"), body); }
  /** RM3060 : créer/compléter/retirer une version, ou y rattacher une fonctionnalité. */
  async versionEdit(body) { return await post(this.path("version"), body); }
  async file(path) { const r = await raw(this.path("file") + "?path=" + enc(path)); return r.text(); }
}
