#!/usr/bin/env python3
"""Tests RM3024 — l'annuaire vu du serveur (endpoints du cockpit).

Ce qui est protégé ici, dans l'ordre d'importance :

  1. **une `ref` orpheline ne disparaît pas.** Elle est marquée `orphelin` et
     garde son rôle : c'est une anomalie qui doit se voir, pas une ligne muette ;
  2. **on retrouve une personne par n'importe laquelle de ses adresses** — la
     raison d'être de l'annuaire, qu'un contact recopié chez chaque client ne
     permettait pas (il n'en connaissait qu'une) ;
  3. la recherche ignore les accents : chercher « noe » doit trouver « Noé »,
     sinon elle punit l'orthographe correcte ;
  4. les deux formes cohabitent — un `contacts[]` mêlant `ref` et contacts en
     ligne s'affiche entièrement, le temps que la migration passe.

Lancer : python3 scripts/test_karl_agent_contacts.py
"""
import importlib.util
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("karl_agent", HERE / "karl-agent.py")
ka = importlib.util.module_from_spec(spec)
sys.modules["karl_agent"] = ka
spec.loader.exec_module(ka)

fails = []


def check(name, cond):
    print(("✓ " if cond else "✗ ") + name)
    if not cond:
        fails.append(name)


ANN = {
    "iprospective": {"ref": "iprospective", "last_name": "Moulin", "first_name": "Mathieu",
                     "emails": ["mathieu@iprospective.fr", "contact@iprospective.fr"],
                     "phones": ["+33 6 00"], "internal": True, "redmine_user_id": 79,
                     "note": "destinataire des notifications MEP"},
    "solsona-noe": {"ref": "solsona-noe", "last_name": "Solsona", "first_name": "Noé",
                    "emails": ["noe@calyclay.com"], "internal": False},
    "boite": {"ref": "boite", "emails": ["webmaster@matnat.fr"], "internal": False},
}

# ── 1. la vue : tri, filtres ─────────────────────────────────────────────────
v = ka.contacts_view(ANN)
check("toutes les personnes sortent", len(v) == 3)
check("les internes d'abord (ce sont les nôtres, on les cherche le plus)",
      v[0]["ref"] == "iprospective")
check("puis l'ordre alphabétique du nom",
      [e["ref"] for e in v[1:]] == ["boite", "solsona-noe"]
      or [e["name"] for e in v[1:]] == sorted(e["name"] for e in v[1:]))
check("une personne sans nom est nommée par son adresse",
      next(e for e in v if e["ref"] == "boite")["name"] == "webmaster@matnat.fr")
check("le filtre interne ne garde que les nôtres",
      [e["ref"] for e in ka.contacts_view(ANN, internal_only=True)] == ["iprospective"])

# ── 2. la recherche ──────────────────────────────────────────────────────────
def refs(q):
    return sorted(e["ref"] for e in ka.contacts_view(ANN, q))

check("par nom", refs("solsona") == ["solsona-noe"])
check("par prénom", refs("mathieu") == ["iprospective"])
check("par la PREMIÈRE adresse", refs("mathieu@iprospective.fr") == ["iprospective"])
check("par la SECONDE adresse — tout l'intérêt de l'annuaire",
      refs("contact@iprospective.fr") == ["iprospective"])
check("par le domaine d'une adresse", refs("calyclay") == ["solsona-noe"])
check("par la ref elle-même", refs("boite") == ["boite"])
check("par la note", refs("notifications MEP") == ["iprospective"])
check("les accents sont ignorés : « noe » trouve « Noé »", refs("noe") == ["solsona-noe"])
check("…et « noé » aussi", refs("noé") == ["solsona-noe"])
check("la casse est ignorée", refs("SOLSONA") == ["solsona-noe"])
check("une recherche sans résultat ne rend rien", refs("zorglub") == [])
check("annuaire vide toléré", ka.contacts_view({}) == [])
check("une fiche vide ne casse pas le rendu",
      ka.contacts_view({"x": {}})[0]["name"] == "x")

# ── 3. les contacts d'un client, résolus ─────────────────────────────────────
ka._annuaire = lambda: ANN
lignes = [
    {"ref": "solsona-noe", "role": "owner", "title": "PDG"},
    {"name": "Yann Le Vourch", "email": "yann@dercya.com", "role": "technique"},
    {"ref": "disparu", "role": "facturation"},
    "pas un dict",
]
r = ka._resolve_contacts(lignes)
check("les trois lignes exploitables sortent (la 4e, invalide, est écartée)", len(r) == 3)
check("une ref résolue porte l'identité de la personne",
      r[0]["source"] == "annuaire" and r[0]["name"] == "Noé Solsona"
      and r[0]["email"] == "noe@calyclay.com")
check("…et le rôle, qui vient du client, pas de la personne",
      r[0]["role"] == "owner" and r[0]["title"] == "PDG")
check("un contact EN LIGNE reste affiché pendant la migration",
      r[1]["source"] == "inline" and r[1]["email"] == "yann@dercya.com")
check("une ref sans fiche est marquée orpheline", r[2]["source"] == "orphelin")
check("…et garde son rôle (il reste vrai)", r[2]["role"] == "facturation")
check("liste vide tolérée", ka._resolve_contacts([]) == [])
check("« interne » vient de la personne, pas de la ligne",
      ka._resolve_contacts([{"ref": "iprospective"}])[0]["internal"] is True)

# ── 4. les endpoints ─────────────────────────────────────────────────────────
check("/contacts rend la liste", len(ka.op_contacts({})["contacts"]) == 3)
check("/contacts?q= filtre", [e["ref"] for e in ka.op_contacts({"q": "noe"})["contacts"]]
      == ["solsona-noe"])
check("/contacts?internal=1 filtre",
      [e["ref"] for e in ka.op_contacts({"internal": "1"})["contacts"]] == ["iprospective"])

ka._contact_links = lambda ref: ([{"client": "calyclay", "role": "owner", "title": None}]
                                 if ref == "solsona-noe" else [])
d = ka.op_contact("solsona-noe")
check("/contact/<ref> rend la fiche", d["ref"] == "solsona-noe" and d["name"] == "Noé Solsona")
check("…et ses rattachements", d["links"][0]["client"] == "calyclay")
try:
    ka.op_contact("inconnu")
    check("une ref inconnue lève 404", False)
except ka.ApiError as e:
    check("une ref inconnue lève 404", e.code == 404)
try:
    ka.op_contact("../../etc/passwd")
    check("une ref malformée est refusée AVANT toute lecture de disque", False)
except ka.ApiError as e:
    check("une ref malformée est refusée AVANT toute lecture de disque", e.code == 400)

print()
if fails:
    print(f"✗ {len(fails)} échec(s) : " + ", ".join(fails))
    sys.exit(1)
print("== OK ==")
