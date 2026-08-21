#!/usr/bin/env python3
"""Tests RM2712 (L3c) — backend Nextcloud Passwords.

Le backend parle à une API distante : on la remplace par un **vrai serveur HTTP
local** qui reproduit le contrat de l'app Passwords (auth Basic, session, listes
de dossiers et de mots de passe, codes d'erreur). Pas de réseau, pas de compte,
aucun secret réel — mais le vrai chemin de code, jusqu'à urllib.

Ce qui est vérifié en propre :
  - la résolution par chemin de dossier + label, y compris deux items HOMONYMES
    dans des dossiers différents — le piège de ce backend ;
  - un item **chiffré côté client** est REFUSÉ, pas rendu : l'API n'en donne
    qu'un cryptogramme, et le livrer ferait injecter du charabia dans une conf.
    C'est le risque que l'étude demandait de traiter (CDC RM2662 § 6) ;
  - les codes d'erreur traduits (401 → denied, 404 → not_found, 412 → locked,
    serveur muet → unreachable) ;
  - le jeton n'apparaît dans AUCUN message d'erreur.

Lancer : python3 scripts/test_pm_secrets_ncpasswords.py
"""
import base64
import importlib.util
import json
import pathlib
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("pm_secrets", HERE / "pm_secrets.py")
ps = importlib.util.module_from_spec(spec)
sys.modules["pm_secrets"] = ps
spec.loader.exec_module(ps)

fails = []


def check(name, cond):
    print(("✓ " if cond else "✗ ") + name)
    if not cond:
        fails.append(name)


def erreur(fn, *a, **kw):
    try:
        fn(*a, **kw)
        return None
    except ps.SecretError as e:
        return e.code


USER, TOKEN = "karl", "mot-de-passe-application-secret"
MOTDEPASSE = "PWD-prod-db-matnat"

DOSSIERS = [
    {"id": "f-clients", "label": "clients", "parent": None},
    {"id": "f-acme", "label": "acme", "parent": "f-clients"},
    {"id": "f-autre", "label": "autre", "parent": "f-clients"},
]
ITEMS = [
    {"id": "p1", "label": "prod-db", "folder": "f-acme", "cseType": "none",
     "username": "acme_app", "password": MOTDEPASSE, "url": "https://acme.test",
     "notes": "note de test",
     "customFields": json.dumps([{"label": "api_key", "type": "text", "value": "AK-42"}])},
    # homonyme dans un AUTRE dossier : le chemin doit départager
    {"id": "p2", "label": "prod-db", "folder": "f-autre", "cseType": "none",
     "username": "autre_app", "password": "PWD-AUTRE", "url": "", "notes": ""},
    {"id": "p3", "label": "secret-e2e", "folder": "f-acme", "cseType": "CSEv1r1",
     "username": "?", "password": "cryptogramme-illisible", "url": "", "notes": ""},
    {"id": "p4", "label": "a-la-racine", "folder": None, "cseType": "none",
     "username": "root_user", "password": "PWD-RACINE", "url": "", "notes": ""},
]


