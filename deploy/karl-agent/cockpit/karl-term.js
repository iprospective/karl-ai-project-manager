/* karl-term.js — client terminal du cockpit (RM2522, lot L0 de RM2467)
 *
 * Remplace l'<iframe> ttyd par NOTRE propre client xterm.js parlant le
 * protocole WebSocket de ttyd. Deux raisons, décidées le 2026-08-01 :
 *
 *  1. L'iframe ttyd est cross-origin ⇒ boîte noire : le cockpit ne peut ni lire
 *     le contenu du terminal, ni superposer d'interface dessus, ni cliquer à la
 *     place de l'utilisateur. D'où les contournements serveur (capture-pane pour
 *     DEVINER qu'une question est posée, send-keys pour injecter à l'aveugle).
 *     Reprendre la surface est le substrat des lots suivants de RM2467.
 *  2. RM2323 : les accents se perdent par intermittence à la saisie. Le
 *     mécanisme est prouvé (cf. installAccentFix plus bas) et n'est corrigé par
 *     AUCUNE version amont — _inputEvent est identique en 5.4.0, 5.5.0 et 6.0.0.
 *
 * Protocole ttyd (vérifié en lisant le bundle servi par ttyd 1.7.7) :
 *   - WebSocket, sous-protocole « tty », URL <base>/ws?arg=<sid> ;
 *   - handshake  : {"AuthToken":…,"columns":…,"rows":…} encodé UTF-8 ;
 *   - client→srv : premier octet INPUT='0' | RESIZE='1' | PAUSE='2' | RESUME='3' ;
 *   - srv→client : premier octet OUTPUT='0' | SET_WINDOW_TITLE='1' | SET_PREFERENCES='2'.
 *
 * Les fonctions pures du protocole sont encadrées par des marqueurs >>> / <<<
 * et testées sans navigateur par test_cockpit.js.
 */
