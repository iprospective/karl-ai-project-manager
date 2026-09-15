#!/usr/bin/env python3
"""Tests RM3024 — l'annuaire vu du serveur (endpoints du cockpit).

Ce qui est protégé ici, dans l'ordre d'importance :

  1. **une `ref` orpheline ne disparaît pas.** Elle est marquée `orphelin` et
     garde son rôle : c'est une anomalie qui doit se voir, pas une ligne muette ;
  2. **on retrouve une personne par n'importe laquelle de ses adresses** — la
     raison d'être de l'annuaire, qu'un contact recopié chez chaque client ne
     permettait pas (il n'en connaissait qu'une) ;
  3. la recherche ignore les accents : chercher « carol » doit trouver « Carol »,
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
    "solsona-carol": {"ref": "solsona-carol", "last_name": "Solsona", "first_name": "Carol",
                    "emails": ["bob@clientb.example"], "internal": False},
    "boite": {"ref": "boite", "emails": ["webmaster@clientd.example"], "internal": False},
}

# ── 1. la vue : tri, filtres ─────────────────────────────────────────────────
v = ka.contacts_view(ANN)
check("toutes les personnes sortent", len(v) == 3)
check("les internes d'abord (ce sont les nôtres, on les cherche le plus)",
      v[0]["ref"] == "iprospective")
check("puis l'ordre alphabétique du nom",
      [e["ref"] for e in v[1:]] == ["boite", "solsona-carol"]
      or [e["name"] for e in v[1:]] == sorted(e["name"] for e in v[1:]))
check("une personne sans nom est nommée par son adresse",
      next(e for e in v if e["ref"] == "boite")["name"] == "webmaster@clientd.example")
check("le filtre interne ne garde que les nôtres",
      [e["ref"] for e in ka.contacts_view(ANN, internal_only=True)] == ["iprospective"])

# ── 2. la recherche ──────────────────────────────────────────────────────────
def refs(q):
    return sorted(e["ref"] for e in ka.contacts_view(ANN, q))

check("par nom", refs("solsona") == ["solsona-carol"])
check("par prénom", refs("mathieu") == ["iprospective"])
check("par la PREMIÈRE adresse", refs("mathieu@iprospective.fr") == ["iprospective"])
check("par la SECONDE adresse — tout l'intérêt de l'annuaire",
      refs("contact@iprospective.fr") == ["iprospective"])
check("par le domaine d'une adresse", refs("clientb") == ["solsona-carol"])
check("par la ref elle-même", refs("boite") == ["boite"])
check("par la note", refs("notifications MEP") == ["iprospective"])
check("les accents sont ignorés : « carol » trouve « Carol »", refs("carol") == ["solsona-carol"])
check("…et « carol » aussi", refs("carol") == ["solsona-carol"])
check("la casse est ignorée", refs("SOLSONA") == ["solsona-carol"])
check("une recherche sans résultat ne rend rien", refs("zorglub") == [])
check("annuaire vide toléré", ka.contacts_view({}) == [])
check("une fiche vide ne casse pas le rendu",
      ka.contacts_view({"x": {}})[0]["name"] == "x")

# ── 3. les contacts d'un client, résolus ─────────────────────────────────────
ka._annuaire = lambda: ANN
lignes = [
    {"ref": "solsona-carol", "role": "owner", "title": "PDG"},
    {"name": "Bob Le Vourch", "email": "carol@clientc.example", "role": "technique"},
    {"ref": "disparu", "role": "facturation"},
    "pas un dict",
]
r = ka._resolve_contacts(lignes)
check("les trois lignes exploitables sortent (la 4e, invalide, est écartée)", len(r) == 3)
check("une ref résolue porte l'identité de la personne",
      r[0]["source"] == "annuaire" and r[0]["name"] == "Carol Solsona"
      and r[0]["email"] == "bob@clientb.example")
check("…et le rôle, qui vient du client, pas de la personne",
      r[0]["role"] == "owner" and r[0]["title"] == "PDG")
check("un contact EN LIGNE reste affiché pendant la migration",
      r[1]["source"] == "inline" and r[1]["email"] == "carol@clientc.example")
check("une ref sans fiche est marquée orpheline", r[2]["source"] == "orphelin")
check("…et garde son rôle (il reste vrai)", r[2]["role"] == "facturation")
check("liste vide tolérée", ka._resolve_contacts([]) == [])
check("« interne » vient de la personne, pas de la ligne",
      ka._resolve_contacts([{"ref": "iprospective"}])[0]["internal"] is True)

# ── 4. les endpoints ─────────────────────────────────────────────────────────
check("/contacts rend la liste", len(ka.op_contacts({})["contacts"]) == 3)
check("/contacts?q= filtre", [e["ref"] for e in ka.op_contacts({"q": "carol"})["contacts"]]
      == ["solsona-carol"])
check("/contacts?internal=1 filtre",
      [e["ref"] for e in ka.op_contacts({"internal": "1"})["contacts"]] == ["iprospective"])

ka._contact_links = lambda ref: ([{"client": "clientb", "role": "owner", "title": None}]
                                 if ref == "solsona-carol" else [])
d = ka.op_contact("solsona-carol")
check("/contact/<ref> rend la fiche", d["ref"] == "solsona-carol" and d["name"] == "Carol Solsona")
check("…et ses rattachements", d["links"][0]["client"] == "clientb")
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

# ── 5. RM3147 : reconnaître l'expéditeur d'un email ──────────────────────────
PAR_EMAIL = ka_par_email = {}
for _ref, _p in ANN.items():
    for _e in _p.get("emails") or []:
        PAR_EMAIL.setdefault(_e.lower(), _ref)

c = ka.contact_of_email("mathieu@iprospective.fr", PAR_EMAIL, ANN)
check("un expéditeur connu est reconnu", c["known"] and c["ref"] == "iprospective")
check("…avec son nom, pas son adresse", c["name"] == "Mathieu Moulin")
check("…et sa qualité d'interne", c["internal"] is True)
check("reconnu par sa SECONDE adresse aussi",
      ka.contact_of_email("contact@iprospective.fr", PAR_EMAIL, ANN)["ref"] == "iprospective")
check("la casse de l'adresse est ignorée",
      ka.contact_of_email("Mathieu@IProspective.FR", PAR_EMAIL, ANN)["ref"] == "iprospective")
inc = ka.contact_of_email("qui@inconnu.fr", PAR_EMAIL, ANN)
check("un inconnu rend tout de même une réponse", inc is not None and inc["known"] is False)
check("…qui porte l'adresse, de quoi créer sa fiche", inc["email"] == "qui@inconnu.fr")
check("pas d'adresse du tout ⇒ rien à dire",
      ka.contact_of_email("", PAR_EMAIL, ANN) is None
      and ka.contact_of_email(None, PAR_EMAIL, ANN) is None)
check("une personne sans nom est nommée par son adresse",
      ka.contact_of_email("webmaster@clientd.example", PAR_EMAIL, ANN)["name"] == "webmaster@clientd.example")
check("annuaire vide : tout le monde est inconnu, rien ne casse",
      ka.contact_of_email("mathieu@iprospective.fr", {}, {})["known"] is False)

# Le catalogue expose l'annuaire SANS le doubler : pm-contact reste le seul
# point d'écriture, le cockpit ne fait que l'invoquer.
noms = {c["name"]: c for c in ka._pm_commands() if c.get("category") == "contacts"}
check("le catalogue propose de chercher dans l'annuaire", "annuaire-list" in noms)
check("…et d'y créer une fiche", "annuaire-add" in noms)
check("la création est déclarée mutante", noms["annuaire-add"]["mutate"] is True)
check("la recherche ne l'est pas", noms["annuaire-list"]["mutate"] is False)
check("les deux passent par pm-contact.py, jamais par une écriture directe",
      all(noms[n]["script"] == "pm-contact.py" for n in ("annuaire-list", "annuaire-add")))
check("la sous-commande est imposée par le catalogue, pas par le client",
      all(a.get("const") for n in ("annuaire-list", "annuaire-add")
          for a in noms[n]["args"] if a["name"] == "cmd"))

# ── 6. RM3149 : le demandeur d'un ticket ─────────────────────────────────────
# Le demandeur est le membre `owner` de team[] — `creator` est un nom
# d'utilisateur PM, pas une identité : c'est l'ADRESSE qui rejoint l'annuaire.
def meta_team(*membres, creator="iprospective"):
    return {"creator": creator, "team": list(membres)}

OWNER = {"username": "iprospective", "email": "mathieu@iprospective.fr", "role": "owner"}
AUTRE = {"username": "carol", "email": "bob@clientb.example", "role": "intervenant"}

r = ka.requester_of(meta_team(AUTRE, OWNER), PAR_EMAIL, ANN)
check("le demandeur est le membre « owner », pas le premier venu",
      r["known"] and r["ref"] == "iprospective")
check("…rendu par son nom d'annuaire", r["name"] == "Mathieu Moulin")
check("…avec sa qualité d'interne", r["internal"] is True)
r2 = ka.requester_of(meta_team(AUTRE), PAR_EMAIL, ANN)
check("sans owner, le premier membre fait foi", r2["ref"] == "solsona-carol")
r3 = ka.requester_of(meta_team({"username": "zoe", "email": "zoe@ailleurs.fr"}), PAR_EMAIL, ANN)
check("un demandeur hors annuaire reste LISIBLE, il ne disparaît pas",
      r3["known"] is False and r3["name"] == "zoe")
r4 = ka.requester_of(meta_team({"username": "sanmail"}), PAR_EMAIL, ANN)
check("sans adresse, le nom d'utilisateur suffit à l'afficher",
      r4 and r4["known"] is False and r4["name"] == "sanmail")
r5 = ka.requester_of({"creator": "iprospective", "team": []}, PAR_EMAIL, ANN)
check("team vide : on retombe sur creator", r5 and r5["name"] == "iprospective")
check("…sans prétendre le connaître (creator n'est pas une adresse)",
      r5["known"] is False)
check("ni team ni creator ⇒ rien à dire", ka.requester_of({}, PAR_EMAIL, ANN) is None)
check("une entrée de team mal formée est ignorée sans planter",
      ka.requester_of({"team": ["pas un dict"], "creator": "x"}, PAR_EMAIL, ANN)["name"] == "x")

# Le drapeau : le parseur du parc ne paie pas ce que seul le cockpit demande.
import inspect as _insp
_sig = _insp.signature(ka._read_task_meta)
check("_read_task_meta lit team/creator SUR DEMANDE",
      "with_team" in _sig.parameters and _sig.parameters["with_team"].default is False)
_f = ka._find_task_file("3149")
if _f:
    check("drapeau éteint : le parc ne lit pas team[]",
          ka._read_task_meta(_f)["team"] == [])
    check("drapeau allumé : team[] est lu",
          len(ka._read_task_meta(_f, with_team=True)["team"]) >= 1)

print()
if fails:
    print(f"✗ {len(fails)} échec(s) : " + ", ".join(fails))
    sys.exit(1)
print("== OK ==")
