// models/auth/auth — l'authentification du cockpit (RM2334) : état connecté/déconnecté, nom d'appareil, lignes des appareils et des
// comptes. Pur : aucun DOM, aucun stockage. RM2889.

/** Les clés de ce navigateur (le mot de passe n'y est JAMAIS). */
export const AUTH_KEYS = ["karlToken", "karlDeviceId", "karlUser", "karlAdmin"];

/** Nom lisible de l'appareil qui se connecte, depuis le user-agent (« Firefox / Linux »). */
export function deviceName(ua) {
  ua = String(ua || "");
  const os = /Android/.test(ua) ? "Android" : /iPhone|iPad/.test(ua) ? "iOS" : /Windows/.test(ua) ? "Windows" : /Mac/.test(ua) ? "macOS" : "Linux";
  const nav = /Firefox/.test(ua) ? "Firefox" : /Edg\//.test(ua) ? "Edge" : /Chrome/.test(ua) ? "Chrome" : /Safari/.test(ua) ? "Safari" : "navigateur";
  return nav + " / " + os;
}

/** Ce que l'interface montre : écran de login plein-cadre tant qu'on n'est pas connecté, cadenas, carte des comptes (superadmin seul). */
export function authState({ required, token, user, admin, loginEnabled }) {
  const logged = !!(token && user);
  return { required: !!required, logged, gateShown: !!required && !logged, sessionShown: logged,
    lockText: logged ? "🔓 " + user + (admin ? " (admin)" : "") : "🔒 auth requise", usersShown: !!(logged && admin && loginEnabled) };
}

/** Appareils enregistrés — celui-ci est marqué. */
export function deviceRows(devices) { return (devices || []).map(x => ({ id: String(x.device_id), name: x.device_name || "appareil", current: !!x.current, user: x.user || "", seen: String(x.last_seen || "").slice(0, 16) })); }
/** Comptes normaux (le superadmin vit dans le .env, il n'apparaît pas). */
export function userRows(users) { return (users || []).map(u => ({ user: u.user, disabled: !!u.disabled, devices: u.devices || 0, toggleLabel: u.disabled ? "réactiver" : "désactiver" })); }