class Faux(BaseHTTPRequestHandler):
    """Contrat de l'app Passwords, réduit à ce que le backend utilise."""

    exige_session = True      # variables de classe : pilotées par les tests
    defi = False
    app_absente = False

    def log_message(self, *a):
        pass

    def _json(self, code, corps, entetes=None):
        b = json.dumps(corps).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        for k, v in (entetes or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def _auth_ok(self):
        h = self.headers.get("Authorization") or ""
        if not h.startswith("Basic "):
            return False
        try:
            u, _, p = base64.b64decode(h[6:]).decode().partition(":")
        except Exception:                                    # noqa: BLE001
            return False
        return (u, p) == (USER, TOKEN)

    def _route(self):
        prefixe = "/index.php/apps/passwords/api/1.0/"
        return self.path[len(prefixe):] if self.path.startswith(prefixe) else None

    def _servir(self):
        route = self._route()
        if route is None or Faux.app_absente:
            self._json(404, {"status": "error"})
            return
        if not self._auth_ok():
            self._json(401, {"status": "error"})
            return
        if route == "session/request":
            self._json(200, {"challenge": {"type": "pwdv1"}} if Faux.defi else {})
            return
        if route == "session/open":
            self._json(200, {"success": True}, {"X-API-SESSION": "jeton-de-session"})
            return
        if Faux.exige_session and self.headers.get("X-API-SESSION") != "jeton-de-session":
            self._json(412, {"status": "error", "message": "session required"})
            return
        if route == "folder/list":
            self._json(200, DOSSIERS)
            return
        if route == "password/list":
            self._json(200, ITEMS)
            return
        self._json(404, {"status": "error"})

    do_GET = do_POST = _servir


srv = ThreadingHTTPServer(("127.0.0.1", 0), Faux)
threading.Thread(target=srv.serve_forever, daemon=True).start()
URL = f"http://127.0.0.1:{srv.server_address[1]}"


def backend(nom="ncpw-test", **kw):
    return ps.get_backend("nextcloud_passwords", name=nom, url=URL, **kw)


import os  # noqa: E402
os.environ["SECRET__NCPW_TEST__USER"] = USER
os.environ["SECRET__NCPW_TEST__TOKEN"] = TOKEN

b = backend()

# — registre et capacités —
check("type `nextcloud_passwords` enregistré",
      ps.BACKENDS.get("nextcloud_passwords") is ps.NextcloudPasswordsBackend)
check("caps : pas de déverrouillage, listable, hiérarchique",
      b.caps.needs_unlock is False and b.caps.listable and b.caps.hierarchical)
check("caps : jamais en écriture", b.caps.writable is False)

# — résolution —
check("chemin complet + champ", b.resolve(["clients", "acme", "prod-db"], "username")
      == "acme_app")
check("sans champ → le mot de passe",
      b.resolve(["clients", "acme", "prod-db"]) == MOTDEPASSE)
check("chemin partiel (suffixe de dossiers)",
      b.resolve(["acme", "prod-db"], "password") == MOTDEPASSE)
check("HOMONYME départagé par le dossier",
      b.resolve(["autre", "prod-db"], "password") == "PWD-AUTRE")
check("item à la racine (sans dossier)", b.resolve(["a-la-racine"], "password")
      == "PWD-RACINE")
check("champ notes", b.resolve(["acme", "prod-db"], "notes") == "note de test")
check("champ uri", b.resolve(["acme", "prod-db"], "uri") == "https://acme.test")
check("champ personnalisé", b.resolve(["acme", "prod-db"], "api_key") == "AK-42")
check("champ inconnu → chaîne vide (contrat commun aux backends d'items)",
      b.resolve(["acme", "prod-db"], "zzz") == "")
check("statut : utilisable sans déverrouillage", b.status() == "unlocked")

# — le point dur : le chiffrement côté client —
check("item chiffré côté client → REFUSÉ (jamais le cryptogramme)",
      erreur(b.resolve, ["acme", "secret-e2e"]) == "unsupported")
try:
    b.resolve(["acme", "secret-e2e"])
except ps.SecretError as e:
    check("… le message nomme le type de chiffrement et dit quoi faire",
          "CSEv1r1" in str(e) and "autre coffre" in str(e))
    check("… et ne recopie pas le cryptogramme",
          "cryptogramme-illisible" not in str(e))

# — absences —
check("label inconnu → not_found", erreur(b.resolve, ["acme", "zzz"]) == "not_found")
check("bon label, mauvais dossier → not_found",
      erreur(b.resolve, ["inexistant", "prod-db"]) == "not_found")
try:
    b.resolve(["inexistant", "prod-db"])
except ps.SecretError as e:
    check("… en signalant les homonymes ailleurs", "2 item(s)" in str(e))
check("chemin vide → bad_uri", erreur(b.resolve, []) == "bad_uri")

# — listing : des chemins et des labels, aucune valeur —
items = b.list()
check("list() rend un item par mot de passe", len(items) == len(ITEMS))
check("list() range sous le chemin de dossier complet",
      next(i for i in items if i["id"] == "p1")["collections"] == ["clients/acme"])
check("list() ne rend aucune valeur",
      MOTDEPASSE not in repr(items) and TOKEN not in repr(items))
check("list(filtre) filtre sur le label",
      [i["id"] for i in b.list("e2e")] == ["p3"])

# — déverrouillage : il n'y en a pas —
check("unlock() → unsupported", erreur(b.unlock) == "unsupported")

# — erreurs de transport, traduites —
mauvais = backend(nom="ncpw-faux")
os.environ["SECRET__NCPW_FAUX__USER"] = USER
os.environ["SECRET__NCPW_FAUX__TOKEN"] = "pas-le-bon"
mauvais = backend(nom="ncpw-faux")
check("identifiants refusés → denied", erreur(mauvais.resolve, ["x"]) == "denied")
check("… et le statut le dit sans mentir sur l'accessibilité",
      mauvais.status() == "locked")
try:
    mauvais.resolve(["x"])
except ps.SecretError as e:
    check("… sans jamais citer le jeton", "pas-le-bon" not in str(e))

Faux.app_absente = True
check("app Passwords absente (404) → not_found explicite",
      erreur(b.resolve, ["acme", "prod-db"]) == "not_found")
try:
    b.resolve(["acme", "prod-db"])
except ps.SecretError as e:
    check("… en disant que l'app n'est peut-être pas installée",
          "Passwords" in str(e))
Faux.app_absente = False

b2 = backend(nom="ncpw-test")
Faux.defi = True
check("instance qui exige un défi humain → locked", erreur(b2.resolve, ["x"]) == "locked")
Faux.defi = False

# session exigée mais jamais ouverte : le backend doit l'ouvrir de lui-même
b3 = backend(nom="ncpw-test")
check("le backend ouvre la session tout seul (412 évité)",
      b3.resolve(["acme", "prod-db"], "password") == MOTDEPASSE)

muet = ps.get_backend("nextcloud_passwords", name="ncpw-test",
                      url="http://127.0.0.1:1", timeout=2)
check("serveur injoignable → unreachable", erreur(muet.resolve, ["x"]) == "unreachable")
check("statut d'une instance injoignable", muet.status() == "unreachable")

# — configuration incomplète —
sans_url = ps.get_backend("nextcloud_passwords", name="ncpw-vide")
check("aucune URL → unreachable", erreur(sans_url.resolve, ["x"]) == "unreachable")
try:
    sans_url.resolve(["x"])
except ps.SecretError as e:
    check("… en nommant la variable ou la clé de conf", "SECRET__NCPW_VIDE__URL" in str(e))
sans_creds = ps.get_backend("nextcloud_passwords", name="ncpw-vide", url=URL)
check("aucun identifiant → unreachable", erreur(sans_creds.resolve, ["x"]) == "unreachable")
try:
    sans_creds.resolve(["x"])
except ps.SecretError as e:
    check("… en nommant USER et TOKEN",
          "SECRET__NCPW_VIDE__USER" in str(e) and "SECRET__NCPW_VIDE__TOKEN" in str(e))

# ── unlock-vault.sh : le diagnostic d'une instance Nextcloud Passwords ──────
# « Est-ce que ça marche, là, maintenant ? » — la question qu'on ne veut pas
# découvrir au milieu d'un déploiement chez le client.
import subprocess  # noqa: E402
import tempfile  # noqa: E402
import shutil  # noqa: E402

core = pathlib.Path(tempfile.mkdtemp(prefix="rm2712-core-"))
conf = (HERE.parent / "pm.config.yml").read_text(encoding="utf-8")
_a = "    vw-ipro:"
_i = conf.index(_a)
_f = conf.index("\n", _i) + 1
conf = (conf[:_f] + f'    ncpw-diag: {{ axis: secret, type: nextcloud_passwords, '
                    f'url: "{URL}" }}\n' + conf[_f:])
(core / "pm.config.yml").write_text(conf, encoding="utf-8")
(core / ".env").write_text(f"PROJECTS_PATH={core}/projects\n", encoding="utf-8")
(core / "projects").mkdir()


def unlock(*args, **surcharges):
    env = dict(os.environ, PM_CORE_DIR=str(core))
    env.update(surcharges)
    return subprocess.run([str(HERE / "unlock-vault.sh"), "-i", "ncpw-diag", *args],
                          capture_output=True, text=True, env=env, timeout=60)


bons = {"SECRET__NCPW_DIAG__USER": USER, "SECRET__NCPW_DIAG__TOKEN": TOKEN}
p = unlock("--print-instance", **bons)
check("unlock-vault.sh --print-instance : type nextcloud_passwords",
      "type=nextcloud_passwords" in p.stdout and f"url={URL}" in p.stdout)
check("… liste les clés attendues (des NOMS)",
      "USER" in p.stdout and "TOKEN" in p.stdout)
check("… et jamais la valeur du jeton", TOKEN not in p.stdout)

p = unlock(**bons)
check("unlock-vault.sh : accès vérifié → exit 0", p.returncode == 0)
check("… en disant qu'il n'y a rien à déverrouiller",
      "aucun déverrouillage" in p.stdout)
p = unlock(**{"SECRET__NCPW_DIAG__USER": USER,
              "SECRET__NCPW_DIAG__TOKEN": "mauvais"})
check("identifiants refusés → exit 1, message qui distingue du réseau",
      p.returncode == 1 and "refusés" in p.stderr)
check("… sans citer le jeton essayé", "mauvais" not in p.stderr)

shutil.rmtree(core, ignore_errors=True)
srv.shutdown()

if fails:
    print(f"\n{len(fails)} test(s) en échec : {fails}")
    sys.exit(1)
print("\nOK — tous les tests du backend Nextcloud Passwords passent")
