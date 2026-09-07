// controllers/notify.controller — le toast du cockpit : message simple (3,2 s), erreur, et toast porteur d'une ACTION (RM2451 : « annuler »
// vaut mieux qu'une confirmation préalable — zéro friction quand tout va bien, vrai filet quand on s'est trompé). RM2889.
export function mountNotify(host, ctx = {}) {
  const later = ctx.later || ((fn, ms) => setTimeout(fn, ms));
  const clear = ctx.clear || ((id) => clearTimeout(id));
  const createEl = ctx.createEl || ((tag) => document.createElement(tag));
  let timer = null;
  const arm = (ms) => { if (timer) clear(timer); timer = later(() => { host.className = "toast"; timer = null; }, ms); };
  function toast(msg, err) { if (!host) return; host.textContent = String(msg); host.className = "toast show" + (err ? " err" : ""); arm(3200); }
  function toastAction(msg, label, fn, ms) {
    if (!host) return;
    host.textContent = String(msg) + "  ";
    const a = createEl("span"); a.textContent = label; a.style.cssText = "text-decoration:underline;cursor:pointer;font-weight:600";
    a.addEventListener("click", () => { host.className = "toast"; fn(); });
    host.appendChild(a); host.className = "toast show"; arm(ms || 8000);
  }
  return { toast, toastAction, unmount() { if (timer) { clear(timer); timer = null; } } };
}
