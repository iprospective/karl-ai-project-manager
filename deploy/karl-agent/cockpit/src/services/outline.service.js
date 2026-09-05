// services/outline.service — l'outline : chargement sans réentrance (RM2466), sauts, retour au direct, copie. RM2889.
import { OutlineRepository } from "../models/outline/OutlineRepository.js";

export class OutlineService {
  constructor({ repo = new OutlineRepository(), clipboard = null } = {}) { this.repo = repo; this.clipboard = clipboard; this.reset(); this.loading = false; }
  reset() { this.data = { items: [], total: 0, source: "tmux" }; }
  get items() { return this.data.items; }
  get source() { return this.data.source; }
  /** Déplier la colonne ET attacher une session déclenchent tous deux un chargement : une seule requête à la fois. */
  async load(sid) {
    if (!sid || this.loading) return null;
    this.loading = true;
    try { this.data = await this.repo.load(sid); return this.data; } finally { this.loading = false; }
  }
  /** tmux (scrollback) : on fait défiler le terminal. Les sessions « transcript » (écran alterné) n'ont pas de scrollback
   *  à piloter — on ne touche pas à tmux, la vue des autres clients ne bouge pas (RM2549). Rend vrai si tmux a été piloté. */
  async scrollTo(sid, line) { if (this.source === "transcript") return false; await this.repo.scrollTo(sid, line); return true; }
  async scrollLive(sid) { if (this.source === "transcript") return false; await this.repo.scrollBottom(sid); return true; }
  async copy(text) { if (!this.clipboard) return false; try { await this.clipboard.writeText(text); return true; } catch (e) { return false; } }
}
