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

print("\nOK — pm-norms-doctor --check est vert (RM2750)")