(function (global) {
  "use strict";

  var ENC = new TextEncoder();
  var DEC = new TextDecoder();

  // >>> ttydHandshake
  // Premier message après l'ouverture : ttyd attend ce JSON tel quel.
  function ttydHandshake(token, cols, rows) {
    return JSON.stringify({ AuthToken: token || "", columns: cols, rows: rows });
  }
  // <<< ttydHandshake

  // >>> ttydEncodeResize
  // RESIZE_TERMINAL = '1' suivi du JSON des dimensions (le tout en texte).
  function ttydEncodeResize(cols, rows) {
    return "1" + JSON.stringify({ columns: cols, rows: rows });
  }
  // <<< ttydEncodeResize

  // >>> ttydEncodeInput
  // INPUT = '0' suivi du texte en UTF-8. Retourne un Uint8Array prêt à
  // envoyer. `encode` est injecté pour rester testable hors navigateur.
  function ttydEncodeInput(text, encode) {
    var payload = encode(text);
    var frame = new Uint8Array(payload.length + 1);
    frame[0] = 0x30;              // '0'
    frame.set(payload, 1);
    return frame;
  }
  // <<< ttydEncodeInput

  // >>> ttydDecode
  // Découpe un message reçu : premier octet = commande, reste = charge utile.
  // Retourne null sur un message vide (que ttyd n'émet pas, mais un proxy
  // fantaisiste pourrait).
  function ttydDecode(bytes) {
    if (!bytes || !bytes.length) return null;
    return { cmd: String.fromCharCode(bytes[0]), payload: bytes.slice(1) };
  }
  // <<< ttydDecode

  /* ── Le correctif des accents (RM2323) ─────────────────────────────────────
   *
   * Mécanisme, prouvé en comparant les sources extraites des sourcemaps de
   * xterm 5.4.0 / 5.5.0 / 6.0.0 — la méthode est identique dans les trois :
   *
   *     if (ev.data && ev.inputType === 'insertText'
   *         && (!ev.composed || !this._keyDownSeen)      // ← la garde
   *         && !screenReaderMode) { … triggerDataEvent(text) }
   *     return false;                                    // sinon : rien n'est envoyé
   *
   * Sous Firefox/GTK, un « é » arrive en keydown {key:"Process"} PUIS
   * input {data:"é", isComposing:false}, sans aucun compositionstart. Cet
   * `input` est composed:true et un keydown a été vu (_keyDownSeen), donc la
   * garde tombe : le caractère n'est jamais transmis. L'intermittence vient de
   * la course entre les deux évènements.
   *
   * On écoute donc sur le CONTENEUR en phase de capture : l'évènement y descend
   * AVANT d'atteindre la .xterm-helper-textarea, donc avant le listener de
   * xterm. Quand on prend la main, stopImmediatePropagation() garantit que
   * xterm ne le verra pas — pas de risque de double saisie.
   */
  function installAccentFix(container, term) {
    container.addEventListener("input", function (ev) {
      var ta = ev.target;
      if (!ta || ta.classList === undefined) return;
      if (!ta.classList.contains("xterm-helper-textarea")) return;
      // mêmes conditions que xterm, SANS la garde qui perd le caractère
      if (!ev.data || ev.inputType !== "insertText") return;
      // vraie composition en cours (IME japonais/chinois…) : ne pas interférer,
      // xterm a un chemin dédié (compositionstart/update/end) qui fonctionne.
      if (ev.isComposing) return;
      ev.stopImmediatePropagation();
      ta.value = "";                 // xterm ne le fera pas : il ne voit rien
      term.input(ev.data, true);
    }, true);
  }

  /* ── Client ────────────────────────────────────────────────────────────── */

  /**
   * Attache un terminal dans `container` sur la session `sid`.
   * options : { base } — origine de ttyd (ex. « http://karl.lxc:7681 »).
   * Retourne { term, dispose } ; `dispose()` ferme la socket et libère xterm.
   */
  function attach(container, sid, options) {
    var opts = options || {};
    var base = String(opts.base || "").replace(/\/+$/, "");
    var wsBase = base.replace(/^http/, "ws");

    var term = new global.Terminal({
      allowProposedApi: true,
      cursorBlink: true,
      fontSize: 14,
      fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace',
      // le thème suit les tokens du cockpit (RM2386) — aucune couleur en dur
      theme: readThemeTokens(container),
      scrollback: 5000,
    });

    var fit = new global.FitAddon.FitAddon();
    term.loadAddon(fit);
    try {
      var u11 = new global.Unicode11Addon.Unicode11Addon();
      term.loadAddon(u11);
      term.unicode.activeVersion = "11";
    } catch (e) { /* addon absent : largeurs de caractères par défaut */ }

    term.open(container);
    installAccentFix(container, term);
    fit.fit();

    var socket = null, closed = false, retry = 0, retryTimer = null;

    function send(frame) {
      if (socket && socket.readyState === WebSocket.OPEN) socket.send(frame);
    }

    function connect() {
      socket = new WebSocket(wsBase + "/ws?arg=" + encodeURIComponent(sid), ["tty"]);
      socket.binaryType = "arraybuffer";

      socket.onopen = function () {
        retry = 0;
        send(ENC.encode(ttydHandshake(opts.token, term.cols, term.rows)));
      };

      socket.onmessage = function (ev) {
        var msg = ttydDecode(new Uint8Array(ev.data));
        if (!msg) return;
        if (msg.cmd === "0") term.write(msg.payload);              // OUTPUT
        else if (msg.cmd === "1") { /* SET_WINDOW_TITLE : ignoré (le cockpit a son entête) */ }
        else if (msg.cmd === "2") { /* SET_PREFERENCES : le cockpit impose les siennes */ }
      };

      socket.onclose = function () {
        if (closed) return;
        // reconnexion progressive : la session tmux, elle, survit à la coupure
        retry = Math.min(retry + 1, 6);
        term.write("\r\n\x1b[33m[cockpit] connexion perdue — reprise dans " + retry + "s…\x1b[0m\r\n");
        retryTimer = setTimeout(connect, retry * 1000);
      };
    }

    term.onData(function (data) { send(ttydEncodeInput(data, function (s) { return ENC.encode(s); })); });
    term.onResize(function (size) { send(ENC.encode(ttydEncodeResize(size.cols, size.rows))); });

    connect();

    var onWinResize = function () { try { fit.fit(); } catch (e) {} };
    global.addEventListener("resize", onWinResize);

    return {
      term: term,
      fit: function () { try { fit.fit(); } catch (e) {} },
      dispose: function () {
        closed = true;
        clearTimeout(retryTimer);
        global.removeEventListener("resize", onWinResize);
        if (socket) { try { socket.close(); } catch (e) {} }
        term.dispose();
      },
    };
  }

  // Couleurs du terminal reprises des variables CSS du cockpit (RM2386 :
  // dark/light pilotés par data-theme sur <html>) — rien en dur ici.
  function readThemeTokens(el) {
    var cs = getComputedStyle(el);
    var pick = function (name, fallback) {
      var v = cs.getPropertyValue(name);
      return (v && v.trim()) || fallback;
    };
    return {
      background: pick("--term-bg", pick("--bg", "#0b0e14")),
      foreground: pick("--term-fg", pick("--fg", "#c8d3e0")),
      cursor: pick("--accent", "#7aa2f7"),
      selectionBackground: pick("--sel", "rgba(122,162,247,.35)"),
    };
  }

  global.KarlTerm = {
    attach: attach,
    // exposés pour les tests et le futur composer (L1 de RM2467)
    ttydHandshake: ttydHandshake,
    ttydEncodeInput: ttydEncodeInput,
    ttydEncodeResize: ttydEncodeResize,
    ttydDecode: ttydDecode,
  };
})(window);
