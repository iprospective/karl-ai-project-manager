// Script de début de document injecté par l'app Android (RM2331), sur la SEULE
// origine du serveur karl. Sert les clés d'auth du cockpit (karlToken & co)
// depuis la mémoire : elles ne sont jamais écrites dans le localStorage réel de
// la WebView (toute copie résiduelle est purgée). Connexions / déconnexions
// faites dans le cockpit remontent à l'app par le canal KarlApp (même origine).
// Le marqueur de l'objet mem ci-dessous est remplacé par l'app (JSON des clés). Méthodes natives rappelées par
// .call(this, …) : un natif détaché lève « Illegal invocation ».
// Testé par test_karl_boot.js (node, contre le vrai AuthService du cockpit).
(function () {
  if (window.__karlApp) return; window.__karlApp = true;
  var mem = __MEM__, own = Object.prototype.hasOwnProperty;
  var known = mem.karlToken;   // jeton déjà détenu par l'app : le re-signaler serait un faux « login »
  var P = Storage.prototype, get = P.getItem, set = P.setItem, del = P.removeItem;
  var local = function (s) { try { return s === window.localStorage; } catch (e) { return false; } };
  var post = function (o) { try { KarlApp.postMessage(JSON.stringify(o)); } catch (e) { /* hors app */ } };
  try { for (var k in mem) del.call(window.localStorage, k); } catch (e) { /* stockage bloqué */ }
  P.getItem = function (k) {
    if (local(this) && own.call(mem, k)) return mem[k] === null ? null : String(mem[k]);
    return get.call(this, k);
  };
  P.setItem = function (k, v) {
    if (!(local(this) && own.call(mem, k))) return set.call(this, k, v);
    mem[k] = String(v);
    // AuthService.login écrit karlToken, karlDeviceId, karlUser puis karlAdmin : la
    // session est complète à karlAdmin. whoami() réécrit ces clés avec le MÊME jeton.
    if (k === "karlAdmin" && mem.karlToken && mem.karlToken !== known) {
      known = mem.karlToken;
      post({ type: "login", karlToken: mem.karlToken, karlDeviceId: mem.karlDeviceId || "",
        karlUser: mem.karlUser || "", karlAdmin: mem.karlAdmin });
    }
  };
  P.removeItem = function (k) {
    if (!(local(this) && own.call(mem, k))) return del.call(this, k);
    var had = mem[k]; mem[k] = null;
    if (k === "karlToken" && had) { known = null; post({ type: "logout" }); }
  };
})();

