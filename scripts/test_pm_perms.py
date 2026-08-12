#!/usr/bin/env python3
"""Tests de pm-perms — diagnostic des écarts de perms (RM2438 T6).

Lancer : python3 scripts/test_pm_perms.py
Couvre la fonction PURE `diagnose` (sans privilège) : conforme, sticky interdit,
mode divergent, groupe divergent, dossier absent ignoré.
"""
import importlib.util
import os
import stat
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("pm_perms", SCRIPTS / "pm-perms.py")
pm_perms = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pm_perms)
diagnose = pm_perms.diagnose


def test_conforme(tmp):
    d = tmp / "ok"
    d.mkdir()
    os.chmod(d, 0o2770)
    gid = d.stat().st_gid  # groupe courant = "attendu" pour ce test
    assert diagnose(d, 0o2770, gid) == [], "conforme → aucun écart"
    print("✓ conforme : aucun écart")


def test_sticky_interdit(tmp):
    d = tmp / "sticky"
    d.mkdir()
    os.chmod(d, 0o3770)  # setgid + STICKY (le bug RM2438)
    gid = d.stat().st_gid
    issues = diagnose(d, 0o2770, gid)
    assert any("sticky" in i.lower() for i in issues), "sticky doit être signalé"
    print("✓ sticky bit (3770) signalé comme INTERDIT")


def test_mode_divergent(tmp):
    d = tmp / "mode"
    d.mkdir()
    os.chmod(d, 0o2755)  # squelette là où on attend churn 2770
    gid = d.stat().st_gid
    issues = diagnose(d, 0o2770, gid)
    assert any("mode" in i for i in issues)
    print("✓ mode divergent signalé")


def test_groupe_divergent(tmp):
    d = tmp / "grp"
    d.mkdir()
    os.chmod(d, 0o2770)
    cur = d.stat().st_gid
    # attendre un gid volontairement différent → doit signaler
    issues = diagnose(d, 0o2770, cur + 12345)
    assert any("groupe" in i for i in issues), "groupe ≠ attendu signalé"
    print("✓ groupe divergent signalé")


def test_absent_ignore(tmp):
    issues = diagnose(tmp / "nope", 0o2770, None)
    assert issues == [], "dossier absent → ignoré (projets partiels)"
    print("✓ dossier absent ignoré")


def main():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        test_conforme(tmp)
        test_sticky_interdit(tmp)
        test_mode_divergent(tmp)
        test_groupe_divergent(tmp)
        test_absent_ignore(tmp)
    print("\nOK — tests pm-perms passent")
    return 0


if __name__ == "__main__":
    sys.exit(main())
