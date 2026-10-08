// modules/mail/mailbox — la boîte aux lettres 📬 de l'en-tête (RM3319). Pur : aucun DOM, aucun réseau.
//
// Deux signaux, qui ne se confondent pas :
//   - du NOUVEAU courrier pour karl (des mails « à traiter » que ce navigateur n'a pas encore vus
//     dans le panneau 📧) → la boîte clignote doucement ;
//   - un REJET d'un envoi de karl (MAILER-DAEMON) encore ouvert dans le fil de notifications →
//     la boîte passe en alerte rouge, quel que soit le reste. Un mail « envoyé » qui n'est jamais
//     arrivé ne doit plus passer inaperçu (incident RM1839, 2026-09-28).
// « Vu » = le panneau 📧 a été ouvert : les clés présentes à ce moment sont mémorisées par navigateur.

export const SEEN_KEY = "karlMailSeen";
const A_TRAITER = new Set(["à traiter", "proposé"]);

/** État de la boîte : {count, fresh, alert: ""|"warn"|"critical", bounces, title}. */
export function mailboxState({ emails = [], pending = 0, bounces = [] } = {}, seen = []) {
  const vus = new Set(seen || []);
  const todo = (emails || []).filter(e => A_TRAITER.has(e.state));
  const fresh = todo.filter(e => !vus.has(e.key)).length;
  const rejets = bounces || [];
  const alert = !rejets.length ? "" : rejets.some(b => b.level === "critical") ? "critical" : "warn";
  const morceaux = [];
  if (rejets.length) morceaux.push(`⚠ ${rejets.length} envoi(s) rejeté(s) — à traiter dans le fil 🔔`);
  if (fresh) morceaux.push(`${fresh} nouveau(x) mail(s)`);
  if (pending) morceaux.push(`${pending} à traiter`);
  const title = morceaux.length ? "Courrier de karl — " + morceaux.join(" · ") : "Courrier de karl — rien de neuf";
  return { count: pending || 0, fresh, alert, bounces: rejets.length, title };
}

/** Clés à retenir comme vues après ouverture du panneau (les mails à traiter affichés). */
export function seenKeys(emails = []) {
  return (emails || []).filter(e => A_TRAITER.has(e.state)).map(e => e.key);
}

/** Lecture/écriture tolérantes du « déjà vu » (stockage absent, JSON abîmé → vide). */
export function readSeen(storage) {
  try { const v = storage && storage.getItem(SEEN_KEY); const a = v ? JSON.parse(v) : []; return Array.isArray(a) ? a : []; }
  catch { return []; }
}
export function writeSeen(storage, keys) {
  try { if (storage) storage.setItem(SEEN_KEY, JSON.stringify((keys || []).slice(-500))); } catch { /* quota, mode privé */ }
}

/** Applique l'état au bouton d'en-tête (injectable : un élément factice suffit en test). */
export function paintMailbox(btn, st) {
  if (!btn || !st) return;
  const badge = btn.querySelector ? btn.querySelector(".mail-badge") : null;
  if (badge) badge.textContent = st.bounces ? "!" : (st.count ? String(st.count) : "");
  const cl = btn.classList;
  if (cl) {
    cl.toggle("has-new", !!st.fresh && !st.alert);
    cl.toggle("has-warn", st.alert === "warn");
    cl.toggle("has-critical", st.alert === "critical");
  }
  btn.title = st.title;
}
