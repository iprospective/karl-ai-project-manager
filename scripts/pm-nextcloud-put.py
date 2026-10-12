#!/usr/bin/env python3
"""pm-nextcloud-put — dépose un fichier sur le Nextcloud du compte karl et rend son lien (RM3447).

Un livrable à partager (rapport, schéma, étude) vit dans le repo ; cet outil le DÉPOSE sur le
Nextcloud (fournisseur `nextcloud` du registre `pm.config.yml :: providers.servers`, défaut
`nc-ipro`) et, avec `--share`, rend un lien public. Jamais un artefact claude.ai : l'URL va dans
la note Redmine.

Usage :
    pm-nextcloud-put <fichier> [--project client/slug] [--instance nc-ipro] [--dest <sous-dossier>]
                     [--share] [--expire J] [--name <nom>] [--porcelain] [--dry-run]

Dépôt (WebDAV, `urllib`, sans dépendance) :
    <racine>/<client>/<projet>/[<dest>/]<AAAA-MM-JJ>-<slug>.<ext>
  `racine` = `providers.servers.<instance>.root` (défaut `Partages`). Un nom qui commence déjà
  par une date n'en reçoit pas une seconde ; `--name` force le nom tel quel. Dépôt idempotent :
  re-déposer le même nom écrase le fichier (PUT) et les dossiers existants sont tolérés (MKCOL).

Identifiants (jamais affichés, jamais loggués) :
    user    `providers.servers.<instance>.user`   (défaut `karl`)
    secret  `providers.servers.<instance>.secret` : URI résolue par `scripts/resolve-secret.sh`
            (ex. `secret://vw-ipro/agents/nextcloud-karl#password`) ; repli : variable
            d'environnement `NEXTCLOUD_APP_PASSWORD` (essais manuels).

Partage (`--share`) : API OCS `files_sharing` (lien public, `shareType=3`, lecture seule) ;
`--expire J` pose une échéance dans J jours. `--porcelain` : l'URL seule (ou, sans `--share`, le
chemin WebDAV). `--dry-run` : montre ce qui serait fait, sans réseau ni secret.

Fichier `.md` : déposé tel quel (Nextcloud le rend). Aucun convertisseur md → pdf n'existe au
repo (pandoc/soffice absents de `scripts/` et `tools/`) : pas d'option `--pdf` tant qu'il n'y en
a pas.

Codes retour : 0 ok · 2 vault verrouillé (demander `unlock-vault.sh`) · 3 erreur réseau/HTTP ·
4 configuration manquante ou usage invalide (instance inconnue, pas de secret, projet ambigu…).
"""
import argparse
import base64
import datetime
import os
import re
import subprocess
import sys
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

DEFAULT_INSTANCE = "nc-ipro"
DEFAULT_USER = "karl"
DEFAULT_ROOT = "Partages"
ENV_PASSWORD = "NEXTCLOUD_APP_PASSWORD"
TIMEOUT = 60

EXIT_OK, EXIT_LOCKED, EXIT_NET, EXIT_CONF = 0, 2, 3, 4


class PutError(Exception):
    """Erreur portant son code de sortie."""

    def __init__(self, message, code):
        super().__init__(message)
        self.code = code


# ── Chemin de dépôt ───────────────────────────────────────────────────────────
def slugify(text):
    s = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()
    return s or "fichier"


_DATED = re.compile(r"^\d{4}-\d{2}-\d{2}-")


def deposit_name(filename, name=None, today=None):
    """Nom du fichier déposé : `--name` tel quel ; sinon `AAAA-MM-JJ-<slug>.<ext>`."""
    if name:
        return name
    p = Path(filename)
    ext = p.suffix.lower()
    slug = slugify(p.stem)
    if _DATED.match(slug):
        return slug + ext
    today = today or datetime.date.today()
    return f"{today.isoformat()}-{slug}{ext}"


def _safe_segment(seg):
    seg = str(seg).strip().strip("/")
    if not seg or seg in (".", "..") or "/" in seg or "\\" in seg:
        raise PutError(f"segment de chemin invalide : {seg!r}", EXIT_CONF)
    return seg


def deposit_path(root, client, project, filename, dest=None, name=None, today=None):
    """Chemin relatif (sans slash initial) : <racine>/<client>/<projet>/[<dest>/]<nom>."""
    segs = [_safe_segment(s) for s in str(root).strip("/").split("/") if s.strip()]
    segs += [_safe_segment(client), _safe_segment(project)]
    if dest:
        segs += [_safe_segment(s) for s in str(dest).strip("/").split("/") if s.strip()]
    segs.append(_safe_segment(deposit_name(filename, name, today)))
    return "/".join(segs)


def webdav_url(base, user, relpath):
    q = lambda s: urllib.parse.quote(s, safe="")
    return (base.rstrip("/") + "/remote.php/dav/files/" + q(user) + "/"
            + "/".join(q(s) for s in relpath.split("/")))


