#!/usr/bin/env python3
"""Tests du daemon multi-instances — L2/RM2683.

Lancer : python3 scripts/test_vault_agentd_multi.py

Fait tourner un vrai `vault-agentd` sur un socket temporaire, avec un faux `bw` en
tête de PATH et un `pm.config.yml` de test déclarant DEUX instances de vault. Aucun
vault réel, aucun secret réel, aucun réseau.

Ce que ça prouve :
  - deux instances déverrouillées en parallèle, sans interférence ;
  - `LOCK <slug>` n'atteint que la sienne, et le daemon survit ;
  - l'expiration d'inactivité est **par instance** ;
  - `STATUS <slug>` garde le format historique, `STATUS` nu liste tout ;
  - une instance inconnue est refusée (jamais résolue sur le vault par défaut) ;
  - les appels sans slug continuent de viser l'instance par défaut.
"""
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent
DAEMON = _HERE / "vault-agentd.py"

# Deux items distincts, un par instance : c'est ce qui rend l'isolation VISIBLE.
ITEM_IPRO = {"id": "u-ipro", "name": "prod-db",
             "login": {"password": "PWD-IPRO", "username": "user-ipro"}}
ITEM_CLIENT = {"id": "u-cli", "name": "prod-db",
               "login": {"password": "PWD-CLIENT", "username": "user-client"}}

# Le faux `bw` distingue les instances par l'URL passée dans la session de test :
# le daemon appelle `bw --session <token>`, et nos tokens encodent l'instance.
FAKE_BW = """#!/usr/bin/env python3
import json, sys
IPRO = json.loads(%r)
CLI  = json.loads(%r)
a = sys.argv[1:]
session = a[a.index("--session") + 1] if "--session" in a else ""
item = CLI if "client" in session else IPRO
if a[:2] == ["get", "item"]:
    print(json.dumps(item)); sys.exit(0)
if a[:2] == ["list", "items"]:
    print(json.dumps([item])); sys.exit(0)
if a[:1] == ["sync"]:
    sys.exit(0)
print("unexpected: %%s" %% a, file=sys.stderr); sys.exit(1)
""" % (json.dumps(ITEM_IPRO), json.dumps(ITEM_CLIENT))

# Config de test : celle du dépôt, avec une SECONDE instance de vault ajoutée.
# Repartir du fichier réel évite de maintenir un faux `pm.config.yml` (qui doit
# porter `paths:`, `roots:`… sous peine de faire échouer `PMConfig.load`).
EXTRA_INSTANCE = (
    '    vw-clientx:  { axis: secret, type: vaultwarden, '
    'url: "https://vault.client-x.test" }\n')


def _config_avec_deux_vaults():
    src = (_HERE.parent / "pm.config.yml").read_text(encoding="utf-8")
    ancre = "    vw-ipro:"
    i = src.index(ancre)
    fin = src.index("\n", i) + 1
    return src[:fin] + EXTRA_INSTANCE + src[fin:]


def _ask(sock_path, line, timeout=10):
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(timeout)
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


class Daemon:
    """Un daemon de test, avec sa config, son faux `bw` et son socket."""

    def __init__(self, work, idle_timeout=None, tag="d", supervisor_interval=None):
        self.work = work
        self.sock = str(work / f"{tag}.sock")
        self.env = dict(os.environ)
        self.env["PATH"] = f"{work}/bin:{self.env['PATH']}"
        self.env["VAULT_SOCK"] = self.sock
        self.env["VAULT_LOCK_AT_HOUR"] = "-1"
        self.env["PM_CONFIG"] = str(work / "pm.config.yml")
        self.env["PM_CORE_DIR"] = str(work)
        self.args = [sys.executable, str(DAEMON)]
        if idle_timeout is not None:
            self.args += ["--idle-timeout", str(idle_timeout)]
        if supervisor_interval is not None:
            self.args += ["--supervisor-interval", str(supervisor_interval)]
        self.log = open(work / f"{tag}.log", "w")
        self.proc = None

    def __enter__(self):
        self.proc = subprocess.Popen(self.args, env=self.env,
                                     stdout=self.log, stderr=self.log,
                                     cwd=str(self.work))
        if not _wait_socket(self.sock):
            raise RuntimeError("daemon de test non démarré")
        return self

    def __exit__(self, *_):
        if self.proc:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.log.close()

    def ask(self, line):
        return _ask(self.sock, line)

    @property
    def alive(self):
        return self.proc.poll() is None


