#!/usr/bin/env python3
"""Tests RM3070 L5 — une instance de karl-agent par développeur.

Le multi-utilisateur se tient par le routage : un gabarit système `karl-agent@<login>` par
développeur, un front unique devant. Ce que ces tests protègent :

  * **deux instances ne partagent pas un port** — le conflit se verrait sinon au démarrage de la
    seconde, avec un message de systemd qui ne dit pas laquelle est en cause ;
  * **rien n'est écrit dans /etc par le script** — poser un fichier système exige root, et cette
    barrière est voulue ;
  * **KillMode=process survit au gabarit** : sans lui, un restart tue toutes les sessions tmux ;
  * **l'unité tourne sous le développeur** (`User=%i`), pas sous le compte de service.

Lancer : python3 scripts/test_pm_karl_service.py
"""
import importlib.util
import os
import pathlib
import pwd
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
FAIL = []


def check(label, cond, detail=""):
    print(("  ✓ " if cond else "  ✗ ") + label + ("" if cond else f"  {detail}"))
    if not cond:
        FAIL.append(label)


moi = pwd.getpwuid(os.getuid()).pw_name
etc = tempfile.mkdtemp(prefix="karl-etc-")
os.environ["KARL_SERVICE_ETC"] = etc
spec = importlib.util.spec_from_file_location("ks", HERE / "pm-karl-service.py")
K = importlib.util.module_from_spec(spec); spec.loader.exec_module(K)

print("[L5] le gabarit d'unité")
unit = (HERE.parent / "deploy" / "karl-agent" / "karl-agent@.service").read_text(encoding="utf-8")
check("tourne sous le DÉVELOPPEUR (User=%i), pas sous le compte de service", "User=%i" in unit)
check("KillMode=process conservé — sinon un restart tue toutes ses sessions tmux",
      "KillMode=process" in unit)
check("le port vient d'un fichier par développeur, obligatoire",
      "EnvironmentFile=/etc/karl-agent/%i.env" in unit and "EnvironmentFile=-" not in unit)
check("le mode est déclaré multi (L0 le lit, et le contrôle de cohérence avec)",
      "KARL_INSTALL_MODE=multi" in unit)
check("aucun chemin d'instance en dur : @PM_ROOT@ est rendu à la pose (L1)",
      "/zfs/workspaces" not in unit and "@PM_ROOT@" in unit)
check("journaux par développeur, état commun (RM2992 : l'instance le partage)",
      "KARL_AGENT_LOG_DIR=/var/lib/karl-agent/%i" in unit and "KARL_AGENT_STATE_DIR" not in unit)

print("\n[L5] attribution des ports : le conflit est refusé AVANT systemd")
check("un port libre passe", K.valide(moi, 9881, {}) == "")
check("le port d'un AUTRE développeur est refusé, en le nommant",
      "déjà attribué à bob" in K.valide(moi, 9881, {"bob": 9881}), K.valide(moi, 9881, {"bob": 9881}))
check("…mais reposer SON propre port n'est pas un conflit", K.valide(moi, 9881, {moi: 9881}) == "")
check("un port privilégié est refusé", "hors plage" in K.valide(moi, 80, {}))
check("un compte système inexistant est refusé", "compte système" in K.valide("nexistepas-xyz", 9881, {}))
check("un login qui n'en est pas un est refusé", "login invalide" in K.valide("../etc/passwd", 9881, {}))

print("\n[L5] ce que le script écrit — et ce qu'il n'écrit pas")
with tempfile.TemporaryDirectory() as d:
    K.main(["--user", moi, "--port", "9881", "--out", d])
    ecrits = sorted(p.name for p in pathlib.Path(d).iterdir())
    check("les trois pièces sont rendues (env, unité, fragment de front)",
          ecrits == sorted([f"{moi}.env", "karl-agent@.service", f"karl-{moi}.conf"]), str(ecrits))
    env = pathlib.Path(d, f"{moi}.env").read_text()
    check("le fichier d'environnement porte le port", f"KARL_AGENT_PORT=9881" in env)
    vhost = pathlib.Path(d, f"karl-{moi}.conf").read_text()
    check("le front route par upgrade=websocket, jamais ProxyPass ws:// (RM2700)",
          "upgrade=websocket" in vhost and "ws://" not in vhost, vhost)
    rendu = pathlib.Path(d, "karl-agent@.service").read_text()
    check("l'unité rendue ne contient plus de marqueur", "@PM_ROOT@" not in rendu)
check("rien n'a été écrit dans /etc : la pose système reste un geste root",
      not list(pathlib.Path(etc).iterdir()), str(list(pathlib.Path(etc).iterdir())))

print("\n" + ("ÉCHEC — " + ", ".join(FAIL) if FAIL else "OK — service d'équipe, une instance par développeur (RM3070 L5)"))
sys.exit(1 if FAIL else 0)
