// modules/billing/BillingViewModel — ce que l'écran « Facturation » présente d'une journée. Inerte. RM3229, L3.
import { fmtMin, fmtTokens, longDate, shiftDay, timeline, totaux, parClient, etat,
         ETAT_LABEL, heuresTravaillees, isWeekend, estAutomatique, libelleLisible,
         poseParOutil, traces, commits, toursIA, clientsEtProjets, LIEUX,
         libelleLieu, pause, nonFacturable, bandes, legende, bandePause,
         transversalParClient, fil, totauxIA, liens, correspondances,
         bilanCorrespondance, blocsRedmine, iaHorsPlage, bilanBlocs, note, legendeIA, grilleSemaine, grilleMois, avancement,
         cumulClients, nomMois, moisDe, decalerMois, weekOf, suggestion, agenda, activites,
         enAttente } from "./billing.js";

export class BillingViewModel {
  constructor({ day, jour, form, loading, error, busy, dirty, projets, vue, resumes, moisCharge,
                ligne, ligneEdit, ajout, enAttente: att }) {
    this.ligne = ligne || null; this.le = ligneEdit || null; this.aj = ajout || null;
    this.att = att || null;
    this.day = day; this.j = jour || null; this.f = form || {};
    this.loading = !!loading; this.error = error || null; this.busy = busy || null; this.dirty = !!dirty;
    this.p = clientsEtProjets(projets || []);
    this.vue = vue || "jour";
    this.r = resumes || {};
    this.moisCharge = moisCharge || null;
  }

  /** Les trois vues, et celle qui est ouverte. */
  get vues() {
    return [["jour", "journée"], ["semaine", "semaine"], ["mois", "mois"]]
      .map(([k, l]) => ({ key: k, label: l, on: this.vue === k }));
  }
  get mois() { return moisDe(this.day); }
  get moisLabel() { return nomMois(this.mois); }
  get moisPrec() { return decalerMois(this.mois, -1); }
  get moisSuiv() { return decalerMois(this.mois, 1); }
  /** Les mois à charger pour la vue courante (une semaine peut être à cheval). */
  get moisNecessaires() {
    if (this.vue === "mois") return [this.mois];
    if (this.vue === "semaine") return [...new Set(weekOf(this.day).map(moisDe))];
    return [];
  }
  get semaine() { return grilleSemaine(this.day, this.r, this.day); }
  get semaineLabel() {
    const s = weekOf(this.day);
    return s.length ? `${longDate(s[0]).replace(/ \d{4}$/, "")} → ${longDate(s[6])}` : "";
  }
  get grille() { return grilleMois(this.mois, this.r, this.day); }
  /**
   * Les journées de la PÉRIODE regardée, et elles seules.
   *
   * Le service garde les résumés par mois ; une vue semaine affichait donc
   * l'avancement et le cumul du mois entier — un chiffre qui ne correspondait pas à
   * ce qu'on avait sous les yeux.
   */
  get portee() {
    if (this.vue !== "semaine") return this.r;
    const dedans = new Set(weekOf(this.day));
    return Object.fromEntries(Object.entries(this.r).filter(([j]) => dedans.has(j)));
  }
  get avancement() { return avancement(this.portee); }
  get cumul() { return cumulClients(this.portee); }
  get grilleVide() { return !Object.keys(this.r).length; }

  /** Les deux menus du formulaire : les clients PM, et les projets du client choisi. */
  get clients() {
    const cur = this.f.client || "";
    const liste = this.p.clients.slice();
    // Un client posé à la main mais absent du référentiel reste proposé : on ne perd
    // jamais une valeur existante en la remplaçant par un menu.
    if (cur && !liste.includes(cur)) liste.unshift(cur);
    return liste.map(c => ({ value: c, selected: c === cur }));
  }
  get projetsDuClient() {
    const cur = this.f.projet || "";
    const liste = this.p.projets(this.f.client || "");
    if (cur && !liste.includes(cur)) liste.unshift(cur);
    return liste.map(x => ({ value: x, selected: x === cur }));
  }

  /** Le temps IA : déclaré et borné. L'écart est le chevauchement de tours parallèles. */
  get iaTotaux() { return totauxIA(this.j); }

  /** La note que Mathieu a écrite ce jour-là — texte libre, affiché tel quel. */
  get note() { return note(this.j); }

