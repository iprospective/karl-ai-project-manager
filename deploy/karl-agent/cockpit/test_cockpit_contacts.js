#!/usr/bin/env node
// Tests RM3024 — l'annuaire de contacts dans le cockpit.
//
// Ce qui est protégé ici, dans l'ordre d'importance :
//   1. une ligne de client RATTACHÉE (`ref`) est cliquable et porte l'identité
//      de la personne — avant, le cockpit ne connaissait que l'ancienne forme
//      et affichait « — » pour un rattachement ;
//   2. une `ref` dont la fiche a disparu se VOIT (pastille) au lieu de passer
//      pour un contact vide, et n'est pas cliquable vers le néant ;
//   3. la recherche est mémorisée dans la clé de vue : rouvrir l'onglet rejoue
//      la MÊME recherche, pas un annuaire entier où l'on ne retrouve rien ;
//   4. rien de ce qui vient d'une fiche n'atteint le DOM sans échappement —
//      une note d'annuaire est du texte libre.
"use strict";
const path = require("path"); const assert = require("assert"); const DIR = __dirname;
(async () => {
  const VM = await import(path.join(DIR, "src/modules/center/CenterViewModels.js"));
  const V = await import(path.join(DIR, "src/modules/center/Center.view.js"));
  const K = await import(path.join(DIR, "src/modules/center/viewKey.js"));
  const E = await import(path.join(DIR, "src/core/entities.js"));

  // — 1. les contacts d'un client, résolus —
  const client = new VM.ClientViewModel({
    client: "calyclay", contacts: [
      { ref: "solsona-noe", role: "owner", title: "PDG", source: "annuaire",
        name: "Noé Solsona", first_name: "Noé", last_name: "Solsona",
        email: "noe@calyclay.com", phone: "04 75", internal: false },
      { ref: "iprospective", role: "technique", source: "annuaire",
        name: "Mathieu Moulin", first_name: "Mathieu", last_name: "Moulin",
        email: "mathieu@iprospective.fr", internal: true },
      { name: "Vieille ligne", email: "x@y.fr", role: "autre", source: "inline" },
      { ref: "disparu", role: "facturation", source: "orphelin" },
    ], projects: [], used: [], docs: [], team: [],
  });
  const cs = client.contacts();
  assert.equal(cs.length, 4);
  assert.equal(cs[0].nom, "Noé Solsona", "le nom vient de l'annuaire");
  assert.equal(cs[0].ref, "solsona-noe", "…et la ligne est cliquable");
  assert.ok(cs[0].det.includes("PDG") && cs[0].det.includes("noe@calyclay.com"),
    "rôle, titre et adresse sur la même ligne");
  assert.equal(cs[1].internal, true, "« interne » vient de la PERSONNE (RM3024)");
  assert.equal(cs[2].ref, "", "un contact en ligne n'est pas cliquable : il n'a pas de fiche");
  assert.equal(cs[2].nom, "Vieille ligne", "…mais il reste affiché pendant la migration");
  assert.equal(cs[3].orphelin, true, "une ref sans fiche est signalée");
  assert.equal(cs[3].ref, "", "…et ne renvoie pas vers une fiche qui n'existe pas");
  console.log("✓ contacts d'un client résolus (RM3024) : ref cliquable, inline lisible, orphelin visible");

  const hv = String(V.ClientView(client));
  assert.ok(/data-action="open-contact" data-value="solsona-noe"/.test(hv),
    "la ligne rattachée porte le geste d'ouverture");
  assert.ok(!/data-action="open-contact" data-value=""/.test(hv),
    "aucune ligne sans ref ne porte le geste");
  assert.ok(/ref inconnue/.test(hv), "l'orpheline est nommée à l'écran");

  // — 2. l'annuaire : liste et recherche —
  const ann = new VM.ContactsViewModel({ contacts: [
    { ref: "iprospective", name: "Mathieu Moulin", internal: true,
      emails: ["mathieu@iprospective.fr", "contact@iprospective.fr"] },
    { ref: "solsona-noe", name: "Noé Solsona", internal: false, emails: ["noe@calyclay.com"] },
  ] }, "noe");
  const rows = ann.rows();
  assert.equal(rows.length, 2);
  assert.deepEqual(rows[0].emails, ["mathieu@iprospective.fr", "contact@iprospective.fr"],
    "toutes les adresses sont montrées — c'est par elles qu'on retrouve la personne");
  const av = String(V.ContactsView(ann));
  assert.ok(/value="noe"/.test(av), "la recherche reste dans le champ après rendu");
  assert.ok(/data-action="contacts-search"/.test(av) && /data-action="contacts-clear"/.test(av),
    "champ et bouton de vidage câblés");
  assert.ok(/data-action="open-contact" data-value="iprospective"/.test(av),
    "chaque ligne ouvre la fiche");
  const vide = String(V.ContactsView(new VM.ContactsViewModel({ contacts: [] }, "zorglub")));
  assert.ok(/aucune personne pour/.test(vide) && /zorglub/.test(vide),
    "un résultat vide dit CE QU'ON cherchait");

  // — 3. la fiche d'une personne —
  const fiche = new VM.ContactViewModel({
    ref: "iprospective", name: "Mathieu Moulin", internal: true,
    emails: ["mathieu@iprospective.fr"], phones: ["+33 6 00"], note: "note libre",
    created: "2026-09-08", updated: "2026-09-12",
    links: [{ client: "calyclay", role: "owner", title: "Gérant" },
            { client: "abatik", role: null, title: null }],
  });
  assert.equal(fiche.name, "Mathieu Moulin");
  assert.equal(fiche.dates, "créée 2026-09-08 · màj 2026-09-12");
  const liens = fiche.links();
  assert.equal(liens[0].det, "owner · Gérant");
  assert.equal(liens[1].det, "sans rôle", "un rattachement sans rôle le dit, au lieu d'être vide");
  const fv = String(V.ContactView(fiche));
  assert.ok(/data-action="open-client" data-value="calyclay"/.test(fv),
    "depuis la fiche on retourne au client");
  const seule = String(V.ContactView(new VM.ContactViewModel({ ref: "x", links: [] })));
  assert.ok(/aucun client ne la référence/.test(seule), "une fiche sans rattachement le dit");
  console.log("✓ annuaire et fiche personne (RM3024) : recherche, adresses, rattachements");

  // — 4. échappement : une note est du texte libre —
  const xss = String(V.ContactView(new VM.ContactViewModel({
    ref: "x", name: "<img src=x onerror=alert(1)>", note: "<script>alert(2)</script>",
    emails: ["<b>@x.fr"], links: [],
  })));
  assert.ok(!/<img/.test(xss) && !/<script>/.test(xss) && !/<b>@/.test(xss),
    "nom, note et adresses sont échappés");
  console.log("✓ échappement (RM3024) : nom, note et adresses d'une fiche");

  // — 5. la recherche vit dans la clé de vue —
  assert.equal(K.viewKey(["noe"]), "noe", "la clé porte la recherche");
  assert.deepEqual(K.parseViewKey(K.viewKey(["noe"])), ["noe"], "aller-retour de clé");
  assert.equal(E.tabLabelOf("contacts", ["noe"]), "👤 noe",
    "l'onglet dit CE QU'ON cherche, pas seulement « annuaire »");
  assert.equal(E.tabLabelOf("contacts", [""]), "annuaire");
  assert.equal(E.tabLabelOf("contact", ["solsona-noe"]), "solsona-noe");
  console.log("✓ onglets (RM3024) : la recherche est rejouée à la réouverture");
  // — 6. RM3146 : l'annuaire est atteignable depuis le menu du haut —
  // Sans cette garde, le bouton peut disparaître d'index.html ou sa commande
  // sortir de la carte de boot.js sans qu'aucun test ne bronche : l'annuaire
  // redeviendrait ce qu'il était, une capacité livrée mais introuvable.
  const fs = require("fs");
  const htm = fs.readFileSync(path.join(DIR, "index.html"), "utf8");
  const boot = fs.readFileSync(path.join(DIR, "src/boot.js"), "utf8");
  assert(/data-cmd="contacts"/.test(htm),
    "RM3146 : le bouton « annuaire » du menu de l'en-tête a disparu d'index.html");
  assert(/"contacts":\s*\(\)\s*=>\s*center\.openContacts/.test(boot),
    "RM3146 : la commande « contacts » n'est plus déclarée dans la carte data-cmd de boot.js");
  assert(!/onclick=/.test(htm.slice(htm.indexOf('id="contactsbtn"') - 400,
                                    htm.indexOf('id="contactsbtn"') + 400)),
    "le geste doit passer par data-cmd, pas par un on* en dur (convention du cockpit)");
  // L'entrée contextuelle du panneau Projets reste : on y est déjà dans les clients.
  assert(/data-action="contacts"/.test(
    fs.readFileSync(path.join(DIR, "src/modules/projects/ProjectsPanel.view.js"), "utf8")),
    "RM3146 : le 👤 du panneau Projets doit rester — c'est une entrée contextuelle");
  console.log("✓ accès à l'annuaire (RM3146) : menu de l'en-tête + entrée contextuelle Projets");

  // — 7. RM3147 : l'expéditeur d'un email, reconnu ou non —
  const MVM = await import(path.join(DIR, "src/modules/mail/EmailViewModel.js"));
  const MC = await import(path.join(DIR, "src/modules/mail/EmailCard.view.js"));

  const connu = new MVM.EmailViewModel({
    key: "k1", subject: "Devis", from: "sandrine@calicote.com", from_name: "Sandrine Roche-Pizzo",
    contact: { known: true, ref: "sandrine-roche-pizzo", name: "Sandrine Roche-Pizzo", internal: false },
  }, {});
  assert.equal(connu.known, true);
  assert.equal(connu.sender, "Sandrine Roche-Pizzo", "le nom de l'annuaire prime sur l'adresse");
  assert.equal(connu.contactRef, "sandrine-roche-pizzo");
  assert.equal(connu.internal, false);

  const interne = new MVM.EmailViewModel({
    key: "k2", from: "mathieu@iprospective.fr",
    contact: { known: true, ref: "iprospective", name: "Mathieu Moulin", internal: true },
  }, {});
  assert.equal(interne.internal, true, "la qualité d'interne vient de la personne");

  const inconnu = new MVM.EmailViewModel({
    key: "k3", from: "Yann@Dercya.com", from_name: "Yann Le Vourch",
    contact: { known: false, email: "yann@dercya.com" },
  }, {});
  assert.equal(inconnu.known, false);
  assert.equal(inconnu.sender, "Yann Le Vourch", "à défaut d'annuaire, le nom de l'email");
  const pre = inconnu.newContact;
  // Convention PARTAGÉE avec person_from_legacy (pm_contacts) : dernier mot = nom.
  // Elle découpe mal un nom composé (« Yann Le Vourch » → « Yann Le » / « Vourch »),
  // et c'est assumé : mieux vaut UNE convention imparfaite que deux divergentes.
  // C'est pourquoi la fiche est PROPOSÉE, pas créée — la confirmation montre le
  // découpage, et `pm-contact set` le corrige d'un geste.
  assert.deepEqual(pre, { email: "yann@dercya.com", first_name: "Yann Le", last_name: "Vourch" },
    "la fiche est pré-remplie DEPUIS l'email — adresse normalisée, nom coupé au dernier mot");
  const monoNom = new MVM.EmailViewModel({ from: "x@y.fr", from_name: "Sandrine" }, {}).newContact;
  assert.deepEqual(monoNom, { email: "x@y.fr", first_name: "Sandrine", last_name: "" },
    "un seul mot reste un prénom : on ne devine pas un nom de famille");
  const sansNom = new MVM.EmailViewModel({ from: "x@y.fr" }, {}).newContact;
  assert.equal(sansNom.first_name, "", "aucun nom dans l'email : rien n'est inventé");
  const sansRien = new MVM.EmailViewModel({}, {});
  assert.equal(sansRien.known, false, "un email sans contact résolu ne casse rien");
  assert.equal(sansRien.newContact.email, "", "…et ne propose pas de créer une fiche vide");

  const cConnu = String(MC.EmailCard(connu)), cInconnu = String(MC.EmailCard(inconnu));
  assert(/data-action="contact"/.test(cConnu), "un expéditeur connu ouvre sa fiche");
  assert(!/contact-add/.test(cConnu), "…et ne propose pas de la recréer");
  assert(/data-action="contact-add"/.test(cInconnu), "un inconnu propose « ＋ annuaire »");
  assert(!/data-action="contact"[^-]/.test(cInconnu.replace(/contact-add/g, "")),
    "…et n'ouvre pas une fiche qui n'existe pas");
  assert(/interne/.test(String(MC.EmailCard(interne))), "la pastille interne se voit");
  const xssMail = String(MC.EmailCard(new MVM.EmailViewModel({
    from: "x@y.fr", contact: { known: true, ref: "r", name: "<img src=x>" } }, {})));
  assert(!/<img/.test(xssMail), "le nom venu de l'annuaire est échappé");
  console.log("✓ expéditeur reconnu (RM3147) : nom, pastille interne, création pré-remplie, échappement");

  // Le câblage : les deux gestes existent, et l'écriture passe par le catalogue.
  const mailCtl = fs.readFileSync(path.join(DIR, "src/modules/mail/mail.controller.js"), "utf8");
  assert(/"contact-add":/.test(mailCtl) && /contact:\s*\(key\)/.test(mailCtl),
    "RM3147 : les gestes contact / contact-add doivent être déclarés");
  assert(/ctx\.addContact/.test(mailCtl), "la création est déléguée au contexte, pas faite ici");
  assert(/annuaire-add/.test(boot),
    "RM3147 : la création doit passer par la commande catalogue annuaire-add (pm-contact reste le seul point d'écriture)");
  console.log("✓ câblage (RM3147) : gestes déclarés, écriture par le catalogue");

  // — 8. RM3149 : le demandeur d'un ticket —
  const RVM = await import(path.join(DIR, "src/modules/review/ReviewViewModel.js"));
  // `this.r` est l'entité du ticket, portée par `e.r` (cf. ReviewViewModel).
  const mk = (req) => new RVM.ReviewViewModel({ r: { found: true, title: "T", requester: req } }, { rm: "1" });
  const dConnu = String(mk({ known: true, ref: "iprospective", name: "Mathieu Moulin", internal: true }).requester);
  assert(/data-action="open-contact" data-value="iprospective"/.test(dConnu),
    "un demandeur connu ouvre sa fiche");
  assert(/Mathieu Moulin/.test(dConnu) && /interne/.test(dConnu),
    "…par son nom, avec sa pastille interne");
  const dInconnu = String(mk({ known: false, name: "zoe", email: "zoe@ailleurs.fr" }).requester);
  assert(/zoe/.test(dInconnu), "un demandeur hors annuaire reste lisible");
  assert(!/open-contact/.test(dInconnu), "…et n'ouvre pas une fiche qui n'existe pas");
  assert.strictEqual(mk(null).requester, null, "aucun demandeur : la section reste vide");
  assert.strictEqual(mk({ known: false }).requester, null,
    "un demandeur sans nom ni adresse n'est pas affiché à moitié");
  const dXss = String(mk({ known: true, ref: "r", name: "<img src=x>" }).requester);
  assert(!/<img/.test(dXss), "le nom du demandeur est échappé");
  const sections = mk({ known: true, ref: "r", name: "N" }).sections().map(x => x.id);
  assert(sections.includes("requester"), "la fiche porte une section « demandeur »");
  const revCtl = fs.readFileSync(path.join(DIR, "src/modules/review/review.controller.js"), "utf8");
  assert(/"open-contact":/.test(revCtl), "RM3149 : le geste doit être déclaré dans le panneau ticket");
  console.log("✓ demandeur d'un ticket (RM3149) : connu cliquable, inconnu lisible, échappement");
})().catch(e => { console.error(e && e.message || e); process.exit(1); });
