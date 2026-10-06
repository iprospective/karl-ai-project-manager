#!/usr/bin/env python3
"""Tests RM3318 — conf PM de l'utilisateur dans `<core>/var/users/<user>/`, jamais dans `~`.

Couvre : l'ordre de résolution de `pm_paths.user_conf_file`, le script de migration
`pm-user-conf-migrate.py` (déplacement, fusion de `.env`, conflit conservé, refus d'un worktree),
et les préférences mail de `karl-mail-send.py` (signature sans doublon, nom d'affichage).
Tout est isolé dans des dossiers temporaires : ni le vrai home ni le vrai `var/` ne sont lus.
"""
import importlib.util
import os
import pwd
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pm_paths  # noqa: E402

ok = ko = 0


def check(label, cond, detail=""):
    global ok, ko
    if cond:
        ok += 1
        print(f"✓ {label}")
    else:
        ko += 1
        print(f"✗ {label} — {detail}")


ISOLE = ("PM_USER_ENV", "PM_USER_DIR", "PM_CORE_DIR", "PM_STATE_DIR", "XDG_CONFIG_HOME")
MOI = pwd.getpwuid(os.geteuid()).pw_name


def env_isole(tmp: Path, **extra):
    e = {k: v for k, v in os.environ.items() if k not in ISOLE}
    e.update(PM_STATE_DIR=str(tmp / "state"), XDG_CONFIG_HOME=str(tmp / "home-config"))
    e.update(extra)
    return e


print("[RM3318] résolution user_conf_file")
with tempfile.TemporaryDirectory() as t:
    tmp = Path(t)
    sauve = {k: os.environ.get(k) for k in ISOLE}
    try:
        for k in ISOLE:
            os.environ.pop(k, None)
        os.environ.update(PM_STATE_DIR=str(tmp / "state"), XDG_CONFIG_HOME=str(tmp / "home-config"))
        nouveau = tmp / "state" / "users" / MOI / "invoice.yml"
        ancien = tmp / "home-config" / "mmi-pm" / "invoice.yml"
        check("absent partout → le nouveau chemin (pour le créer)", pm_paths.user_conf_file("invoice.yml") == nouveau)
        ancien.parent.mkdir(parents=True); ancien.write_text("a: 1\n")
        check("seul l'ancien existe → repli transitoire", pm_paths.user_conf_file("invoice.yml", warn=False) == ancien)
        nouveau.parent.mkdir(parents=True); nouveau.write_text("a: 2\n")
        check("le nouveau existe → il prime", pm_paths.user_conf_file("invoice.yml") == nouveau)
        check("user_conf_dir = <state>/users/<user>", pm_paths.user_conf_dir() == tmp / "state" / "users" / MOI)
        os.environ["PM_STATE_DIR"] = ""
        os.environ["PM_CORE_DIR"] = str(tmp / "core")
        check("sans PM_STATE_DIR : <PM_CORE_DIR>/var/users/<user>",
              pm_paths.user_conf_dir() == (tmp / "core").resolve() / "var" / "users" / MOI)
    finally:
        for k, v in sauve.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

