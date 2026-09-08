// models/glossary/HelpRepository — l'aide intégrée (RM2593 : sommaire /help, pages /help/<topic>) et la lecture
// brute d'un fichier du projet pour la modale doc (RM2309). RM2889.
import { Repository } from "../../core/Repository.js";
import { Factory } from "../../core/Factory.js";
import { get, raw } from "../../core/api.js";
const enc = encodeURIComponent;

export class HelpRepository extends Repository {
  constructor() { super({ name: "help", ttl: 60000, max: 50, factory: new Factory({ type: "help-topic" }), routes: { help: "glossary.help", file: "file.file", cdc: "doc.cdc" } }); }
  async topics() { const r = await get(this.path("help")); return (r && r.topics) || []; }
  async page(topic) { const r = await get(this.path("help") + "/" + enc(topic)); return (r && r.markdown) || ""; }
  /** RM3043 : les CDC vivants (sommaire + chapitres par projet). */
  async cdcs() { const r = await get(this.path("cdc")); return (r && r.cdcs) || []; }
  /** Le texte d'un fichier du projet, tel quel (la modale le rend en markdown). */
  async file(path) { const r = await raw(this.path("file") + "?path=" + enc(path)); return r.text(); }
}
