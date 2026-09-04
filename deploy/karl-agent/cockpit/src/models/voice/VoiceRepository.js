// models/voice/VoiceRepository — capacités, question, capture, envoi, STT, TTS. RM2889, L5.
import { Repository } from "../Repository.js";
import { Factory } from "../Factory.js";
import { get, post, raw } from "../../core/api.js";
const enc = encodeURIComponent;

export class VoiceRepository extends Repository {
  constructor() {
    super({ name: "voice", ttl: 60000, max: 4, factory: new Factory({ type: "voice-caps" }),
            routes: { caps: "voice.caps", question: "voice.question", capture: "terminal.capture", send: "session.send", stt: "voice.stt", tts: "voice.tts" } });
  }
  caps() { return this.store.ensure("caps", () => get(this.path("caps"))); }
  question(rm) { return get(this.path("question") + "/" + enc(rm)); }
  /** Les dernières lignes du terminal, en texte. */
  capture(rm, lines = 8) { return get(this.path("capture") + "/" + enc(rm) + "?lines=" + lines); }
  send(rm, msg) { return post(this.path("send"), { rm_id: rm, msg, enter: true }); }
  stt(audio_b64, lang) { return post(this.path("stt"), { audio_b64, lang }); }
  async tts(text, lang) { return (await raw(this.path("tts"), { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text, lang }) })).blob(); }
}
