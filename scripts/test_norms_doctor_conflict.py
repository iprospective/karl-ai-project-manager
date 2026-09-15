#!/usr/bin/env python3
"""Tests RM3194 — l'invariant « aucun marqueur de conflit » détecte vraiment.

Le doctor lançait 8 invariants VERTS sur un KERNEL qui portait, en `main`, trois
marqueurs de merge non résolus. La fraîcheur ne pouvait pas les voir : elle compare
NORMS.md à `assemble(src)`, et la source portait les mêmes marqueurs.

Deux cas, parce qu'un gate qui ne détecte rien reste vert lui aussi :
  1. sur un fichier pollué → il doit CRIER (sinon le gate est décoratif) ;
  2. sur les sources réelles du dépôt → il doit être MUET.

Lancer : python3 scripts/test_norms_doctor_conflict.py
"""
import importlib.util
import pathlib
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("doctor", HERE / "pm-norms-doctor.py")
doctor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(doctor)

fail = 0

# 1) fichier pollué : une ligne par marqueur, chacune doit être vue.
with tempfile.TemporaryDirectory() as d:
    p = pathlib.Path(d) / "pollue.md"
    ours, sep, theirs = doctor.CONFLICT_MARKERS
    p.write_text(
        f"# titre\n{ours} HEAD\nversion A\n{sep}\nversion B\n{theirs} abc123 (sujet)\n",
        encoding="utf-8")
    bad = doctor.check_conflict_markers([p])
    if len(bad) != 3:
        print(f"ÉCHEC : 3 marqueurs attendus, {len(bad)} détecté(s) : {bad}")
        fail = 1
    else:
        print(f"✓ marqueurs détectés sur un fichier pollué : {', '.join(bad)}")

# 2) le dépôt lui-même doit être propre.
bad = doctor.check_conflict_markers()
if bad:
    print(f"ÉCHEC : marqueur(s) de conflit dans le dépôt : {', '.join(bad)}")
    print("  → résoudre dans norms/src/, puis régénérer : pm-norms-assemble.py")
    fail = 1
else:
    n = len(doctor.conflict_targets())
    print(f"✓ dépôt propre : {n} fichier(s) scanné(s) (sources assemblées + généré)")

sys.exit(fail)
