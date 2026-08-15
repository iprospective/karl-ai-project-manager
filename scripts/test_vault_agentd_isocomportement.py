#!/usr/bin/env python3
"""Non-régression bout-en-bout de vault-agentd — L0/RM2681.

Lancer : python3 scripts/test_vault_agentd_isocomportement.py

Compare la version **avant refonte** (extraite de git) et la version courante, en
les faisant tourner pour de vrai sur un socket temporaire, avec un faux `bw` en
tête de PATH. Aucun vault réel, aucun secret réel, aucun réseau — le comparatif
porte sur ce que le daemon renvoie au client, ce qui est précisément le contrat
que `resolve-secret.sh` et ses appelants consomment.

Le test échoue si une commande nominale (GET/LIST/STATUS/PING/SYNC) ne rend plus
exactement la même chose qu'avant. Pour les cas d'erreur, il vérifie la **classe**
de réponse (préfixe `ERR`) et non le texte : les messages ont volontairement gagné
un code (`ERR bad_uri: …`), ce que `resolve-secret.sh` traduit toujours par le même
code de sortie 4.

Prérequis : `git` et `nc` (déjà requis par le flux vault).
"""
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent
CURRENT = _HERE / "vault-agentd.py"
BASE_REF = os.environ.get("ISO_BASE_REF", "origin/dev")

# Item factice servi par le faux `bw` — aucune ressemblance avec un vrai secret.
FAKE_ITEM = {
    "id": "uuid-fake-1", "name": "prod-db", "notes": "note libre",
    "login": {"password": "FAKE-PASSWORD", "username": "dbuser",
              "uris": [{"uri": "https://db.invalid"}]},
    "fields": [{"name": "port", "value": "5432"}],
}
FAKE_ITEM_SANS_PWD = {"id": "uuid-fake-2", "name": "note-seule",
                      "notes": "juste une note"}
FAKE_LIST = [FAKE_ITEM, FAKE_ITEM_SANS_PWD]

FAKE_BW = """#!/usr/bin/env python3
import json, sys
ITEM = json.loads(%r)
SANS = json.loads(%r)
LIST = json.loads(%r)
a = sys.argv[1:]
if a[:3] == ["get", "item", "note-seule"]:
    print(json.dumps(SANS)); sys.exit(0)
if a[:2] == ["get", "item"]:
    if a[2] == "absent":
        print("Not found.", file=sys.stderr); sys.exit(1)
    print(json.dumps(ITEM)); sys.exit(0)
if a[:2] == ["list", "items"]:
    print(json.dumps(LIST)); sys.exit(0)
if a[:1] == ["sync"]:
    sys.exit(0)
print("unexpected args: %%s" %% a, file=sys.stderr); sys.exit(1)
""" % (json.dumps(FAKE_ITEM), json.dumps(FAKE_ITEM_SANS_PWD), json.dumps(FAKE_LIST))

# (commande envoyée, comparaison stricte du texte ?)
COMMANDES = [
    ("PING", True),
    ("SET-SESSION faux-token-de-test", True),
    ("STATUS", False),                      # contient des horodatages → variable
    ("GET vaultwarden://org/coll/prod-db", True),
    ("GET vaultwarden://org/coll/prod-db password", True),
    ("GET vaultwarden://org/coll/prod-db username", True),
    ("GET vaultwarden://org/coll/prod-db notes", True),
    ("GET vaultwarden://org/coll/prod-db uri", True),
    ("GET vaultwarden://org/coll/prod-db port", True),          # champ personnalisé
    ("GET vaultwarden://org/coll/prod-db inexistant", True),    # → chaîne vide
    ("GET vaultwarden://org/coll/note-seule", True),            # → JSON complet
    ("LIST", True),
    ("LIST prod", True),
    ("SYNC", True),
    # Cas d'erreur : on compare la classe de réponse, pas le texte.
    ("GET", False),
    ("GET vaultwarden://org/item", False),                      # legacy malformé
    ("GET keepass://fichier/item", False),                      # scheme non géré en L0
    ("GET vaultwarden://org/coll/absent", False),               # item absent côté bw
    ("BIDON", False),
]


def _wait_socket(path, timeout=5.0):
    fin = time.time() + timeout
    while time.time() < fin:
        if os.path.exists(path):
            try:
                s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                s.settimeout(0.3); s.connect(path); s.close()
                return True
            except OSError:
                pass
        time.sleep(0.05)
    return False


def _ask(sock_path, line):
    """Une commande, une réponse — comme le fait `nc -N -U`."""
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(10)
    s.connect(sock_path)
    s.sendall((line + "\n").encode())
    chunks = []
    try:
        while True:
            b = s.recv(65536)
            if not b:
                break
            chunks.append(b)
    except socket.timeout:
        pass
    s.close()
    return b"".join(chunks).decode("utf-8", errors="replace")


