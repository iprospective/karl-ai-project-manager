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
})().catch(e => { console.error(e && e.message || e); process.exit(1); });
