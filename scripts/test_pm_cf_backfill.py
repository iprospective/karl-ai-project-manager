#!/usr/bin/env python3
"""Tests RM2592/RM2701 — ce que le backfill accepte d'écrire dans « GIT Branche ».

Trois situations qu'il ne faut surtout pas confondre :
  · champ VIDE          → on remplit (c'est l'objet de RM2592) ;
  · champ RENSEIGNÉ     → on ne touche à rien, jamais ;
  · champ GÉNÉRIQUE     → `dev`, écrit par les MR de promotion d'avant RM2701.
                          Ce n'est pas une valeur renseignée, c'est une valeur
                          fausse : on la remplace, mais seulement sur demande
                          explicite (`--repair-generic`).

Lancer : python3 scripts/test_pm_cf_backfill.py
"""
import importlib.util
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("bf", HERE / "pm-cf-git-backfill.py")
bf = importlib.util.module_from_spec(spec)
sys.modules["bf"] = bf
spec.loader.exec_module(bf)

fails = []


def check(name, cond):
    print(("✓ " if cond else "✗ ") + name)
    if not cond:
        fails.append(name)


def issue(branche="", pr=""):
    return {"custom_fields": [{"id": 3, "value": branche}, {"id": 4, "value": pr}]}


INFO = {"branch": "2701-vraie-branche", "pr": "https://forge/mr/1"}


def vals(todo):
    return {c["id"]: c["value"] for c in todo}


# — champ vide : on remplit —
check("un champ vide est rempli",
      vals(bf.to_write(2701, issue(), INFO)).get(3) == "2701-vraie-branche")
check("la PR aussi", vals(bf.to_write(2701, issue(), INFO)).get(4) == "https://forge/mr/1")

# — champ renseigné : intouchable, dans les DEUX modes —
plein = issue("2701-branche-deja-la", "https://forge/mr/9")
check("un champ renseigné n'est pas touché", bf.to_write(2701, plein, INFO) == [])
check("…même en mode réparation", bf.to_write(2701, plein, INFO, repair=True) == [])

# — champ générique : faux, donc remplaçable — mais sur demande seulement —
for gen in ("dev", "main", "master", "preprod"):
    check("« %s » n'est pas touché par défaut" % gen,
          3 not in vals(bf.to_write(2701, issue(gen), INFO)))
    check("« %s » est réparé quand on le demande" % gen,
          vals(bf.to_write(2701, issue(gen), INFO, repair=True)).get(3) == "2701-vraie-branche")

# — on ne remplace jamais par une valeur qui ne vaut pas mieux —
faux = {"branch": "main", "pr": None}
check("un frontmatter à `main` ne remplace pas un `dev` : ce serait un lavage",
      bf.to_write(2701, issue("dev"), faux, repair=True) == [])
check("…ni ne remplit un champ vide",
      bf.to_write(2701, issue(), faux) == [])
autre = {"branch": "2659-branche-d-un-autre", "pr": None}
check("la branche d'un AUTRE ticket est refusée",
      bf.to_write(2701, issue(), autre) == [])

# — le CF absent du tracker ne doit rien déclencher (Redmine le jetterait) —
sans_cf = {"custom_fields": [{"id": 4, "value": ""}]}
check("un tracker sans le CF branche ne produit pas d'écriture de branche",
      3 not in vals(bf.to_write(2701, sans_cf, INFO)))

# — branche_de_ticket : le préfixe doit être exact —
check("préfixe exact exigé",
      bf.branche_de_ticket(2701, "2701-x") and not bf.branche_de_ticket(270, "2701-x")
      and not bf.branche_de_ticket(2701, "2701x"))

if fails:
    print("ÉCHEC :", ", ".join(fails))
    sys.exit(1)
print("OK — tests backfill CF RM2592/RM2701 passent")
