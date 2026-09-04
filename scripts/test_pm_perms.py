#!/usr/bin/env python3
"""Tests de pm-perms — diagnostic des écarts de perms (RM2438 T6).

Lancer : python3 scripts/test_pm_perms.py
Couvre la fonction PURE `diagnose` (sans privilège) : dossiers (conforme, sticky
interdit, mode/groupe divergents, absent ignoré, lien symbolique exclu) ET fichiers env
(mode, groupe, propriétaire — RM2502 : pm.env/.env → root:pm 640). Couvre aussi le
contrat `model_dirs()` consommé par `pm-env-helper ws-init` (RM2909).
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


# ── Fichiers env communs (RM2502 : root:pm 640) ────────────────────────────

def test_fichier_env_conforme(tmp):
    f = tmp / "pm.env"
    f.write_text("X=1")
    os.chmod(f, 0o640)
    st = f.stat()
    # conforme sur mode/groupe/propriétaire courants → aucun écart, PAS de faux sticky
    assert diagnose(f, 0o640, st.st_gid, want_uid=st.st_uid) == [], "fichier 640 conforme"
    print("✓ fichier env conforme (640, owner/group ok, pas de faux sticky)")


def test_fichier_env_mode_divergent(tmp):
    f = tmp / ".env"
    f.write_text("SECRET=1")
    os.chmod(f, 0o644)  # world-readable là où on attend 640
    st = f.stat()
    issues = diagnose(f, 0o640, st.st_gid, want_uid=st.st_uid)
    assert any("mode" in i for i in issues), "mode 644≠640 signalé"
    print("✓ fichier env mode 644≠640 signalé")


def test_fichier_env_proprietaire_divergent(tmp):
    f = tmp / "env-owner"
    f.write_text("X=1")
    os.chmod(f, 0o640)
    st = f.stat()
    # attendre un uid volontairement différent → doit signaler (cas .env root:mathieu)
    issues = diagnose(f, 0o640, st.st_gid, want_uid=st.st_uid + 54321)
    assert any("propriétaire" in i for i in issues), "propriétaire ≠ attendu signalé"
    print("✓ propriétaire divergent signalé (fichier env)")


def test_symlink_ignore(tmp):
    """Un lien symbolique n'est JAMAIS normalisé : chmod/chown déréférencent, donc
    normaliser un `.mmi-pm` symlinké vers le core PROD le chownerait root → pm."""
    cible = tmp / "cible"
    cible.mkdir()
    os.chmod(cible, 0o2755)  # volontairement non conforme
    lien = tmp / "lien"
    lien.symlink_to(cible)
    avant = stat.S_IMODE(cible.stat().st_mode)
    issues = diagnose(lien, 0o2770, cible.stat().st_gid)
    assert any("lien symbolique" in i for i in issues), "le lien doit être signalé comme tel"
    assert not any("mode" in i for i in issues), "…et surtout PAS proposé à la normalisation"
    assert stat.S_IMODE(cible.stat().st_mode) == avant, "la cible du lien ne doit pas bouger"
    print("✓ lien symbolique signalé et exclu de la normalisation")


def test_model_dirs_contrat():
    """`model_dirs()` est le contrat consommé par `pm-env-helper ws-init` (RM2909) :
    chemins relatifs, racine exclue du parcours mkdir, parents avant enfants."""
    dirs = pm_perms.model_dirs()
    assert dirs[0] == ".", "la racine est émise en premier"
    reste = dirs[1:]
    assert all(not r.startswith("/") and ".." not in r for r in reste), \
        "aucun chemin absolu ni remontée — le helper les refuserait"
    for parent in (".mmi-pm",):
        enfants = [r for r in reste if r.startswith(parent + "/")]
        assert enfants, f"{parent} devrait avoir des enfants dans le modèle"
        for e in enfants:
            assert reste.index(parent) < reste.index(e), \
                f"{parent} doit précéder {e} (mkdir ordonné, sans -p)"
    for attendu in ("repos", "envs", "tmp", "sessions", "logs", "data", ".mmi-pm"):
        assert attendu in reste, f"{attendu} absent du modèle"
    print(f"✓ model_dirs : {len(dirs)} entrées, ordonnées, dont les partagés du layout")


def main():
    test_model_dirs_contrat()
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        test_conforme(tmp)
        test_sticky_interdit(tmp)
        test_mode_divergent(tmp)
        test_groupe_divergent(tmp)
        test_absent_ignore(tmp)
        test_fichier_env_conforme(tmp)
        test_fichier_env_mode_divergent(tmp)
        test_fichier_env_proprietaire_divergent(tmp)
        test_symlink_ignore(tmp)
    print("\nOK — tests pm-perms passent")
    return 0


if __name__ == "__main__":
    sys.exit(main())
