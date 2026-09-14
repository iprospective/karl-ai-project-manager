#!/usr/bin/env python3
"""Tests RM3145 (lot 0) — le registre des modules.

Ce qui doit tenir : un manifeste se valide plutôt que de se deviner, un manifeste cassé devient un
module EN ERREUR (jamais un module absent — une erreur qu'on ne voit pas est pire qu'un module qui
manque), les dépendances se résolvent avec leurs bornes, un cycle se NOMME, et l'inventaire dit la
vérité sur l'écart entre ce qui est décrit et ce que les registres portent.

Lancer : python3 scripts/test_pm_modules.py
"""
import importlib
import os
import pathlib
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
FAIL = []


def check(label, cond, detail=""):
    print(("  ✓ " if cond else "  ✗ ") + label + ("" if cond else f"  {detail}"))
    if not cond:
        FAIL.append(label)


def frais(d):
    os.environ["PM_MODULES_DIR"] = str(d)
    if "pm_modules" in sys.modules:
        del sys.modules["pm_modules"]
    return importlib.import_module("pm_modules")


def pose(racine, nom, texte):
    d = pathlib.Path(racine) / nom
    d.mkdir(parents=True, exist_ok=True)
    (d / "module.yml").write_text(texte, encoding="utf-8")


with tempfile.TemporaryDirectory() as tmp:
    M = frais(tmp)
    print("[RM3145] un manifeste se valide, il ne se devine pas")
    pose(tmp, "bon", 'name: bon\nversion: 1.2.0\nlabel: "Bon"\ndescription: "fait une chose"\n'
                     'provides:\n  - {kind: provider, axis: task, type: x}\n')
    pose(tmp, "sans-desc", 'name: sans-desc\nversion: 1.0.0\n')
    pose(tmp, "mauvais-nom", 'name: "Pas Un Nom"\nversion: 1.0.0\ndescription: "x"\n')
    pose(tmp, "version-floue", 'name: version-floue\nversion: "1.2"\ndescription: "x"\n')
    pose(tmp, "nature-inconnue", 'name: nature-inconnue\nversion: 1.0.0\ndescription: "x"\n'
                                 'provides:\n  - {kind: soucoupe, name: y}\n')
    pose(tmp, "dep-illisible", 'name: dep-illisible\nversion: 1.0.0\ndescription: "x"\n'
                               'requires: ["core superieur a 3"]\n')
    pose(tmp, "yaml-casse", "name: [non\n  fermé\n")
    pose(tmp, "pas-un-mapping", "- juste\n- une\n- liste\n")
    (pathlib.Path(tmp) / "dossier-sans-manifeste").mkdir()

    # indexé par DOSSIER : c'est l'identité sur le disque, et un manifeste peut mentir sur son nom.
    par_nom = {m.path.parent.name: m for m in M.decouvre()}
    check("un manifeste correct passe", par_nom["bon"].ok)
    check("la description est EXIGÉE — sans elle, on activerait à l'aveugle",
          not par_nom["sans-desc"].ok and any("description" in e for e in par_nom["sans-desc"].errors))
    check("un nom hors convention est refusé", not par_nom["mauvais-nom"].ok)
    pose(tmp, "renomme", 'name: autre-chose\nversion: 1.0.0\ndescription: "x"\n')
    ren = {m.path.parent.name: m for m in M.decouvre()}["renomme"]
    check("un nom qui diffère du dossier est refusé — une seule identité par module",
          not ren.ok and any("dossier" in e for e in ren.errors), str(ren.errors))
    check("une version qui n'est pas X.Y.Z est refusée", not par_nom["version-floue"].ok)
    check("une nature inconnue de « provides » est refusée",
          not par_nom["nature-inconnue"].ok
          and any("soucoupe" in e for e in par_nom["nature-inconnue"].errors))
    check("une dépendance illisible est nommée", not par_nom["dep-illisible"].ok)
    check("un YAML cassé donne un module EN ERREUR, pas un module absent",
          "yaml-casse" in par_nom and not par_nom["yaml-casse"].ok)
    check("un manifeste qui n'est pas un mapping aussi",
          "pas-un-mapping" in par_nom and not par_nom["pas-un-mapping"].ok)
    check("un dossier sans manifeste est ignoré en silence", "dossier-sans-manifeste" not in par_nom)
    check("ce qu'un module fournit se lit sous une forme comparable",
          par_nom["bon"].fournit() == [("provider", "task/x")])

