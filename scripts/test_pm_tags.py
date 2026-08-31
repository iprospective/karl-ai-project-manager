#!/usr/bin/env python3
"""Tests RM2829 — étiquettes de ticket (pm_tags).

Ce qui compte : une étiquette écrite de trois façons est UNE étiquette, l'ordre
est stable (sinon chaque écriture produit un diff vide de sens), et l'absence du
CF Redmine ne casse rien (il se crée à la main, l'API ne le permet pas).
"""
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import pm_tags

fails = []


def check(name, cond, detail=""):
    print(("✓ " if cond else "✗ ") + name + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(name)


# — normalisation : le piège des trois écritures —
check("accents et casse : une seule étiquette",
      pm_tags.normalize("Tunnel de Commande") == "tunnel-de-commande"
      and pm_tags.normalize("TUNNEL_DE_COMMANDE") == "tunnel-de-commande"
      and pm_tags.normalize("  tunnel  de commande  ") == "tunnel-de-commande",
      pm_tags.normalize("TUNNEL_DE_COMMANDE"))
check("accents français réduits", pm_tags.normalize("Référencement") == "referencement")
check("ponctuation en bordure retirée", pm_tags.normalize("--front--") == "front")
check("étiquette vide → vide", pm_tags.normalize("  ---  ") == "")
check("longueur bornée, sans tiret orphelin",
      len(pm_tags.normalize("a" * 60)) == pm_tags.MAX_LEN
      and not pm_tags.normalize("x" * 39 + " suite").endswith("-"))

# — liste : dédoublonnage, tri stable, plafond —
check("dédoublonnage sur la forme normalisée",
      pm_tags.clean(["Front", "front", "FRONT"]) == ["front"])
check("ordre stable (deux saisies, un seul frontmatter)",
      pm_tags.clean(["refacto", "bo", "front"]) == pm_tags.clean(["front", "refacto", "bo"])
      == ["bo", "front", "refacto"])
check("plafond appliqué", len(pm_tags.clean([f"t{i}" for i in range(30)])) == pm_tags.MAX_TAGS)
check("csv : virgule ou point-virgule",
      pm_tags.parse_csv("front, bo ; refacto") == ["bo", "front", "refacto"])
check("csv vide → liste vide", pm_tags.parse_csv("") == [] and pm_tags.parse_csv(None) == [])

# — gestes —
check("ajout sans doublon",
      pm_tags.apply_change(["front"], add=["BO", "front"]) == ["bo", "front"])
check("retrait insensible à la forme",
      pm_tags.apply_change(["front", "bo"], remove=["FRONT"]) == ["bo"])
check("retrait de la dernière étiquette possible",
      pm_tags.apply_change(["front"], remove=["front"]) == [])
check("replace prime sur add/remove",
      pm_tags.apply_change(["front"], add=["bdd"], remove=["front"], replace=["livraison"])
      == ["livraison"])
check("replace vide = tout retirer", pm_tags.apply_change(["front"], replace=[]) == [])
check("aucun geste = liste normalisée, pas de perte",
      pm_tags.apply_change(["Front", "bo"]) == ["bo", "front"])

# — RM2829 (reprise) : le CF livré est en format ENUMERATION —
# L'API veut l'id de chaque valeur, pas son libellé : un push de labels est
# refusé (422). Le registre porte la table slug ↔ label ↔ id.
reg = pm_tags.load_registry()
if reg:
    check("registre chargé (tags.registry.yml)", "front" in reg and reg["front"]["id"].isdigit(), reg)
    p32 = pm_tags.cf_payload(["Front", "refacto"])
    check("payload = ids d'énumération, pas des libellés",
          p32 and all(str(v).isdigit() for v in p32["value"]), p32)
    check("étiquette hors registre écartée du push (elle ferait échouer TOUT le PUT)",
          pm_tags.cf_payload(["front", "cockpit-inconnu"])["value"] == [reg["front"]["id"]])
    check("split_known sépare ce qui peut monter de ce qui reste local",
          pm_tags.split_known(["front", "zzz-inconnu"]) == (["front"], ["zzz-inconnu"]))
    check("lecture : les ids reviennent en slugs",
          pm_tags.from_issue({"custom_fields": [{"id": pm_tags.cf_id(),
                                                 "value": [reg["front"]["id"]]}]}) == ["front"])
    check("vider reste exprimable (liste vide, pas chaîne vide)",
          pm_tags.cf_payload([])["value"] == [])
else:
    print("… registre absent : partie enumeration non jouée")

# — CF absent : rien ne casse (il se crée à la main) —
os.environ.pop(pm_tags.ENV_VAR, None)
if pm_tags.cf_id() is None:
    check("CF non configuré → pas de payload (miroir frontmatter seul)",
          pm_tags.cf_payload(["front"]) is None)
    check("CF non configuré → lecture par NOM du champ",
          pm_tags.from_issue({"custom_fields": [{"name": pm_tags.CF_NAME, "value": ["Front", "bo"]}]})
          == ["bo", "front"])
else:
    check("CF déjà configuré : payload construit", pm_tags.cf_payload(["front"]) is not None)

# — CF configuré par .env —
os.environ[pm_tags.ENV_VAR] = "99"
check("override .env pris en compte", pm_tags.cf_id() == 99)
p = pm_tags.cf_payload(["Front", "front", "BO"])
# Le CF réel est en ENUMERATION : la valeur est une liste d'ids, dans l'ordre des
# slugs (dédoublonnés, triés). Sans registre, ce seraient les slugs eux-mêmes.
attendu = ([reg[t]["id"] for t in ("bo", "front")] if reg else ["bo", "front"])
check("payload : id du CF + LISTE de valeurs (ids si registre)",
      p == {"id": 99, "value": attendu}, p)
check("payload vide = liste vide (Redmine refuse \"\" sur un CF multiple)",
      pm_tags.cf_payload([]) == {"id": 99, "value": []})
check("lecture d'une issue : valeur en liste",
      pm_tags.from_issue({"custom_fields": [{"id": 99, "value": ["BO", "front", "bo"]}]})
      == ["bo", "front"])
check("lecture d'une issue : valeur en chaîne (case « multiple » non cochée)",
      pm_tags.from_issue({"custom_fields": [{"id": 99, "value": "front,bo"}]}) == ["bo", "front"])
check("issue sans le CF → aucune étiquette (pas d'exception)",
      pm_tags.from_issue({"custom_fields": [{"id": 3, "value": "x"}]}) == []
      and pm_tags.from_issue({}) == [] and pm_tags.from_issue(None) == [])
os.environ.pop(pm_tags.ENV_VAR, None)

if fails:
    print("ÉCHEC :", ", ".join(fails))
    sys.exit(1)
print("OK — tests étiquettes (RM2829) passent")
