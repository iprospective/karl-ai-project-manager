#!/usr/bin/env python3
"""Tests RM3447 — pm-nextcloud-put, 100 % hors ligne (transport HTTP et vault simulés).

Protégé :
  1. chemin de dépôt : <racine>/<client>/<projet>/[<dest>/]<AAAA-MM-JJ>-<slug>.<ext>, `--name`,
     pas de double date, segments dangereux refusés ;
  2. instance lue d'un `pm.config.yml` factice (user/root/secret, défauts inertes, type refusé) ;
  3. séquence WebDAV (MKCOL récursif tolérant le 405, puis PUT) et OCS (en-têtes, corps, échéance) ;
  4. parsing de la réponse OCS (XML → URL) et de ses échecs ;
  5. codes retour : 0, 2 (vault verrouillé), 3 (HTTP/réseau), 4 (config) ;
  6. aucun secret dans aucune sortie ; `--dry-run` n'ouvre ni réseau ni vault.

Lancer : python3 scripts/test_pm_nextcloud_put.py
"""
import base64
import contextlib
import datetime
import importlib.util
import io
import pathlib
import sys
import tempfile
import urllib.error

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
spec = importlib.util.spec_from_file_location("pm_nextcloud_put", HERE / "pm-nextcloud-put.py")
nc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(nc)

fails = []