with tempfile.TemporaryDirectory() as tmp:
    M = frais(tmp)
    print("\n[RM3145] les dépendances se résolvent, et un refus DIT pourquoi")
    pose(tmp, "socle", 'name: socle\nversion: 2.0.0\ndescription: "le socle"\nrequires: ["core >= 3.0"]\n')
    pose(tmp, "dessus", 'name: dessus\nversion: 1.0.0\ndescription: "au-dessus"\nrequires: ["socle >= 2.0"]\n')
    pose(tmp, "trop-exigeant", 'name: trop-exigeant\nversion: 1.0.0\ndescription: "x"\nrequires: ["socle >= 9.0"]\n')
    pose(tmp, "orphelin", 'name: orphelin\nversion: 1.0.0\ndescription: "x"\nrequires: ["fantome >= 1.0"]\n')
    pose(tmp, "futur", 'name: futur\nversion: 1.0.0\ndescription: "x"\nrequires: ["core >= 99.0"]\n')
    pose(tmp, "eteint", 'name: eteint\nversion: 1.0.0\ndescription: "x"\nenabled: false\n')
    pose(tmp, "sur-eteint", 'name: sur-eteint\nversion: 1.0.0\ndescription: "x"\nrequires: ["eteint >= 1.0"]\n')

    r = M.resout(M.decouvre(), core_version="3.0.0")
    check("l'ordre met la dépendance AVANT celui qui en dépend",
          r["ordre"].index("socle") < r["ordre"].index("dessus"), str(r["ordre"]))
    check("une version trop basse bloque, avec la borne citée",
          any("9.0" in m for m in r["bloques"].get("trop-exigeant", [])), str(r["bloques"]))
    check("une dépendance absente est NOMMÉE",
          any("fantome" in m for m in r["bloques"].get("orphelin", [])))
    check("le noyau se compare comme une dépendance",
          "futur" in r["bloques"] and any("noyau" in m for m in r["bloques"]["futur"]))
    check("un module désactivé ne se charge pas", "eteint" not in r["ordre"])
    check("…et ce qui en dépend est bloqué, en le disant",
          any("désactivée" in m for m in r["bloques"].get("sur-eteint", [])))
    check("un module bloqué n'empêche pas les autres de se charger", "socle" in r["ordre"])

with tempfile.TemporaryDirectory() as tmp:
    M = frais(tmp)
    print("\n[RM3145] un cycle se nomme — sinon on le cherche longtemps")
    pose(tmp, "poule", 'name: poule\nversion: 1.0.0\ndescription: "x"\nrequires: ["oeuf >= 1.0"]\n')
    pose(tmp, "oeuf", 'name: oeuf\nversion: 1.0.0\ndescription: "x"\nrequires: ["poule >= 1.0"]\n')
    pose(tmp, "libre", 'name: libre\nversion: 1.0.0\ndescription: "x"\n')
    r = M.resout(M.decouvre())
    check("le cycle est détecté", bool(r["cycles"]))
    check("et ses membres sont cités", set(r["cycles"][0]) >= {"poule", "oeuf"}, str(r["cycles"]))
    check("aucun des deux ne se charge — il n'y a pas de « premier »",
          "poule" not in r["ordre"] and "oeuf" not in r["ordre"])
    check("le module libre, lui, se charge", "libre" in r["ordre"])

print("\n[RM3145] comparer des versions, pas des chaînes")
check("1.10 est APRÈS 1.9", M.version_tuple("1.10.0") > M.version_tuple("1.9.0"))
for v, op, b, attendu in (("3.0.0", ">=", "3.0", True), ("2.9.0", ">=", "3.0", False),
                          ("1.0.0", "==", "1.0.0", True), ("1.0.0", "<", "2.0", True),
                          ("1.0.0", None, None, True)):
    check(f"{v} {op or '(sans borne)'} {b or ''}", M.satisfait(v, op, b) is attendu)

print("\n[RM3145] l'inventaire dit la vérité sur l'écart")
os.environ.pop("PM_MODULES_DIR", None)
if "pm_modules" in sys.modules:
    del sys.modules["pm_modules"]
M = importlib.import_module("pm_modules")
inv = M.inventaire()
check("les registres existants sont lus", inv["total"] > 20, str(inv["total"]))
check("l'écart est mesuré", inv["total"] == inv["decrits"] + inv["non_decrits"])
check("les fournisseurs sont inventoriés", "provider" in inv["registres"])
check("les travaux périodiques aussi", "job" in inv["registres"])
mods = M.decouvre()
check("les modules témoins sont décrits et valides", len(mods) >= 5 and all(m.ok for m in mods),
      ", ".join(m.name + ":" + ";".join(m.errors) for m in mods if not m.ok))
r = M.resout(mods)
check("…et se résolvent sans blocage ni cycle", not r["bloques"] and not r["cycles"], str(r))
noms = {m.name for m in mods}
check("une dépendance RÉELLE est décrite (les issues d'une forge ont besoin de son transport)",
      {"forge-gogs", "task-gogs-issues"} <= noms
      and any(d == "forge-gogs" for d, _, _ in next(m for m in mods if m.name == "task-gogs-issues").deps()))
decrits = {n for m in mods for k, n in m.fournit() if k == "provider"}
check("un point d'extension décrit est reconnu comme tel",
      any(x["decrit"] for x in inv["registres"]["provider"]) and "task/gogs_issues" in decrits)

print("\n[RM3145] le verbe existe et ne charge rien")
cli = (HERE / "pm-module.py")
check("pm-module.py est là", cli.is_file())
src = cli.read_text(encoding="utf-8") if cli.is_file() else ""
for verbe in ("list", "show", "check", "inventory"):
    check(f"verbe « {verbe} »", f'"{verbe}"' in src or f"'{verbe}'" in src)
check("il n'importe ni n'exécute le code d'un module",
      "importlib" not in src and "exec(" not in src and "subprocess" not in src)

print("\n" + ("ÉCHEC — " + ", ".join(FAIL) if FAIL else "OK — registre des modules (RM3145 lot 0)"))
sys.exit(1 if FAIL else 0)
