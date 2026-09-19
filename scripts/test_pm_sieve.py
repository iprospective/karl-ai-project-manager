#!/usr/bin/env python3
"""Tests pm-sieve (RM3171) — protocole ManageSieve sans serveur, puis gardes d'écriture contre un faux serveur.

Lancer : python3 scripts/test_pm_sieve.py
"""
import importlib.util
import io
import re
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("pm_sieve", HERE / "pm-sieve.py")
ps = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ps)


class Protocole(unittest.TestCase):
    def test_quote_echappe(self):
        self.assertEqual(ps.quote('a"b\\c'), '"a\\"b\\\\c"')

    def test_quote_refuse_multiligne(self):
        with self.assertRaises(ValueError):
            ps.quote("a\nb")

    def test_literal_non_synchronisant_compte_les_octets(self):
        self.assertEqual(ps.literal("é\r\n"), b"{4+}\r\n\xc3\xa9\r\n")

    def test_tokens(self):
        self.assertEqual(ps.tokens('"roundcube" ACTIVE'), ["roundcube", "ACTIVE"])
        self.assertEqual(ps.tokens('"a \\"b\\"" x'), ['a "b"', "x"])

    def test_status(self):
        self.assertEqual(ps.parse_status('OK "Logged in."'), ("OK", "", "Logged in."))
        self.assertEqual(ps.parse_status('NO (NONEXISTENT) "Script does not exist."'),
                         ("NO", "NONEXISTENT", "Script does not exist."))
        self.assertEqual(ps.parse_status("BYE"), ("BYE", "", ""))
        self.assertIsNone(ps.parse_status('"SIEVE" "fileinto"'))

    def test_capacites(self):
        caps = ps.parse_capabilities(['"IMPLEMENTATION" "Dovecot Pigeonhole"', '"SIEVE" "fileinto copy"',
                                      '"STARTTLS"', '"VERSION" "1.0"'])
        self.assertEqual(caps["STARTTLS"], "")
        self.assertEqual(caps["VERSION"], "1.0")

    def test_listscripts(self):
        self.assertEqual(ps.parse_listscripts(['"a"', '"roundcube" ACTIVE']), (["a", "roundcube"], "roundcube"))
        self.assertEqual(ps.parse_listscripts([]), ([], None))

    def test_auth_plain(self):
        self.assertEqual(ps.base64.b64decode(ps.auth_plain("u", "p")), b"\0u\0p")

    def test_boite(self):
        self.assertTrue(ps.same_account("Karl@iprospective.fr ", "karl@iprospective.fr"))
        self.assertFalse(ps.same_account("mathieu@iprospective.fr", "karl@iprospective.fr"))
        self.assertFalse(ps.same_account("", "karl@iprospective.fr"))

    def test_nom(self):
        ps.check_name("roundcube")
        for bad in ("", "a b", '"x"', "../x", "-x"):
            with self.assertRaises(ps.SieveError):
                ps.check_name(bad)

    def test_reponse_avec_litteral(self):
        body = "require [\"fileinto\"];\r\n"
        raw = b"{%d}\r\n" % len(body.encode()) + body.encode() + b"\r\nOK \"Getscript completed.\"\r\n"
        cli = ps.Client(ps.Conn(io.BytesIO(raw), io.BytesIO()))
        st, code, text, items = cli.response()
        self.assertEqual(st, "OK")
        self.assertEqual(items, [body.encode()])

    def test_connexion_coupee(self):
        cli = ps.Client(ps.Conn(io.BytesIO(b'"SIEVE" "x"\r\n'), io.BytesIO()))
        with self.assertRaises(ps.SieveError):
            cli.response()


