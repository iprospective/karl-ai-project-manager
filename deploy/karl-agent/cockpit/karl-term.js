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

  // >>> bracketedPaste
  // Encadre un texte en « collage entre crochets » (mode 2004 : ESC[200~ … ESC[201~).
  // Sans ça, un texte multi-ligne envoyé frappe par frappe fait soumettre le TUI à
  // CHAQUE saut de ligne : un prompt de cinq lignes part en cinq messages tronqués.
  // Encadré, le TUI le reçoit comme UN collage et n'y voit aucune validation.
  //
  // Les fins de ligne sont normalisées en \n : un \r à l'intérieur d'un collage est
  // interprété par certains TUI comme une validation malgré l'encadrement.
  function bracketedPaste(text) {
    return "\x1b[200~" + String(text == null ? "" : text).replace(/\r\n?/g, "\n") + "\x1b[201~";
  }
  // <<< bracketedPaste

  // >>> composerFrames
  // Les trames à émettre pour envoyer `text` au TUI. Le retour chariot de
  // validation est émis SÉPARÉMENT, hors du collage : à l'intérieur il serait
  // du texte, et le message resterait dans la zone de saisie du TUI.
  // Un texte vide ne produit rien — pas même un Entrée à vide.
  function composerFrames(text, submit) {
    var body = String(text == null ? "" : text);
    if (!body) return [];
    var frames = [bracketedPaste(body)];
    if (submit !== false) frames.push("\r");
    return frames;
  }
  // <<< composerFrames

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
   * xterm, et stopImmediatePropagation() l'empêche de le voir.
   *
   * Attention : couper l'`input` ne suffit PAS à éviter la double saisie. Sur un
   * caractère ordinaire, xterm a déjà émis depuis le KEYDOWN, bien avant que
   * l'`input` n'arrive — c'est ce qui a doublé les espaces en prod. La décision
   * se prend donc sur ce qu'xterm a réellement émis (cf. shouldTakeOverInput),
   * pas sur l'identité de la touche.
   */
  // >>> shouldTakeOverInput
  // Faut-il envoyer NOUS-MÊMES ce caractère, ou xterm l'a-t-il déjà fait ?
  //
  // On NE discrimine PAS sur le nom de la touche (key="Process", keyCode 229) :
  // c'est une propriété du clavier et de la version de Firefox, pas du fait qui
  // nous intéresse. Une première version le faisait et doublait tous les espaces.
  //
  // Le fait décisif est observable directement : xterm a-t-il émis des données
  // depuis le keydown en cours ? Mesuré dans le navigateur (RM2522) —
  //   espace :  keydown " "       → xterm émet "0 "  → input {data:" "}
  //   « é »  :  keydown "Process" → xterm n'émet rien → input {data:"é"}
  // Un `input` qui suit une émission d'xterm est donc un doublon à ignorer ;
  // un `input` sans émission est un caractère que xterm a abandonné, et que
  // personne n'enverra si nous ne le faisons pas.
  function shouldTakeOverInput(ev, xtermEmitted) {
    if (!ev || !ev.data || ev.inputType !== "insertText") return false;
    // vraie composition (IME japonais/chinois…) : xterm a un chemin dédié
    // (compositionstart/update/end) qui fonctionne — ne pas interférer.
    if (ev.isComposing) return false;
    return !xtermEmitted;
  }
  // <<< shouldTakeOverInput

  // Retourne la fonction de désinstallation — À APPELER dans dispose(). Les
  // écouteurs sont posés sur le conteneur, qui SURVIT aux remontages (le
  // cockpit se contente de vider son innerHTML) : sans ça, chaque changement de
  // session en empile un de plus. Le plus ancien s'exécute en premier, coupe la
  // propagation et réémet sur un terminal déjà disposé dont la socket est
  // fermée — le caractère disparaît en silence (défaut constaté en prod).
  // >>> installAccentFix
  function installAccentFix(container, term) {
    var xtermEmitted = false, selfSend = false;

    // Notre propre réémission repasse par onData : ne pas la compter comme une
    // émission d'xterm, sinon deux accents de suite perdraient le second.
    var sub = term.onData(function () { if (!selfSend) xtermEmitted = true; });

    function onKeyDown() { xtermEmitted = false; }

    function onInput(ev) {
      var ta = ev.target;
      if (!ta || ta.classList === undefined) return;
      if (!ta.classList.contains("xterm-helper-textarea")) return;
      if (!shouldTakeOverInput(ev, xtermEmitted)) return;   // xterm s'en charge
      ev.stopImmediatePropagation();
      ta.value = "";                 // xterm ne le fera pas : il ne voit rien
      selfSend = true;
      try { term.input(ev.data, true); } finally { selfSend = false; }
    }

    // Capture : l'évènement descend par le conteneur AVANT d'atteindre la
    // .xterm-helper-textarea, donc avant le listener de xterm.
    container.addEventListener("keydown", onKeyDown, true);
    container.addEventListener("input", onInput, true);

    return function uninstallAccentFix() {
      container.removeEventListener("keydown", onKeyDown, true);
      container.removeEventListener("input", onInput, true);
      try { sub.dispose(); } catch (e) { /* xterm déjà libéré */ }
    };
  }
  // <<< installAccentFix

  // >>> termPalette
  // Palette ANSI 16 couleurs du terminal. xterm n'en fournit une par défaut que
  // pour un fond noir : sur le fond du cockpit, son `brightBlack` (~#666) rend
  // illisibles les gris dont le TUI claude se sert abondamment. On la fixe donc
  // explicitement, dans l'esprit des tokens du cockpit (--accent, --ok, --warn,
  // --danger), et test_cockpit.js en vérifie les contrastes sur les deux fonds.
  function termPalette(light) {
    return light ? {
      black: "#2b3440", red: "#b5232f", green: "#0f7350", yellow: "#8a6100",
      blue: "#1560b8", magenta: "#7a3ba8", cyan: "#0e6d78", white: "#4a5568",
      brightBlack: "#5f6b7d", brightRed: "#8f1a24", brightGreen: "#0a5a3e",
      brightYellow: "#6d4c00", brightBlue: "#0f4a90", brightMagenta: "#5f2d84",
      brightCyan: "#0a545d", brightWhite: "#1c2430",
    } : {
      black: "#2a3446", red: "#ff6b7a", green: "#3ad29f", yellow: "#f5a742",
      blue: "#4ea1ff", magenta: "#c792ea", cyan: "#56d4dd", white: "#c8d3e0",
      brightBlack: "#8b9bb4",           // ← le gris du TUI : doit rester lisible
      brightRed: "#ff9aa5", brightGreen: "#74e3bd", brightYellow: "#ffc978",
      brightBlue: "#85c0ff", brightMagenta: "#dcb6f2", brightCyan: "#8ae7ee",
      brightWhite: "#eaf3ff",
    };
  }
  // <<< termPalette

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
    var uninstallAccentFix = installAccentFix(container, term);
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

    var refit = function () { try { fit.fit(); } catch (e) {} };

    // Le terminal ne bouge pas qu'avec la fenêtre : déplier l'encart de session
    // ou un panneau change sa largeur SANS évènement resize. Un ResizeObserver
    // sur l'hôte couvre tous ces cas d'un coup (retour de test RM2522).
    var ro = null;
    if (global.ResizeObserver) {
      var pending = null;
      ro = new global.ResizeObserver(function () {          // groupé : le dépliage
        clearTimeout(pending);                              // est animé, on ne
        pending = setTimeout(refit, 60);                    // refit qu'à la fin
      });
      ro.observe(container);
    }
    global.addEventListener("resize", refit);

    // Bascule de thème du cockpit (RM2386) : relire les tokens et réappliquer.
    var mo = new MutationObserver(function () {
      try { term.options.theme = readThemeTokens(container); } catch (e) {}
    });
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });

    return {
      term: term,
      fit: refit,
      // Envoi d'un message composé hors du terminal (RM2527). Passe par la même
      // socket que la frappe, donc par le même PTY : le TUI ne fait aucune
      // différence. Retourne false si la socket n'est pas prête — l'appelant en
      // avertit l'utilisateur plutôt que de perdre le message en silence.
      send: function (text, submit) {
        if (!socket || socket.readyState !== WebSocket.OPEN) return false;
        var frames = composerFrames(text, submit);
        for (var i = 0; i < frames.length; i++) {
          send(ttydEncodeInput(frames[i], function (s) { return ENC.encode(s); }));
        }
        return frames.length > 0;
      },
      dispose: function () {
        closed = true;
        clearTimeout(retryTimer);
        global.removeEventListener("resize", refit);
        uninstallAccentFix();          // le conteneur survit au démontage
        if (ro) ro.disconnect();
        mo.disconnect();
        if (socket) { try { socket.close(); } catch (e) {} }
        term.dispose();
      },
    };
  }

  // Fond / premier plan / curseur viennent des tokens CSS du cockpit (RM2386 :
  // dark/light pilotés par data-theme sur <html>) ; la palette ANSI vient de
  // termPalette(). Rien en dur ici.
  function readThemeTokens(el) {
    var cs = getComputedStyle(el);
    var pick = function (name, fallback) {
      var v = cs.getPropertyValue(name);
      return (v && v.trim()) || fallback;
    };
    var light = document.documentElement.getAttribute("data-theme") === "light";
    var theme = {
      background: pick("--term-bg", light ? "#fbfcfe" : "#0b0e14"),
      foreground: pick("--term-fg", light ? "#1c2430" : "#c8d3e0"),
      cursor: pick("--accent", "#4ea1ff"),
      cursorAccent: pick("--term-bg", light ? "#fbfcfe" : "#0b0e14"),
      selectionBackground: pick("--accent-soft", "rgba(78,161,255,.30)"),
    };
    var ansi = termPalette(light);
    for (var k in ansi) theme[k] = ansi[k];
    return theme;
  }

  global.KarlTerm = {
    attach: attach,
    // exposés pour les tests et le composer (L1 de RM2467)
    ttydHandshake: ttydHandshake,
    ttydEncodeInput: ttydEncodeInput,
    ttydEncodeResize: ttydEncodeResize,
    ttydDecode: ttydDecode,
    bracketedPaste: bracketedPaste,
    composerFrames: composerFrames,
  };
})(window);
