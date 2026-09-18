#!/usr/bin/env python3
"""Tests hors ligne du script de MEP par ticket (RM3225) : `pm_mep_script` et ses lecteurs.

Ce qui casserait en silence si on se trompait :
  - le nom du frère (`RM<id>_<slug>.script-mep.sh`) : un cockpit qui cherche ailleurs n'affiche
    rien, et personne ne s'en aperçoit avant la MEP ;
  - la commande de lancement : alias de l'env prod d'abord, sinon celui de l'en-tête, sinon un
    marqueur VISIBLE — jamais une commande qui a l'air juste et vise la mauvaise machine ;
  - le contrat (`lint`) : signalé, jamais bloquant ;
  - la lecture bornée : un script énorme ne gonfle pas chaque ouverture de fiche ;
  - le payload de la fiche (karl-agent) : actions au déploiement + script, et rien quand il n'y
    en a pas ; `pm_think.sheet_of` remonte du script à la fiche.
Aucun réseau, aucun git : tout en répertoire temporaire.
Lancer : python3 scripts/test_pm_mep_script.py
"""
import importlib.util
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from test_support import hermetic_core                 # noqa: E402

hermetic_core()
import pm_mep_script as M                              # noqa: E402
import pm_think                                        # noqa: E402

FAIL = []


def check(label, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + label + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAIL.append(label)


GOOD = """#!/usr/bin/env bash
# MEP RM9001 — exemple
#   ssh cible-prod 'bash -s' < RM9001_x.script-mep.sh
# Rollback : revenir au commit précédent.
set -euo pipefail
[ "${1:-}" = "--apply" ] && echo apply
"""

with tempfile.TemporaryDirectory() as d:
    t = Path(d)
    sheet = t / "RM9001_x.md"
    sheet.write_text("---\nstatus: a_mep\n---\n", encoding="utf-8")

    print("· nom et présence")
    check("frère de la fiche", M.script_path(sheet).name == "RM9001_x.script-mep.sh")
    check("absent → None", M.find(sheet) is None and M.describe(sheet) is None)
    (t / "RM9001_x.script-mep.sh").write_text(GOOD, encoding="utf-8")
    check("présent → trouvé", M.find(sheet) == t / "RM9001_x.script-mep.sh")
    check("sheet_of remonte du script à la fiche",
          pm_think.sheet_of(t / "RM9001_x.script-mep.sh").name == "RM9001_x.md")
    check("le script fait partie des frères", any(p.name.endswith(".script-mep.sh") for p in pm_think.siblings(sheet)))
    check("…mais n'est jamais pris pour une fiche", not pm_think.is_task_sheet(t / "RM9001_x.script-mep.sh"))

    print("· commande de lancement")
    dsc = M.describe(sheet)
    check("alias lu dans l'en-tête", dsc["alias"] == "cible-prod", dsc["alias"])
    check("commande de contrôle", dsc["launch"]["check"] == "ssh cible-prod 'bash -s' < .mmi-pm/tasks/RM9001_x.script-mep.sh", dsc["launch"]["check"])
    check("commande d'exécution", dsc["launch"]["apply"] == "ssh cible-prod 'bash -s -- --apply' < .mmi-pm/tasks/RM9001_x.script-mep.sh")
    check("l'alias de l'env prod prime sur l'en-tête", M.describe(sheet, alias="prod-alias")["alias"] == "prod-alias")
    (t / "RM9001_x.script-mep.sh").write_text(GOOD.replace("ssh cible-prod 'bash -s' <", "lancer <"), encoding="utf-8")
    dsc = M.describe(sheet)
    check("aucun alias connu → marqueur visible, pas une machine devinée",
          dsc["alias"] is None and "<alias-ssh>" in dsc["launch"]["check"])

    print("· contrat")
    check("script conforme : rien à signaler", M.lint(GOOD) == [], M.lint(GOOD))
    manque = M.lint("#!/bin/sh\nrm -rf x\n")
    check("les trois manques sont nommés", len(manque) == 3 and "set -euo pipefail" in manque, manque)
    check("dsc porte le lint", dsc["lint"] == [])

    print("· lecture bornée")
    (t / "RM9001_x.script-mep.sh").write_text(GOOD + "#" * 50000, encoding="utf-8")
    dsc = M.describe(sheet, max_chars=1000)
    check("texte tronqué et signalé", len(dsc["text"]) == 1000 and dsc["truncated"])
    check("lignes comptées sur le fichier entier", dsc["lines"] >= GOOD.count("\n"))

print("· payload de la fiche (karl-agent)")
spec = importlib.util.spec_from_file_location("karl_agent", HERE / "karl-agent.py")
ka = importlib.util.module_from_spec(spec)
sys.modules["karl_agent"] = ka
spec.loader.exec_module(ka)
with tempfile.TemporaryDirectory() as d:
    t = Path(d)
    sheet = t / "RM9002_y.md"
    sheet.write_text("---\n---\n", encoding="utf-8")
    check("sans script : None", ka._ticket_mep_script(sheet, []) is None)
    (t / "RM9002_y.script-mep.sh").write_text(GOOD, encoding="utf-8")
    envs = [{"name": "staging", "url": "", "ssh_alias": "pas-celui-ci"},
            {"name": "prod", "url": "https://x", "ssh_alias": "alias-prod"}]
    got = ka._ticket_mep_script(sheet, envs)
    check("avec script : décrit, alias de l'env PROD", got and got["alias"] == "alias-prod", got and got["alias"])
    proj = t / "proj"; (proj / "project").mkdir(parents=True)
    (proj / "project" / "environments.md").write_text(
        "---\nenvironments:\n- name: prod\n  url: https://x\n  ssh_alias: mon-alias\n- name: dev\n  url: null\nenv_vars: []\n---\n",
        encoding="utf-8")
    envs = ka._read_project_envs(proj)
    check("liste en colonne 0 (YAML valide, forme pisceen) : lue, ssh_alias compris", envs[0].get("ssh_alias") == "mon-alias" and "ssh_alias" not in envs[1], envs)
    (proj / "project" / "environments.md").write_text(
        "---\nenvironments:\n  - name: prod\n    url: https://y   # commentaire\n  - name: dev\n    url: 'http://a#b'\nenv_vars: []\n---\n",
        encoding="utf-8")
    envs = ka._read_project_envs(proj)
    check("liste indentée toujours lue", [e["name"] for e in envs] == ["prod", "dev"], envs)
    check("commentaire de fin de ligne retiré de l'URL", envs[0]["url"] == "https://y", envs[0]["url"])
    check("un # dans une URL entre guillemets est conservé", envs[1]["url"] == "http://a#b", envs[1]["url"])
src = (HERE / "karl-agent.py").read_text(encoding="utf-8")
check("la fiche sert les actions au déploiement", '"deploy_actions": [str(a) for a in (fm.get("deploy_actions")' in src)
check("la fiche sert le script", '"mep_script": _ticket_mep_script(tf, envs)' in src)

print("\n" + ("ÉCHEC : " + ", ".join(FAIL) if FAIL else "tout est vert"))
sys.exit(1 if FAIL else 0)
