#!/usr/bin/env python3
"""Tests RM3371 — le `.gitignore` des dépôts de données PM.

Ce qui est protégé, et pourquoi :

 1. Un `.gitignore` EXISTANT est complété, jamais remplacé. Il appartient au projet ; l'écraser
    ferait réapparaître des fichiers qu'il masquait, et l'outil serait désactivé au premier
    dégât.
 2. Une règle déjà écrite par le projet n'est pas redoublée. Comparer ligne à ligne plutôt que
    chercher notre en-tête évite d'empiler un bloc qui répète `.env` à chaque passage.
 3. `.env.example` reste autorisé : un modèle SANS valeur documente la conf attendue, c'est la
    valeur qui ne doit pas partir.
 4. L'opération est IDEMPOTENTE : rejouée, elle n'ajoute rien.

Lancer : python3 scripts/test_pm_core_gitignore.py
"""
import importlib.util
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
spec = importlib.util.spec_from_file_location("pm_core_gitignore", HERE / "pm-core-gitignore.py")
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)

fails = []


def check(nom, cond, detail=""):
    print(("✓ " if cond else "✗ ") + nom + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(nom)


# ── quelles règles manquent ─────────────────────────────────────────────────
check("fichier absent => les trois règles manquent", M.regles_manquantes("") == [".env", ".env.*", "!.env.example"])
check("fichier sans rapport => les trois manquent", M.regles_manquantes("*.log\nvar/\n") == [".env", ".env.*", "!.env.example"])
check("le projet a déjà `.env` => on ne le redouble pas",
      M.regles_manquantes("*.log\n.env\n") == [".env.*", "!.env.example"])
check("tout est là => rien à faire",
      M.regles_manquantes(".env\n.env.*\n!.env.example\n") == [])
check("les commentaires ne comptent pas comme des règles",
      ".env" in M.regles_manquantes("# .env\n"))
check("espaces autour d'une règle tolérés", M.regles_manquantes("  .env  \n") == [".env.*", "!.env.example"])

# ── ce qu'on ajoute ─────────────────────────────────────────────────────────
ajout = M.bloc_a_ajouter("", [".env", ".env.*", "!.env.example"])
check("fichier vide : pas de ligne vide en tête", not ajout.startswith("\n\n"), repr(ajout[:12]))
check("le bloc porte sa marque", M.MARQUE in ajout)
check("les trois règles sont écrites", all(r in ajout for r in (".env", ".env.*", "!.env.example")))

existant = "*.log\nvar/"          # sans saut de ligne final : le piège classique
ajout = M.bloc_a_ajouter(existant, [".env"])
check("fichier sans saut de ligne final : on en ajoute un avant d'écrire",
      (existant + ajout).splitlines()[1] == "var/" and ".env" in ajout, repr(existant + ajout))
check("le contenu existant n'est jamais touché",
      (existant + ajout).startswith(existant))
check("rien à ajouter => chaîne vide (aucune écriture)", M.bloc_a_ajouter("*.log\n", []) == "")

# ── idempotence : rejouer n'ajoute rien ─────────────────────────────────────
c = ""
for _ in range(3):
    c += M.bloc_a_ajouter(c, M.regles_manquantes(c))
check("trois passages => un seul bloc", c.count(M.MARQUE) == 1, repr(c))
check("…et une seule fois chaque règle", c.count("\n.env\n") == 1, repr(c))

print()
if fails:
    print(f"{len(fails)} échec(s) : {fails}")
    sys.exit(1)
print("tous les tests passent")
