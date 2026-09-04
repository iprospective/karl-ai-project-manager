// models/voice — file d'annonces, choix de voix, moteurs, préférences. RM2889, L5.
// voiceQueue, pickVoice, ttsMode, sttMode, abToB64 repris tels quels (RM2329, RM2350, RM2532, RM2533).

/** Sessions à annoncer = EN ATTENTE (⚠ oui/non ou ❓ choix) pas encore annoncées ;
 *  `spoken` est purgé quand une session sort d'attente (ré-annonce possible ensuite). */
export function voiceQueue(sessions, spoken) {
  const waiting = new Set(["attention", "choice"]);
  const due = [];
  for (const s of sessions) {
    if (waiting.has(s.state)) { if (!spoken[s.rm_id]) due.push(s.rm_id); }
    else delete spoken[s.rm_id];
  }
  return due;
}

/** Meilleure voix pour `lang` : choisie si présente, sinon RÉSEAU, sinon la première. */
export function pickVoice(voices, lang, wanted) {
  const l = String(lang || "").toLowerCase().slice(0, 2);
  const cand = voices.filter(v => String(v.lang || "").toLowerCase().startsWith(l));
  if (!cand.length) return null;
  if (wanted) { const w = cand.find(v => v.name === wanted); if (w) return w; }
  return cand.find(v => v.localService === false) || cand[0];
}

export function ttsMode(caps, pref) { return (pref && caps && caps.tts) ? "server" : "browser"; }
export function sttMode(caps, pref) { return (pref && caps && caps.stt) ? "server" : "browser"; }

/** ArrayBuffer → base64, par blocs (pas de débordement de pile). */
export function abToB64(buf) {
  const bytes = new Uint8Array(buf); let bin = "";
  const chunk = 0x8000;
  for (let i = 0; i < bytes.length; i += chunk) bin += String.fromCharCode.apply(null, bytes.subarray(i, i + chunk));
  return btoa(bin);
}

/** Préférences « ce navigateur » : le stockage est injecté. */
export const prefs = {
  read(store) {
    const g = (k) => { try { return store.getItem(k); } catch (e) { return null; } };
    return { mode: g("karlVoice") === "1", lang: g("karlVoiceLang") || "fr-FR", name: g("karlVoiceName") || "",
             server: g("karlVoiceServer") !== "0", stt: g("karlSttServer") !== "0" };
  },
  write(store, k, v) { try { if (v === null) store.removeItem(k); else store.setItem(k, v); } catch (e) { /* mode privé */ } },
};

/** Ce qu'on dit d'une session qui attend. */
export function announcement(rm, title, question) {
  const label = /^\d+$/.test(String(rm)) ? "Session R M " + rm : "Session " + rm;
  return label + (title ? ", " + title : "") + ". " + (question ? "Question : " + question : "attend une réponse.");
}
