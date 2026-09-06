// viewmodels/voice — la carte « 🔊 Voix », décidée. RM2889, L5.
import { EntityViewModel } from "../../core/EntityViewModel.js";
import { pickVoice } from "./voice.js";

export class VoicePrefsViewModel extends EntityViewModel {
  /** e = { prefs, caps, voices } */
  constructor(e, ctx) { super(e || {}, ctx); }
  get p() { return this.e.prefs || {}; }
  get lang() { return this.p.lang || "fr-FR"; }
  get hasServerTts() { return !!(this.e.caps && this.e.caps.tts); }
  get hasServerStt() { return !!(this.e.caps && this.e.caps.stt); }
  get serverChecked() { return this.hasServerTts && !!this.p.server; }
  get sttChecked() { return this.hasServerStt && !!this.p.stt; }
  get short() { return this.lang.toLowerCase().slice(0, 2); }
  voices() {
    const all = this.e.voices || [];
    const cand = all.filter(v => String(v.lang || "").toLowerCase().startsWith(this.short));
    const best = pickVoice(all, this.lang, this.p.name);
    return cand.map(v => ({ name: v.name, label: v.name + (v.localService === false ? " · réseau ★" : " · locale"), selected: !!best && v.name === best.name }));
  }
  get testText() { return this.lang.startsWith("fr") ? "Ceci est un test de la voix du cockpit." : "This is a cockpit voice test."; }
}
