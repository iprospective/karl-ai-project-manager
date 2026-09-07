// services/settings.service — RM2889, L5.
import { SettingsRepository } from "./SettingsRepository.js";
export class SettingsService {
  constructor(repo = new SettingsRepository()) { this.repo = repo; this.settings = []; }
  async load() { this.settings = await this.repo.all(); return this.settings; }
  async save(entry, value) {
    try { await this.repo.set(entry.key, value); return { ok: true, message: "✓ " + entry.label + " → " + value, themeChanged: entry.key === "conf:ui.theme" }; }
    catch (e) { return { ok: false, message: e.message }; }
  }
}