print("\n[RM3318] migration pm-user-conf-migrate")
MIGR = HERE / "pm-user-conf-migrate.py"
with tempfile.TemporaryDirectory() as t:
    tmp = Path(t)
    src = tmp / "home-config" / "mmi-pm"; src.mkdir(parents=True)
    (src / ".env").write_text("A=1\nB=valeur-ancienne-zq\nexport C=3\n")
    (src / "invoice.yml").write_text("x: 1\n")
    (src / "timesheet.yml").write_text("y: 1\n")
    dst = tmp / "state" / "users" / MOI; dst.mkdir(parents=True)
    (dst / ".env").write_text("PM_MAIL_SENDER=karl\nB=valeur-neuve-zq\n")
    (dst / "timesheet.yml").write_text("y: 2\n")
    e = env_isole(tmp)

    r = subprocess.run([sys.executable, str(MIGR), "--dry-run"], capture_output=True, text=True, env=e)
    check("dry-run : rien ne bouge", (src / "invoice.yml").is_file() and not (dst / "invoice.yml").exists(), r.stdout + r.stderr)
    r = subprocess.run([sys.executable, str(MIGR)], capture_output=True, text=True, env=e)
    env_final = (dst / ".env").read_text()
    check("fichier absent à la destination → déplacé",
          (dst / "invoice.yml").read_text() == "x: 1\n" and not (src / "invoice.yml").exists(), r.stdout)
    check("fichier déplacé en 600", stat.S_IMODE((dst / "invoice.yml").stat().st_mode) == 0o600)
    check("dossier de destination en 700", stat.S_IMODE(dst.stat().st_mode) == 0o700)
    check(".env fusionné : clés manquantes ajoutées (export compris)",
          "A=1" in env_final and "export C=3" in env_final and "PM_MAIL_SENDER=karl" in env_final, env_final)
    check(".env fusionné : la valeur côté var/ gagne", "B=valeur-neuve-zq" in env_final and "valeur-ancienne-zq" not in env_final, env_final)
    check("conflit de valeur → ancien .env conservé", (src / ".env").is_file())
    check("fichier déjà présent → laissé en place, destination intacte",
          (src / "timesheet.yml").is_file() and (dst / "timesheet.yml").read_text() == "y: 2\n")
    check("restes signalés par un code retour non nul", r.returncode == 1, str(r.returncode))
    check("aucune valeur affichée", "-zq" not in r.stdout and "A=1" not in r.stdout, r.stdout)

with tempfile.TemporaryDirectory() as t:
    tmp = Path(t)
    src = tmp / "home-config" / "mmi-pm"; src.mkdir(parents=True)
    (src / ".env").write_text("A=1\n")
    r = subprocess.run([sys.executable, str(MIGR)], capture_output=True, text=True, env=env_isole(tmp))
    check("sans conflit : ancien dossier supprimé", r.returncode == 0 and not src.exists(), r.stdout + r.stderr)
    r = subprocess.run([sys.executable, str(MIGR), "--dry-run"], capture_output=True, text=True,
                       env=env_isole(tmp, PM_STATE_DIR=str(tmp / "envs" / "repo-rm1" / "var")))
    check("destination dans un worktree (envs/) → refus", r.returncode != 0 and "worktree" in r.stderr, r.stderr)

print("\n[RM3318] préférences mail (karl-mail-send)")
spec = importlib.util.spec_from_file_location("karl_mail_send", HERE / "karl-mail-send.py")
kms = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kms)
sauve = {k: os.environ.get(k) for k in ("PM_MAIL_SIGNATURE", "PM_MAIL_FROM_NAME")}
try:
    os.environ["PM_MAIL_SIGNATURE"] = "Karl, pour le compte de X\\niProspective"
    os.environ.pop("PM_MAIL_FROM_NAME", None)
    nom, sig = kms.preferences_mail()
    check("\\n de la signature interprété", sig == "Karl, pour le compte de X\niProspective", repr(sig))
    check("nom d'affichage par défaut conservé", nom == kms.FROM_NAME)
    os.environ["PM_MAIL_FROM_NAME"] = "Karl pour X"
    check("nom d'affichage surchargé", kms.preferences_mail()[0] == "Karl pour X")
    corps = kms.signer("Bonjour\n", sig)
    check("signature ajoutée après le délimiteur standard", corps.endswith("\n\n-- \n" + sig + "\n"), repr(corps))
    check("pas de doublon si le corps la porte déjà", kms.signer(corps, sig) == corps)
    check("signature vide → corps inchangé", kms.signer("Bonjour\n", "") == "Bonjour\n")
finally:
    for k, v in sauve.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v

print(f"\n{ok} ok, {ko} échec(s)")
sys.exit(1 if ko else 0)
