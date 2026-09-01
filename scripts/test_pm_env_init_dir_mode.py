#!/usr/bin/env python3
"""Tests RM2636 — droits des dossiers partagés d'un workspace : jamais de sticky bit.

Régression de l'incident : un durcissement avait posé `3770` (setgid **+ sticky**) sur
les dossiers de données PM. Le sticky interdit de remplacer une entrée dont on n'est pas
propriétaire → `pm_lock.atomic_write` (temp + `os.replace`) plantait en EPERM sur tout
fichier appartenant à un autre membre du groupe `pm`, alors même que le dossier était
inscriptible. `ensure_group_shared` garantit setgid + g+rwx **sans** sticky, et répare
un workspace existant.

Lancer : python3 scripts/test_pm_env_init_dir_mode.py
"""
import importlib.util
import pathlib
import stat
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent


def _load(modname, filename):
    spec = importlib.util.spec_from_file_location(modname, HERE / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


env_init = _load("pm_env_init", "pm-env-init.py")
CTX = env_init.Ctx(dry=False, verbose=False)

fails = []


def check(label, cond):
    print(f"  {'✓' if cond else '✗'} {label}")
    if not cond:
        fails.append(label)


def mode(p):
    return stat.S_IMODE(p.stat().st_mode)


with tempfile.TemporaryDirectory() as tmp:
    root = pathlib.Path(tmp)

    print("1) un dossier en 3770 est réparé en 2770 (sticky retiré, setgid conservé)")
    d = root / "sticky"
    d.mkdir()
    d.chmod(0o3770)
    env_init.ensure_group_shared(CTX, d)
    check("sticky retiré", not mode(d) & stat.S_ISVTX)
    check("setgid conservé", bool(mode(d) & stat.S_ISGID))
    check("mode final 2770", mode(d) == 0o2770)

    print("2) les bits owner/other sont préservés, seul g+rwx est forcé")
    d = root / "0705"
    d.mkdir()
    d.chmod(0o0705)
    env_init.ensure_group_shared(CTX, d)
    check("mode final 2775", mode(d) == 0o2775)

    print("3) idempotent : un dossier déjà conforme n'est pas retouché")
    d = root / "conforme"
    d.mkdir()
    d.chmod(0o2770)
    before = CTX.changed
    env_init.ensure_group_shared(CTX, d)
    check("aucune action comptée", CTX.changed == before)
    check("mode inchangé", mode(d) == 0o2770)

    print("4) dry-run : annonce mais ne mute pas")
    d = root / "dry"
    d.mkdir()
    d.chmod(0o3770)
    env_init.ensure_group_shared(env_init.Ctx(dry=True, verbose=False), d)
    check("mode inchangé en dry-run", mode(d) == 0o3770)

    print("5) chemin inexistant : pas d'exception")
    try:
        env_init.ensure_group_shared(CTX, root / "absent")
        check("silencieux sur dossier absent", True)
    except Exception as e:  # noqa: BLE001
        check(f"silencieux sur dossier absent ({e})", False)

print()
if fails:
    print(f"ÉCHEC : {len(fails)} assertion(s) — {fails}")
    sys.exit(1)
print("OK — tous les tests passent")