# ── Configuration ─────────────────────────────────────────────────────────────
def load_instance(cfg, name):
    """(url, user, root, secret_uri) de l'instance `nextcloud` ; PutError(4) sinon."""
    from pm_registry import Registry, RegistryError
    try:
        reg = Registry.from_config(getattr(cfg, "providers", None) or {})
        inst = reg.get(name)
    except RegistryError as e:
        raise PutError(f"configuration : {e}", EXIT_CONF)
    if (inst.type or "").lower() != "nextcloud":
        raise PutError(f"configuration : l'instance {name!r} est de type "
                       f"{inst.type!r}, pas 'nextcloud'", EXIT_CONF)
    if not inst.url:
        raise PutError(f"configuration : l'instance {name!r} n'a pas d'url", EXIT_CONF)
    o = inst.options or {}
    return (inst.url, str(o.get("user") or DEFAULT_USER),
            str(o.get("root") or DEFAULT_ROOT), str(o.get("secret") or ""))


def resolve_project(cfg, ref=None, start=None):
    """(client, slug) : `--project` (non ambigu, tripwire #14) sinon cwd."""
    if ref:
        try:
            ent, slug, _ = cfg.resolve_project_ref(ref)
        except ValueError as e:
            raise PutError(f"projet : {e}", EXIT_CONF)
        return ent, slug
    found = cfg.detect_project_from_cwd(start)
    if not found:
        raise PutError("projet introuvable depuis le cwd : passer --project client/slug",
                       EXIT_CONF)
    return found


def get_password(secret_uri, runner=subprocess.run, environ=None):
    """Mot de passe d'application. Jamais affiché. Code 2 = vault verrouillé."""
    environ = os.environ if environ is None else environ
    env_pw = environ.get(ENV_PASSWORD, "")
    if secret_uri:
        script = str(HERE / "resolve-secret.sh")
        try:
            r = runner([script, secret_uri], capture_output=True, text=True, timeout=30)
        except (OSError, subprocess.SubprocessError) as e:
            if env_pw:
                return env_pw
            raise PutError(f"résolution du secret impossible : {type(e).__name__}", EXIT_CONF)
        if r.returncode == 0 and (r.stdout or "").strip():
            return r.stdout.strip()
        if env_pw:
            return env_pw
        if r.returncode == 2:
            raise PutError("vault verrouillé : demander à Mathieu de lancer "
                           "`unlock-vault.sh`", EXIT_LOCKED)
        raise PutError(f"secret {secret_uri.split('#')[0]} non résolu "
                       f"(resolve-secret.sh code {r.returncode})", EXIT_CONF)
    if env_pw:
        return env_pw
    raise PutError(f"pas de secret : définir providers.servers.<instance>.secret "
                   f"(URI) ou ${ENV_PASSWORD}", EXIT_CONF)


# ── HTTP ──────────────────────────────────────────────────────────────────────
def _http(method, url, headers, data=None):
    """(statut, corps bytes) ; les statuts 4xx/5xx sont RENDUS, pas levés. Réseau → PutError(3)."""
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        try:
            body = e.read()
        except Exception:                       # noqa: BLE001
            body = b""
        return e.code, body
    except (urllib.error.URLError, OSError) as e:
        raise PutError(f"erreur réseau vers {urllib.parse.urlparse(url).netloc} : "
                       f"{getattr(e, 'reason', e)}", EXIT_NET)


def _auth(user, password):
    tok = base64.b64encode(f"{user}:{password}".encode()).decode()
    return {"Authorization": "Basic " + tok}


def _scrub(text, password):
    text = text if isinstance(text, str) else text.decode("utf-8", "replace")
    return text.replace(password, "***") if password else text


def mkcol_tree(base, user, password, relpath, http=None):
    """MKCOL récursif des dossiers de `relpath` (sans le fichier). 405 = existe déjà."""
    http = http or _http
    parts = relpath.split("/")[:-1]
    for i in range(1, len(parts) + 1):
        url = webdav_url(base, user, "/".join(parts[:i])) + "/"
        status, body = http("MKCOL", url, _auth(user, password))
        if status not in (201, 405):
            raise PutError(f"MKCOL /{'/'.join(parts[:i])} : HTTP {status} "
                           f"{_scrub(body, password)[:200]}", EXIT_NET)


def put_file(base, user, password, relpath, content, http=None):
    http = http or _http
    headers = dict(_auth(user, password))
    headers["Content-Type"] = "application/octet-stream"
    status, body = http("PUT", webdav_url(base, user, relpath), headers, content)
    if status not in (201, 204):
        raise PutError(f"PUT /{relpath} : HTTP {status} {_scrub(body, password)[:200]}",
                       EXIT_NET)


def parse_ocs_url(body):
    """URL de partage depuis la réponse OCS (XML). PutError(3) si statut OCS en échec."""
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        raise PutError("réponse OCS illisible (pas du XML)", EXIT_NET)
    code = (root.findtext("./meta/statuscode") or "").strip()
    if code not in ("100", "200"):
        msg = (root.findtext("./meta/message") or "").strip()
        raise PutError(f"OCS statut {code or '?'} {msg}".strip(), EXIT_NET)
    url = (root.findtext("./data/url") or "").strip()
    if not url:
        raise PutError("réponse OCS sans <url>", EXIT_NET)
    return url


