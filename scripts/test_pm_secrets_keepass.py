#!/usr/bin/env python3
"""Tests du backend KeePass — L3a/RM2684.

Lancer : python3 scripts/test_pm_secrets_keepass.py

Deux moitiés :

1. **Toujours exécutées** — la dégradation. Sans `pykeepass`, sans fichier, ou
   sans passphrase, l'instance doit se signaler proprement (`unreachable` /
   `locked`) et ne jamais faire tomber le reste.
2. **Conditionnelles** — la résolution réelle sur un vrai `.kdbx`, créé par le
   test lui-même. Elles exigent `pykeepass` : sans lui, elles s'annoncent
   IGNORÉES (et le script le dit en clair) plutôt que de passer en silence.

    sudo apt install python3-pykeepass

Aucun réseau, aucun secret réel : le `.kdbx` est fabriqué dans un dossier
temporaire et détruit avec lui.
"""
import importlib.util
import os
import sys
import tempfile
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
from test_support import core_with, core_env  # noqa: E402

_spec = importlib.util.spec_from_file_location("pm_secrets", str(_HERE / "pm_secrets.py"))
pm_secrets = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pm_secrets)

try:
    import pykeepass  # noqa: F401
    HAS_PYKEEPASS = True
except ImportError:
    HAS_PYKEEPASS = False

PASSPHRASE = "phrase-de-test-non-secrete"


def _make_kdbx(dirpath):
    """Fabrique un .kdbx de test : une entrée à la racine, une dans un groupe."""
    from pykeepass import create_database
    path = os.path.join(dirpath, "test.kdbx")
    kp = create_database(path, password=PASSPHRASE)
    kp.add_entry(kp.root_group, "prod-db", "dbuser", "PWD-RACINE",
                 url="https://db.invalid", notes="note libre")
    clients = kp.add_group(kp.root_group, "clients")
    acme = kp.add_group(clients, "acme")
    e = kp.add_entry(acme, "prod-db", "acme-user", "PWD-ACME")
    e.set_custom_property("port", "5432")
    kp.save()
    return path


# ── 1. Dégradation — toujours exécutées ──────────────────────────────────────
def test_declare_dans_la_fabrique():
    b = pm_secrets.get_backend("keepass", name="kdbx-perso", file="/inexistant.kdbx")
    assert b.type == "keepass"
    assert b.caps.needs_unlock and b.caps.listable and b.caps.hierarchical
    assert not b.caps.writable, "lecture seule en V1 (CDC RM2662)"


def test_sans_fichier_declare_unreachable():
    b = pm_secrets.get_backend("keepass", name="kdbx-vide",
                               session_getter=lambda: PASSPHRASE)
    assert b.status() == "unreachable"
    try:
        b.resolve(("prod-db",))
    except pm_secrets.UnreachableError as e:
        assert "FILE" in str(e) or "file" in str(e), e
    else:
        raise AssertionError("sans fichier déclaré → UnreachableError")


def test_fichier_absent_unreachable():
    b = pm_secrets.get_backend("keepass", name="kdbx-perso",
                               file="/n/existe/pas.kdbx",
                               session_getter=lambda: PASSPHRASE)
    assert b.status() == "unreachable"
    try:
        b.resolve(("prod-db",))
    except pm_secrets.UnreachableError as e:
        assert "introuvable" in str(e), e
    else:
        raise AssertionError("fichier absent → UnreachableError")


def test_sans_passphrase_locked():
    """Fichier là, passphrase absente : verrouillé, pas injoignable."""
    with tempfile.TemporaryDirectory(prefix="kp-") as td:
        faux = Path(td) / "vide.kdbx"
        faux.write_bytes(b"")                     # existe, contenu sans importance
        b = pm_secrets.get_backend("keepass", name="kdbx-perso",
                                   file=str(faux), session_getter=lambda: None)
        if not HAS_PYKEEPASS:
            assert b.status() == "unreachable"    # module absent : prioritaire
            return
        assert b.status() == "locked"
        try:
            b.resolve(("prod-db",))
        except pm_secrets.LockedError:
            pass
        else:
            raise AssertionError("sans passphrase → LockedError")


