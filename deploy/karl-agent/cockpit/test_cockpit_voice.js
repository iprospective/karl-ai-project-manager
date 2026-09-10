#!/usr/bin/env node
// Tests du domaine voix migré (RM2889, L5) — porte RM2329/RM2350/RM2532/RM2533 ; moteurs injectés.
"use strict";
const path = require("path"); const assert = require("assert"); const DIR = __dirname;
function fakeElement() { const L = []; let inner = ""; return { get innerHTML() { return inner; }, set innerHTML(v) { inner = v; }, contains: () => true,
  addEventListener(t, f) { L.push([t, f]); }, removeEventListener(t, f) { const i = L.findIndex(([a, b]) => a === t && b === f); if (i >= 0) L.splice(i, 1); }, get listenerCount() { return L.length; },
  async fire(type, sel, n) { for (const [t, f] of [...L]) if (t === type) await f({ target: { closest: s => s === sel ? n : null } }); } }; }
(async () => {
  const M = await import(path.join(DIR, "src/modules/voice/voice.js"));
  const KS = await import(path.join(DIR, "src/core/store.js")); const mkStore = (name, obj) => { const s = new KS.Store(name, { ttl: 1e9, max: 1000 }); Object.entries(obj || {}).forEach(([k, v]) => s.set(k, v)); return s; };   // RM3005
  const { VoiceService } = await import(path.join(DIR, "src/modules/voice/voice.service.js"));
  const { VoicePrefsViewModel } = await import(path.join(DIR, "src/modules/voice/VoicePrefsViewModel.js"));
  const { VoicePrefs } = await import(path.join(DIR, "src/modules/voice/VoicePrefs.view.js"));
  const { mountVoice } = await import(path.join(DIR, "src/modules/voice/voice.controller.js"));
  let spoken = {}; const vs = [{ rm_id: "1", state: "attention" }, { rm_id: "2", state: "working" }, { rm_id: "3", state: "choice" }];
  assert.deepStrictEqual(M.voiceQueue(vs, spoken), ["1", "3"]); spoken = { "1": "Q", "3": "C" }; assert.deepStrictEqual(M.voiceQueue(vs, spoken), []);
  assert.deepStrictEqual(M.voiceQueue([{ rm_id: "1", state: "working" }], spoken), []); assert(!("1" in spoken), "sortie d'attente → purge");
  assert.deepStrictEqual(M.voiceQueue([{ rm_id: "1", state: "attention" }], spoken), ["1"]);
  const voices = [{ name: "eSpeak French", lang: "fr-FR", localService: true }, { name: "Google français", lang: "fr-FR", localService: false }, { name: "Google US English", lang: "en-US", localService: false }];
  assert.strictEqual(M.pickVoice(voices, "fr-FR", "").name, "Google français"); assert.strictEqual(M.pickVoice(voices, "fr-FR", "eSpeak French").name, "eSpeak French");
  assert.strictEqual(M.pickVoice(voices, "fr-FR", "disparue").name, "Google français"); assert.strictEqual(M.pickVoice(voices, "en-US", "").name, "Google US English");
  assert.strictEqual(M.pickVoice([{ name: "L", lang: "fr-FR", localService: true }], "fr-FR", "").name, "L"); assert.strictEqual(M.pickVoice(voices, "de-DE", ""), null);
  assert.strictEqual(M.ttsMode({ tts: true }, true), "server"); assert.strictEqual(M.ttsMode({ tts: true }, false), "browser"); assert.strictEqual(M.ttsMode({ tts: false }, true), "browser"); assert.strictEqual(M.ttsMode(null, true), "browser");
  assert.strictEqual(M.sttMode({ stt: true }, true), "server"); assert.strictEqual(M.sttMode({ stt: true }, false), "browser"); assert.strictEqual(M.sttMode(null, true), "browser");
  assert.strictEqual(M.announcement("42", "Titre", "Quoi ?"), "Session R M 42, Titre. Question : Quoi ?"); assert.strictEqual(M.announcement("calymix", "", null), "Session calymix. attend une réponse.");
  assert.strictEqual(M.abToB64(new Uint8Array([104, 105]).buffer), "aGk=");
  console.log("✓ modèle voix (RM2329/2350/2532/2533) : file, choix de voix, moteurs, annonce, base64");

  const mem = {}; const store = { getItem: k => (k in mem ? mem[k] : null), setItem: (k, v) => { mem[k] = v; }, removeItem: k => { delete mem[k]; } };
  const said = []; const calls = [];
  const repo = { async caps() { return { tts: true, stt: true }; }, async question(rm) { calls.push(["q", rm]); return rm === "1" ? { question: "Oui ou non ?" } : {}; },
    async capture(rm) { return "a\n\n b \nc\nd\ne"; }, async send(rm, msg) { calls.push(["send", rm, msg]); return { ok: true }; },
    async stt(b64, lang) { calls.push(["stt", lang]); return { text: "transcrit" }; }, async tts(text) { calls.push(["tts", text]); if (text === "KO") throw new Error("tts 500"); return { size: 3 }; } };
  const engines = { voices: () => voices, cancel: () => calls.push("cancel"), speak: (t, l, v) => said.push(["browser", t, l, v && v.name]), audio: async (b) => said.push(["audio", b.size]) };
  const svc = new VoiceService({ repo, store, engines });
  assert.deepStrictEqual(svc.p, { mode: false, lang: "fr-FR", name: "", server: true, stt: true }, "défauts sans stockage");
  await svc.speak("x"); assert.deepStrictEqual(said.pop(), ["browser", "x", "fr-FR", "Google français"], "sans caps : navigateur, voix réseau");
  await svc.loadCaps(); await svc.speak("y"); assert.deepStrictEqual(said.pop(), ["audio", 3], "caps + préférence : TTS serveur");
  await svc.speak("KO"); assert.deepStrictEqual(said.pop()[0], "browser", "erreur serveur → repli navigateur");
  svc.setServer(false); await svc.speak("z"); assert.strictEqual(said.pop()[0], "browser"); assert.strictEqual(mem.karlVoiceServer, "0");
  assert.deepStrictEqual(await svc.announce(vs, {}), [], "mode voix coupé : rien");
  assert.strictEqual(svc.toggleMode(), true); assert.strictEqual(mem.karlVoice, "1");
  const ann = await svc.announce(vs, { "1": { found: true, title: "Facturation" } });
  assert.deepStrictEqual(ann, ["Session R M 1, Facturation. Question : Oui ou non ?", "Session R M 3. attend une réponse."]);
  assert.deepStrictEqual(await svc.announce(vs, {}), [], "déjà annoncées → rien");
  assert.deepStrictEqual(await svc.readQuestion("1"), { question: "Oui ou non ?" }); assert.deepStrictEqual(await svc.readQuestion("2"), { lines: ["b", "c", "d", "e"] }, "sans question : 4 dernières lignes");
  assert.deepStrictEqual(await svc.sendDictated("42", "  ", () => true), { ok: false, message: "Dictée : rien compris" });
  assert.deepStrictEqual(await svc.sendDictated("42", "bonjour", (m) => { assert(/RM42/.test(m) && /bonjour/.test(m)); return false; }), { ok: false, message: "Dictée abandonnée" });
  assert.deepStrictEqual(await svc.sendDictated("42", "bonjour", () => true), { ok: true, message: "🎤 Envoyé : bonjour" }); assert.deepStrictEqual(calls.pop(), ["send", "42", "bonjour"]);
  assert.strictEqual(await svc.transcribe({ size: 2, arrayBuffer: async () => new Uint8Array([1, 2]).buffer }), "transcrit"); assert.deepStrictEqual(calls.pop(), ["stt", "fr"]);
  svc.setLang("en-US"); assert.strictEqual(svc.p.name, ""); assert.strictEqual(mem.karlVoiceLang, "en-US"); assert(!("karlVoiceName" in mem));
  svc.toggleMode(); assert.strictEqual(calls.pop(), "cancel", "couper la voix annule la synthèse");
  console.log("✓ service voix : moteurs injectés, repli serveur→navigateur, annonces sans doublon, dictée confirmée");

  const vm = new VoicePrefsViewModel({ prefs: { lang: "fr-FR", name: "", server: true, stt: false }, caps: { tts: true, stt: true }, voices });
  assert.deepStrictEqual(vm.voices().map(v => [v.label, v.selected]), [["eSpeak French · locale", false], ["Google français · réseau ★", true]]);
  assert(vm.hasServerTts && vm.serverChecked && vm.hasServerStt && !vm.sttChecked);
  const h1 = String(VoicePrefs(vm));
  assert(/<option value="fr-FR" selected>/.test(h1) && /<option value="Google français" selected>/.test(h1) && /id="vx-server" data-pref="server" checked/.test(h1) && /id="vx-stt" data-pref="stt">/.test(h1));
  assert(!/onchange=|onclick=/.test(h1) && /data-action="test"/.test(h1));
  const h2 = String(VoicePrefs(new VoicePrefsViewModel({ prefs: { lang: "de-DE" }, caps: null, voices })));
  assert(/aucune voix de dans ce navigateur/.test(h2) && /id="vx-server-row" style="display:none;/.test(h2), "sans voix de la langue, sans serveur : rangées cachées");
  console.log("✓ vue voix : langue, voix réseau présélectionnée, rangées serveur conditionnelles, zéro handler inline");

  const el = fakeElement(); const ev = []; let recog = null;
  const svc2 = new VoiceService({ repo, store, engines: { ...engines, recognizer: (lang) => (recog = { lang, started: false, start() { this.started = true; }, stop() { this.onend && this.onend(); } }), recorder: null } });
  const c = mountVoice(el, { service: svc2, notify: (m, e) => ev.push([m, !!e]), confirm: () => true, attached: () => "42", resolve: () => mkStore("r"),
    voiceBtn: (on) => ev.push(["btn", on]), mic: (s) => ev.push(["mic", s.text]), engines: svc2.engines });
  await c.boot(); assert(/id="vx-lang"/.test(el.innerHTML)); assert.deepStrictEqual(ev[0], ["btn", false]);
  c.toggle(); assert(ev.some(x => x[0] === "btn" && x[1] === true) && ev.some(x => /Mode voix/.test(x[0])));
  await el.fire("change", "[data-pref]", { dataset: { pref: "lang" }, value: "en-US" }); assert.strictEqual(svc2.lang, "en-US"); assert(/<option value="en-US" selected>/.test(el.innerHTML));
  await el.fire("change", "[data-pref]", { dataset: { pref: "stt" }, type: "checkbox", checked: false }); assert.strictEqual(svc2.p.stt, false);
  svc2.caps = { tts: false, stt: false }; c.dictate(); assert(recog && recog.started && recog.lang === "en-US", "sans STT serveur : reconnaissance navigateur, dans la langue choisie"); assert.deepStrictEqual(ev.pop(), ["mic", "🎤 écoute…"]);
  await recog.onresult({ results: [[{ transcript: " salut " }]] }); assert.deepStrictEqual(calls.pop(), ["send", "42", "salut"]);
  c.dictate(); assert.deepStrictEqual(ev.pop(), ["mic", "🎤 dicter"], "re-clic = stop → repos");
  await c.readQuestion(); assert(ev.some(x => /dernières lignes/.test(x[0])) || calls.some(x => x[0] === "q"));
  c.unmount(); assert.strictEqual(el.listenerCount, 0);
  console.log("✓ contrôleur voix : boot, bascule, préférences, dictée navigateur, stop, démontage");
  console.log("\nTous les tests du domaine voix passent.");
})().catch(e => { console.error("✗", e.message); process.exit(1); });