class FakeServer:
    """Faux Pigeonhole : état (scripts, actif), journal des commandes, validation par un motif."""

    def __init__(self, scripts=None, active=None, checkscript=True):
        self.scripts = dict(scripts or {})
        self.active = active
        self.checkscript = checkscript
        self.log = []
        self.out = b""

    @staticmethod
    def valid(text):
        return "INVALIDE" not in text

    def handle(self, data):
        m = re.match(rb"^(\w+)(.*)\r\n$", data, re.S)
        verb, rest = m.group(1).decode(), m.group(2)
        args, i = [], 0
        while i < len(rest):
            if rest[i:i + 1] == b" ":
                i += 1
            elif rest[i:i + 1] == b'"':
                j = rest.index(b'"', i + 1)
                args.append(rest[i + 1:j].decode()); i = j + 1
            elif rest[i:i + 1] == b"{":
                j = rest.index(b"}", i)
                n = int(rest[i + 1:j].rstrip(b"+"))
                args.append(rest[j + 3:j + 3 + n].decode()); i = j + 3 + n
            else:
                raise AssertionError(rest[i:])
        self.log.append((verb, args))
        ok, no = b'OK "fait"\r\n', b'NO "refus"\r\n'
        if verb == "LISTSCRIPTS":
            lines = b"".join(b'"%s"%s\r\n' % (n.encode(), b" ACTIVE" if n == self.active else b"")
                             for n in self.scripts)
            return lines + ok
        if verb == "GETSCRIPT":
            if args[0] not in self.scripts:
                return b'NO (NONEXISTENT) "absent"\r\n'
            b = self.scripts[args[0]].encode()
            return b"{%d}\r\n" % len(b) + b + b"\r\n" + ok
        if verb == "CHECKSCRIPT":
            return ok if self.valid(args[0]) else b'NO "line 1: error"\r\n'
        if verb == "PUTSCRIPT":
            if not self.valid(args[1]):
                return b'NO "line 1: error"\r\n'
            self.scripts[args[0]] = args[1]
            return ok
        if verb == "DELETESCRIPT":
            if args[0] == self.active:
                return b'NO (ACTIVE) "actif"\r\n'
            self.scripts.pop(args[0], None)
            return ok
        if verb == "SETACTIVE":
            self.active = args[0]
            return ok
        return no


class FakeConn:
    def __init__(self, srv):
        self.srv, self.buf = srv, io.BytesIO()

    def write(self, data):
        pos = self.buf.tell()
        self.buf.write(self.srv.handle(data))
        self.buf.seek(pos)

    def readline(self):
        line = self.buf.readline()
        if not line:
            raise ps.SieveError("fermé")
        return line.rstrip(b"\r\n")

    def read(self, n):
        return self.buf.read(n)


def client(srv):
    cli = ps.Client(FakeConn(srv))
    cli.caps = {"VERSION": "1.0"} if srv.checkscript else {}
    return cli


ORIG = 'require ["fileinto"];\r\nif header :contains "from" "@x" { fileinto "INBOX.Clients"; }\r\n'
NEW = ORIG.replace("@x", "@y")
KARL = "karl@iprospective.fr"


