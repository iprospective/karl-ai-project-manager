#!/usr/bin/env python3
"""Tests du backend 1Password (`op`, service account) — RM2711/L3b.

Lancer : python3 scripts/test_pm_secrets_onepassword.py

La CLI `op` n'est pas dans les dépôts Debian et un *service account* suppose un
plan payant : ces tests s'exécutent donc contre un **faux `op`** posé dans un
PATH temporaire. Ce faux binaire imite la sortie RÉELLE de `op` v2, préfixes
`[ERROR] <date> <heure>` compris, et va jusqu'à ajouter la ligne d'usage que la
CLI fait suivre à certaines erreurs — parce qu'un faux binaire plus propre que le
vrai est un faux témoin : c'est exactement ce piège qui avait laissé passer un
mauvais classement d'erreur sur `age` (RM2713).

Ce que les tests NE prouvent pas : que les messages du vrai `op` tombent dans les
bons paniers. Cela demande un vrai jeton — critère resté ouvert sur le ticket.
Le classement est écrit sur la sortie ENTIÈRE, précisément pour qu'un libellé
inattendu dégrade en erreur générique au lieu d'affirmer une fausse cause.

Aucun réseau. Aucune valeur de secret n'est écrite sur disque hors du tmpdir.
"""
import importlib.util
import json
import os
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("pm_secrets", str(_HERE / "pm_secrets.py"))
ps = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ps)

JETON = "ops_JETON-DE-TEST-TRES-RECONNAISSABLE"
MDP = "MotDePasse-Prod-42"

# ── Faux `op` ────────────────────────────────────────────────────────────────
# Il journalise son argv complet dans $OP_FAKE_ARGV : c'est ce qui permet de
# PROUVER que le jeton n'est jamais passé en argument (il serait lisible par
# n'importe qui dans `ps`).
FAKE_OP = r'''import json, os, sys

argv = sys.argv[1:]
trace = os.environ.get("OP_FAKE_ARGV")
if trace:
    with open(trace, "a", encoding="utf-8") as fh:
        fh.write("\0".join(sys.argv) + "\n")

HORO = "2026/08/27 10:15:42"

def erreur(msg, usage=False):
    print(f"[ERROR] {HORO} {msg}", file=sys.stderr)
    if usage:
        # `op` fait suivre certaines erreurs d'une ligne d'usage : la retenir
        # comme « le message » ferait perdre la cause.
        print("Usage:  op item get <item> [flags]", file=sys.stderr)
    sys.exit(1)

if os.environ.get("OP_FAKE_RESEAU"):
    erreur("could not connect to 1Password.com: dial tcp: lookup my.1password.com: no such host")

for k in os.environ:
    if k.startswith("OP_SESSION"):
        erreur(f"session heritee du shell utilisee: {k}")

jeton = os.environ.get("OP_SERVICE_ACCOUNT_TOKEN", "")
if not jeton:
    erreur("authentication required: no account found")
if jeton != os.environ.get("OP_FAKE_JETON", ""):
    erreur("(401) Unauthorized: invalid service account token")

COFFRES = [{"id": "vlt1", "name": "Agents"}, {"id": "vlt2", "name": "Perso"}]
ITEMS = {
  ("Agents", "prod-db"): {
    "id": "it1", "title": "prod-db", "category": "LOGIN",
    "vault": {"id": "vlt1", "name": "Agents"},
    "fields": [
      {"id": "username", "type": "STRING", "purpose": "USERNAME",
       "label": "username", "value": "dbuser"},
      {"id": "password", "type": "CONCEALED", "purpose": "PASSWORD",
       "label": "password", "value": os.environ["OP_FAKE_MDP"]},
      {"id": "notesPlain", "type": "STRING", "purpose": "NOTES",
       "label": "notesPlain", "value": "bascule le 1er du mois"},
      {"id": "abcd", "type": "CONCEALED", "label": "api key", "value": "CLE-API-XYZ"},
    ],
    "urls": [{"label": "admin", "href": "https://admin.example"},
             {"primary": True, "href": "https://db.example"}],
  },
  ("Agents", "note-seule"): {
    "id": "it2", "title": "note-seule", "category": "SECURE_NOTE",
    "vault": {"id": "vlt1", "name": "Agents"},
    "fields": [{"id": "notesPlain", "type": "STRING", "purpose": "NOTES",
                "label": "notesPlain", "value": "procedure de bascule"},
               {"id": "efgh", "type": "STRING", "label": "contact", "value": "ops@x"}],
    "urls": [],
  },
  ("Perso", "prod-db"): {
    "id": "it3", "title": "prod-db", "category": "LOGIN",
    "vault": {"id": "vlt2", "name": "Perso"},
    "fields": [{"id": "password", "type": "CONCEALED", "purpose": "PASSWORD",
                "label": "password", "value": "AUTRE-COFFRE"}],
    "urls": [],
  },
}

def opt(nom, defaut=""):
    return argv[argv.index(nom) + 1] if nom in argv and argv.index(nom) + 1 < len(argv) else defaut

if argv[:1] == ["whoami"]:
    print(json.dumps({"user_type": "SERVICE_ACCOUNT", "url": "https://my.1password.com"}))
    sys.exit(0)
if argv[:2] == ["vault", "list"]:
    print(json.dumps(COFFRES)); sys.exit(0)
if argv[:2] == ["item", "list"]:
    v = opt("--vault")
    if v and v not in [c["name"] for c in COFFRES]:
        erreur(f'"{v}" isn\'t a vault. Specify the vault with its UUID or name.')
    print(json.dumps([{"id": it["id"], "title": it["title"], "vault": it["vault"]}
                      for (cv, _), it in ITEMS.items() if not v or cv == v]))
    sys.exit(0)
if argv[:2] == ["item", "get"]:
    nom = argv[2] if len(argv) > 2 else ""
    v = opt("--vault")
    if v and v not in [c["name"] for c in COFFRES]:
        erreur(f'"{v}" isn\'t a vault. Specify the vault with its UUID or name.')
    it = ITEMS.get((v, nom))
    if it is None:
        erreur(f'"{nom}" isn\'t an item. Specify the item with its UUID, name, or domain.',
               usage=True)
    print(json.dumps(it)); sys.exit(0)
erreur(f"unknown command {' '.join(argv)!r}")
'''


