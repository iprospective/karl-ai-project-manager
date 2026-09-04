// services/voice.service — parler, annoncer, dicter. RM2889, L5.
//
// Les moteurs du navigateur (speechSynthesis, SpeechRecognition, MediaRecorder,
// <audio>) sont INJECTÉS : le service se teste sans navigateur, et le repli
// d'un moteur vers l'autre (serveur → navigateur) est une règle du service,
// pas un accident du code.
import { VoiceRepository } from "../models/voice/VoiceRepository.js";
import { voiceQueue, pickVoice, ttsMode, sttMode, abToB64, prefs, announcement } from "../models/voice/voice.js";

export class VoiceService {
  constructor({ repo = new VoiceRepository(), store, engines = {} } = {}) {
    this.repo = repo; this.store = store || { getItem() { return null; }, setItem() {}, removeItem() {} };
    this.engines = engines;                 // { synth, voices(), audio(blob), recognizer(lang), recorder() }
    this.p = prefs.read(this.store);
    this.caps = null; this.spoken = {}; this.busy = false; this.rec = null; this.mediaRec = null;
  }
  get mode() { return this.p.mode; }
  get lang() { return this.p.lang; }
  set(k, v) { this.p[k] = v; }
  async loadCaps() { try { this.caps = await this.repo.caps(); } catch (e) { this.caps = null; } return this.caps; }
  voices() { return this.engines.voices ? this.engines.voices() : []; }
  bestVoice() { return pickVoice(this.voices(), this.p.lang, this.p.name); }
  tts() { return ttsMode(this.caps, this.p.server); }
  stt() { return sttMode(this.caps, this.p.stt); }

  toggleMode() { this.p.mode = !this.p.mode; prefs.write(this.store, "karlVoice", this.p.mode ? "1" : "0"); if (!this.p.mode && this.engines.cancel) this.engines.cancel(); return this.p.mode; }
  setLang(lang) { this.p.lang = lang; this.p.name = ""; prefs.write(this.store, "karlVoiceLang", lang); prefs.write(this.store, "karlVoiceName", null); }
  setName(name) { this.p.name = name; prefs.write(this.store, "karlVoiceName", name); }
  setServer(on) { this.p.server = !!on; prefs.write(this.store, "karlVoiceServer", on ? "1" : "0"); }
  setStt(on) { this.p.stt = !!on; prefs.write(this.store, "karlSttServer", on ? "1" : "0"); }

  browserSpeak(text) { try { if (this.engines.speak) this.engines.speak(text, this.p.lang, this.bestVoice()); } catch (e) { /* synthèse indisponible */ } }
  async speak(text) {
    if (this.tts() !== "server") return this.browserSpeak(text);
    try { const blob = await this.repo.tts(text, this.p.lang.slice(0, 2)); if (this.engines.audio) await this.engines.audio(blob); }
    catch (e) { this.browserSpeak(text); }             // repli navigateur sur toute erreur serveur
  }
  /** Annonce les sessions nouvellement en attente (fire-and-forget, appelé à chaque refresh). */
  async announce(sessions, resolve = {}) {
    if (!this.p.mode) return [];
    const said = [];
    for (const rm of voiceQueue(sessions, this.spoken)) {
      this.spoken[rm] = "…";                            // réserve l'annonce (polls rapprochés)
      let q = null;
      try { q = (await this.repo.question(rm)).question; } catch (e) { /* partie */ }
      this.spoken[rm] = q || "?";
      const r = resolve[rm];
      const text = announcement(rm, r && r.found && r.title ? r.title : "", q);
      said.push(text); this.speak(text);
    }
    return said;
  }
  /** Lit la question de la session, sinon ses dernières lignes. Rend {question|lines}. */
  async readQuestion(rm) {
    const r = await this.repo.question(rm);
    if (r.question) { this.speak("Question : " + r.question); return { question: r.question }; }
    const lines = String(await this.repo.capture(rm, 8)).split("\n").map(l => l.trim()).filter(Boolean).slice(-4);
    this.speak(lines.length ? lines.join(". ") : "Le terminal est vide.");
    return { lines };
  }
  /** Envoi d'une dictée : confirmation (injectée) puis /send. Rend {ok, message}. */
  async sendDictated(rm, txt, confirm) {
    txt = (txt || "").trim();
    if (!txt) return { ok: false, message: "Dictée : rien compris" };
    const dest = /^\d+$/.test(String(rm)) ? "RM" + rm : rm;
    if (!confirm("Envoyer à " + dest + " :\n\n« " + txt + " »")) return { ok: false, message: "Dictée abandonnée" };
    try { await this.repo.send(rm, txt); return { ok: true, message: "🎤 Envoyé : " + (txt.length > 60 ? txt.slice(0, 60) + "…" : txt) }; }
    catch (e) { return { ok: false, message: e.message }; }
  }
  /** Transcription serveur d'un blob audio. */
  async transcribe(blob) {
    this.busy = true;
    try { return (await this.repo.stt(abToB64(await blob.arrayBuffer()), this.p.lang.slice(0, 2))).text; }
    finally { this.busy = false; }
  }
}