def _run_scenario(daemon_path, root, tag, commandes):
    """Lance un daemon, joue les commandes données, rend {commande: réponse}.

    `root` porte le faux `bw` (root/bin) ; `tag` isole socket et log de chaque run."""
    run_dir = root / tag
    run_dir.mkdir(exist_ok=True)
    sock_path = str(run_dir / "agentd.sock")
    env = dict(os.environ)
    env["PATH"] = f"{root}/bin:{env['PATH']}"
    env["VAULT_SOCK"] = sock_path
    env["VAULT_LOCK_AT_HOUR"] = "-1"
    log = open(run_dir / "daemon.log", "w")
    proc = subprocess.Popen([sys.executable, str(daemon_path)],
                            env=env, stdout=log, stderr=log, cwd=str(run_dir))
    try:
        if not _wait_socket(sock_path):
            raise RuntimeError(f"daemon {daemon_path} n'a pas ouvert son socket")
        return {cmd: _ask(sock_path, cmd) for cmd in commandes}
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        log.close()


# resolve-secret.sh, vault déverrouillé : (arguments, code de sortie attendu).
# Le contrat que TOUS les appelants consomment — il ne doit pas bouger.
SH_CASES = [
    (["vaultwarden://org/coll/prod-db", "username"], 0),
    (["secret://vw-ipro/coll/prod-db", "username"], 0),
    (["secret:coll/prod-db#username"], 0),
    ([], 4),                                   # pas d'argument
    (["keepass://f/i"], 4),                    # scheme non géré en L0
    (["secret://autre-vault/coll/i"], 4),      # instance inconnue
]
# Deux états à part, chacun avec son daemon : verrouillé → 2, absent → 3.
SH_CASES_ETATS = 2


def _test_resolve_secret_sh():
    """Vérifie les codes de sortie du script, daemon lancé / verrouillé / absent."""
    script = _HERE / "resolve-secret.sh"
    if shutil.which("nc") is None:
        print("    (nc absent — section ignorée)")
        return 0
    fails = 0
    with tempfile.TemporaryDirectory(prefix="iso-sh-") as td:
        work = Path(td)
        (work / "bin").mkdir()
        fake = work / "bin" / "bw"
        fake.write_text(FAKE_BW)
        fake.chmod(0o755)
        sock = str(work / "agentd.sock")
        env = dict(os.environ)
        env["PATH"] = f"{work}/bin:{env['PATH']}"
        env["VAULT_SOCK"] = sock
        env["VAULT_LOCK_AT_HOUR"] = "-1"

        log = open(work / "daemon.log", "w")
        proc = subprocess.Popen([sys.executable, str(CURRENT)],
                                env=env, stdout=log, stderr=log, cwd=str(work))
        try:
            if not _wait_socket(sock):
                print("    ✗ daemon de test non démarré")
                return len(SH_CASES) + SH_CASES_ETATS
            _ask(sock, "SET-SESSION faux-token-de-test")
            for args, attendu in SH_CASES:
                r = subprocess.run([str(script), *args], env=env,
                                   capture_output=True, text=True)
                ok = r.returncode == attendu
                print(f"    {'✓' if ok else '✗'} resolve-secret.sh {' '.join(args) or '(sans arg)'}"
                      f" → exit {r.returncode}"
                      f"{'' if ok else f' (attendu {attendu})'}")
                fails += 0 if ok else 1
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
            log.close()

        # Vault verrouillé : daemon neuf, aucune session poussée → exit 2.
        sock2 = str(work / "agentd2.sock")
        env2 = dict(env); env2["VAULT_SOCK"] = sock2
        log2 = open(work / "daemon2.log", "w")
        proc2 = subprocess.Popen([sys.executable, str(CURRENT)],
                                 env=env2, stdout=log2, stderr=log2, cwd=str(work))
        try:
            if _wait_socket(sock2):
                r = subprocess.run([str(script), "vaultwarden://org/coll/prod-db"],
                                   env=env2, capture_output=True, text=True)
                ok = r.returncode == 2
                print(f"    {'✓' if ok else '✗'} resolve-secret.sh (vault verrouillé)"
                      f" → exit {r.returncode}{'' if ok else ' (attendu 2)'}")
                fails += 0 if ok else 1
            else:
                print("    ✗ daemon verrouillé non démarré"); fails += 1
        finally:
            proc2.terminate()
            try:
                proc2.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc2.kill()
            log2.close()

        # Daemon absent : socket inexistant → exit 3.
        env3 = dict(env); env3["VAULT_SOCK"] = str(work / "inexistant.sock")
        r = subprocess.run([str(script), "vaultwarden://org/coll/prod-db"],
                           env=env3, capture_output=True, text=True)
        ok = r.returncode == 3
        print(f"    {'✓' if ok else '✗'} resolve-secret.sh (daemon absent)"
              f" → exit {r.returncode}{'' if ok else ' (attendu 3)'}")
        fails += 0 if ok else 1
    return fails


