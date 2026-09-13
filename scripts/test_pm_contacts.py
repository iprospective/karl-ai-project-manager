#!/usr/bin/env python3
"""Tests RM2703 — l'annuaire de contacts.

Ce qui est protégé ici, dans l'ordre d'importance :

  1. **le dédoublonnage ne fusionne jamais deux personnes réelles.** La clé est
     l'adresse ; deux homonymes sans adresse commune restent deux fiches. Une
     migration qui se trompe ici fait disparaître quelqu'un ;
  2. **la fusion ne perd rien** : les adresses et téléphones s'unissent (une
     personne en a plusieurs, c'est le fait à représenter, pas un conflit), et
     `internal` est un OU — être des nôtres chez un seul client suffit ;
  3. **les deux formes cohabitent** pendant la migration : un `contacts[]` peut
     porter des `ref` et des contacts en ligne, et les deux doivent s'afficher.
     Une `ref` dont la fiche a disparu ne se tait pas — elle se signale, et le
     rôle qu'elle porte reste vrai ;
  4. la clé est **lisible et stable** : `nom-prenom`, repli sur l'adresse pour
     une boîte fonctionnelle, suffixe en cas d'homonymie.

Lancer : python3 scripts/test_pm_contacts.py
"""
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pm_contacts as pc                                   # noqa: E402

fails = []


def check(name, cond):
    print(("✓ " if cond else "✗ ") + name)
    if not cond:
        fails.append(name)


# ── 1. la clé ────────────────────────────────────────────────────────────────
check("nom + prénom → slug lisible", pc.slugify_person("Moulin", "Mathieu") == "moulin-mathieu")
check("les accents et la casse tombent",
      pc.slugify_person("MOULIN", "Mathïeu") == "moulin-mathieu")
check("un nom composé reste lisible",
      pc.slugify_person("Roche-Pizzo", "Sandrine") == "roche-pizzo-sandrine")
check("homonyme ⇒ suffixe, jamais d'écrasement",
      pc.slugify_person("Moulin", "Mathieu", {"moulin-mathieu"}) == "moulin-mathieu-2")
check("…et le suffixe grimpe",
      pc.slugify_person("Moulin", "Mathieu",
                        {"moulin-mathieu", "moulin-mathieu-2"}) == "moulin-mathieu-3")
check("sans nom, la boîte fonctionnelle prend son adresse",
      pc.slugify_person(None, None, email="webmaster@matnat.fr") == "webmaster-matnat")
check("sans rien, une clé terne plutôt qu'un plantage",
      pc.slugify_person(None, None) == "contact")
check("prénom seul accepté", pc.slugify_person(None, "Lyse") == "lyse")

# ── 2. l'ancienne forme ──────────────────────────────────────────────────────
p = pc.person_from_legacy({"name": "Mathieu Moulin", "email": "Mathieu@iProspective.FR",
                           "phone": "+33 6 00", "role": "owner"})
check("`name` est coupé au dernier mot (nom en dernier)",
      p["last_name"] == "Moulin" and p["first_name"] == "Mathieu")
check("l'adresse est normalisée", p["emails"] == ["mathieu@iprospective.fr"])
check("une adresse maison pose `internal` toute seule", p["internal"] is True)
check("le rôle n'entre PAS dans l'identité (il est dans la relation)", "role" not in p)
p2 = pc.person_from_legacy({"last_name": "Solsona", "first_name": "Noé",
                            "email": "noe@calyclay.com"})
check("la forme structurée est prise telle quelle",
      p2["last_name"] == "Solsona" and p2["internal"] is False)
check("un contact vide ne casse rien", pc.person_from_legacy({})["emails"] == [])

# ── 3. la fusion ne perd rien ────────────────────────────────────────────────
a = {"last_name": "MOULIN", "first_name": "Mathieu",
     "emails": ["mathieu@iprospective.fr"], "phones": ["+33 6 00"], "internal": False}
b = {"last_name": "Moulin", "first_name": "Mathieu",
     "emails": ["MATHIEU@iprospective.fr", "perso@gmail.com"], "phones": [], "internal": True}
m = pc.merge_person(a, b)
check("l'orthographe criée cède à la normale", m["last_name"] == "Moulin")
check("les adresses s'unissent sans doublon de casse",
      m["emails"] == ["mathieu@iprospective.fr", "perso@gmail.com"])
check("le téléphone connu d'un seul côté survit", m["phones"] == ["+33 6 00"])
check("`internal` est un OU", m["internal"] is True)
check("fusionner avec du vide ne détruit rien",
      pc.merge_person(a, {})["emails"] == ["mathieu@iprospective.fr"])