def test_unlock_renvoie_a_l_humain():
    b = pm_secrets.get_backend("keepass", name="kdbx-perso", file="/x.kdbx")
    try:
        b.unlock(passphrase="peu importe")
    except pm_secrets.UnsupportedError as e:
        assert "unlock-vault.sh" in str(e), e
    else:
        raise AssertionError("unlock() doit renvoyer vers unlock-vault.sh")


def test_chemin_depuis_les_creds_du_dev():
    """Le chemin du .kdbx peut venir de `SECRET__<SLUG>__FILE`."""
    var = pm_secrets.creds_env_key("kdbx-perso", "FILE")
    assert var == "SECRET__KDBX_PERSO__FILE", var
    os.environ[var] = "/chemin/depuis/env.kdbx"
    try:
        b = pm_secrets.get_backend("keepass", name="kdbx-perso",
                                   session_getter=lambda: PASSPHRASE)
        try:
            b.resolve(("x",))
        except pm_secrets.UnreachableError as e:
            assert "/chemin/depuis/env.kdbx" in str(e), e
        else:
            raise AssertionError("le chemin des creds doit être utilisé")
    finally:
        os.environ.pop(var, None)


# ── 2. Résolution réelle — exigent pykeepass ─────────────────────────────────
def test_resolution_champs_reels():
    if not HAS_PYKEEPASS:
        raise SkipTest()
    with tempfile.TemporaryDirectory(prefix="kp-") as td:
        path = _make_kdbx(td)
        b = pm_secrets.get_backend("keepass", name="kdbx-perso", file=path,
                                   session_getter=lambda: PASSPHRASE)
        assert b.status() == "unlocked"
        assert b.resolve(("prod-db",), "password") == "PWD-RACINE"
        assert b.resolve(("prod-db",), "username") == "dbuser"
        assert b.resolve(("prod-db",), "notes") == "note libre"
        assert b.resolve(("prod-db",), "uri") == "https://db.invalid"
        # Sans champ demandé → le mot de passe (même contrat que Vaultwarden).
        assert b.resolve(("prod-db",)) == "PWD-RACINE"
        # Champ inconnu → chaîne vide, jamais d'exception.
        assert b.resolve(("prod-db",), "inexistant") == ""


def test_resolution_par_groupe():
    """Deux entrées de même titre : le chemin de groupes les départage."""
    if not HAS_PYKEEPASS:
        raise SkipTest()
    with tempfile.TemporaryDirectory(prefix="kp-") as td:
        path = _make_kdbx(td)
        b = pm_secrets.get_backend("keepass", name="kdbx-perso", file=path,
                                   session_getter=lambda: PASSPHRASE)
        assert b.resolve(("clients", "acme", "prod-db"), "password") == "PWD-ACME"
        assert b.resolve(("acme", "prod-db"), "username") == "acme-user"  # suffixe
        assert b.resolve(("clients", "acme", "prod-db"), "port") == "5432"  # perso
        try:
            b.resolve(("clients", "inconnu", "prod-db"))
        except pm_secrets.NotFoundError:
            pass
        else:
            raise AssertionError("groupe inexistant → NotFoundError")


def test_liste_et_mauvaise_passphrase():
    if not HAS_PYKEEPASS:
        raise SkipTest()
    with tempfile.TemporaryDirectory(prefix="kp-") as td:
        path = _make_kdbx(td)
        b = pm_secrets.get_backend("keepass", name="kdbx-perso", file=path,
                                   session_getter=lambda: PASSPHRASE)
        noms = [i["name"] for i in b.list()]
        assert noms.count("prod-db") == 2, noms
        assert [i for i in b.list("prod")], "le filtre doit matcher"
        mauvais = pm_secrets.get_backend("keepass", name="kdbx-perso", file=path,
                                         session_getter=lambda: "mauvaise")
        try:
            mauvais.resolve(("prod-db",))
        except pm_secrets.DeniedError:
            pass
        except pm_secrets.UnreachableError as e:
            raise AssertionError(f"une mauvaise passphrase doit donner DeniedError : {e}")
        else:
            raise AssertionError("mauvaise passphrase → DeniedError")


