#!/usr/bin/env python3
"""Tests RM2384 — cohérence git d'un ticket livré (mergeabilité avant verdict).

Unitaire : la classification pure `mergecheck_verdict` (niveau + remédiation) et
le parsing de la sortie de `git merge-tree`. La partie I/O (fetch, rev-list,
merge-tree réel) n'est pas testée ici — c'est le classement du résultat qui porte
la valeur métier (anticiper l'échec de merge décrit sur RM2000).

Lancer : python3 scripts/test_karl_agent_mergecheck.py
"""
import importlib.util
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("karl_agent", HERE / "karl-agent.py")
ka = importlib.util.module_from_spec(spec)
sys.modules["karl_agent"] = ka
spec.loader.exec_module(ka)

fails = []


def check(name, cond):
    print(("✓ " if cond else "✗ ") + name)
    if not cond:
        fails.append(name)


V = ka.mergecheck_verdict

# — worktree introuvable / pas de git → indéterminé, jamais bloquant à tort —
r = V(is_git=False, has_worktree=False, target="dev")
check("no-git → unknown", r["level"] == "unknown")
r = V(is_git=True, has_worktree=False, target="dev")
check("pas de worktree → unknown", r["level"] == "unknown")

# — cible introuvable → unknown (on ne peut pas comparer) —
r = V(is_git=True, has_worktree=True, target="dev", target_missing=True)
check("cible absente → unknown", r["level"] == "unknown")
check("cible absente → mentionne dev", "dev" in r["headline"])

# — conflit de merge → block + liste + remédiation (le cœur RM2000) —
r = V(is_git=True, has_worktree=True, target="dev", behind=3, mergeable=False,
      conflicts=["CHANGELOG.md", "src/app.py"])
check("conflit → block", r["level"] == "block")
check("conflit → compte fichiers", "2 fichier" in r["headline"])
check("conflit → liste les fichiers", "CHANGELOG.md" in r["detail"])
check("conflit → conseille de merger la cible", "merge" in r["advice"].lower() and "dev" in r["advice"])

# — conflit avec beaucoup de fichiers : tronqué avec « … » —
r = V(is_git=True, has_worktree=True, target="dev", mergeable=False,
      conflicts=[f"f{i}.py" for i in range(10)])
check("conflit >6 fichiers → détail tronqué", "…" in r["detail"])
check("conflit >6 fichiers → compte exact dans le titre", "10 fichier" in r["headline"])

# — merge propre malgré retard → ok (merge-tree fait autorité sur le behind) —
r = V(is_git=True, has_worktree=True, target="dev", behind=5, mergeable=True)
check("propre + en retard → ok", r["level"] == "ok")
check("propre + en retard → mentionne le retard", "5" in r["headline"])
check("propre + en retard → pas de remédiation", r["advice"] == "")

# — branche à jour et mergeable → ok net —
r = V(is_git=True, has_worktree=True, target="dev", behind=0, mergeable=True)
check("à jour + propre → ok", r["level"] == "ok")
check("à jour + propre → sans conseil", r["advice"] == "")

# — mergeabilité inconnue (merge-tree indispo) + retard → warn heuristique —
r = V(is_git=True, has_worktree=True, target="dev", behind=4, mergeable=None)
check("inconnu + retard → warn", r["level"] == "warn")
check("inconnu + retard → conseille la prudence", "dev" in r["advice"])

# — mergeabilité inconnue mais branche à jour → ok (rien d'alarmant) —
r = V(is_git=True, has_worktree=True, target="dev", behind=0, mergeable=None)
check("inconnu + à jour → ok", r["level"] == "ok")

# — la cible personnalisée (≠ dev) est bien reportée —
r = V(is_git=True, has_worktree=True, target="main", behind=2, mergeable=None)
check("cible personnalisée reportée", "main" in r["headline"])

# — parsing merge-tree : rc 0 propre, rc 1 conflit (OID + blanc + fichiers), autre indéterminé —
P = ka._parse_merge_tree_conflicts
m, c = P(0, "abc123def456\n")
check("merge-tree rc0 → mergeable", m is True and c == [])
m, c = P(1, "abc123\n\nCHANGELOG.md\nsrc/app.py\n")
check("merge-tree rc1 → conflit + fichiers", m is False and c == ["CHANGELOG.md", "src/app.py"])
check("merge-tree rc1 → l'OID n'est pas compté comme fichier", "abc123" not in c)
m, c = P(128, "")
check("merge-tree rc128 → indéterminé", m is None and c == [])

if fails:
    print(f"\n{len(fails)} test(s) en échec : {fails}")
    sys.exit(1)
print("\nOK — tous les tests mergecheck passent")
