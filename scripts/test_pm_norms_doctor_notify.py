#!/usr/bin/env python3
"""Tests RM3177 — le doctor signale au fil quand des invariants NORMS sont rouges.

Un invariant rouge est un ÉTAT : il se notifie, il ne se ticket pas. Ces tests vérifient que
le doctor sait lire ses propres échecs, qu'il notifie avec un message STABLE (la liste en
champ, pour que la même panne fasse UNE entrée), et qu'il n'échoue jamais en mode veille.

Lancer : python3 scripts/test_pm_norms_doctor_notify.py
"""
import importlib.util
import io
import os
import pathlib
import sys
import tempfile
import contextlib

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
fails = []


def check(name, cond):
    print(("✓ " if cond else "✗ ") + name)
    if not cond:
        fails.append(name)


spec = importlib.util.spec_from_file_location("nd", HERE / "pm-norms-doctor.py")
ND = importlib.util.module_from_spec(spec); spec.loader.exec_module(ND)

# — lire ses échecs —
sortie = """== pm-norms-doctor ==
  ✓ fraîcheur : check OK
  ✗ non-perte (couverture) : 3 ligne(s) de l'oracle absentes
  ✓ manifest : sources cohérentes
  ✗ index PÉRIMÉ : scripts/INDEX.md → régénère
  · runtime : 82 %
== ÉCHEC =="""
r = ND.rouges(sortie)
check("les invariants rouges sont extraits", r == ["non-perte (couverture)", "index PÉRIMÉ"])
check("une sortie verte ne rend aucun rouge", ND.rouges("  ✓ tout : ok\n== OK ==") == [])
check("une sortie vide ne lève pas", ND.rouges("") == [] and ND.rouges(None) == [])

# — notifier quand c'est rouge, avec un message STABLE —
with tempfile.TemporaryDirectory() as tmp:
    os.environ["PM_NOTIFY_DIR"] = tmp
    import pm_notify
    import importlib
    pm_notify = importlib.reload(pm_notify)
    vrai_main = ND.main
    ND.main = lambda: (print(sortie), 1)[1]            # un doctor rouge simulé
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            rc1 = ND.notifie(); rc2 = ND.notifie()
    finally:
        ND.main = vrai_main
    check("le mode veille n'échoue JAMAIS, même doctor rouge", rc1 == 0 and rc2 == 0)
    f = [e for e in pm_notify.feed() if e.get("job") == "norms-doctor"]
    check("une notification est émise", len(f) == 1)
    check("… deux passages sur la même panne font UNE entrée qui remonte", f and f[0]["repeats"] == 2)
    check("… la liste des invariants part en champ", f and f[0].get("invariants") == r)
    check("… et le message ne la contient pas (il reste stable)",
          f and "non-perte" not in f[0]["msg"])

# — vert : rien —
with tempfile.TemporaryDirectory() as tmp:
    os.environ["PM_NOTIFY_DIR"] = tmp
    pm_notify = importlib.reload(pm_notify)
    vrai_main = ND.main
    ND.main = lambda: (print("  ✓ tout\n== OK =="), 0)[1]
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            ND.notifie()
    finally:
        ND.main = vrai_main
    check("doctor vert : aucune notification", pm_notify.feed() == [])

print(("ÉCHEC : " + "; ".join(fails)) if fails else "OK — le doctor notifie ses invariants rouges")
sys.exit(1 if fails else 0)
