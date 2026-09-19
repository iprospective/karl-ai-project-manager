#!/usr/bin/env python3
"""Tests RM3145 lot 1 — activer, éteindre, forcer, créer un module.

Les trois arbitrages du demandeur (2026-09-14) sont vérifiés ici :

  Q001 — un module NATIF s'éteint, il ne se retire pas. Tout ce qui vit sous `modules/` est natif ;
  Q003 — éteindre un module dont d'autres dépendent est REFUSÉ, en disant qui. Le forçage exige une
         confirmation FORTE, ses conséquences se signalent tant qu'elles durent, et les objets du
         module survivent ;
  D005 — transformer une partie du core en module doit être SIMPLE : `squelette()` crée un module
         valide du premier coup.

Et deux choses qui ne se voient pas mais qui comptent :
  * l'état vit dans la configuration de l'INSTANCE — dans le manifeste, éteindre un module
    modifierait le code livré ;
  * `module list` ne plante plus quand un module expose une route (régression du lot 4).

Lancer : python3 scripts/test_pm_modules_activation.py
"""
import os
import pathlib
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
fails = []


def check(name, cond):
    print(("✓ " if cond else "✗ ") + name)
    if not cond:
        fails.append(name)


import pm_modules as M
import yaml


def banc():
    tmp = tempfile.mkdtemp()
    d = pathlib.Path(tmp) / "modules"
    d.mkdir()
    os.environ["PM_MODULES_DIR"] = str(d)
    M.squelette("socle", "Le socle dont un autre dépend")
    M.squelette("dessus", "Un module qui a besoin du socle")
    f = d / "dessus" / "module.yml"
    data = yaml.safe_load(f.read_text()); data["requires"].append("socle")
    f.write_text(yaml.safe_dump(data, sort_keys=False))
    return pathlib.Path(tmp), d


# — D005 : l'outil d'extraction —
tmp, d = banc()
mods = M.decouvre()
check("squelette() crée un module VALIDE du premier coup", all(m.ok for m in mods) and len(mods) == 2)
check("… avec les dossiers standard du contrat", all((d / "socle" / s).is_dir() for s in M.SOUS_DOSSIERS))
check("… et natif par défaut (Q001)", all(m.native for m in mods))
for bad, why in (("Maj", "majuscule"), ("x", "trop court"), ("", "vide")):
    try:
        M.squelette(bad, "desc"); check(f"nom invalide refusé ({why})", False)
    except M.ModuleError:
        check(f"nom invalide refusé ({why})", True)
try:
    M.squelette("sans-desc", "   "); check("un module sans description est refusé", False)
except M.ModuleError:
    check("un module sans description est refusé", True)
try:
    M.squelette("socle", "doublon"); check("on ne recouvre pas un module existant", False)
except M.ModuleError:
    check("on ne recouvre pas un module existant", True)

# — Q003 : refus motivé —
try:
    M.desactiver("socle"); check("éteindre un module dont un autre dépend est REFUSÉ", False)
except M.ModuleError as e:
    check("éteindre un module dont un autre dépend est REFUSÉ", True)
    check("… et le refus NOMME le dépendant", "dessus" in str(e))
check("… rien n'a été écrit après un refus", M.etat_instance() == {})

# — Q003 : forçage —
r = M.desactiver("socle", force=True)
check("le forçage éteint le module", r["etat"] == "eteint" and r["force"])
check("… et dit ce qu'il casse", r["casses"] == ["dessus"])
mods = M.decouvre(); socle = next(m for m in mods if m.name == "socle")
check("l'état « éteint en forçant » est conservé", not socle.enabled and socle.forced)
check("le dépendant est signalé bloqué tant que ça dure",
      "dessus" in M.resout(mods)["bloques"])

# — l'état vit dans la config de l'INSTANCE —
check("l'état est écrit dans pm.config.local.yml", (tmp / "pm.config.local.yml").is_file())
check("… et JAMAIS dans le manifeste versionné",
      "enabled" not in (d / "socle" / "module.yml").read_text())

# — les objets survivent : éteindre ne supprime rien —
(d / "socle" / "services" / "donnee.txt").write_text("produit par le module")
M.desactiver("dessus"); M.desactiver("socle")
check("éteindre ne supprime rien de ce que le module contient",
      (d / "socle" / "services" / "donnee.txt").read_text() == "produit par le module")

# — activation —
try:
    M.activer("dessus"); check("allumer un module dont la dépendance est éteinte est REFUSÉ", False)
except M.ModuleError as e:
    check("allumer un module dont la dépendance est éteinte est REFUSÉ", "socle" in str(e))
M.activer("socle"); M.activer("dessus")
mods = M.decouvre()
check("rallumés dans l'ordre, tous deux actifs", all(m.enabled for m in mods))
check("un module rallumé n'est plus « forcé »", not any(m.forced for m in mods))
check("éteindre un module déjà éteint n'est pas une erreur",
      (M.desactiver("dessus"), M.desactiver("dessus"))[1]["etat"] == "deja-eteint")
try:
    M.activer("inconnu"); check("un module inconnu est refusé", False)
except M.ModuleError as e:
    check("un module inconnu est refusé, en listant les connus", "socle" in str(e))

# — la ligne de commande : confirmation forte —
env = dict(os.environ)
def cli(*a):
    return subprocess.run([sys.executable, str(HERE / "pm-module.py"), *a], capture_output=True, text=True, env=env)
M.activer("dessus")
r1 = cli("disable", "socle", "--force")
check("--force SANS confirmation est refusé", r1.returncode != 0 and "--confirm socle" in r1.stderr)
r2 = cli("disable", "socle", "--force", "--confirm", "mauvais")
check("--force avec une MAUVAISE confirmation est refusé", r2.returncode != 0)
r3 = cli("disable", "socle", "--force", "--confirm", "socle")
check("--force --confirm <le nom> passe", r3.returncode == 0 and "FORÇANT" in r3.stdout)

# — régression du lot 4 : `list` ne plante plus sur un module qui expose une route —
(d / "socle" / "routes" / "etat.yml").write_text("method: GET\npath: etat\nrun: [\"true\"]\n")
r4 = cli("list")
check("`module list` va jusqu'au bout même quand un module expose une route",
      r4.returncode == 0 and "Traceback" not in r4.stderr and "dessus" in r4.stdout)

del os.environ["PM_MODULES_DIR"]
print(("ÉCHEC : " + "; ".join(fails)) if fails else "OK — activation des modules (RM3145 lot 1)")
sys.exit(1 if fails else 0)
