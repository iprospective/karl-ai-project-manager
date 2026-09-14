#!/usr/bin/env python3
"""Tests RM3157 — qui d'autre touche à ce que je touche.

Le 2026-09-14, deux sessions ont corrigé le même défaut à trente minutes d'intervalle (RM3142 et
RM3143). Les TICKETS étaient différents — la garde de RM3086, qui veille sur le même ticket, ne
pouvait rien dire — mais le CODE était commun. La seconde MR a été mergée par-dessus la première et
a laissé `dev` mélangé : un lot de travail perdu, plus la réparation.

Git ne prévient pas : il ne voit un conflit que si les lignes se chevauchent exactement, et il le
voit au merge, quand les deux raisonnements sont déjà écrits. On regarde donc plus tôt (à la
création de la MR, là où les fichiers sont enfin connus) et plus large (le même fichier suffit).

Ce que ces tests tiennent :
  - un recoupement est vu et nommé, avec ses fichiers ;
  - l'absence de recoupement ne produit AUCUN bruit ;
  - les fichiers que tout le monde touche sont exclus — sinon le signal crie à chaque MR et
    cesse d'être lu ;
  - l'avertissement avertit, il n'interdit pas.

Lancer : python3 scripts/test_pm_mr_collisions.py
"""
import importlib.util
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from test_support import hermetic_core                       # noqa: E402
hermetic_core()

spec = importlib.util.spec_from_file_location("pmr", HERE / "pm-mr.py")
pmr = importlib.util.module_from_spec(spec); sys.modules["pmr"] = pmr
try:
    spec.loader.exec_module(pmr)
except SystemExit:
    pass

fails = []


def check(name, cond, detail=""):
    print(("✓ " if cond else "✗ ") + name + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(name)


C, T = pmr.collisions, pmr.texte_collisions

# ── le cas vécu : deux tickets, un même fichier ─────────────────────────────
miens = ["scripts/pm_index.py", "scripts/mmi-pm.py", "Changelog.md"]
autres = {"3143-regression-prod": ["scripts/pm_index.py", "scripts/pm_searchdb.py", "Changelog.md"],
          "3100-moisson": ["scripts/pm-think-harvest.py"]}
r = C(miens, autres)
check("la branche qui partage un fichier est vue, et elle seule",
      [b for b, _ in r] == ["3143-regression-prod"], str(r))
check("…avec le fichier commun nommé", r[0][1] == ["scripts/pm_index.py"], str(r))
check("Changelog.md ne compte pas : tout le monde y écrit, le signaler ferait crier à chaque MR",
      "Changelog.md" not in r[0][1])

# ── le silence quand il n'y a rien à dire ───────────────────────────────────
check("aucun recoupement : rien, pas même une ligne",
      C(["scripts/a.py"], {"3100-x": ["scripts/b.py"]}) == [])
check("…et le message est vide, donc rien ne s'affiche", T([]) == "")
check("seulement des fichiers partagés : pas de collision",
      C(["Changelog.md", "norms/VERSION"], {"3100-x": ["Changelog.md", "norms/VERSION"]}) == [])
check("aucune autre branche : rien", C(["scripts/a.py"], {}) == [])

# ── le message ──────────────────────────────────────────────────────────────
txt = T(r, ouvertes={"3143-regression-prod": 1113})
check("le message nomme la branche et sa MR", "3143-regression-prod" in txt and "!1113" in txt, txt)
check("…les fichiers communs", "scripts/pm_index.py" in txt, txt)
check("…et ce qu'il faut faire : regarder avant de merger", "avant de merger" in txt, txt)
check("il dit pourquoi git ne dira rien — sinon on se fie à git", "chevauchent" in txt, txt)
txt2 = T(r)
check("sans information sur la MR : la branche est nommée, et RIEN n'est affirmé sur son absence",
      "3143-regression-prod" in txt2 and "MR" not in txt2.split("3143-regression-prod")[1].split("\n")[0], txt2)
check("beaucoup de fichiers : la liste est écourtée, pas déversée",
      "…" in T(C(["f%d.py" % i for i in range(12)], {"3100-x": ["f%d.py" % i for i in range(12)]})))

# ── avertir n'est pas interdire ─────────────────────────────────────────────
src = (HERE / "pm-mr.py").read_text(encoding="utf-8")
bloc = src.split("def avertir_collisions")[1][:1200]
check("l'avertissement ne peut pas faire échouer une livraison (tout est attrapé)",
      "except Exception" in bloc and "return \"\"" in bloc)
check("il est posé AVANT le push et la création, là où il sert encore",
      src.index("avertir_collisions(repo, src, tgt") < src.index('"push", "-u", "origin", src'))
check("il passe par `warn` : `info` est muet en sortie dense, donc invisible",
      "out.warn(mot)" in src)

print()
if fails:
    print(f"✗ {len(fails)} échec(s) : " + ", ".join(fails)); sys.exit(1)
print("OK — collisions de fichiers entre branches de ticket (RM3157)")
