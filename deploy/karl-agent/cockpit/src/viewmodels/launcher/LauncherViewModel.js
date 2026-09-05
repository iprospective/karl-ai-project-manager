// viewmodels/launcher/LauncherViewModel — la ligne de résolution et les sélecteurs du lanceur, décidés. RM2889.
import { EntityViewModel } from "../EntityViewModel.js";
import { resolvedLine, modelOptions, clientCtxList, clientCtxProject, typeOptions, prioOptions } from "../../models/launcher/launcher.js";

/** e = { resolved, cfg, engine, prevModel, projects, clientContext } */
export class LauncherViewModel extends EntityViewModel {
  constructor(e, ctx) { super(e || {}, ctx); }
  get line() { return resolvedLine(this.e.resolved); }
  get models() { return modelOptions((this.e.cfg || {}).models, this.e.engine, this.e.resolved, this.e.prevModel); }
  get clients() { return clientCtxList(this.e.projects); }
  get contextProject() { return clientCtxProject(this.e.projects, this.e.clientContext); }
  get types() { return typeOptions(this.e.cfg); }
  get priorities() { return prioOptions(this.e.cfg); }
}