def main():
    if shutil.which("git") is None:
        print("git absent — test ignoré"); return 0
    with tempfile.TemporaryDirectory(prefix="iso-vault-") as td:
        work = Path(td)
        (work / "bin").mkdir()
        fake = work / "bin" / "bw"
        fake.write_text(FAKE_BW)
        fake.chmod(0o755)

        # Version de référence : le fichier tel qu'il était avant la refonte.
        base_src = subprocess.run(
            ["git", "-C", str(_HERE.parent), "show", f"{BASE_REF}:scripts/vault-agentd.py"],
            capture_output=True, text=True)
        if base_src.returncode != 0:
            print(f"référence {BASE_REF} introuvable — test ignoré "
                  f"({base_src.stderr.strip()})")
            return 0
        base = work / "vault-agentd-base.py"
        # La version d'avant n'a pas VAULT_SOCK : on l'injecte pour ne pas
        # toucher au socket de la session en cours.
        src = base_src.stdout.replace(
            'SOCK_PATH = f"{SOCK_DIR}/vault-agentd.sock"',
            'SOCK_PATH = os.environ.get("VAULT_SOCK") or f"{SOCK_DIR}/vault-agentd.sock"')
        assert "VAULT_SOCK" in src, "injection du socket de test impossible"
        base.write_text(src)

        scenario = [c for c, _ in COMMANDES]
        avant = _run_scenario(base, work, "avant", scenario)
        apres = _run_scenario(CURRENT, work, "apres", scenario)

        # Garde anti-faux-positif : deux versions qui échouent PAREIL passeraient
        # la comparaison. On exige donc que le scénario ait vraiment résolu.
        temoin = "GET vaultwarden://org/coll/prod-db password"
        for nom, res in (("avant", avant), ("après", apres)):
            if res.get(temoin) != "FAKE-PASSWORD\n":
                print(f"  ✗ garde : {nom} n'a pas résolu l'item factice "
                      f"({res.get(temoin)!r}) — le faux `bw` n'a pas été utilisé")
                return 1

        # Formes d'URI nouvelles : sans équivalent avant, donc vérifiées seules.
        nouveaux = [
            ("GET secret://vw-ipro/coll/prod-db username", "dbuser\n"),
            ("GET secret:coll/prod-db password", "FAKE-PASSWORD\n"),
            ("GET secret:coll/prod-db#username", "dbuser\n"),
            # Le champ explicite l'emporte sur le `#champ` de l'URI.
            ("GET secret:coll/prod-db#username notes", "note libre\n"),
        ]
        neuf = _run_scenario(CURRENT, work, "neuf-uri",
                             ["SET-SESSION faux-token-de-test"]
                             + [c for c, _ in nouveaux]
                             + ["GET secret://autre-vault/coll/prod-db"])

    fails = 0
    for cmd, strict in COMMANDES:
        a, b = avant.get(cmd, ""), apres.get(cmd, "")
        if strict:
            ok = a == b
            detail = "" if ok else f"\n      avant={a!r}\n      après={b!r}"
        else:
            # Même classe de réponse : ERR ↔ ERR, valeur ↔ valeur.
            ok = (a.startswith("ERR") == b.startswith("ERR"))
            if ok and cmd == "STATUS":
                ok = bool(re.match(r"^(locked|unlocked )", b))
            detail = "" if ok else f"\n      avant={a!r}\n      après={b!r}"
        print(f"  {'✓' if ok else '✗'} {cmd}{'' if strict else '  (classe)'}{detail}")
        fails += 0 if ok else 1

    print("  — formes d'URI nouvelles (version courante seule) —")
    for cmd, attendu in nouveaux:
        got = neuf.get(cmd, "")
        ok = got == attendu
        print(f"  {'✓' if ok else '✗'} {cmd}"
              f"{'' if ok else f' — attendu {attendu!r}, reçu {got!r}'}")
        fails += 0 if ok else 1

    # Un slug inconnu doit être REFUSÉ, jamais résolu en silence dans le vault
    # par défaut : ce serait chercher un secret dans le mauvais coffre.
    inconnu = neuf.get("GET secret://autre-vault/coll/prod-db", "")
    ok = inconnu.startswith("ERR unsupported") and "autre-vault" in inconnu
    print(f"  {'✓' if ok else '✗'} GET secret://autre-vault/… refusé explicitement"
          f"{'' if ok else f' — reçu {inconnu!r}'}")
    fails += 0 if ok else 1

    print("  — resolve-secret.sh : codes de sortie —")
    fails += _test_resolve_secret_sh()

    total = len(COMMANDES) + len(nouveaux) + 1 + len(SH_CASES) + SH_CASES_ETATS
    print(f"\n{total - fails}/{total} ok")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
