// core/prefs — le stockage de CE navigateur, cloisonné par utilisateur (RM3070, lot L2).
//
// Les préférences du cockpit (tri, plis, gel, onglet courant…) vivaient dans `localStorage` sous
// des clés nues. Un poste partagé les mélangeait donc : deux développeurs sur le même navigateur
// se marchaient dessus, et une déconnexion laissait les réglages du précédent en place.
//
// Ici, chaque clé est préfixée par l'utilisateur connecté (`u:<user>:<clé>`). Deux choix méritent
// d'être dits :
//
//   - **Sans utilisateur connu, rien ne change** (préfixe vide). En mono, où personne ne se
//     connecte, les clés restent celles d'hier : le cloisonnement ne coûte rien à qui n'en a pas
//     besoin, et aucune préférence n'est perdue à la mise à jour.
//   - **Les clés d'IDENTITÉ ne sont jamais préfixées** (`karlToken`, `karlUser`…) : elles
//     désignent la session de ce navigateur, pas les goûts d'un utilisateur — les préfixer
//     rendrait le jeton introuvable au chargement, avant même de savoir qui est là.
//
// Le premier utilisateur connecté ADOPTE les préférences nues qui traînent (celles d'avant ce
// cloisonnement) au lieu de repartir de zéro ; l'original est laissé en place pour que le
// navigateur reste utilisable par une version antérieure du cockpit.

export const IDENTITE = ["karlToken", "karlDeviceId", "karlUser", "karlAdmin"];

/**
 * @param {Storage|null} base  le stockage réel (localStorage), ou null s'il n'y en a pas
 * @param {function} qui       rend l'utilisateur connecté ("" si aucun)
 */
export function createPrefs(base, qui = () => "") {
  if (!base) return null;
  const nu = (k) => IDENTITE.includes(k);
  const user = () => { try { return (qui() || "").trim(); } catch { return ""; } };
  const clef = (k) => { const u = user(); return (!u || nu(k)) ? k : `u:${u}:${k}`; };
  return {
    getItem(k) {
      const c = clef(k);
      let v = null;
      try { v = base.getItem(c); } catch { return null; }
      if (v === null && c !== k) {
        // préférence d'avant le cloisonnement : on l'adopte, sans effacer l'original
        try { v = base.getItem(k); if (v !== null) base.setItem(c, v); } catch { /* quota, mode privé */ }
      }
      return v;
    },
    setItem(k, v) { try { base.setItem(clef(k), v); } catch { /* quota, mode privé */ } },
    removeItem(k) { try { base.removeItem(clef(k)); } catch { /* idem */ } },
    /** Efface les préférences de l'utilisateur donné (défaut : celui qui est connecté).
     *  L'identité n'est pas touchée : c'est la déconnexion qui s'en charge. */
    purge(u = null) {
      const cible = (u === null ? user() : u).trim();
      if (!cible) return 0;
      const pre = `u:${cible}:`;
      let cles = [];
      try {
        for (let i = 0; i < base.length; i++) {
          const k = base.key(i);
          if (k && k.startsWith(pre)) cles.push(k);
        }
      } catch { return 0; }
      for (const k of cles) { try { base.removeItem(k); } catch { /* idem */ } }
      return cles.length;
    },
    /** Pour les tests et le panneau mémoire : la clé réellement écrite. */
    _clef: clef,
  };
}
