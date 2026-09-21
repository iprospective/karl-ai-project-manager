// modules/billing/billing.controller — l'écran « Facturation » : une journée, ses gestes, sa validation. RM3229, lot L3.
//
// Hôte : `card` (#billingcard, dans le panneau central #cp-billing). Le centre appelle `open()` à
// l'ouverture du menu. La journée regardée est retenue d'une ouverture à l'autre (ce navigateur).
//
// Deux garde-fous tiennent dans ce fichier, et ils sont la raison d'être de l'écran :
//   — on ne valide QUE la journée affichée, jamais un lot ;
//   — la validation demande une confirmation qui NOMME ce qui va être écrit, puis relit Redmine.
import { BillingService } from "./billing.service.js";
import { BillingViewModel } from "./BillingViewModel.js";
import { Card } from "./Billing.view.js";
import { mount } from "../../core/dom.js";

const CLE_JOUR = "karlBillingDay";

export function mountBilling({ card } = {}, ctx = {}) {
  const svc = ctx.service || new BillingService({ run: ctx.run });
  const notify = ctx.notify || (() => {});
  const confirm = ctx.confirm || ((m) => (typeof window !== "undefined" ? window.confirm(m) : false));
  const store = ctx.storage || null;
  let opened = false;

  const lu = (() => { try { return store ? store.getItem(CLE_JOUR) : null; } catch (e) { return null; } })();
  if (lu && /^\d{4}-\d{2}-\d{2}$/.test(lu)) svc.setDay(lu);
  const retiens = (j) => { try { if (store) store.setItem(CLE_JOUR, j); } catch (e) { /* mode privé */ } };

  const vm = () => new BillingViewModel({
    day: svc.day, jour: svc.jour, form: svc.form(), loading: svc.loading,
    error: svc.error, busy: svc.busy, dirty: svc.dirty, projets: svc.projets,
  });
  const h = card ? mount(card, "", { events: [
    ["click", "[data-action]", (ev, el) => onClick(ev, el)],
    ["change", "[data-action=\"field\"]", (ev, el) => onField(el)],
    ["change", "[data-action=\"date\"]", (ev, el) => goto(el.value)],
  ] }) : null;

  function render() { if (h) h.update(Card(vm())); }

  async function load(refresh) { render(); await svc.load(refresh); render(); }

  /** Ouverture du menu : la première fois charge, ensuite réaffiche (et relit si la journée est celle du jour). */
  async function open() {
    if (!opened) {
      opened = true;
      svc.chargerProjets().then(render);   // les menus se peuplent dès qu'ils arrivent
      return load(false);
    }
    render();
    return svc.jour;
  }

  function goto(jour) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(String(jour || ""))) return;
    svc.setDay(jour); retiens(svc.day); return load(false);
  }

  function onField(el) {
    svc.setField(el.dataset.field, el.value);
    // Changer de client invalide le projet : un projet appartient à UN client, et
    // laisser l'ancien afficherait une paire qui n'existe pas.
    if (el.dataset.field === "client") svc.setField("projet", "");
    render();
  }

  async function garde(fn, succes) {
    try { await fn(); notify(succes); }
    catch (e) { notify(e.message, true); }
    finally { render(); }
  }

  async function onClick(ev, el) {
    if (ev && ev.preventDefault && el.dataset.action === "ticket") ev.preventDefault();
    const a = el.dataset.action;
    if (a === "prev") return goto(vm().prev);
    if (a === "next") return goto(vm().next);
    if (a === "today") return goto(new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 10));
    if (a === "reload") return load(true);
    if (a === "ticket") return ctx.showTicket && ctx.showTicket(el.dataset.rm);
    if (a === "save") return garde(() => svc.adjust(), "journée ajustée");
    if (a === "clear") return garde(() => svc.clearOverride(), "ajustement retiré");
    if (a === "dry") {
      return garde(async () => {
        const r = await svc.apply({ dryRun: true });
        notify("simulation : " + String((r && r.stdout) || "").trim().split("\n").slice(-1)[0]);
      }, "simulation faite — rien n'a été écrit");
    }
    if (a === "revoke") {
      const v = vm();
      // Geste destructif : la confirmation dit ce qui PART, ce qui RESTE, et qu'une sauvegarde
      // est écrite. Une reprise ne se déclenche jamais seule — seulement ici, sur ce clic.
      const reste = v.manuelles
        ? `\n${v.manuelles} saisie(s) notée(s) à la main ne sont PAS touchées.` : "";
      if (!confirm(`Reprendre le ${v.titre} ?\n\nRetirer ${v.auto.label} posée(s) par l'outil.${reste}`
                   + "\n\nUne sauvegarde est écrite avant suppression, et la journée est réanalysée ensuite.")) return;
      return garde(async () => {
        const r = await svc.revoke();
        if (r && r.ok === false) throw new Error(String(r.stderr || r.stdout || "échec").trim().slice(-300));
      }, "journée reprise — saisies retirées, journée réanalysée");
    }
    if (a === "validate-empty") {
      const v = vm();
      if (!confirm(`Marquer le ${v.titre} comme validée sans créer de saisie ?`)) return;
      return garde(() => svc.validateEmpty(), "journée validée (rien ajouté)");
    }
    if (a === "apply") {
      const v = vm();
      // La confirmation NOMME ce qui part : un « êtes-vous sûr ? » ne protège de rien.
      const lignes = v.groupes.map(g => `  ${g.client} : ${g.total}`).join("\n");
      if (!confirm(`Écrire dans Redmine le temps du ${v.titre} ?\n\n${lignes}\n\nTotal ${v.chiffres[2].valeur}.`)) return;
      return garde(async () => {
        const r = await svc.apply();
        if (r && r.ok === false) throw new Error(String(r.stderr || r.stdout || "échec").trim().slice(-300));
      }, "journée validée — saisies créées dans Redmine");
    }
  }

  return { open, load, render, goto, day: () => svc.day, data: () => svc.jour, svc,
           unmount() { if (h) h.unmount(); } };
}