class Ecriture(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp()) / "karl"
        self.msgs = []

    def put(self, srv, text, **kw):
        opts = dict(account=KARL, authenticated=KARL, backup_dir=self.dir, dry_run=False, log=self.msgs.append)
        opts.update(kw)
        return ps.put(client(srv), "roundcube", text, **opts)

    def verbs(self, srv):
        return [v for v, _ in srv.log]

    def test_mauvaise_boite_refus_sans_rien_lire_ni_ecrire(self):
        srv = FakeServer({"roundcube": ORIG}, "roundcube")
        with self.assertRaisesRegex(ps.SieveError, "≠"):
            self.put(srv, NEW, authenticated="mathieu@iprospective.fr")
        self.assertEqual(srv.log, [])
        self.assertEqual(srv.scripts["roundcube"], ORIG)

    def test_script_invalide_laisse_l_original_intact(self):
        srv = FakeServer({"roundcube": ORIG}, "roundcube")
        with self.assertRaisesRegex(ps.SieveError, "refusé par le serveur"):
            self.put(srv, "INVALIDE")
        self.assertEqual(srv.scripts["roundcube"], ORIG)
        self.assertNotIn("PUTSCRIPT", self.verbs(srv))
        self.assertFalse(self.dir.exists())

    def test_invalide_sans_checkscript_nom_temporaire(self):
        srv = FakeServer({"roundcube": ORIG}, "roundcube", checkscript=False)
        with self.assertRaises(ps.SieveError):
            self.put(srv, "INVALIDE")
        self.assertEqual(srv.scripts, {"roundcube": ORIG})

    def test_valide_sans_checkscript_temporaire_supprime(self):
        srv = FakeServer({"roundcube": ORIG}, "roundcube", checkscript=False)
        self.put(srv, NEW)
        self.assertEqual(set(srv.scripts), {"roundcube"})
        self.assertTrue(any(v == "PUTSCRIPT" and a[0].startswith("pm-sieve-check-") for v, a in srv.log))

    def test_dry_run_n_ecrit_rien(self):
        srv = FakeServer({"roundcube": ORIG}, "roundcube")
        self.assertIsNone(self.put(srv, NEW, dry_run=True))
        self.assertEqual(srv.scripts["roundcube"], ORIG)
        self.assertNotIn("PUTSCRIPT", self.verbs(srv))
        self.assertFalse(self.dir.exists())
        self.assertIn("CHECKSCRIPT", self.verbs(srv))   # la validation serveur a bien eu lieu

    def test_ecriture_sauvegarde_octet_pour_octet_avant(self):
        srv = FakeServer({"roundcube": ORIG}, "roundcube")
        saved = self.put(srv, NEW)
        self.assertEqual(saved.read_bytes(), ORIG.encode())
        self.assertEqual(saved.stat().st_mode & 0o777, 0o600)
        self.assertEqual(srv.scripts["roundcube"], NEW)
        self.assertEqual(srv.active, "roundcube")
        v = self.verbs(srv)
        self.assertLess(v.index("CHECKSCRIPT"), v.index("PUTSCRIPT"))
        self.assertEqual(v[-1], "GETSCRIPT")                 # relecture indépendante

    def test_identique_rien_a_faire(self):
        srv = FakeServer({"roundcube": ORIG}, "roundcube")
        self.assertIsNone(self.put(srv, ORIG))
        self.assertNotIn("PUTSCRIPT", self.verbs(srv))

    def test_nouveau_script_sans_sauvegarde(self):
        srv = FakeServer({}, None)
        self.assertIsNone(self.put(srv, NEW))
        self.assertEqual(srv.scripts["roundcube"], NEW)

    def test_suppression_du_script_actif_refusee(self):
        srv = FakeServer({"roundcube": ORIG, "vieux": ORIG}, "roundcube")
        with self.assertRaisesRegex(ps.SieveError, "ACTIF"):
            ps.delete(client(srv), "roundcube", account=KARL, authenticated=KARL)
        self.assertIn("roundcube", srv.scripts)
        ps.delete(client(srv), "vieux", account=KARL, authenticated=KARL)
        self.assertNotIn("vieux", srv.scripts)

    def test_suppression_mauvaise_boite_refusee(self):
        srv = FakeServer({"vieux": ORIG}, None)
        with self.assertRaises(ps.SieveError):
            ps.delete(client(srv), "vieux", account=KARL, authenticated="autre@x.fr")
        self.assertIn("vieux", srv.scripts)


class Secrets(unittest.TestCase):
    def test_aucun_secret_dans_les_messages_d_erreur(self):
        class Srv(FakeServer):
            def handle(self, data):
                return b'NO "Authentication failed."\r\n'
        cli = client(Srv())
        with self.assertRaises(ps.SieveError) as cm:
            cli.login("karl@iprospective.fr", "S3CRET-pass")
        self.assertNotIn("S3CRET", str(cm.exception))
        self.assertNotIn(ps.auth_plain("karl@iprospective.fr", "S3CRET-pass"), str(cm.exception))

    def test_le_secret_ne_passe_pas_par_argv(self):
        src = (HERE / "pm-sieve.py").read_text()
        # Ni option de mot de passe, ni lecture de l'environnement : le vault est la seule source.
        for motif in ("--password", "os.environ", "getenv"):
            self.assertFalse(motif in src, f"{motif!r} trouvé dans pm-sieve.py")


if __name__ == "__main__":
    unittest.main(verbosity=1)
