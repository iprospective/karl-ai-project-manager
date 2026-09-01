#!/usr/bin/env python3
"""Tests RM2750 — `pm-norms-doctor --check` doit sortir en succès.

Le doctor est le seul garde-fou contre la perte silencieuse d'une règle NORMS.
Il est resté ROUGE sur `dev` du jalon v2.0.0 (RM2438) jusqu'à RM2750 : deux
lignes de l'oracle réécrites sans entrée au registre. Personne ne l'a vu, parce
que rien ne le lançait — un contrôle qu'aucun test n'exécute finit par crier en
permanence, et un contrôle qui crie en permanence n'est plus lu.

Ce test le lance. C'est tout, et c'est le point : il transforme « le doctor est
vert aujourd'hui » en « le doctor reste vert ».

Le doctor est hermétique (il ne lit que `norms/`, pas de `.env`, pas de réseau) :
ce test ne dépend donc PAS de l'environnement d'exécution — cf. RM2749.

Lancer : python3 scripts/test_norms_doctor.py
"""
import importlib.util
import os
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
DOCTOR = HERE / "pm-norms-doctor.py"

# Environnement volontairement NEUTRE : le doctor ne doit rien exiger du poste.
# Si un jour il se met à dépendre d'un `.env`, ce test le dira ici, pas trois
# tickets plus loin.
env = {k: v for k, v in os.environ.items() if k != "PM_CORE_DIR"}
r = subprocess.run([sys.executable, str(DOCTOR), "--check"],
                   capture_output=True, text=True, env=env)
out = (r.stdout or "") + (r.stderr or "")
print(out.rstrip())

if r.returncode != 0:
    print("\nÉCHEC : pm-norms-doctor --check sort en erreur.")
    print("Chaque ✗ ci-dessus se répare à sa source :")
    print("  · non-perte    → la ligne de l'oracle a été réécrite ou supprimée :")
    print("                   l'inscrire dans norms/src/dedup-ledger.yml AVEC son motif")
    print("                   (`rewritten` + `old`, ou `removed`) — jamais éditer l'oracle.")
    print("  · fraîcheur    → `python3 scripts/pm-norms-assemble.py build`")
    print("                   (ne JAMAIS éditer norms/NORMS.md ni norms/VERSION à la main)")
    print("  · manifest     → une source listée manque, ou un module n'est pas listé")
    print("  · fences       → un bloc de code non refermé dans une source")
    sys.exit(1)

# ── RM2751 : ce que le contrôle « outils cités » doit ET ne doit PAS voir ──
# Le doctor était vert au sens du code de retour, mais crachait à chaque
# exécution « outils cités INTROUVABLES : mmi-pm-client, mmi-pm-core ». Faux
# positifs : ce sont les SYMLINKS d'ancrage `.mmi-pm-core` / `.mmi-pm-client`,
# pas des skills. Le risque n'est pas le bruit en soi, c'est qu'un VRAI trou
# d'outillage s'y confonde — donc on verrouille les deux sens.
_spec = importlib.util.spec_from_file_location("nd", DOCTOR)
nd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(nd)

_fails = []


def _check(name, cond):
    print(("✓ " if cond else "✗ ") + name)
    if not cond:
        _fails.append(name)


_ancres = "le lien `.mmi-pm-core` et son pendant `.mmi-pm-client` à la racine"
_check("les symlinks d'ancrage ne sont pas pris pour des skills",
       nd.SKILL_RE.findall(_ancres) == [])
_check("… même collés à un chemin",
       nd.SKILL_RE.findall("/zfs/workspaces/.mmi-pm-core/scripts/x.py") == [])

_vrais = "lance `mmi-pm-take` puis mmi-pm-task-list, cf. mmi-pm-client-new."
_check("un skill réellement cité est toujours détecté",
       set(nd.SKILL_RE.findall(_vrais)) == {"mmi-pm-take", "mmi-pm-task-list",
                                            "mmi-pm-client-new"})
_check("… y compris en début de phrase après un point",
       nd.SKILL_RE.findall("Fini. mmi-pm-deliver ensuite.") == ["mmi-pm-deliver"])

# le garde-fou de fond : un skill cité mais ABSENT de skills/ doit rester signalé.
_check("un skill inexistant est toujours déclaré introuvable",
       not nd.tool_exists("mmi-pm-skill-qui-n-existe-pas"))
_check("… et un skill existant ne l'est pas",
       nd.tool_exists("mmi-pm-task-list"))

# et sur les sources RÉELLES : plus aucun avertissement d'outillage.
_gaps = sorted(t for t in nd.scan_tools()
               if not nd.tool_exists(t) and t not in nd.KNOWN_GAPS)
_check(f"aucun outil cité introuvable dans les NORMS ({_gaps or 'aucun'})", not _gaps)

if _fails:
    print("\nÉCHEC (RM2751) :", ", ".join(_fails))
    sys.exit(1)

print("\nOK — pm-norms-doctor --check est vert (RM2750) et sans faux positif (RM2751)")