def create_share(base, user, password, relpath, expire_days=None, http=None, today=None):
    http = http or _http
    form = {"path": "/" + relpath, "shareType": "3", "permissions": "1"}
    if expire_days:
        d = (today or datetime.date.today()) + datetime.timedelta(days=int(expire_days))
        form["expireDate"] = d.isoformat()
    headers = dict(_auth(user, password))
    headers["OCS-APIRequest"] = "true"
    headers["Content-Type"] = "application/x-www-form-urlencoded"
    url = base.rstrip("/") + "/ocs/v2.php/apps/files_sharing/api/v1/shares"
    status, body = http("POST", url, headers, urllib.parse.urlencode(form).encode())
    if status not in (100, 200):
        raise PutError(f"partage OCS : HTTP {status} {_scrub(body, password)[:200]}", EXIT_NET)
    return parse_ocs_url(body)


# ── Orchestration ─────────────────────────────────────────────────────────────
def run(args, cfg, http=None, runner=subprocess.run, environ=None, today=None, out=None):
    out = out or sys.stdout
    src = Path(args.file)
    if not src.is_file():
        raise PutError(f"fichier introuvable : {src}", EXIT_CONF)
    base, user, root, secret_uri = load_instance(cfg, args.instance)
    client, project = resolve_project(cfg, args.project)
    rel = deposit_path(root, client, project, src.name, args.dest, args.name, today)

    if args.dry_run:
        if args.porcelain:
            print("/" + rel, file=out)
            return EXIT_OK
        print(f"[dry-run] instance : {args.instance} ({base}) · compte : {user}", file=out)
        print(f"[dry-run] secret   : {'URI ' + secret_uri.split('#')[0] if secret_uri else '$' + ENV_PASSWORD} (non résolu)", file=out)
        print(f"[dry-run] MKCOL    : {'/'.join(rel.split('/')[:-1])}/ (récursif)", file=out)
        print(f"[dry-run] PUT      : /{rel} ({src.stat().st_size} octets)", file=out)
        if args.share:
            exp = f", échéance +{args.expire} j" if args.expire else ""
            print(f"[dry-run] PARTAGE  : lien public, lecture seule{exp}", file=out)
        print("[dry-run] aucun réseau, rien d'écrit", file=out)
        return EXIT_OK

    password = get_password(secret_uri, runner, environ)
    content = src.read_bytes()
    mkcol_tree(base, user, password, rel, http)
    put_file(base, user, password, rel, content, http)
    url = create_share(base, user, password, rel, args.expire, http, today) if args.share else None
    if args.porcelain:
        print(url or "/" + rel, file=out)
    else:
        print(f"Déposé : /{rel}", file=out)
        if url:
            print(f"URL    : {url}", file=out)
    return EXIT_OK


class _Parser(argparse.ArgumentParser):
    def error(self, message):                    # argparse sort en 2 : réservé au vault ici
        self.print_usage(sys.stderr)
        print(f"{self.prog}: {message}", file=sys.stderr)
        sys.exit(EXIT_CONF)


def build_parser():
    p = _Parser(prog="pm-nextcloud-put", description="Dépose un fichier sur le Nextcloud de karl.")
    p.add_argument("file", help="fichier à déposer")
    p.add_argument("--project", help="client/slug (sinon résolu depuis le cwd)")
    p.add_argument("--instance", default=DEFAULT_INSTANCE, help=f"défaut {DEFAULT_INSTANCE}")
    p.add_argument("--dest", help="sous-dossier sous <client>/<projet>/")
    p.add_argument("--share", action="store_true", help="crée un lien public (OCS)")
    p.add_argument("--expire", type=int, metavar="J", help="échéance du lien, en jours")
    p.add_argument("--name", help="nom du fichier déposé (sinon AAAA-MM-JJ-<slug>.<ext>)")
    p.add_argument("--porcelain", action="store_true", help="l'URL seule (ou le chemin)")
    p.add_argument("--dry-run", action="store_true", help="montre sans rien faire")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.expire is not None and args.expire < 1:
        print("--expire attend un nombre de jours >= 1", file=sys.stderr)
        return EXIT_CONF
    try:
        from pm_paths import PMConfig, PMConfigError
        try:
            cfg = PMConfig.load(Path(os.environ["PM_CORE_DIR"]) if os.environ.get("PM_CORE_DIR") else None)
        except (PMConfigError, SystemExit) as e:
            raise PutError(f"configuration PM illisible : {e}", EXIT_CONF)
        return run(args, cfg)
    except PutError as e:
        print(f"pm-nextcloud-put : {e}", file=sys.stderr)
        return e.code


if __name__ == "__main__":
    sys.exit(main())
