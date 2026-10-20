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
    vue: svc.vue, resumes: svc.resumes(vueMois()), moisCharge: svc.moisCharge,
    ligne: svc.ligne, ligneEdit: svc.ligneEdit, ajout: svc.ajout,
  });
  /** Les mois dont la vue courante a besoin — lus du service, jamais devinés. */
  function vueMois() {
    if (svc.vue === "mois") return [svc.day.slice(0, 7)];
    if (svc.vue === "semaine") {
      return [...new Set(semaineDe(svc.day).map(j => j.slice(0, 7)))];
    }
    return [];
  }
  function semaineDe(jour) {
    const d = new Date(jour + "T12:00:00Z");
    const lundi = new Date(d); lundi.setUTCDate(d.getUTCDate() - ((d.getUTCDay() + 6) % 7));
    return Array.from({ length: 7 }, (_, i) => {
      const x = new Date(lundi); x.setUTCDate(lundi.getUTCDate() + i);
      return x.toISOString().slice(0, 10);
    });
  }

  /** Charge ce qui manque pour la vue courante, puis redessine. */
  async function assurerGrille() {
    for (const m of vueMois()) {
      if (!svc.mois[m]) { render(); await svc.chargerMois(m); }
    }
    render();
  }
  const h = card ? mount(card, "", { events: [
    // Un champ de saisie porte un `data-action` pour ses CHANGEMENTS, pas pour les
    // clics : laisser passer le clic rejouait le geste et re-rendait l'écran, ce qui
    // détruisait le champ sous le curseur — « ça saute dès que je clique » (20/10).
    ["click", "[data-action]", (ev, el) => {
      const t = (el.tagName || "").toLowerCase();
      if (t === "input" || t === "select" || t === "textarea") return;
      onClick(ev, el);
    }],
    ["change", "[data-action=\"field\"]", (ev, el) => onField(el)],
    ["change", "[data-action=\"date\"]", (ev, el) => goto(el.value)],
    // Un `select` n'émet pas de clic : sans cet écouteur, corriger le client d'une
    // ligne n'aurait jamais rien changé.
    ["change", "[data-action=\"ligne-champ\"]", (ev, el) => onClick(ev, el)],
    ["change", "[data-action=\"ajout-champ\"]", (ev, el) => onClick(ev, el)],
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
    if (a === "vue") {
      svc.setVue(el.dataset.vue);
      render();
      return assurerGrille();
    }
    if (a === "aller") {
      // Un clic sur une case ouvre SA journée : c'est le chemin naturel depuis la grille.
      svc.setVue("jour");
      return goto(el.dataset.jour);
    }
    if (a === "mois-prec" || a === "mois-suiv") {
      const [an, mo] = svc.day.slice(0, 7).split("-").map(Number);
      const d = new Date(Date.UTC(an, mo - 1 + (a === "mois-suiv" ? 1 : -1), 1));
      svc.setDay(d.toISOString().slice(0, 10));
      retiens(svc.day);
      render();
      return assurerGrille();
    }
    if (a === "prev") return goto(vm().prev);
    if (a === "next") return goto(vm().next);
    if (a === "today") return goto(new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 10));
    if (a === "reload") return load(true);
    if (a === "ticket") return ctx.showTicket && ctx.showTicket(el.dataset.rm);
    if (a === "note-heures") {
      // Reporté dans le formulaire, pas enregistré : il relit, il corrige, il valide.
      svc.setField("debut", el.dataset.debut);
      svc.setField("fin", el.dataset.fin);
      render();
      return notify("horaires de la note reportés — à enregistrer");
    }
    if (a === "save") return garde(() => svc.adjust(), "journée ajustée");
    if (a === "pause-trou") {
      // Reprend le trou mesuré comme bornes de pause : un clic au lieu de deux saisies.
      svc.setField("pauseDebut", el.dataset.debut);
      svc.setField("pauseFin", el.dataset.fin);
      render();
      return notify("trou de midi repris — à enregistrer");
    }
    if (a === "pause-midi") {
      // Un clic : la pause proposée est posée et enregistrée. Elle n'écrit rien dans
      // Redmine — elle entre dans la proposition, qui reste à valider.
      svc.setField("pause", String(vm().pause.proposition));
      return garde(() => svc.adjust(), "pause de midi notée");
    }
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
      // La confirmation NOMME ce qui ne sera PAS écrit : clore une journée qui
      // propose encore des heures, c'est renoncer à les facturer.
      const reste = v.clore && v.clore.reste > 0
        ? `\n\n⚠ les ${v.clore.resteLabel} proposées ne seront PAS écrites.`
        : "";
      if (!confirm(`Clore le ${v.titre} sans créer aucune saisie ?${reste}`
                   + `\n\nLa journée passera en « validée ». « reprendre » la rouvre.`)) return;
      return garde(() => svc.validateEmpty(), "journée validée (rien ajouté)");
    }
    // — les gestes qui ne visent QU'UNE ligne —
    if (a === "ligne-edit") {
      const cle = el.getAttribute("data-cle");
      const l = vm().groupes.flatMap(g => g.lignes.map(x => ({ ...x, client: g.client })))
                   .find(x => x.cle === cle);
      svc.editerLigne(cle, l ? { client: l.client, projet: l.projet,
                                 ticket: l.rm ? String(l.rm) : "" } : null);
      return render();
    }
    if (a === "ligne-cancel") { svc.editerLigne(null); return render(); }
    if (a === "ligne-champ") {
      const champ = el.getAttribute("data-champ");
      svc.setLigneChamp(champ, el.value);
      // Changer de client vide le projet : celui d'avant n'existe pas forcément chez lui.
      if (champ === "client") svc.setLigneChamp("projet", "");
      return render();
    }
    if (a === "ligne-save") {
      return garde(() => svc.enregistrerLigne(), "rattachement corrigé");
    }
    if (a === "ligne-clear") {
      return garde(() => svc.retablirLigne(el.getAttribute("data-cle")),
                   "rattachement rétabli");
    }
    // Retenir le client que l'agenda propose : un clic, pas une saisie. Il ne
    // s'applique jamais tout seul — proposer n'est pas décider.
    if (a === "sugg-client") {
      svc.setField("client", el.getAttribute("data-client"));
      render();
      return garde(() => svc.adjust(), "client de la journée retenu depuis l'agenda");
    }
    if (a === "ligne-split") {
      const cle = el.getAttribute("data-cle");
      const l = vm().groupes.flatMap(g => g.lignes).find(x => x.cle === cle);
      const total = l ? l.minutesBrutes : 0;
      const rep = prompt(`Scinder « ${l ? l.projet : cle} » (${total} min) en deux.\n\n`
                         + `Minutes gardées par la première ligne :`, String(Math.round(total / 2)));
      if (rep === null) return;
      const n = parseInt(rep, 10);
      if (!(n > 0) || n >= total) {
        return garde(() => { throw new Error(`coupure impossible : les deux morceaux doivent être > 0 (ligne de ${total} min)`); });
      }
      return garde(() => svc.scinderLigne(cle, n), `ligne scindée en ${n} + ${total - n} min`);
    }
    if (a === "ligne-delete") {
      const cle = el.getAttribute("data-cle");
      const l = vm().groupes.flatMap(g => g.lignes.map(x => ({ ...x, client: g.client })))
                   .find(x => x.cle === cle);
      const quoi = l ? `${l.client} / ${l.projet} — ${l.minutes}` : cle;
      // Le seul geste qui RETIRE du temps de la proposition : il se nomme.
      if (!confirm(`Retirer cette ligne de la proposition ?\n\n  ${quoi}\n\n`
                   + `Ce temps ne sera facturé à personne. « rétablir » la ramène.`)) return;
      return garde(() => svc.supprimerLigne(cle), "ligne retirée de la proposition");
    }
    if (a === "ajout-open") { svc.editerAjout(true); return render(); }
    if (a === "ajout-cancel") { svc.editerAjout(false); return render(); }
    if (a === "ajout-champ") {
      const champ = el.getAttribute("data-champ");
      svc.setAjoutChamp(champ, el.value);
      if (champ === "client") svc.setAjoutChamp("projet", "");
      return render();
    }
    if (a === "ajout-save") {
      return garde(() => svc.ajouterLigne(), "ligne ajoutée");
    }
    if (a === "ligne-apply") {
      const cle = el.getAttribute("data-cle");
      const l = vm().groupes.flatMap(g => g.lignes.map(x => ({ ...x, client: g.client })))
                   .find(x => x.cle === cle);
      // Comme pour la journée, la confirmation NOMME ce qui part.
      const quoi = l ? `${l.client} / ${l.projet}${l.rm ? ` RM${l.rm}` : " (au projet)"} — ${l.minutes}`
                     : cle;
      if (!confirm(`Écrire cette seule ligne dans Redmine ?\n\n  ${quoi}`)) return;
      return garde(async () => {
        const r = await svc.ecrireLigne(cle);
        if (r && r.ok === false) throw new Error(String(r.stderr || r.stdout || "échec").trim().slice(-300));
      }, "ligne écrite dans Redmine");
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