  /** La pause de midi : déclarée, visible dans les traces, ou manquante. */
  get pause() { return pause(this.j); }

  /** Ce que la journée ne facturera à personne (son propre temps). */
  get nonFacturable() {
    const nf = nonFacturable(this.j);
    return { ...nf, label: nf.minutes ? fmtMin(nf.minutes) : "" };
  }

  /** Présentiel ou distanciel : renseigné à la journée, il conditionne le déplacement. */
  get lieux() { return LIEUX.map(l => ({ ...l, selected: l.value === (this.f.lieu || "") })); }
  get lieu() { return libelleLieu(this.f.lieu); }

  /** Les traces horodatées — la pièce à conviction de la journée. */
  get traces() { return traces(this.j); }
  get tracesHumaines() { return this.traces.filter(t => t.humain).length; }

  /** Les commits, travail d'abord, plomberie PM repliée. */
  get commits() { return commits(this.j); }

  /** Les tours d'agent, groupés par ticket. */
  get ia() {
    return toursIA(this.j).map(g => ({
      ...g, duree: fmtMin(g.minutes), jetons: fmtTokens(g.tokens),
      plage: g.premier === g.dernier ? g.premier : `${g.premier}–${g.dernier}`,
    }));
  }
  get titre() { return longDate(this.day); }
  get weekend() { return isWeekend(this.day); }
  get prev() { return shiftDay(this.day, -1); }
  get next() { return shiftDay(this.day, 1); }
  get etat() { return etat(this.j); }
  get etatLabel() { return ETAT_LABEL[this.etat] || ""; }
  get validee() { return this.etat === "validee"; }
  get vide() { return !this.j || this.etat === "vide"; }
  get t() { return totaux(this.j); }
  get frise() {
    const t = timeline(this.j, { start: this.f.debut, end: this.f.fin });
    return { ...t, bandes: bandes(this.j, t), pause: bandePause(this.j, t), liens: liens(this.j, t) };
  }
  /** La notice de la frise : un client, sa couleur, son cumul. */
  get legende() { return legende(this.j); }
  /** La notice de la voie IA : pour qui les agents ont travaillé, et combien. */
  get legendeIA() { return legendeIA(this.j); }
  /** Le cumul de transversal reçu par chaque client — en minutes, pas en pourcentage. */
  get transversalCumul() { return transversalParClient(this.j); }
  /** Tout ce qui s'est passé, dans l'ordre. */
  get fil() { return fil(this.j); }

  /** Les blocs qui partiront dans Redmine, chacun avec ses preuves. L'unité de validation. */
  get blocs() { return blocsRedmine(this.j); }
  /** Les tours d'agent hors de toute plage humaine — montrés, jamais facturés. */
  get iaHorsPlage() { return iaHorsPlage(this.j); }
  get bilanBlocs() { return bilanBlocs(this.j); }

  /** Chaque plage humaine et ce qui la justifie — la pièce maîtresse du dossier. */
  get correspondances() {
    const { periodes, orphelins } = correspondances(this.j);
    return {
      periodes: periodes.map(p => ({
        ...p, duree: fmtMin(p.minutes),
        iaDuree: fmtMin(p.ia.reduce((n, k) => n + k.minutes, 0)),
        vide: !p.preuves,
      })),
      orphelins,
      aOrphelins: !!(orphelins.ia.length || orphelins.commits.length
                     || orphelins.fusions.length || orphelins.prompts.length),
    };
  }
  get bilan() { return bilanCorrespondance(this.j); }
  get ajuste() { return this.f.source === "ajuste"; }

  /** Les heures normales, et ce qu'elles font une fois la pause déduite. */
  get heures() {
    const h = heuresTravaillees(this.f.debut, this.f.fin, this.f.pause);
    return { debut: this.f.debut || "", fin: this.f.fin || "", pause: this.f.pause == null ? "" : this.f.pause,
             total: h, label: h ? `${String(h).replace(".", ",")} h` : "—" };
  }

  /** Ce que le bornage à la plage ouvrée a laissé dehors — dit, jamais escamoté. */
  get hors() {
    const h = this.f.hors;
    return h ? `traces de ${h.premiere} à ${h.derniere} : le soir et la nuit restent hors des heures normales` : "";
  }