class Bac:
    """PATH temporaire portant le faux `op`, plus l'environnement qui va avec."""

    def __init__(self, avec_op=True, jeton=JETON):
        self.dir = tempfile.TemporaryDirectory(prefix="op-")
        self.root = Path(self.dir.name)
        self.trace = self.root / "argv.log"
        bindir = self.root / "bin"
        bindir.mkdir()
        if avec_op:
            exe = bindir / "op"
            # Shebang sur l'interpréteur COURANT : le PATH du bac est réduit au
            # seul dossier du faux binaire (pour qu'aucun `op` réel ne s'y
            # glisse), donc `/usr/bin/env python3` n'y résoudrait rien.
            exe.write_text(f"#!{sys.executable}\n" + FAKE_OP, encoding="utf-8")
            exe.chmod(exe.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
        self.env = {
            "PATH": str(bindir),                   # PATH RÉDUIT : pas d'`op` réel
            "OP_FAKE_ARGV": str(self.trace),
            "OP_FAKE_JETON": jeton,
            "OP_FAKE_MDP": MDP,
        }

    def __enter__(self):
        self._sauve = {k: os.environ.get(k) for k in
                       list(self.env) + ["SECRET__OP_TEST__SERVICE_ACCOUNT_TOKEN"]}
        os.environ.update(self.env)
        return self

    def __exit__(self, *a):
        for k, v in self._sauve.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        self.dir.cleanup()

    def backend(self, jeton=JETON, **kw):
        if jeton is None:
            os.environ.pop("SECRET__OP_TEST__SERVICE_ACCOUNT_TOKEN", None)
        else:
            os.environ["SECRET__OP_TEST__SERVICE_ACCOUNT_TOKEN"] = jeton
        kw.setdefault("vault", "Agents")
        return ps.BACKENDS["onepassword"](name="op-test", **kw)

    def argv_vus(self):
        if not self.trace.exists():
            return []
        return [l.split("\0") for l in self.trace.read_text(encoding="utf-8").splitlines()]


def lire(b, uri):
    ref = ps.parse_uri(uri)
    return b.resolve(ref.path, ref.field)


def attend(exc_type, code, fn):
    try:
        fn()
    except ps.SecretError as e:
        assert isinstance(e, exc_type), f"attendu {exc_type.__name__}, reçu {type(e).__name__} : {e}"
        assert e.code == code, f"code attendu {code!r}, reçu {e.code!r} : {e}"
        return e
    raise AssertionError(f"aucune erreur levée (attendu {exc_type.__name__})")


# ── Tests ────────────────────────────────────────────────────────────────────
def test_capabilities_pas_de_deverrouillage():
    """Le jeton EST la session : `needs_unlock=False`, comme age et Nextcloud."""
    with Bac() as bac:
        c = bac.backend().caps
        assert c.needs_unlock is False and c.listable and c.hierarchical
        assert c.writable is False, "lecture seule (décision CDC RM2662)"


def test_resolution_du_mot_de_passe():
    with Bac() as bac:
        b = bac.backend()
        assert lire(b, "secret://op-test/Agents/prod-db#password") == MDP
        # `vault:` déclaré → le coffre peut être omis de l'URI.
        assert lire(b, "secret://op-test/prod-db#password") == MDP


def test_correspondance_des_champs():
    """username / notes / uri / champ personnalisé, via `purpose` puis `label`."""
    with Bac() as bac:
        b = bac.backend()
        u = "secret://op-test/Agents/prod-db"
        assert lire(b, u + "#username") == "dbuser"
        assert lire(b, u + "#notes") == "bascule le 1er du mois"
        assert lire(b, u + "#uri") == "https://db.example", "l'URL `primary` d'abord"
        assert lire(b, u + "#api key") == "CLE-API-XYZ", "champ personnalisé par label"
        assert lire(b, u + "#inexistant") == "", "champ inconnu → chaîne vide (contrat commun)"


def test_sans_champ_demande():
    """Mot de passe s'il existe ; sinon un résumé qui ne cite QUE des noms."""
    with Bac() as bac:
        b = bac.backend()
        assert lire(b, "secret://op-test/Agents/prod-db") == MDP
        resume = json.loads(lire(b, "secret://op-test/Agents/note-seule"))
        assert resume["title"] == "note-seule"
        assert "contact" in resume["fields"] and "notesPlain" in resume["fields"]
        assert "procedure de bascule" not in json.dumps(resume), \
            "le résumé ne doit citer aucune VALEUR (tripwire 11)"


def test_le_coffre_de_l_uri_departage_les_homonymes():
    with Bac() as bac:
        b = bac.backend()
        assert lire(b, "secret://op-test/Agents/prod-db#password") == MDP
        assert lire(b, "secret://op-test/Perso/prod-db#password") == "AUTRE-COFFRE"


def test_jeton_jamais_en_argument():
    """`ps` ne doit jamais montrer le jeton : il passe par l'environnement."""
    with Bac() as bac:
        lire(bac.backend(), "secret://op-test/Agents/prod-db#password")
        appels = bac.argv_vus()
        assert appels, "le faux `op` n'a pas été appelé"
        for argv in appels:
            assert JETON not in " ".join(argv), f"jeton en argument : {argv}"
            assert not any("token" in a.lower() for a in argv), argv


def test_jeton_jamais_dans_les_messages():
    with Bac() as bac:
        b = bac.backend(jeton="ops_MAUVAIS-JETON-RECONNAISSABLE")
        e = attend(ps.DeniedError, "denied",
                   lambda: lire(b, "secret://op-test/Agents/prod-db#password"))
        assert "ops_MAUVAIS" not in str(e), str(e)


def test_op_absente():
    """Dépendance optionnelle : l'instance est `unreachable`, avec la marche à suivre."""
    with Bac(avec_op=False) as bac:
        b = bac.backend()
        e = attend(ps.UnreachableError, "unreachable",
                   lambda: lire(b, "secret://op-test/Agents/prod-db#password"))
        assert "développeur" in str(e) or "developer.1password.com" in str(e), str(e)
        assert b.status() == "unreachable"


def test_jeton_absent():
    with Bac() as bac:
        b = bac.backend(jeton=None)
        e = attend(ps.UnreachableError, "unreachable",
                   lambda: lire(b, "secret://op-test/Agents/prod-db#password"))
        assert "SECRET__OP_TEST__SERVICE_ACCOUNT_TOKEN" in str(e), str(e)
        assert b.status() == "unreachable"


def test_jeton_refuse_est_denied_pas_locked():
    """Personne ne peut « déverrouiller » un jeton refusé : il faut en émettre un autre."""
    with Bac() as bac:
        b = bac.backend(jeton="ops_MAUVAIS")
        attend(ps.DeniedError, "denied",
               lambda: lire(b, "secret://op-test/Agents/prod-db#password"))
        assert b.status() == "locked", "joignable mais accès refusé"


def test_item_inconnu():
    with Bac() as bac:
        e = attend(ps.NotFoundError, "not_found",
                   lambda: lire(bac.backend(), "secret://op-test/Agents/absent#password"))
        # La cause, pas la ligne d'usage que `op` ajoute derrière.
        assert "isn't an item" in str(e), str(e)
        assert "Usage:" not in str(e), f"la ligne d'usage a été retenue : {e}"


def test_coffre_inconnu():
    with Bac() as bac:
        attend(ps.NotFoundError, "not_found",
               lambda: lire(bac.backend(), "secret://op-test/Absent/prod-db#password"))


def test_panne_reseau_nest_pas_un_jeton_refuse():
    """Un échec de connexion cite le point d'accès : il ne doit pas passer pour `denied`."""
    with Bac() as bac:
        os.environ["OP_FAKE_RESEAU"] = "1"
        try:
            b = bac.backend()
            attend(ps.UnreachableError, "unreachable",
                   lambda: lire(b, "secret://op-test/Agents/prod-db#password"))
            assert b.status() == "unreachable"
        finally:
            os.environ.pop("OP_FAKE_RESEAU", None)


def test_session_du_shell_neutralisee():
    """Un `OP_SESSION_*` hérité résoudrait avec la mauvaise identité."""
    with Bac() as bac:
        os.environ["OP_SESSION_moncompte"] = "session-du-shell"
        try:
            assert lire(bac.backend(), "secret://op-test/Agents/prod-db#password") == MDP
        finally:
            os.environ.pop("OP_SESSION_moncompte", None)


def test_uri_sans_coffre_et_sans_defaut():
    with Bac() as bac:
        b = bac.backend(vault="")
        e = attend(ps.UriError, "bad_uri", lambda: lire(b, "secret://op-test/prod-db"))
        assert "vault:" in str(e), str(e)


def test_status_et_unlock():
    with Bac() as bac:
        b = bac.backend()
        assert b.status() == "unlocked"
        attend(ps.UnsupportedError, "unsupported", b.unlock)


def test_listing():
    with Bac() as bac:
        noms = [r["name"] for r in bac.backend().list()]
        assert "prod-db" in noms and "note-seule" in noms
        assert [r["collections"] for r in bac.backend().list()] == [["Agents"], ["Agents"]]
        # Sans coffre par défaut, on balaye tous les coffres.
        tous = bac.backend(vault="").list()
        assert {r["collections"][0] for r in tous} == {"Agents", "Perso"}
        assert bac.backend().list(filt="prod") == [
            r for r in bac.backend().list() if "prod" in r["name"]]


def test_extraction_du_message_derriere_le_prefixe():
    """`[ERROR] <date> <heure> cause…` → `cause…`, et la ligne d'usage est ignorée."""
    brut = ('[ERROR] 2026/08/27 10:15:42 "x" isn\'t an item.\n'
            "Usage:  op item get <item> [flags]\n")
    assert ps._derniere_ligne_op(brut) == '"x" isn\'t an item.'
    assert ps._derniere_ligne_op("") == "sans message"
    assert ps._derniere_ligne_op("message nu") == "message nu"


def test_enregistre_dans_la_fabrique():
    assert ps.BACKENDS["onepassword"] is ps.OnePasswordBackend
    b = ps.get_backend("onepassword", name="op-test", vault="Agents")
    assert isinstance(b, ps.OnePasswordBackend)


def test_diagnostic_shell_ne_montre_que_des_noms():
    """`unlock-vault.sh --print-instance` : des NOMS de clés, jamais les valeurs."""
    with Bac() as bac:
        env = dict(os.environ)
        env["SECRET__OP_TEST__SERVICE_ACCOUNT_TOKEN"] = JETON
        env["VAULT_INSTANCE"] = "op-test"
        env["PRINT_INSTANCE"] = "1"
        env["PATH"] = env["PATH"] + ":" + os.defpath
        p = subprocess.run(["bash", str(_HERE / "unlock-vault.sh"), "--print-instance"],
                           capture_output=True, text=True, env=env, timeout=60)
        sortie = p.stdout + p.stderr
        assert JETON not in sortie, sortie
        # L'instance n'est pas déclarée dans le registre livré : le script doit
        # le dire, pas prétendre l'avoir trouvée.
        assert "op-test" in sortie, sortie


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    echecs = 0
    for nom, fn in tests:
        try:
            fn()
            print(f"  ✓ {nom}")
        except Exception as e:  # noqa: BLE001 — un runner rapporte tout
            echecs += 1
            print(f"  ✗ {nom} : {type(e).__name__}: {e}")
    print(f"\n{len(tests) - echecs}/{len(tests)} tests passés")
    sys.exit(1 if echecs else 0)
