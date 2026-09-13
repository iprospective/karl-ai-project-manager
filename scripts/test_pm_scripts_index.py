#!/usr/bin/env python3
"""Tests RM3110 — les deux index d'outillage disent la vérité sur `scripts/`.

Le dépôt porte deux index GÉNÉRÉS depuis les docstrings, pour deux usages :

  * `norms/CHEATSHEET.md` — le condensé des outils du quotidien, **préchargé par
    tous**, donc sous budget serré (1 200 tokens) ;
  * `scripts/INDEX.md` — la liste **exhaustive**, groupée par domaine, ouverte à la
    demande quand l'outil cherché n'est pas dans le condensé.

Aucun des deux n'était vérifié. Le 2026-09-12, la cheatsheet listait 47 outils pour
95 réels : périmée de 48 entrées, et personne ne pouvait le voir — un index qui ment
coûte plus cher que pas d'index, puisqu'on cherche l'outil, on ne le trouve pas, et
on refait à la main ce qui existait.

Ces tests empêchent trois régressions : la péremption (le gate du doctor), le
retour à une liste NOIRE pour la cheatsheet (qui se périme par construction : tout
script ajouté y entre par défaut), et la confusion exécutables / bibliothèques.

Lancer : python3 scripts/test_pm_scripts_index.py
"""
import pathlib
import re
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
ASSEMBLE = HERE / "pm-norms-assemble.py"
INDEX = HERE / "INDEX.md"
CHEATSHEET = ROOT / "norms" / "CHEATSHEET.md"

fails = []


def check(name, cond):
    print(("✓ " if cond else "✗ ") + name)
    if not cond:
        fails.append(name)


def run(*args):
    return subprocess.run([sys.executable, str(ASSEMBLE), *args],
                          capture_output=True, text=True)


# — les deux artefacts existent et sont à jour —
check("scripts/INDEX.md existe", INDEX.is_file())
check("norms/CHEATSHEET.md existe", CHEATSHEET.is_file())
check("INDEX.md est à jour (--check passe)", run("index", "--check").returncode == 0)
check("CHEATSHEET.md est à jour (--check passe)", run("cheatsheet", "--check").returncode == 0)

# — --check DÉTECTE une péremption : un gate qui ne détecte rien n'est pas un gate —
before = INDEX.read_text(encoding="utf-8")
try:
    INDEX.write_text(before + "- `outil-fantome` — n'existe pas\n", encoding="utf-8")
    r = run("index", "--check")
    check("--check échoue sur un INDEX périmé", r.returncode != 0)
    check("--check nomme la commande de régénération", "pm-norms-assemble.py index" in r.stdout)
finally:
    INDEX.write_text(before, encoding="utf-8")
check("l'INDEX est restauré après le test", INDEX.read_text(encoding="utf-8") == before)

# — le doctor porte bien le gate —
doctor = (HERE / "pm-norms-doctor.py").read_text(encoding="utf-8")
check("le doctor appelle check_generated_indexes", "check_generated_indexes" in doctor)

# — exhaustivité : tout exécutable pm-*/redmine-*/karl-* est dans l'INDEX —
index_txt = INDEX.read_text(encoding="utf-8")
manquants = []
for p in sorted(HERE.glob("*.py")):
    n = p.name[:-3]
    if n.startswith(("test_", "test-")) or not re.match(r"^(pm|redmine|karl|mmi)-", n):
        continue
    if f"`{n}`" not in index_txt:
        manquants.append(n)
check(f"tous les exécutables sont dans l'INDEX (manquants : {manquants[:5]})", not manquants)

# — les bibliothèques sont séparées : on ne les LANCE pas, on les importe —
libs_section = index_txt.split("## Bibliothèques")[-1]
check("pm_paths est rangé en bibliothèque", "`pm_paths`" in libs_section)
check("pm-task-add n'est PAS en bibliothèque", "`pm-task-add`" not in libs_section)

# — la cheatsheet reste sous son budget, et reste une liste BLANCHE —
r = run("cheatsheet")
check("la cheatsheet tient dans son budget", r.returncode == 0 and "BUDGET DÉPASSÉ" not in r.stdout)
asm = ASSEMBLE.read_text(encoding="utf-8")
check("la cheatsheet est filtrée par liste blanche (KEEP), pas par exclusions",
      "KEEP = {" in asm and 'exclude = re.compile' not in asm)
check("la cheatsheet renvoie vers l'INDEX exhaustif", "scripts/INDEX.md" in CHEATSHEET.read_text(encoding="utf-8"))

# — un script sans docstring est SIGNALÉ, jamais omis en silence —
check("la génération signale les scripts sans docstring",
      "sans docstring" in asm)

print(("ÉCHEC : " + "; ".join(fails)) if fails else "OK — index d'outillage")
sys.exit(1 if fails else 0)