m2 = pc.merge_person({"last_name": "Dupont"}, {"last_name": "Dupont-Durand"})
check("à casse égale, la forme la plus informative gagne",
      m2["last_name"] == "Dupont-Durand")

# ── 4. l'index par adresse : trouver par N'IMPORTE laquelle ──────────────────
ann = {"moulin-mathieu": {"ref": "moulin-mathieu", "last_name": "Moulin",
                          "first_name": "Mathieu", "internal": True,
                          "emails": ["mathieu@iprospective.fr", "perso@gmail.com"],
                          "phones": ["+33 6 00"]},
       "solsona-noe": {"ref": "solsona-noe", "last_name": "Solsona", "first_name": "Noé",
                       "emails": ["noe@calyclay.com"], "phones": []}}
idx = pc.index_by_email(ann)
check("la première adresse trouve la personne", idx["mathieu@iprospective.fr"] == "moulin-mathieu")
check("la seconde aussi — c'est tout l'intérêt", idx["perso@gmail.com"] == "moulin-mathieu")
check("une adresse inconnue ne rend rien", "x@y.fr" not in idx)

# ── 4 bis. « des nôtres » est un fait de personne (RM3024) ───────────────────
# Le routage s'en sert : une adresse maison ne doit jamais servir d'indice de
# client (le gabarit en pose une chez CHACUN), et la boîte hors domaine d'un
# interne doit compter comme nôtre sans qu'on ait à l'inscrire quelque part.
ANN_I = {"moi": {"internal": True,
                 "emails": ["Mathieu@iProspective.FR", "perso@gmail.com"]},
         "lui": {"internal": False, "emails": ["noe@calyclay.com"]},
         "vide": {"internal": True}}
ia = pc.internal_addresses(ANN_I)
check("les adresses d'un interne sont retenues", "mathieu@iprospective.fr" in ia)
check("…y compris hors domaine — c'est l'apport de l'annuaire",
      "perso@gmail.com" in ia)
check("elles sont normalisées (casse)", "Mathieu@iProspective.FR" not in ia)
check("celles d'un externe ne le sont pas", "noe@calyclay.com" not in ia)
check("une fiche interne sans adresse ne casse rien", len(ia) == 2)
check("annuaire vide ⇒ ensemble vide", pc.internal_addresses({}) == set())
check("des ADRESSES, jamais des domaines : rien ne ressemble à un domaine nu",
      all("@" in a for a in ia))

# ── 5. les deux formes cohabitent ────────────────────────────────────────────
r = pc.resolve_link({"ref": "solsona-noe", "role": "owner", "title": "PDG"}, ann)
check("un rattachement rend l'identité de l'annuaire", r["source"] == "annuaire")
check("…avec le rôle, qui vient du client", r["role"] == "owner" and r["title"] == "PDG")
check("…et les adresses de la fiche", r["emails"] == ["noe@calyclay.com"])
r2 = pc.resolve_link({"name": "Yann Le Vourch", "email": "yann@dercya.com",
                      "role": "technique"}, ann)
check("un contact EN LIGNE reste lisible pendant la migration",
      r2["source"] == "inline" and r2["last_name"] == "Vourch")
r3 = pc.resolve_link({"ref": "disparu", "role": "facturation"}, ann)
check("une ref sans fiche est signalée, pas tue", r3["source"] == "orphelin")
check("…et le rôle qu'elle porte reste vrai", r3["role"] == "facturation")
check("un rattachement vide ne casse rien", pc.resolve_link({}, ann)["source"] == "inline")

# ── 6. le libellé n'est jamais vide ──────────────────────────────────────────
check("nom + prénom", pc.display_name(ann["moulin-mathieu"]) == "Mathieu Moulin")
check("à défaut, l'adresse",
      pc.display_name({"emails": ["w@m.fr"], "ref": "w-m"}) == "w@m.fr")
check("à défaut, la ref", pc.display_name({"ref": "x"}) == "x")
check("et jamais rien", pc.display_name({}) == "?")

# ── 7. la garde qui évite le pire ────────────────────────────────────────────
check("deux homonymes SANS adresse commune restent deux personnes",
      pc.slugify_person("Martin", "Jean") != pc.slugify_person("Martin", "Jean",
                                                              {"martin-jean"}))
check("une adresse maison ne dit rien du client (RM2669)",
      pc.is_internal_email("mathieu@iprospective.fr")
      and not pc.is_internal_email("noe@calyclay.com"))

print()
if fails:
    print(f"✗ {len(fails)} échec(s) : " + ", ".join(fails))
    sys.exit(1)
print("== OK ==")
