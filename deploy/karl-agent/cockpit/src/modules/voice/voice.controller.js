// controllers/voice.controller — la voix : trois gestes. RM2889, L5.
// Le contexte prête : la session attachée, le cache de résolution, la notification,
// la confirmation, les boutons de l'en-tête et du composer, et les MOTEURS du
// navigateur (synthèse, reconnaissance, enregistreur, audio) — injectés, donc
// testables sans navigateur, et remplaçables sans toucher au service.
import { mount } from "../../core/dom.js";
import { VoiceService } from "./voice.service.js";
import { VoicePrefsViewModel } from "./VoicePrefsViewModel.js";
import { VoicePrefs, MIC } from "./VoicePrefs.view.js";

export function mountVoice(el, ctx = {}) {
  const svc = ctx.service || new VoiceService({ store: ctx.storage, engines: ctx.engines });
  const notify = ctx.notify || ((m, err) => (err ? console.error : console.log)(m));
  const confirm = ctx.confirm || ((m) => window.confirm(m));
  const attached = () => (ctx.attached ? ctx.attached() : null);
  const mic = (s) => ctx.mic && ctx.mic(MIC[s]);

  const paint = () => handle.update(VoicePrefs(new VoicePrefsViewModel({ prefs: svc.p, caps: svc.caps, voices: svc.voices() })));
  const paintBtn = () => ctx.voiceBtn && ctx.voiceBtn(svc.mode);
  async function boot() { paintBtn(); paint(); await svc.loadCaps(); paint(); if (ctx.onVoicesChanged) ctx.onVoicesChanged(paint); }

  function toggle() {
    const on = svc.toggleMode(); paintBtn();
    notify(on ? "🔊 Mode voix : les sessions en attente seront annoncées" : "Mode voix coupé");
    if (on) svc.speak("Mode voix activé");
  }
  const announce = (sessions) => svc.announce(sessions, ctx.resolve ? ctx.resolve() : {});
  async function readQuestion() {
    const rm = attached(); if (!rm) return;
    try { const r = await svc.readQuestion(rm); if (r.lines) notify("Pas de question en attente — lecture des dernières lignes"); }
    catch (e) { notify(e.message, true); }
  }
  async function deliver(txt) { const r = await svc.sendDictated(attached(), txt, confirm); notify(r.message, !r.ok); }

  // Repli navigateur : Web Speech API (verrouillé Chrome+HTTPS/localhost).
  function browserDictate() {
    const mk = ctx.engines && ctx.engines.recognizer;
    if (!mk) { mic("idle"); notify("Reconnaissance vocale indisponible — Chrome + HTTPS/localhost requis", true); return; }
    const rec = svc.rec = mk(svc.lang);
    mic("rec");
    const done = () => { svc.rec = null; mic("idle"); };
    rec.onerror = (e) => { done(); notify("Dictée : " + (e.error === "not-allowed" ? "micro refusé (HTTPS/localhost requis)" : e.error), true); };
    rec.onend = done;
    rec.onresult = async (e) => { await deliver((e.results[0][0].transcript || "").trim()); };
    try { rec.start(); } catch (e) { done(); notify("Dictée impossible : " + e.message, true); }
  }
  // STT serveur : enregistreur → /stt (Whisper). Tout échec retombe sur le navigateur.
  async function serverDictate() {
    const mk = ctx.engines && ctx.engines.recorder;
    if (!mk) return browserDictate();
    let r;
    try { r = await mk(); } catch (e) { notify("Micro refusé — repli reconnaissance navigateur"); return browserDictate(); }
    if (!r) return browserDictate();
    svc.mediaRec = r; mic("rec");
    r.onstop = async (blob) => {
      svc.mediaRec = null;
      if (!blob || !blob.size) { mic("idle"); notify("Dictée vide"); return; }
      mic("work");
      try { const text = await svc.transcribe(blob); mic("idle"); await deliver(text); }
      catch (e) { mic("idle"); notify("STT serveur indisponible — repli reconnaissance navigateur"); browserDictate(); }
    };
    try { r.start(); } catch (e) { svc.mediaRec = null; mic("idle"); browserDictate(); }
  }
  function dictate() {
    if (!attached()) return;
    if (svc.mediaRec) { try { svc.mediaRec.stop(); } catch (e) {} return; }
    if (svc.rec) { try { svc.rec.stop(); } catch (e) {} return; }
    if (svc.busy) { notify("Transcription en cours…"); return; }
    return svc.stt() === "server" ? serverDictate() : browserDictate();
  }

  const prefGestures = {
    lang: (v) => { svc.setLang(v); paint(); notify("Langue voix : " + (v.startsWith("fr") ? "français" : "anglais")); },
    name: (v) => svc.setName(v),
    server: (v) => { svc.setServer(v); notify(v ? "Voix serveur (Piper) activée" : "Voix du navigateur"); svc.speak("Test de la voix."); },
    stt: (v) => { svc.setStt(v); notify(v ? "Dictée serveur (Whisper) activée" : "Dictée du navigateur"); },
  };
  const handle = mount(el, "", { events: [
    ["change", "[data-pref]", (ev, n) => prefGestures[n.dataset.pref](n.type === "checkbox" ? !!n.checked : n.value)],
    ["click", "[data-action]", (ev, n) => n.dataset.action === "test" && svc.speak(new VoicePrefsViewModel({ prefs: svc.p }).testText)],
  ] });
  return Object.assign(handle, { boot, toggle, announce, readQuestion, dictate, paint, svc });
}
