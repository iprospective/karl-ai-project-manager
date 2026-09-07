// views/voice — la carte des préférences vocales (#voicecard). RM2889, L5. Balisage repris.
import { html } from "../../core/html.js";

export function VoicePrefs(vm) {
  const vs = vm.voices();
  return html`<h2>🔊 Voix <span style="color:var(--muted);font-weight:normal">(ce navigateur)</span></h2>
<label for="vx-lang">Langue (dictée + lecture)</label>
<select id="vx-lang" data-pref="lang"><option value="fr-FR"${vm.lang === "fr-FR" ? " selected" : ""}>français</option><option value="en-US"${vm.lang === "en-US" ? " selected" : ""}>anglais</option></select>
<label for="vx-voice">Voix de synthèse</label>
<select id="vx-voice" data-pref="name">${vs.length ? vs.map(v => html`<option value="${v.name}"${v.selected ? " selected" : ""}>${v.label}</option>`) : html`<option value="">(aucune voix ${vm.short} dans ce navigateur)</option>`}</select>
<div id="vx-server-row" style="${vm.hasServerTts ? "" : "display:none;"}margin-top:8px"><label style="display:flex;align-items:center;gap:7px;cursor:pointer"><input type="checkbox" id="vx-server" data-pref="server"${vm.serverChecked ? " checked" : ""}><span>Voix serveur haute qualité (Piper) <span id="vx-server-tag" style="color:var(--ok)">★</span></span></label><div style="color:var(--muted);font-size:11.5px;margin-top:3px">Voix neurale locale, indépendante du navigateur. Décochez pour revenir aux voix du navigateur.</div></div>
<div id="vx-stt-row" style="${vm.hasServerStt ? "" : "display:none;"}margin-top:8px"><label style="display:flex;align-items:center;gap:7px;cursor:pointer"><input type="checkbox" id="vx-stt" data-pref="stt"${vm.sttChecked ? " checked" : ""}><span>Dictée serveur haute précision (Whisper) <span style="color:var(--ok)">★</span></span></label><div style="color:var(--muted);font-size:11.5px;margin-top:3px">Transcription locale, tout navigateur (pas de verrou Chrome). Décochez pour la reconnaissance du navigateur.</div></div>
<div style="color:var(--muted);font-size:11.5px;margin-top:6px">Les voix « Google » (réseau) sonnent bien mieux que les voix locales (espeak). La liste dépend du navigateur — Chrome recommandé.</div>
<button class="mini" style="margin-top:8px" data-action="test">🔊 Tester la voix</button>`;
}

/** États du bouton 🎤 du composer et du bouton 🔊 voix de l'en-tête. */
export const MIC = { idle: { color: "", text: "🎤 dicter" }, rec: { color: "var(--danger)", text: "🎤 écoute…" }, work: { color: "var(--warn)", text: "⏳ transcription…" } };
