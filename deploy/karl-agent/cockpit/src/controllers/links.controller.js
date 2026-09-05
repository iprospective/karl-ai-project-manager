// controllers/links.controller — les références cliquables (RM2585/2596/2718) et leur geste : UN écouteur en phase de CAPTURE sur le document.
// Un clic sur `[data-link]` ouvre la fiche ℹ ou l'onglet Fichiers et NE REMONTE PAS — la tuile qui porte le titre ne s'attache pas, comme
// le `event.stopPropagation()` inline qu'il remplace. RM2889.
import { linkify, titleLink, markPillHtml } from "../views/common/Links.view.js";

export function mountLinks(root, ctx = {}) {
  const handler = (ev) => {
    const n = ev.target && ev.target.closest ? ev.target.closest("[data-link]") : null;
    if (!n) return;
    ev.stopPropagation();
    const kind = n.dataset.link;
    if (kind === "ticket" && ctx.showTicket) ctx.showTicket(n.dataset.rm);
    else if (kind === "file" && ctx.openFileRef) ctx.openFileRef(n.dataset.path);
    // "ext" : le navigateur suit le lien ; on a seulement empêché la tuile de s'attacher
  };
  if (root && root.addEventListener) root.addEventListener("click", handler, true);
  return {
    linkify: (text) => linkify(text, ctx.glossify),
    titleLink: (rm, title) => titleLink(rm, title, ctx.redmineBase ? ctx.redmineBase() : ""),
    markPillHtml,
    unmount() { if (root && root.removeEventListener) root.removeEventListener("click", handler, true); },
  };
}
