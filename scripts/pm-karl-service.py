#!/usr/bin/env python3
"""pm-karl-service — une instance de karl-agent par développeur (RM3070, lot L5).

Le mode multi-utilisateur se tient par le ROUTAGE, pas par une réécriture du superviseur :
`karl-agent@<login>.service` (gabarit système) fait tourner une instance sous le compte de
chaque développeur, et un front unique route vers la bonne.

Ce script RÉDIGE les trois pièces et ne les installe pas lui-même : poser un fichier dans
/etc ou recharger systemd exige root, et cette barrière est voulue (§13a). Il imprime donc ce
qu'il y a à écrire — ou l'écrit dans un dossier donné avec `--out` — puis rappelle les deux
commandes root à lancer.

  1. `/etc/karl-agent/<login>.env` — le port de CE développeur (et son jeton s'il en a un) ;
  2. l'unité `karl-agent@.service` rendue depuis `deploy/karl-agent/` (chemins de l'instance) ;
  3. le fragment de reverse-proxy qui envoie `/<login>/` vers son port.

Le port est le seul réglage obligatoire : deux instances sur le même port refuseraient de
démarrer sans dire pourquoi. Le script refuse un port déjà attribué à un autre développeur et
un port hors de la plage non privilégiée.

Usage :
    pm-karl-service.py --user alice --port 9881            # imprime tout
    pm-karl-service.py --user alice --port 9881 --out /tmp/karl-alice
    pm-karl-service.py --list                              # qui est déclaré, sur quel port
"""
import argparse
import os
import pwd
import re
import sys
from pathlib import Path

ETC = Path(os.environ.get("KARL_SERVICE_ETC") or "/etc/karl-agent")
UNIT_SRC = Path(__file__).resolve().parent.parent / "deploy" / "karl-agent" / "karl-agent@.service"
REPO = Path(__file__).resolve().parent.parent
LOGIN_RE = re.compile(r"^[a-z_][a-z0-9_-]{0,31}$")
PORT_MIN, PORT_MAX = 1024, 65535


def env_file(login: str) -> Path:
    return ETC / f"{login}.env"


def declares() -> dict:
    """{login: port} d'après les fichiers d'environnement déjà posés."""
    out = {}
    if not ETC.is_dir():
        return out
    for f in sorted(ETC.glob("*.env")):
        for ligne in f.read_text(encoding="utf-8", errors="replace").splitlines():
            if ligne.startswith("KARL_AGENT_PORT="):
                try:
                    out[f.stem] = int(ligne.split("=", 1)[1].strip())
                except ValueError:
                    pass
    return out


def valide(login: str, port: int, occupes: dict) -> str:
    """Le motif de refus, ou "" si tout va bien. On refuse TÔT : un port en double ne se voit
    qu'au démarrage de la deuxième instance, et le message de systemd ne dit pas laquelle."""
    if not LOGIN_RE.match(login):
        return f"login invalide : {login!r}"
    try:
        pwd.getpwnam(login)
    except KeyError:
        return f"{login} n'a pas de compte système — l'unité tournerait sous un compte inexistant"
    if not PORT_MIN <= port <= PORT_MAX:
        return f"port hors plage non privilégiée ({PORT_MIN}-{PORT_MAX}) : {port}"
    pris = {p: u for u, p in occupes.items() if u != login}
    if port in pris:
        return f"port {port} déjà attribué à {pris[port]}"
    return ""


def rendu_env(login: str, port: int) -> str:
    return (f"# karl-agent — réglages propres à {login} (RM3070 L5). 0640 root:{login}.\n"
            f"# Un secret (jeton du cockpit) se pose ICI, jamais dans l'unité versionnée.\n"
            f"KARL_AGENT_PORT={port}\n")


def rendu_unit() -> str:
    return UNIT_SRC.read_text(encoding="utf-8").replace("@PM_ROOT@", str(REPO))


def rendu_vhost(login: str, port: int) -> str:
    """Le front route /<login>/ vers l'instance de ce développeur. WebSocket compris : un
    ProxyPass `ws://` ne déclenche PAS l'upgrade — le backend verrait un GET nu (RM2700)."""
    return (f"# karl-agent — {login} (RM3070 L5)\n"
            f"<Location /{login}/>\n"
            f"    ProxyPass        http://127.0.0.1:{port}/ upgrade=websocket\n"
            f"    ProxyPassReverse http://127.0.0.1:{port}/\n"
            f"</Location>\n")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--user", help="le login du développeur")
    ap.add_argument("--port", type=int, help="son port (obligatoire, unique)")
    ap.add_argument("--out", help="écrit les fichiers dans ce dossier au lieu de les imprimer")
    ap.add_argument("--list", action="store_true", help="les développeurs déclarés et leurs ports")
    a = ap.parse_args(argv)

    occupes = declares()
    if a.list:
        if not occupes:
            print(f"aucun développeur déclaré dans {ETC}")
        for u, p in sorted(occupes.items(), key=lambda kv: kv[1]):
            print(f"  {u:16} port {p}")
        return 0
    if not (a.user and a.port):
        ap.error("--user et --port sont requis (ou --list)")
    motif = valide(a.user, a.port, occupes)
    if motif:
        sys.exit(f"ERREUR : {motif}")

    pieces = {f"{a.user}.env": rendu_env(a.user, a.port),
              "karl-agent@.service": rendu_unit(),
              f"karl-{a.user}.conf": rendu_vhost(a.user, a.port)}
    if a.out:
        d = Path(a.out)
        d.mkdir(parents=True, exist_ok=True)
        for nom, contenu in pieces.items():
            (d / nom).write_text(contenu, encoding="utf-8")
            print(f"✓ {d / nom}")
    else:
        for nom, contenu in pieces.items():
            print(f"── {nom} " + "─" * max(0, 60 - len(nom)))
            print(contenu)
    print(f"À faire en root (barrière humaine voulue) :\n"
          f"  install -d -m 0755 {ETC} && install -m 0640 -o root -g {a.user} "
          f"<{a.user}.env> {env_file(a.user)}\n"
          f"  install -m 0644 <karl-agent@.service> /etc/systemd/system/karl-agent@.service\n"
          f"  systemctl daemon-reload && systemctl enable --now karl-agent@{a.user}\n"
          f"  puis le fragment de reverse-proxy dans le vhost du front, et `apachectl -t` avant rechargement")
    return 0


if __name__ == "__main__":
    sys.exit(main())