def check(name, cond, detail=""):
    print(("✓ " if cond else "✗ ") + name + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(name)


SECRET = "s3cr3t-app-pw-XYZ"
TODAY = datetime.date(2026, 10, 12)
TMP = pathlib.Path(tempfile.mkdtemp(prefix="rm3447-"))
SRC = TMP / "Étude Labels (v2).md"
SRC.write_text("# étude\n", encoding="utf-8")
DATED = TMP / "2026-10-06-etude-labels.md"
DATED.write_text("x", encoding="utf-8")

# ── 1. chemin de dépôt ───────────────────────────────────────────────────────
check("nom : date + slug + extension", nc.deposit_name("Étude Labels (v2).md", today=TODAY) == "2026-10-12-etude-labels-v2.md")
check("nom : déjà daté → pas de double date", nc.deposit_name("2026-10-06-etude-labels.md", today=TODAY) == "2026-10-06-etude-labels.md")
check("nom : --name forcé tel quel", nc.deposit_name("a.md", name="Rapport Final.pdf", today=TODAY) == "Rapport Final.pdf")
check("chemin : racine/client/projet/nom",
      nc.deposit_path("Partages", "calicote", "prestashop", "a b.md", today=TODAY) == "Partages/calicote/prestashop/2026-10-12-a-b.md")
check("chemin : --dest multi-niveaux",
      nc.deposit_path("Partages", "c", "p", "a.md", dest="etudes/v2", today=TODAY) == "Partages/c/p/etudes/v2/2026-10-12-a.md")
check("chemin : racine à deux niveaux",
      nc.deposit_path("/Docs/Partages/", "c", "p", "a.md", today=TODAY).startswith("Docs/Partages/c/p/"))
for bad in ("..", "a/../b", ""):
    try:
        nc.deposit_path("Partages", "c", bad, "a.md", today=TODAY) if "/" not in bad else nc.deposit_path("Partages", "c", "p", "a.md", dest=bad, today=TODAY)
        ok = False
    except nc.PutError as e:
        ok = e.code == 4
    check(f"chemin : segment dangereux {bad!r} refusé (4)", ok)
check("URL WebDAV : encodage des segments",
      nc.webdav_url("https://x.fr/", "karl", "Partages/c/é f.md") == "https://x.fr/remote.php/dav/files/karl/Partages/c/%C3%A9%20f.md")

# ── 2. instance depuis une conf factice ──────────────────────────────────────
class FakeCfg:
    def __init__(self, servers, projects=None, cwd=None):
        self.providers = {"servers": servers}
        self._projects = projects or {"calicote/prestashop": ("calicote", "prestashop", "/x")}
        self._cwd = cwd

    def resolve_project_ref(self, ref, require_redmine=False):
        if ref in self._projects:
            return self._projects[ref]
        if ref == "infra":
            raise ValueError("slug 'infra' ambigu (abatik/infra, matnat/infra)")
        raise ValueError(f"projet '{ref}' introuvable")

    def detect_project_from_cwd(self, start=None):
        return self._cwd


FULL = {"nc-ipro": {"axis": "doc", "type": "nextcloud", "url": "https://cloud.test", "share_expire_days": 14,
                    "user": "robot", "root": "Docs", "secret": "secret://vw/agents/nc#password"}}
BARE = {"nc-ipro": {"axis": "doc", "type": "nextcloud", "url": "https://cloud.test"}}
check("instance : user/root/secret lus", nc.load_instance(FakeCfg(FULL), "nc-ipro") == ("https://cloud.test", "robot", "Docs", "secret://vw/agents/nc#password", 14))
check("instance : défauts inertes (karl / Partages / pas de secret)", nc.load_instance(FakeCfg(BARE), "nc-ipro") == ("https://cloud.test", "karl", "Partages", "", None))


def code_of(fn, *a, **k):
    try:
        fn(*a, **k)
        return 0
    except nc.PutError as e:
        return e.code


check("instance inconnue → 4", code_of(nc.load_instance, FakeCfg(BARE), "nc-nope") == 4)
check("instance d'un autre type → 4", code_of(nc.load_instance, FakeCfg({"nc-ipro": {"axis": "doc", "type": "redmine_wiki", "url": "https://r"}}), "nc-ipro") == 4)
check("instance sans url → 4", code_of(nc.load_instance, FakeCfg({"nc-ipro": {"axis": "doc", "type": "nextcloud"}}), "nc-ipro") == 4)
check("projet : --project explicite", nc.resolve_project(FakeCfg(BARE), "calicote/prestashop") == ("calicote", "prestashop"))
check("projet : slug ambigu → 4 (tripwire 14)", code_of(nc.resolve_project, FakeCfg(BARE), "infra") == 4)
check("projet : depuis le cwd", nc.resolve_project(FakeCfg(BARE, cwd=("a", "b"))) == ("a", "b"))
check("projet : cwd hors projet → 4", code_of(nc.resolve_project, FakeCfg(BARE)) == 4)

# ── 3. mots de passe : vault, repli env, codes ───────────────────────────────
class R:
    def __init__(self, rc, out="", err=""):
        self.returncode, self.stdout, self.stderr = rc, out, err


check("secret : résolu par resolve-secret.sh", nc.get_password("secret://vw/a#password", lambda *a, **k: R(0, SECRET + "\n"), {}) == SECRET)
check("secret : vault verrouillé → 2", code_of(nc.get_password, "secret://vw/a#password", lambda *a, **k: R(2, "", "locked"), {}) == 2)
check("secret : verrouillé mais repli env", nc.get_password("secret://vw/a#password", lambda *a, **k: R(2), {"NEXTCLOUD_APP_PASSWORD": "envpw"}) == "envpw")
check("secret : autre erreur vault → 4", code_of(nc.get_password, "secret://vw/a#password", lambda *a, **k: R(4), {}) == 4)
check("secret : sans URI, repli env", nc.get_password("", None, {"NEXTCLOUD_APP_PASSWORD": "envpw"}) == "envpw")
check("secret : sans URI ni env → 4", code_of(nc.get_password, "", None, {}) == 4)

# ── 4. WebDAV / OCS avec transport simulé ────────────────────────────────────
OCS_OK = (b'<?xml version="1.0"?><ocs><meta><status>ok</status><statuscode>200</statuscode><message>OK</message></meta>'
          b'<data><id>7</id><url>https://cloud.test/s/AbC123</url></data></ocs>')


OCS_EMPTY = b'<ocs><meta><statuscode>200</statuscode></meta><data/></ocs>'
OCS_LIST = (b'<ocs><meta><statuscode>200</statuscode></meta><data><element><share_type>0</share_type><url>https://cloud.test/nope</url></element>'
            b'<element><share_type>3</share_type><url>https://cloud.test/s/Exist1</url><expiration>2026-10-20 00:00:00</expiration></element></data></ocs>')
base = "https://cloud.test/remote.php/dav/files/robot/"


class Wire:
    def __init__(self, mkcol=201, put=201, share=(200, OCS_OK), existing=(), tree=None, listing=(200, OCS_EMPTY)):
        self.calls, self.mkcol, self.put, self.share, self.existing = [], mkcol, put, share, set(existing)
        self.tree, self.listing = tree or {}, listing      # tree : {chemin parent: [dossiers existants]}

    def __call__(self, method, url, headers, data=None):
        self.calls.append((method, url, dict(headers), data))
        if method == "PROPFIND":
            parent = url[len(base):].rstrip("/")
            if parent not in self.tree:
                return 404, b""
            rows = "".join(f"<d:response><d:href>/remote.php/dav/files/robot/{parent}/{n}/</d:href><d:propstat><d:prop><d:resourcetype><d:collection/></d:resourcetype></d:prop></d:propstat></d:response>" for n in self.tree[parent])
            rows += f"<d:response><d:href>/remote.php/dav/files/robot/{parent}/f.md</d:href><d:propstat><d:prop><d:resourcetype/></d:prop></d:propstat></d:response>"
            return 207, (f'<?xml version="1.0"?><d:multistatus xmlns:d="DAV:"><d:response><d:href>/remote.php/dav/files/robot/{parent}/</d:href><d:propstat><d:prop><d:resourcetype><d:collection/></d:resourcetype></d:prop></d:propstat></d:response>{rows}</d:multistatus>').encode()
        if method == "GET":
            return self.listing
        if method == "MKCOL":
            return (405, b"") if url in self.existing else (self.mkcol, b"")
        if method == "PUT":
            return self.put, b"boom " + SECRET.encode() if self.put >= 400 else b""
        return self.share


class A:
    def __init__(self, **kw):
        d = dict(file=str(SRC), project="calicote/prestashop", instance="nc-ipro", dest=None, share=False,
                 expire=None, name=None, porcelain=False, dry_run=False)
        d.update(kw)
        self.__dict__.update(d)


def go(args, servers=FULL, wire=None, runner=None, environ=None):
    wire = wire or Wire()
    buf, rc = io.StringIO(), None
    runner = runner or (lambda *a, **k: R(0, SECRET + "\n"))
    try:
        rc = nc.run(args, FakeCfg(servers), http=wire, runner=runner, environ=environ if environ is not None else {}, today=TODAY, out=buf)
    except nc.PutError as e:
        rc = e.code
        buf.write(str(e))
    return rc, buf.getvalue(), wire


rc, out, w = go(A())
methods = [(m, u) for m, u, _, _ in w.calls if m != "PROPFIND"]
check("run ok : code 0", rc == 0, out)
check("WebDAV : MKCOL récursif racine → projet puis PUT",
      methods == [("MKCOL", base + "Docs/"), ("MKCOL", base + "Docs/Calicote/"), ("MKCOL", base + "Docs/Calicote/prestashop/"),
                  ("PUT", base + "Docs/Calicote/prestashop/2026-10-12-etude-labels-v2.md")], str(methods))
check("WebDAV : Basic auth correct", w.calls[0][2]["Authorization"] == "Basic " + base64.b64encode(f"robot:{SECRET}".encode()).decode())
check("WebDAV : le PUT porte le contenu", w.calls[-1][3] == b"# \xc3\xa9tude\n")
check("PROPFIND Depth 1 racine puis dossier client",
      [(m, h.get("Depth")) for m, _, h, _ in w.calls if m == "PROPFIND"] == [("PROPFIND", "1")] * 2)
check("sortie : chemin déposé, pas d'URL sans --share", "Déposé : /Docs/Calicote/prestashop/2026-10-12-etude-labels-v2.md" in out and "URL" not in out)

rc, out, w = go(A(), wire=Wire(existing=[base + "Docs/", base + "Docs/Calicote/"]))
check("MKCOL 405 (dossier existant) toléré", rc == 0, out)

rc, out, w = go(A(share=True, expire=30, dest="etudes"))
m, u, h, d = w.calls[-1]
check("OCS : POST sur l'API files_sharing v2", m == "POST" and u == "https://cloud.test/ocs/v2.php/apps/files_sharing/api/v1/shares", u)
check("OCS : en-tête OCS-APIRequest", h.get("OCS-APIRequest") == "true")
body = d.decode()
check("OCS : shareType=3, chemin déposé, échéance +30 j",
      "shareType=3" in body and "path=%2FDocs%2FCalicote%2Fprestashop%2Fetudes%2F2026-10-12-etude-labels-v2.md" in body
      and "expireDate=2026-11-11" in body, body)
check("--dest : sous-dossier créé", ("MKCOL", base + "Docs/Calicote/prestashop/etudes/") in [(a, b) for a, b, _, _ in w.calls])
check("sortie --share : chemin + URL", rc == 0 and "URL    : https://cloud.test/s/AbC123" in out and "Déposé : /Docs/" in out, out)

rc, out, _ = go(A(share=True, porcelain=True))
check("--porcelain --share : l'URL seule", out == "https://cloud.test/s/AbC123\n", repr(out))
rc, out, _ = go(A(porcelain=True, name="Rapport.md"))
check("--porcelain sans --share + --name : le chemin seul", out == "/Docs/Calicote/prestashop/Rapport.md\n", repr(out))
rc, out, w = go(A(share=True))
check("sans --expire : défaut instance", "expireDate" in w.calls[-1][3].decode())

# ── 4b. casse client/projet, expiration par défaut, lien réutilisé ──────────
rc, out, w = go(A(), wire=Wire(tree={"Docs": ["Calicote", "Autre"], "Docs/Calicote": ["prestashop"]}))
puts = [u for m, u, _, _ in w.calls if m == "PUT"]
check("casse : client existant `Calicote` réutilisé (slug `calicote`), projet existant",
      rc == 0 and puts == [base + "Docs/Calicote/prestashop/2026-10-12-etude-labels-v2.md"], str(puts))
check("casse : rien à créer → MKCOL tolère l'existant, aucun dossier `calicote` minuscule", not any("/Docs/calicote/" in u for _, u, _, _ in w.calls))
rc, out, w = go(A(), wire=Wire(tree={"Docs": ["CALICOTE"], "Docs/CALICOTE": ["PrestaShop"]}))
check("casse : insensible (CALICOTE / PrestaShop)", [u for m, u, _, _ in w.calls if m == "PUT"] == [base + "Docs/CALICOTE/PrestaShop/2026-10-12-etude-labels-v2.md"])
rc, out, w = go(A(), wire=Wire(tree={"Docs": ["Autre"]}))
check("casse : client absent → créé avec majuscule initiale, projet tel quel",
      [u for m, u, _, _ in w.calls if m == "PUT"] == [base + "Docs/Calicote/prestashop/2026-10-12-etude-labels-v2.md"])
rc, out, w = go(A(), wire=Wire(tree={"Docs": ["Calicote"]}))
check("casse : client présent, projet absent → créé tel quel", [u for m, u, _, _ in w.calls if m == "PUT"] == [base + "Docs/Calicote/prestashop/2026-10-12-etude-labels-v2.md"])
rc, out, w = go(A(), wire=Wire(tree={}))
check("racine absente (PROPFIND 404) → client capitalisé, dépôt ok", rc == 0 and "Docs/Calicote/prestashop/" in out, out)

rc, out, w = go(A(share=True))
check("--expire absent → share_expire_days de l'instance (+14 j)", "expireDate=2026-10-26" in w.calls[-1][3].decode(), w.calls[-1][3].decode())
rc, out, w = go(A(share=True, expire=3))
check("--expire explicite l'emporte", "expireDate=2026-10-15" in w.calls[-1][3].decode())
rc, out, w = go(A(share=True), servers=dict(FULL, **{"nc-ipro": dict(FULL["nc-ipro"], share_expire_days=None)}))
check("ni --expire ni défaut instance → pas d'échéance", "expireDate" not in w.calls[-1][3].decode())

rc, out, w = go(A(share=True), wire=Wire(listing=(200, OCS_LIST)))
check("lien public existant réutilisé : aucun POST", rc == 0 and not any(m == "POST" for m, _, _, _ in w.calls), out)
check("lien existant : URL, mention et échéance en sortie", "https://cloud.test/s/Exist1" in out and "réutilisé" in out and "2026-10-20" in out, out)
gets = [u for m, u, _, _ in w.calls if m == "GET"]
check("GET shares?path= sur le chemin déposé", len(gets) == 1 and "shares?path=%2FDocs%2Fcalicote%2Fprestashop%2F2026-10-12-etude-labels-v2.md" in gets[0].replace("Calicote", "calicote"), str(gets))
rc, out, _ = go(A(share=True, porcelain=True), wire=Wire(listing=(200, OCS_LIST)))
check("--porcelain avec lien existant : l'URL seule", out == "https://cloud.test/s/Exist1\n", repr(out))
rc, out, w = go(A(share=True), wire=Wire(listing=(500, b"x")))
check("liste des partages en HTTP 500 → 3", rc == 3 and "HTTP 500" in out, out)
rc, out, w = go(A(), wire=Wire(tree={"Docs": []}))
check("sans --share : aucun GET shares", not any(m == "GET" for m, _, _, _ in w.calls))

# ── 5. parsing OCS ───────────────────────────────────────────────────────────
check("OCS : URL extraite", nc.parse_ocs_url(OCS_OK) == "https://cloud.test/s/AbC123")
check("OCS : statut v1 (100) accepté", nc.parse_ocs_url(OCS_OK.replace(b"200", b"100")) == "https://cloud.test/s/AbC123")
check("OCS : statut 404 → 3", code_of(nc.parse_ocs_url, b"<ocs><meta><statuscode>404</statuscode><message>Wrong path</message></meta></ocs>") == 3)
check("OCS : pas du XML → 3", code_of(nc.parse_ocs_url, b"<html>login") == 3)
check("OCS : sans <url> → 3", code_of(nc.parse_ocs_url, b"<ocs><meta><statuscode>200</statuscode></meta><data/></ocs>") == 3)

# ── 6. codes retour ──────────────────────────────────────────────────────────
rc, out, _ = go(A(), runner=lambda *a, **k: R(2))
check("vault verrouillé → 2 + « unlock-vault.sh »", rc == 2 and "unlock-vault.sh" in out, out)
rc, out, _ = go(A(), wire=Wire(put=403))
check("PUT 403 → 3 avec le statut", rc == 3 and "HTTP 403" in out, out)
check("erreur HTTP : le secret du corps est masqué", SECRET not in out, out)
rc, out, _ = go(A(), wire=Wire(mkcol=401))
check("MKCOL 401 → 3", rc == 3 and "HTTP 401" in out, out)
rc, out, _ = go(A(share=True), wire=Wire(share=(404, b"nope")))
check("OCS HTTP 404 → 3", rc == 3 and "HTTP 404" in out, out)
rc, out, _ = go(A(), servers={})
check("instance absente → 4", rc == 4, out)
rc, out, _ = go(A(), servers=BARE)
check("pas de secret configuré ni env → 4", rc == 4, out)
rc, out, w = go(A(), servers=BARE, environ={"NEXTCLOUD_APP_PASSWORD": SECRET})
check("repli $NEXTCLOUD_APP_PASSWORD → 0", rc == 0, out)
rc, out, _ = go(A(file=str(TMP / "absent.md")))
check("fichier absent → 4", rc == 4, out)
rc, out, _ = go(A(project="infra"))
check("projet ambigu → 4", rc == 4, out)


def raising(*a, **k):
    raise urllib.error.URLError("Name or service not known")


orig = nc.urllib.request.urlopen
nc.urllib.request.urlopen = raising
try:
    try:
        nc._http("GET", "https://cloud.test/x", {})
        rc = 0
    except nc.PutError as e:
        rc = e.code
finally:
    nc.urllib.request.urlopen = orig
check("_http : URLError → 3", rc == 3)


class FakeResp:
    status = 201

    def read(self):
        return b"ok"

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


nc.urllib.request.urlopen = lambda req, timeout=None: FakeResp()
try:
    st = nc._http("PUT", "https://cloud.test/x", {}, b"d")
finally:
    nc.urllib.request.urlopen = orig
check("_http : urlopen simulé rend (statut, corps)", st == (201, b"ok"))


def http_err(req, timeout=None):
    raise urllib.error.HTTPError(req.full_url, 423, "Locked", {}, io.BytesIO(b"locked"))


nc.urllib.request.urlopen = http_err
try:
    st = nc._http("PUT", "https://cloud.test/x", {}, b"d")
finally:
    nc.urllib.request.urlopen = orig
check("_http : HTTPError rendu comme statut", st == (423, b"locked"))

# ── 7. dry-run + absence de secret dans les sorties ──────────────────────────
def boom(*a, **k):
    raise AssertionError("réseau/vault touché en dry-run")


buf = io.StringIO()
rc = nc.run(A(dry_run=True, share=True, expire=7), FakeCfg(FULL), http=boom, runner=boom, environ={}, today=TODAY, out=buf)
dry = buf.getvalue()
check("dry-run : 0, ni réseau ni vault", rc == 0)
check("dry-run : montre MKCOL/PUT/PARTAGE", all(k in dry for k in ("MKCOL", "PUT", "PARTAGE", "+7 j", "/Docs/Calicote/prestashop/2026-10-12-etude-labels-v2.md")), dry)
check("dry-run : n'affiche que l'URI du secret, jamais sa valeur", "secret://vw/agents/nc" in dry and SECRET not in dry and "#password" not in dry)
buf = io.StringIO()
nc.run(A(dry_run=True, porcelain=True), FakeCfg(FULL), http=boom, runner=boom, environ={}, today=TODAY, out=buf)
check("dry-run --porcelain : le chemin seul", buf.getvalue() == "/Docs/Calicote/prestashop/2026-10-12-etude-labels-v2.md\n")

allout = "".join(go(A(share=True))[1:2]) + out
check("aucun secret dans les sorties normales", SECRET not in allout)

# CLI : argparse en erreur → 4 (le 2 est réservé au vault)
err = io.StringIO()
try:
    with contextlib.redirect_stderr(err):
        nc.build_parser().parse_args([])
    rc = 0
except SystemExit as e:
    rc = e.code
check("CLI : usage invalide → 4", rc == 4)

print()
if fails:
    print(f"✗ {len(fails)} échec(s) : " + ", ".join(fails))
    sys.exit(1)
print("== OK ==")
