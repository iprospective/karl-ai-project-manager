#!/usr/bin/env python3
"""Tests RM3242 — renommer le titre d'un ticket.

Ce que ces tests protègent :

  * **un titre refusé l'est avant toute écriture** : vide, multi-ligne (collage
    raté d'une description) ou au-delà des 255 caractères que Redmine accepte ;
  * **l'ancien titre survit** dans la note Redmine et le journal — c'est sous ce nom
    qu'on cherchera encore le ticket ;
  * **Redmine est relu après le PUT** : il répond 204 même quand il ignore `subject`
    faute de permission ;
  * **les fichiers ne sont pas renommés** (le slug est référencé ailleurs) ;
  * **le verrou et la relecture sont bien là**.

Lancer : python3 scripts/test_pm_task_rename.py
"""
import importlib.util
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
fails = []


def check(name, cond):
    print(("✓ " if cond else "✗ ") + name)
    if not cond:
        fails.append(name)


spec = importlib.util.spec_from_file_location("ren", HERE / "pm-task-rename.py")
R = importlib.util.module_from_spec(spec)
spec.loader.exec_module(R)


def refuse(t):
    try:
        R.normalize_title(t)
        return False
    except ValueError:
        return True


# — normalisation —
check("espaces multiples et de bord réduits",
      R.normalize_title("  Index  /data :   liens  ") == "Index /data : liens")
check("titre vide refusé", refuse("") and refuse("   "))
check("titre absent refusé", refuse(None))
check("saut de ligne refusé (collage raté), pas corrigé en silence", refuse("titre\nsuite"))
check("retour chariot refusé", refuse("titre\rsuite"))
check("255 caractères acceptés", R.normalize_title("x" * 255) == "x" * 255)
check("256 caractères refusés (limite Redmine)", refuse("x" * 256))
check("accents conservés", R.normalize_title("Créer l'index des données") == "Créer l'index des données")

# — note Redmine et journal : l'ancien titre survit —
n = R.redmine_note("Déplacer les données", "Indexer les données", "plus de déplacement")
check("la note porte l'ancien titre en entier", "« Déplacer les données »" in n)
check("la note porte le nouveau titre", "« Indexer les données »" in n)
check("la note porte le motif", "Motif : plus de déplacement" in n)
check("pas de ligne Motif sans motif", "Motif" not in R.redmine_note("a", "b"))
L = R.log_entry("A", "B", "m", "claude", "2026-09-19T10:00")
check("entrée de journal au format imposé",
      L.startswith("\n## 2026-09-19T10:00 — Titre renommé (pm-task-rename)\nTokens : 0 | Durée : 0 min"))
check("le journal garde l'ancien titre", "- avant : « A »" in L and "- après : « B »" in L)

# — protocole —
src = (HERE / "pm-task-rename.py").read_text(encoding="utf-8")
check("verrou par ticket pris", "ticket_lock(" in src)
check("relecture du frontmatter SOUS le verrou",
      src.index("ticket_lock(") < src.index("read_task(args.rm_id)"))
check("Redmine relu après le PUT (204 trompeur)",
      src.index("update_issue_fields(") < src.index("fetch_issue(args.rm_id)"))
check("aucun renommage de fichier", ".rename(" not in src and "os.rename" not in src)
ru = (HERE / "redmine_utils.py").read_text(encoding="utf-8")
check("update_issue_fields sait pousser le titre", 'issue["subject"] = subject' in ru)


# — CLI : les refus sortent AVANT toute écriture, sans toucher au PM —
def cli(*args):
    return subprocess.run([sys.executable, str(HERE / "pm-task-rename.py"), *args],
                          capture_output=True, text=True)


r = cli("1", "--title", "   ")
check("CLI : titre vide → erreur", r.returncode != 0 and "titre vide" in (r.stderr + r.stdout))
r = cli("1", "--title", "x" * 300)
check("CLI : titre trop long → erreur", r.returncode != 0 and "trop long" in (r.stderr + r.stdout))
r = cli("--help")
check("CLI : --help", r.returncode == 0 and "--title" in r.stdout)

if fails:
    print(f"\nÉCHEC : {len(fails)} test(s)")
    sys.exit(1)
print("\nOK — pm-task-rename")