  /** L'en-tête chiffré : mesuré, déjà noté, proposé, et le travail de l'IA en face. */
  get chiffres() {
    const t = this.t;
    return [
      { cle: "mesure", label: "mesuré", valeur: fmtMin(t.mesure), aide: "temps humain observé dans les traces, plages fusionnées" },
      { cle: "deja", label: "déjà noté", valeur: fmtMin(t.deja), aide: "saisies de temps déjà présentes dans Redmine ce jour-là" },
      { cle: "propose", label: "proposé", valeur: fmtMin(t.propose), aide: "ce que la validation ajouterait dans Redmine" },
      { cle: "ia", label: "IA", valeur: `${this.iaTotaux.tours} tours · ${fmtMin(this.iaTotaux.minutes)}`,
        aide: `${fmtTokens(t.tokens)} tokens`
              + (this.iaTotaux.paralleles > 0
                 ? ` — ${this.iaTotaux.paralleles} tour(s) en parallèle d'un autre (${fmtMin(this.iaTotaux.horloge)} d'horloge) : le travail produit dépasse le temps écoulé, c'est normal`
                 : "") },
    ];
  }

  /** La proposition, groupée par client : c'est la maille à laquelle on relit. */
  get groupes() {
    return parClient(this.j).map(g => ({
      client: g.client, total: fmtMin(g.minutes),
      facturable: g.lignes.some(l => l.facturable !== false),
      lignes: g.lignes.map(l => ({
        projet: l.projet, ticket: l.ticket ? `RM${l.ticket}` : "", rm: l.ticket || null,
        minutes: fmtMin(l.minutes),
        outillage: l.outillage_min ? `dont ${fmtMin(l.outillage_min)} d'outillage PM mutualisé` : "",
        // Une ligne se corrige et s'écrit seule : il lui faut un nom stable.
        cle: l.cle || "",
        // Ce que Redmine recevra en commentaire. La marque `[timesheet:…]` sert à ne
        // pas créer deux fois la même saisie : elle part aussi, mais elle n'intéresse
        // pas le lecteur — on la sépare plutôt que de la cacher.
        description: (l.description || "").replace(/\s*\[timesheet:[^\]]*\]\s*$/, ""),
        //

        // Ce que l'humain a écrit pour le client, s'il l'a écrit : c'est lui qui
        // part en facture, pas le texte reconstruit.
        commentaire: l.commentaire || "",
        marque: (String(l.description || "").match(/\[timesheet:[^\]]*\]/) || [""])[0],
        amendee: !!l.amendee,
        origine: l.origine ? `${l.origine.client || "?"}/${l.origine.projet || "?"}`
                             + (l.origine.ticket ? ` RM${l.origine.ticket}` : "") : "",
        // Le ticket lâché en déplaçant la ligne : Redmine range une saisie dans le
        // projet de son ticket, le garder ramènerait le temps d'où il vient.
        abandonne: l.ticket_abandonne ? `RM${l.ticket_abandonne}` : "",
        edition: this.ligne === l.cle,
        manuelle: !!l.manuelle,
        minutesBrutes: l.minutes,
      })),
    }));
  }

  /** La ligne en cours de correction : sa saisie et les cibles proposées. */
  get ligneEdit() {
    if (!this.ligne) return null;
    const e = this.le || {};
    return { cle: this.ligne, client: e.client || "", projet: e.projet || "",
             ticket: e.ticket || "", commentaire: e.commentaire || "",
             clients: this.p.clients,
             projets: e.client ? this.p.projets(e.client) : [],
             busy: this.busy === "ligne" || this.busy === "ligne-apply" };
  }

  /** Le formulaire d'ajout d'une ligne, s'il est ouvert. */
  get activites() { return activites(this.j); }

  get ajout() {
    if (!this.aj) return null;
    const a = this.aj;
    return { client: a.client || "", projet: a.projet || "", ticket: a.ticket || "",
             minutes: a.minutes || "", commentaire: a.commentaire || "",
             activite: a.activite || "", activites: this.activites,
             clients: this.p.clients,
             projets: a.client ? this.p.projets(a.client) : [],
             busy: this.busy === "ligne" };
  }

  /** Le client que l'agenda propose pour cette journée, s'il en propose un. */
  get suggestion() { return suggestion(this.j); }

  /** Les rendez-vous de la journée — ce qui justifie la proposition. */
  get agenda() { return agenda(this.j); }

  /** Le rappel des mois clos sans facture, s'il y en a. */
  get enAttente() { return enAttente(this.att); }

  get dejaSaisi() {
    return ((this.j && this.j.deja_saisi) || []).map(s => ({
      minutes: fmtMin(s.minutes), ticket: s.ticket ? `RM${s.ticket}` : "", rm: s.ticket || null,
      libelle: libelleLisible(s), auto: estAutomatique(s),
      client: s.client || "", projet: s.projet || "",
    }));
  }

  /**
   * Ce que l'OUTIL a posé sur cette journée — ce qui peut donc être repris.
   *
   * La distinction est le cœur du geste : les saisies notées à la main sont hors d'atteinte,
   * et l'écran le dit avant qu'on clique, pas après.
   */
  get auto() {
    const a = poseParOutil(this.j);
    return { ...a, label: `${a.count} saisie${a.count > 1 ? "s" : ""} (${fmtMin(a.minutes)})` };
  }
  get reprenable() { return this.auto.count > 0 && this.busy !== "revoke"; }
  get manuelles() { return this.dejaSaisi.filter(s => !s.auto).length; }

  get regie() {
    return ((this.j && this.j.regie) || []).map(r => ({
      client: r.client, minutes: fmtMin(r.minutes), motif: r.motif,
    }));
  }

  /** Ce que le serveur a décidé du temps transversal (PM, infra, écosystèmes) — et pourquoi. */
  get transversal() {
    const d = (this.j && this.j.journal) || {};
    if (!d.destin) return null;
    const cle = Object.entries(d.cle || {}).sort((a, b) => b[1] - a[1])
      .map(([c, p]) => `${c} ${Math.round(p * 100)} %`).join(" · ");
    const mots = { refacture: "réparti sur les clients travaillés", garde: "à ma charge",
                   ecarte: "écarté (journée sans client)" };
    return {
      destin: mots[d.destin] || d.destin, cle,
      ouvre: d.pot_ouvre_h ? `${d.pot_ouvre_h.toFixed(1).replace(".", ",")} h en heures ouvrées` : "",
      hors: d.pot_hors_h ? `${d.pot_hors_h.toFixed(1).replace(".", ",")} h hors heures` : "",
      alerte: d.alerte_absence ? "journée déclarée absente, mais de l'activité cliente y figure — à trancher" : "",
    };
  }

  /**
   * Le bouton principal : ce qu'il propose dépend de l'état, jamais d'un réglage caché.
   *
   * Une journée DÉJÀ validée reste complétable (décision du 2026-09-21 : juin à août se
   * repassent journée par journée). Corriger les heures d'une journée ancienne peut faire
   * apparaître un complément ; le bouton le propose alors, et dit qu'il complète — il
   * n'écrit jamais deux fois le même temps, le déjà-saisi étant déduit en amont.
   */
  get action() {
    if (this.busy === "apply") return { label: "validation en cours…", disabled: true, geste: "" };
    if (this.t.propose > 0) {
      return { label: `${this.validee ? "Compléter" : "Valider"} — écrire ${fmtMin(this.t.propose)} dans Redmine`,
               disabled: false, geste: "apply" };
    }
    if (this.validee) return { label: "journée validée", disabled: true, geste: "" };
    if (this.t.deja > 0) return { label: "Valider sans rien ajouter", disabled: false, geste: "validate-empty" };
    return { label: "rien à valider", disabled: true, geste: "" };
  }

  /**
   * Clore la journée SANS rien écrire — la sortie qui manquait.
   *
   * Le bouton principal n'offrait « valider sans rien ajouter » que lorsque la
   * proposition était déjà vide : pour clore une journée dont on ne veut écrire
   * aucune ligne, il fallait les retirer une à une d'abord. Ce geste-ci existe
   * tant que la journée n'est pas validée, quoi qu'elle propose.
   */
  get clore() {
    if (this.validee || this.busy) return null;
    return { label: "clore sans écrire", reste: this.t.propose,
             resteLabel: this.t.propose > 0 ? fmtMin(this.t.propose) : "" };
  }
}