def _workdir(td):
    work = Path(td)
    (work / "bin").mkdir()
    fake = work / "bin" / "bw"
    fake.write_text(FAKE_BW)
    fake.chmod(0o755)
    (work / "pm.config.yml").write_text(_config_avec_deux_vaults())
    # `PMConfig.load(<dir>)` cherche aussi les scripts à côté : on lie le dossier
    # scripts/ du dépôt pour que la config de test reste une simple surcouche.
    (work / "scripts").symlink_to(_HERE)
    return work


# ── Tests ────────────────────────────────────────────────────────────────────
def test_deux_instances_isolees():
    """Deux vaults déverrouillés en parallèle rendent CHACUN son propre secret."""
    with tempfile.TemporaryDirectory(prefix="multi-") as td:
        work = _workdir(td)
        with Daemon(work) as d:
            assert d.ask("SET-SESSION vw-ipro tok-ipro").strip() == "OK"
            assert d.ask("SET-SESSION vw-clientx tok-client").strip() == "OK"
            a = d.ask("GET secret://vw-ipro/coll/prod-db password").strip()
            b = d.ask("GET secret://vw-clientx/coll/prod-db password").strip()
            assert a == "PWD-IPRO", a
            assert b == "PWD-CLIENT", b
            # …et l'URI sans slug vise bien l'instance par défaut.
            c = d.ask("GET secret:coll/prod-db password").strip()
            assert c == "PWD-IPRO", c


def test_lock_par_instance():
    """`LOCK <slug>` ne verrouille que la sienne ; le daemon survit."""
    with tempfile.TemporaryDirectory(prefix="multi-") as td:
        work = _workdir(td)
        with Daemon(work) as d:
            d.ask("SET-SESSION vw-ipro tok-ipro")
            d.ask("SET-SESSION vw-clientx tok-client")
            assert d.ask("LOCK vw-clientx").strip() == "OK"
            time.sleep(0.3)
            assert d.alive, "le daemon ne doit pas quitter : une instance reste ouverte"
            assert d.ask("GET secret://vw-clientx/coll/prod-db").strip() == "ERR locked"
            assert d.ask("GET secret://vw-ipro/coll/prod-db password").strip() == "PWD-IPRO"


def test_lock_global_quitte():
    """`LOCK` nu garde le comportement historique : tout verrouiller et quitter."""
    with tempfile.TemporaryDirectory(prefix="multi-") as td:
        work = _workdir(td)
        with Daemon(work) as d:
            d.ask("SET-SESSION vw-ipro tok-ipro")
            d.ask("SET-SESSION vw-clientx tok-client")
            assert d.ask("LOCK").strip() == "OK"
            fin = time.time() + 3
            while time.time() < fin and d.alive:
                time.sleep(0.05)
            assert not d.alive, "le daemon doit quitter après un LOCK global"


def test_lock_derniere_instance_quitte():
    """Verrouiller la DERNIÈRE instance ouverte fait quitter le daemon (iso mono-instance)."""
    with tempfile.TemporaryDirectory(prefix="multi-") as td:
        work = _workdir(td)
        with Daemon(work) as d:
            d.ask("SET-SESSION vw-ipro tok-ipro")
            assert d.ask("LOCK vw-ipro").strip() == "OK"
            fin = time.time() + 3
            while time.time() < fin and d.alive:
                time.sleep(0.05)
            assert not d.alive, "plus aucune instance ouverte → le daemon quitte"