# ── 3. Câblage dans le daemon — toujours exécuté ─────────────────────────────
def test_daemon_sert_une_instance_keepass():
    """Le daemon accepte une instance `keepass` déclarée, sa passphrase, et
    dégrade proprement à la résolution si `pykeepass` manque.

    Ce test vaut même sans la dépendance : il vérifie le CÂBLAGE (registre →
    daemon → backend), qui est la part la plus facile à casser en silence.
    """
    import socket
    import subprocess
    import time

    def ask(sock, line):
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(10); s.connect(sock); s.sendall((line + "\n").encode())
        out = []
        try:
            while True:
                b = s.recv(65536)
                if not b:
                    break
                out.append(b)
        except socket.timeout:
            pass
        s.close()
        return b"".join(out).decode()

    with tempfile.TemporaryDirectory(prefix="kp-daemon-") as td:
        work = Path(td)
        kdbx = work / "test.kdbx"
        if HAS_PYKEEPASS:
            _make_kdbx(str(work))
            kdbx = work / "test.kdbx"
        else:
            kdbx.write_bytes(b"")
        # Core de test VALIDE (RM2749) : sans son `pm.env`, `PMConfig.load`
        # sortait sur `roots.projects_root` non résolu, le daemon dégradait vers
        # la config livrée et `kdbx-test` n'y était évidemment pas déclarée.
        core_with(work, {
            "kdbx-test": {"axis": "secret", "type": "keepass", "file": str(kdbx)}})

        sock = str(work / "agentd.sock")
        env = core_env(work, VAULT_SOCK=sock, VAULT_LOCK_AT_HOUR="-1")
        log = open(work / "daemon.log", "w")
        proc = subprocess.Popen([sys.executable, str(_HERE / "vault-agentd.py")],
                                env=env, stdout=log, stderr=log, cwd=str(work))
        try:
            for _ in range(80):
                if os.path.exists(sock):
                    break
                time.sleep(0.05)
            # Une passphrase peut contenir des espaces : le protocole doit la
            # prendre entière (le reste de la ligne), pas son premier mot.
            assert ask(sock, f"SET-SESSION kdbx-test {PASSPHRASE} avec espaces").strip() == "OK"
            tableau = dict(l.split("\t", 1) for l in ask(sock, "STATUS").strip().splitlines())
            assert "kdbx-test" in tableau, tableau
            assert tableau["kdbx-test"].startswith("unlocked "), tableau
            r = ask(sock, "GET secret://kdbx-test/prod-db password").strip()
            if HAS_PYKEEPASS:
                # Passphrase volontairement fausse (suffixe « avec espaces »).
                assert r.startswith("ERR denied"), r
            else:
                assert r.startswith("ERR unreachable") and "pykeepass" in r, r
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
            log.close()


class SkipTest(Exception):
    """Test conditionnel non exécuté (dépendance absente) — signalé, pas masqué."""


CASES = [v for k, v in sorted(globals().items()) if k.startswith("test_")]

if __name__ == "__main__":
    fails = skipped = 0
    for fn in CASES:
        try:
            fn(); print(f"  ✓ {fn.__name__}")
        except SkipTest:
            skipped += 1; print(f"  ⏭ {fn.__name__} — IGNORÉ (pykeepass absent)")
        except AssertionError as e:
            fails += 1; print(f"  ✗ {fn.__name__} — {e}")
        except Exception as e:  # noqa: BLE001
            fails += 1; print(f"  ✗ {fn.__name__} — ERREUR {type(e).__name__}: {e}")
    total = len(CASES)
    print(f"\n{total - fails - skipped}/{total} ok"
          + (f" — {skipped} IGNORÉS : `sudo apt install python3-pykeepass` "
             f"puis relancer pour valider la résolution réelle" if skipped else ""))
    sys.exit(1 if fails else 0)
