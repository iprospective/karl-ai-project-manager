#!/usr/bin/env python3
"""Tests du lanceur de suite `mmi-pm test` (RM2749).

Ce qu'ils protègent — les trois façons dont un lanceur ment sur son verdict :
  1. il compte vert un test qui s'est en fait ignoré (la convention 77) ;
  2. il rend 0 alors qu'un test est rouge (l'échec devient invisible en CI) ;
  3. il laisse fuiter l'environnement du shell dans les tests, ce qui ramène
     le défaut fondateur : un verdict qui dépend du poste.

Lancer : python3 scripts/test_pm_test_runner.py
"""
import contextlib
import importlib.util
import io
import os
import pathlib
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("pm_test", HERE / "pm-test.py")
pmtest = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pmtest)

fails = []


def check(name, cond):
    print(("✓ " if cond else "✗ ") + name)
    if not cond:
        fails.append(name)


# — découverte —
noms = [f.name for f in pmtest.discover([])]
check("la suite se découvre seule (les deux conventions de nommage)",
      "test_pm_task.py" in noms and "test-karl-agent-auth.py" in noms)
check("le socle commun n'est pas lancé comme un test",
      "test_support.py" not in noms)
check("un motif filtre par sous-chaîne",
      [f.name for f in pmtest.discover(["mmi_pm"])] == ["test_mmi_pm.py"])

# — les trois verdicts, sur de vrais sous-processus —
with tempfile.TemporaryDirectory() as td:
    tmp = pathlib.Path(td)
    cas = {
        "test_vert.py": "import sys; print('tout va bien'); sys.exit(0)",
        "test_rouge.py": "import sys; print('cassé'); sys.exit(1)",
        "test_ignore.py": "import sys; print('pas de vault ici'); sys.exit(77)",
        # Le shell ne doit PAS transpirer dans le test : c'est le contrat du
        # lanceur, et la raison d'être du ticket.
        "test_fuite.py": ("import os, sys; "
                          "sys.exit(0 if 'PM_CORE_DIR' not in os.environ else 3)"),
    }
    for nom, code in cas.items():
        (tmp / nom).write_text(code, encoding="utf-8")
    ancien, pmtest.SCRIPTS = pmtest.SCRIPTS, tmp
    sortie = io.StringIO()
    try:
        os.environ["PM_CORE_DIR"] = "/un/core/qui/ne/doit/pas/passer"
        # La sortie du lanceur est capturée : sans ça, ses « ✗ » de démonstration
        # se mêlent au verdict de CE test et donnent à lire un échec inexistant.
        with contextlib.redirect_stdout(sortie):
            rc_purge = pmtest.main([])
            rc_herite = pmtest.main(["test_fuite", "--inherit"])
    finally:
        pmtest.SCRIPTS = ancien
        os.environ.pop("PM_CORE_DIR", None)

vu = sortie.getvalue()
check("un rouge fait sortir le lanceur en échec", rc_purge == 1)
check("le compte distingue vert / rouge / ignoré",
      "2 vert(s), 1 rouge(s), 1 ignoré(s)" in vu)
check("un test qui s'ignore dit pourquoi (et n'est pas compté vert)",
      "⊘ test_ignore.py — pas de vault ici" in vu)
check("l'échec est restitué avec la sortie du test", "cassé" in vu)
check("l'environnement est purgé : PM_CORE_DIR ne traverse pas",
      "✓ test_fuite.py" in vu)
check("--inherit rend au contraire le shell tel quel (donc ici : rouge)",
      rc_herite == 1 and "environnement hérité" in vu)

print()
if fails:
    print(f"ÉCHEC — {len(fails)} contrôle(s) : " + " · ".join(fails))
    sys.exit(1)
print("OK — lanceur de suite (découverte, verdicts, purge d'environnement)")