def test_expiration_par_instance():
    """L'inactivité expire instance par instance, pas globalement.

    TTL d'1 s, superviseur toutes les 0,25 s : on maintient UNE des deux instances
    active par des accès réguliers. Attendu : l'inactive tombe, l'active survit —
    c'est tout l'intérêt d'un compteur par instance.
    """
    with tempfile.TemporaryDirectory(prefix="multi-") as td:
        work = _workdir(td)
        with Daemon(work, idle_timeout=1, supervisor_interval=0.25, tag="exp") as d:
            d.ask("SET-SESSION vw-ipro tok-ipro")
            d.ask("SET-SESSION vw-clientx tok-client")
            fin = time.time() + 3
            while time.time() < fin:
                d.ask("GET secret://vw-ipro/coll/prod-db password")
                time.sleep(0.3)
            assert d.alive, "une instance reste active : le daemon ne doit pas quitter"
            actif = d.ask("GET secret://vw-ipro/coll/prod-db password").strip()
            assert actif == "PWD-IPRO", f"l'instance utilisée a expiré : {actif!r}"
            inactif = d.ask("STATUS vw-clientx").strip()
            assert inactif == "locked", f"l'instance inactive devait expirer : {inactif!r}"
            assert d.ask("GET secret://vw-clientx/coll/prod-db").strip() == "ERR locked"


def test_status_formats():
    """`STATUS <slug>` = format historique ; `STATUS` nu = une ligne par instance."""
    with tempfile.TemporaryDirectory(prefix="multi-") as td:
        work = _workdir(td)
        with Daemon(work) as d:
            assert d.ask("STATUS vw-ipro").strip() == "locked"
            d.ask("SET-SESSION vw-ipro tok-ipro")
            un = d.ask("STATUS vw-ipro").strip()
            assert un.startswith("unlocked since=") and "idle_timeout=" in un, un
            tableau = d.ask("STATUS").strip().splitlines()
            slugs = {l.split("\t")[0] for l in tableau}
            assert slugs == {"vw-ipro", "vw-clientx"}, slugs
            etats = dict(l.split("\t", 1) for l in tableau)
            assert etats["vw-ipro"].startswith("unlocked "), etats
            assert etats["vw-clientx"] == "locked", etats


def test_instance_inconnue_refusee():
    """Une instance non déclarée est refusée — jamais rabattue sur le défaut."""
    with tempfile.TemporaryDirectory(prefix="multi-") as td:
        work = _workdir(td)
        with Daemon(work) as d:
            d.ask("SET-SESSION vw-ipro tok-ipro")
            r = d.ask("GET secret://vw-inexistant/coll/prod-db password").strip()
            assert r.startswith("ERR unsupported"), r
            assert "vw-inexistant" in r, r
            assert "PWD-IPRO" not in r, "un slug inconnu ne doit RIEN résoudre"


def test_list_et_sync_par_instance():
    with tempfile.TemporaryDirectory(prefix="multi-") as td:
        work = _workdir(td)
        with Daemon(work) as d:
            d.ask("SET-SESSION vw-ipro tok-ipro")
            d.ask("SET-SESSION vw-clientx tok-client")
            # LIST nu → instance par défaut ; LIST-IN <slug> → instance nommée.
            assert "u-ipro" in d.ask("LIST")
            assert "u-cli" in d.ask("LIST-IN vw-clientx")
            assert d.ask("SYNC").strip() == "OK"
            assert d.ask("SYNC vw-clientx").strip() == "OK"
            # LIST-IN sans argument : erreur explicite, pas de plantage.
            assert d.ask("LIST-IN").startswith("ERR")


def test_sans_registre_instance_unique():
    """Sans config providers lisible, le daemon sert la seule instance par défaut."""
    with tempfile.TemporaryDirectory(prefix="multi-") as td:
        work = _workdir(td)
        (work / "pm.config.yml").unlink()          # plus de registre du tout
        with Daemon(work, tag="noreg") as d:
            assert d.ask("SET-SESSION tok-ipro").strip() == "OK"   # forme sans slug
            assert d.ask("GET vaultwarden://o/c/prod-db password").strip() == "PWD-IPRO"
            r = d.ask("GET secret://vw-clientx/coll/prod-db").strip()
            assert r.startswith("ERR unsupported"), r


CASES = [v for k, v in sorted(globals().items()) if k.startswith("test_")]

if __name__ == "__main__":
    fails = 0
    for fn in CASES:
        try:
            fn(); print(f"  ✓ {fn.__name__}")
        except AssertionError as e:
            fails += 1; print(f"  ✗ {fn.__name__} — {e}")
        except Exception as e:  # noqa: BLE001
            fails += 1; print(f"  ✗ {fn.__name__} — ERREUR {type(e).__name__}: {e}")
    print(f"\n{len(CASES) - fails}/{len(CASES)} ok")
    sys.exit(1 if fails else 0)
