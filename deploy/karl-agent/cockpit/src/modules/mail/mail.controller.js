// controllers/mail.controller — trois gestes, pas un de plus. RM2889, L1 (pilote).
//
//   (1) récupérer les paramètres — l'état du panneau, le geste cliqué, une
//       réponse à une invite ;
//   (2) déléguer au service ;
//   (3) passer un ViewModel à la vue.
//
// Aucune règle métier, aucun balisage, aucun appel réseau direct. Ce que le
// contrôleur reçoit de l'extérieur (invites, notification, ouverture au
// centre, aide) vient du contexte injecté — testable sans navigateur.

import { mount } from "../../core/dom.js";
import { MailService } from "./mail.service.js";
import { EmailViewModel } from "./EmailViewModel.js";
import { MailPanel } from "./MailPanel.view.js";

export function mountMailPanel(el, ctx = {}) {
  const svc = ctx.service || new MailService();
  const ask = ctx.ask || { confirm: (m) => window.confirm(m), prompt: (m, d) => window.prompt(m, d) };
  const notify = ctx.notify || ((msg, err) => (err ? console.error : console.log)(msg));
  const state = { done: false, fullBody: false, openKey: null, emails: [], pending: 0, bounces: [], error: null };

  const paint = () => handle.update(MailPanel({
    vms: state.emails.map(e => new EmailViewModel(e, { openKey: state.openKey })),
    pending: state.pending, done: state.done, fullBody: state.fullBody, error: state.error,
    bounces: state.bounces,
  }));

  async function refresh() {
    try {
      const q = await svc.queue({ done: state.done, key: state.openKey });
      Object.assign(state, { emails: q.emails, pending: q.pending, bounces: q.bounces || [], error: null });
    } catch (e) { state.error = e.message; }
    paint();
    if (ctx.badge) ctx.badge(state.pending);
    if (ctx.mailbox) ctx.mailbox({ emails: state.emails, pending: state.pending, bounces: state.bounces });   // RM3319 : 📬
  }

  async function run(promise) {
    const r = await promise;
    notify(r.message, !r.ok);
    await refresh();
  }

  // les valeurs du formulaire déplié — lues au moment du geste, pas stockées
  const field = (id) => { const n = handle.el.querySelector("#" + id); return n ? n.value : ""; };

  const gestures = {
    help:    ()    => ctx.help && ctx.help("emails"),
    fetch:   ()    => run(svc.fetch()),
    route:   ()    => run(svc.route()),
    refresh: ()    => refresh(),
    ticket:  (rm)  => ctx.showTicket && ctx.showTicket(Number(rm)),   // RM3319 : le ticket du mail rejeté
    toggle:  (key) => { state.openKey = state.openKey === key ? null : key; return refresh(); },
    center:  (key) => ctx.openCenter && ctx.openCenter(key, (state.emails.find(e => e.key === key) || {}).subject || ""),
    // RM3147 — l'expéditeur : sa fiche s'il est connu, sa création sinon.
    contact: (key) => {
      const e = state.emails.find(x => x.key === key) || {};
      const ref = ((e.contact || {}).known && e.contact.ref) || "";
      if (ref && ctx.openContact) ctx.openContact(ref);
    },
    "contact-add": async (key) => {
      const e = state.emails.find(x => x.key === key);
      if (!e || !ctx.addContact) return;
      const champs = new EmailViewModel(e, {}).newContact;
      if (!champs.email) { notify("cet email n'a pas d'adresse d'expéditeur", true); return; }
      // Montrer le DÉCOUPAGE, pas seulement le nom : la convention « dernier mot
      // = nom » se trompe sur un nom composé, et c'est ici qu'on peut s'en
      // apercevoir avant d'écrire.
      const apercu = [champs.first_name, champs.last_name].filter(Boolean).join(" / ") || champs.email;
      if (!ask.confirm("Créer dans l'annuaire ?\n\nprénom / NOM : " + apercu
                       + "\nadresse : " + champs.email)) return;
      const r = await ctx.addContact(champs);
      notify(r && r.message, !(r && r.ok));
      await refresh();          // la file se relit : l'expéditeur devient reconnu
    },
    draft:   (key) => run(svc.draft(key, state.fullBody)),
    create:  (key) => {
      const fields = { project: field("ml-project"), title: field("ml-title"), priority: field("ml-prio") };
      if (!ask.confirm("Créer le ticket dans « " + (fields.project || "?") + " » ?")) return;
      return run(svc.create(key, fields));
    },
    note:    (key) => { const rm = ask.prompt("Rattacher à quel ticket ? (numéro RM)"); if (rm) return run(svc.noteOn(key, rm)); },
    reroute: (key) => { const to = ask.prompt("Client ou client/projet :"); if (to) return run(svc.reroute(key, to)); },
    dismiss: (key) => { const why = ask.prompt("Motif (facultatif) :", "pas une demande"); if (why !== null) return run(svc.dismiss(key, why)); },
  };

  const handle = mount(el, "", {
    events: [
      ["click", "[data-action]", async (ev, btn) => {
        const card = btn.closest ? btn.closest("[data-key]") : null;
        const g = gestures[btn.dataset.action];
        if (!g) return;
        btn.disabled = true;
        try { await g(card ? card.dataset.key : null); } finally { btn.disabled = false; }
      }],
      ["change", "#mail-done",     (ev, box) => { state.done = !!box.checked; return refresh(); }],
      ["change", "#mail-fullbody", (ev, box) => { state.fullBody = !!box.checked; }],
    ],
  });
  handle.track(svc.subscribe(() => {}));   // réservé : invalidation poussée par SSE (L1c)
  paint();

  return Object.assign(handle, { refresh, state });
}
