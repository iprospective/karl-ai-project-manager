// controllers/commands.controller — les boutons « statiques » de la page (en-tête, aides des panneaux, barre du terminal) : un seul
// écouteur délégué sur `[data-cmd]`, une carte `nom → geste` fournie par boot.js. `data-arg` porte l'argument ; `data-stop` demande
// preventDefault + stopPropagation (un bouton d'aide dans un <summary> ne doit pas replier la carte). RM2889.
export function mountCommands(root, map = {}) {
  const handler = (ev) => {
    const n = ev.target && ev.target.closest ? ev.target.closest("[data-cmd]") : null;
    if (!n) return;
    const fn = map[n.dataset.cmd];
    if (!fn) return;
    if (n.dataset.stop !== undefined) { ev.preventDefault(); ev.stopPropagation(); }
    fn(n.dataset.arg, n, ev);
  };
  if (root && root.addEventListener) root.addEventListener("click", handler);
  return { run: (cmd, arg) => (map[cmd] ? map[cmd](arg) : undefined), has: (cmd) => !!map[cmd], unmount() { if (root && root.removeEventListener) root.removeEventListener("click", handler); } };
}
