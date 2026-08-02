#!/usr/bin/env python3
"""Tests de la politique « core » de pm-protect (RM2440).

Ce qui doit être garanti :
  1. un dépôt portant un `.mmi-pm/` RÉEL à sa racine est un core ;
  2. un workspace de CODE, dont le `.mmi-pm` est un *symlink* vers le dossier PM
     centralisé, n'en est PAS un — sa `main` doit rester protégée comme du code
     (c'est le piège : les deux se ressemblent depuis un `ls`) ;
  3. la politique core pose push=Developer(30) sur la prod, la politique code
     push=personne(0) ;
  4. `allow_force_push=false` dans les deux cas — le filet de sécurité ne bouge pas.

Lancement : python3 scripts/test_pm_protect_core.py
"""
import importlib.util
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
_spec = importlib.util.spec_from_file_location("pm_protect", HERE / "pm-protect.py")
pmp = importlib.util.module_from_spec(_spec)
sys.modules["pm_protect"] = pmp
_spec.loader.exec_module(pmp)

FAILURES = []


def check(label, got, want):
    if got == want:
        print(f"  ✓ {label}")
    else:
        print(f"  ✗ {label} : attendu {want!r}, obtenu {got!r}")
        FAILURES.append(label)


def git_init(path):
    subprocess.run(["git", "init", "-q", str(path)], check=True)


def test_detection():
    print("Détection d'un dépôt core :")
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)

        core = tmp / "matnat-infra-core"
        core.mkdir()
        git_init(core)
        (core / ".mmi-pm").mkdir()
        check("dossier .mmi-pm réel → core", pmp.is_core_repo(core), True)

        client = tmp / "matnat-core"
        client.mkdir()
        git_init(client)
        (client / ".mmi-pm-client").mkdir()
        check("dossier .mmi-pm-client réel → core", pmp.is_core_repo(client), True)

        code = tmp / "workspace-de-code"
        code.mkdir()
        git_init(code)
        (code / ".mmi-pm").symlink_to(core / ".mmi-pm")
        check("symlink .mmi-pm (workspace de code) → PAS core",
              pmp.is_core_repo(code), False)

        plain = tmp / "repo-nu"
        plain.mkdir()
        git_init(plain)
        check("aucun marqueur → PAS core", pmp.is_core_repo(plain), False)

        check("hors dépôt git → PAS core", pmp.is_core_repo(tmp / "nexistepas"), False)


def test_policy():
    """desired_policy() sans réseau : on stubbe branch_exists."""
    print("Politique appliquée :")
    original = pmp.branch_exists
    try:
        pmp.branch_exists = lambda pid, name, token: name in ("main", "dev")

        code = dict((n, (p, m)) for n, p, m in pmp.desired_policy(1, "tok", core=False))
        check("code — main push=personne(0)", code["main"][0], pmp.NONE)
        check("code — main merge=Maintainer(40)", code["main"][1], pmp.MAINT)

        core = dict((n, (p, m)) for n, p, m in pmp.desired_policy(1, "tok", core=True))
        check("core — main push=Developer(30)", core["main"][0], pmp.DEV)
        check("core — main merge=Maintainer(40)", core["main"][1], pmp.MAINT)
        check("core — dev conservée au même niveau", core["dev"], (pmp.MAINT, pmp.MAINT))

        # master en repli quand main est absente
        pmp.branch_exists = lambda pid, name, token: name == "master"
        m = dict((n, (p, m2)) for n, p, m2 in pmp.desired_policy(1, "tok", core=True))
        check("core — master en repli de main", m["master"][0], pmp.DEV)
    finally:
        pmp.branch_exists = original


def test_force_push_never_allowed():
    """`allow_force_push` est câblé à false dans apply_one, quelle que soit la
    politique : on capture le POST plutôt que de faire confiance à la lecture."""
    print("Garde force-push :")
    sent = {}

    def fake_api(method, path, token, fields=None):
        if method == "POST":
            sent.update(fields or {})
            return 201, {"push_access_levels": [{"access_level": fields["push_access_level"]}],
                         "merge_access_levels": [{"access_level": fields["merge_access_level"]}]}, ""
        return 404, None, ""

    original = pmp.api
    try:
        pmp.api = fake_api
        pmp.apply_one(1, "main", pmp.DEV, pmp.MAINT, "tok", dry=False)
        check("allow_force_push=false même en politique core",
              sent.get("allow_force_push"), "false")
        check("push_access_level transmis tel quel", sent.get("push_access_level"), pmp.DEV)
    finally:
        pmp.api = original


if __name__ == "__main__":
    test_detection()
    test_policy()
    test_force_push_never_allowed()
    if FAILURES:
        print(f"\n{len(FAILURES)} échec(s) : {', '.join(FAILURES)}")
        sys.exit(1)
    print("\nTous les tests passent.")
