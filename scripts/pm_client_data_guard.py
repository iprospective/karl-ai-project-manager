#!/usr/bin/env python3
"""pm_client_data_guard — aucune donnée client dans un dépôt publiable (RM3201).

Un dépôt qui porte un `.client-data-guard.yml` à sa racine est **publié** : le dépôt
de code PM part sur un miroir GitHub public (incident RM3200 : domaines de prod,
versions déployées, chemins serveurs et adresses de contacts clients y étaient
versionnés). Ce module dit si un texte nomme un client ou l'une de ses instances.

Les motifs ne sont JAMAIS écrits dans le code : ils sont lus, à chaque exécution,
dans les données privées du PM —

- les entités `type: client` (slug + nom), jamais `product` ni `self` ;
- les noms d'hôtes, adresses et IP de leurs manifestes (`meta.yml` d'entité et de
  projet) et des `environments.md` de leurs projets ;
- l'annuaire de contacts (`contacts_dir`) : adresses et « prénom nom » des contacts
  non internes ;
- la table de routage mail (`mail_routing_file`) : adresses et domaines appris.

Limite assumée : le garde-fou ne connaît que ce que les données déclarent. Un client
dont le domaine ne porte pas son nom lui échappe tant que son `environments.md` est
vide — c'est exactement ainsi que le domaine commercial d'un client avait échappé au
premier audit de RM3200. Renseigner les instances est donc aussi ce qui arme le garde-fou.

Le fichier `.client-data-guard.yml` (versionné, sans donnée client) porte :
  `exempt`        globs de chemins non contrôlés (à éviter : chaque entrée est un trou) ;
  `common_words`  mots courants qui, s'ils sont aussi un slug de client, ne sont
                  signalés qu'en position d'identifiant (`clients/<x>/`, `php_<x>`,
                  `<x>-presta`…), jamais en prose — sinon un slug comme un adverbe
                  bloquerait chaque phrase.

Une ligne portant le marqueur `client-data-guard: allow` n'est pas contrôlée : pour
une dette connue et tracée, jamais pour faire passer un commit.
"""
from __future__ import annotations

import fnmatch
import ipaddress
import re
import subprocess
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import yaml

GUARD_FILE = ".client-data-guard.yml"
ALLOW_MARKER = "client-data-guard: allow"

# Plateformes partagées : ni elles ni leurs sous-domaines ne désignent un client
# (`github.com`, `api.github.com`, `cluster021.hosting.ovh.net`).
SHARED_DOMAINS = {
    "github.com", "gitlab.com", "bitbucket.org", "googleapis.com", "google.com",
    "gstatic.com", "cloudflare.com", "amazonaws.com", "azurewebsites.net",
    "ovh.net", "ovh.com", "ovh.fr", "ovhcloud.com", "o2switch.net", "gandi.net",
    "scaleway.com", "hetzner.com", "online.net", "free.fr", "orange.fr",
    "wordpress.com", "wordpress.org", "prestashop.com", "dolibarr.org",
    "nextcloud.com", "redmine.org", "brevo.com", "sendinblue.com", "mailjet.com",
    "stripe.com", "paypal.com", "letsencrypt.org",
}
# TLD reconnus. Liste fermée, volontairement : dans un texte technique, `sys.stdin`,
# `json.load` ou `depot.git` ont la forme d'un nom d'hôte. Un client sous un TLD absent
# d'ici n'est simplement pas connu du garde-fou — l'ajouter ici, c'est le seul coût.
KNOWN_TLDS = set("""
com net org info biz pro name mobi asia tel travel eu fr be ch de lu nl it es pt at uk
ie dk se no fi pl cz sk hu ro bg gr hr si ee lv lt ca us mx br ar cl ma tn dz sn ci re
gp mq gf yt pf nc pm wf io co me tv cc ai app dev cloud online site tech store shop xyz
top club live space website agency studio design digital email network solutions
services company group bzh paris alsace corsica eus quebec immo bio eco farm wine
restaurant cafe boutique fashion art photo media news blog page social academy
education school training coach consulting expert finance legal health care fit
""".split())
# TLD et suffixes qui ne désignent jamais une machine publique.
NON_PUBLIC_SUFFIXES = (".example", ".test", ".local", ".localhost", ".lxc", ".lan",
                       ".internal", ".invalid", ".home", ".localdomain")

_HOST_RE = re.compile(r"(?<![a-z0-9@.-])((?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
                      r"[a-z][a-z0-9-]{1,23})(?![a-z0-9-])", re.I)
_EMAIL_RE = re.compile(r"[a-z0-9._%+-]+@(?:[a-z0-9-]+\.)+[a-z]{2,24}", re.I)
_IPV4_RE = re.compile(r"(?<![\d.])(\d{1,3}(?:\.\d{1,3}){3})(?![\d.])")
# Un slug « mot courant » n'est signalé que collé à l'un de ces caractères.
_IDENT_NEIGHBOURS = "/_-@:`"


def fold(s: str) -> str:
    """Minuscules sans accents : « Cliénta » et « clienta » sont le même motif."""
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


@dataclass
class Patterns:
    """Ce que le garde-fou cherche. Les valeurs viennent des données privées."""
    slugs: set = field(default_factory=set)
    common_slugs: set = field(default_factory=set)
    names: set = field(default_factory=set)      # noms d'entité, « prénom nom » de contacts
    hosts: set = field(default_factory=set)      # hôtes complets ET domaines enregistrables
    emails: set = field(default_factory=set)
    ips: set = field(default_factory=set)
    _compiled: list = field(default_factory=list, repr=False)

    def empty(self) -> bool:
        return not (self.slugs or self.common_slugs or self.names or self.hosts
                    or self.emails or self.ips)

    def counts(self) -> dict:
        return {"slugs": len(self.slugs | self.common_slugs), "noms": len(self.names),
                "hôtes": len(self.hosts), "adresses": len(self.emails), "ip": len(self.ips)}

    def compile(self):
        """Motifs appliqués au texte PLIÉ (`fold`) — donc sans casse ni accent."""
        c = []   # le plus spécifique d'abord : adresse > hôte > IP > nom > slug
        for e in sorted(self.emails, key=len, reverse=True):
            c.append(("adresse", re.compile(r"(?<![a-z0-9._%+-])" + re.escape(e) + r"(?![a-z0-9])")))
        for h in sorted(self.hosts, key=len, reverse=True):
            # un point peut être échappé (`srv\.client\.com` dans une regex de test)
            labels = [re.escape(x) for x in h.split(".")]
            c.append(("domaine", re.compile(r"(?<![a-z0-9-])(?:[a-z0-9-]+\\?\.)*"
                                            + r"\\?\.".join(labels) + r"(?![a-z0-9-])")))
        for ip in sorted(self.ips):
            c.append(("ip", re.compile(r"(?<![\d.])" + re.escape(ip) + r"(?![\d.])")))
        for name in sorted(self.names, key=len, reverse=True):
            words = [re.escape(w) for w in name.split()]
            c.append(("nom", re.compile(r"(?<![a-z0-9])" + r"[\s_-]+".join(words) + r"(?![a-z0-9])")))
        for s in sorted(self.slugs, key=len, reverse=True):
            c.append(("client", re.compile(r"(?<![a-z0-9])" + _slug_rx(s) + r"(?![a-z0-9])")))
        for s in sorted(self.common_slugs, key=len, reverse=True):
            n = re.escape(_IDENT_NEIGHBOURS)
            c.append(("client", re.compile(
                rf"(?:(?<=[{n}])" + _slug_rx(s) + r"(?![a-z0-9])|(?<![a-z0-9])" + _slug_rx(s)
                + rf"(?=[{n}]))")))
        self._compiled = c
        return self

    def scan(self, line: str):
        """→ [(type, extrait)] pour une ligne. Vide si rien, ou marqueur d'exception."""
        if ALLOW_MARKER in line:
            return []
        if not self._compiled:
            self.compile()
        folded = fold(line)
        hits, taken = [], []
        for kind, rx in self._compiled:
            for m in rx.finditer(folded):
                a, b = m.span()
                if any(a < y and x < b for x, y in taken):   # déjà couvert par un motif plus long
                    continue
                taken.append((a, b))
                hits.append((kind, m.group(0)))
        return hits


def _slug_rx(slug: str) -> str:
    """`client-h` couvre aussi `client_h` et `clienth`."""
    return r"[-_]?".join(re.escape(p) for p in re.split(r"[-_]", fold(slug)))


# ── collecte dans les données privées ────────────────────────────────────────

def _walk_strings(obj):
    if isinstance(obj, dict):
        for v in obj.values():
            yield from _walk_strings(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from _walk_strings(v)
    elif isinstance(obj, str):
        yield obj


def _registrable(host: str) -> str:
    parts = host.split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


def _public_host(h: str) -> bool:
    h = h.lower().rstrip(".")
    if "." not in h or h.endswith(NON_PUBLIC_SUFFIXES):
        return False
    return h.rsplit(".", 1)[1] in KNOWN_TLDS


def _add_text(text: str, pat: Patterns, own: set, public: set):
    for e in _EMAIL_RE.findall(text):
        e = e.lower()
        dom = e.split("@", 1)[1]
        if dom in own or _registrable(dom) in own or not _public_host(dom):
            continue
        pat.emails.add(e)
        _add_host(dom, pat, own, public)
    for h in _HOST_RE.findall(text):
        _add_host(h, pat, own, public)
    for ip in _IPV4_RE.findall(text):
        try:
            a = ipaddress.ip_address(ip)
        except ValueError:
            continue
        # `1.7.8.11` est une version (PrestaShop), pas une machine : une IP de serveur
        # n'a presque jamais tous ses octets aussi petits.
        if a.is_global and max(int(o) for o in ip.split(".")) > 20:
            pat.ips.add(ip)


def _add_host(h: str, pat: Patterns, own: set, public: set):
    h = h.lower().rstrip(".")
    if not _public_host(h):
        return
    reg = _registrable(h)
    if reg in own or reg in public or reg in SHARED_DOMAINS:
        return                     # webmail, domaine maison, plateforme partagée : jamais un client
    pat.hosts.add(h)
    pat.hosts.add(reg)


def load_guard_config(repo_top: Path) -> dict:
    f = Path(repo_top) / GUARD_FILE
    try:
        data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return {}
    return data if isinstance(data, dict) else {}


def collect(cfg, common_words=()) -> Patterns:
    """Motifs tirés des données privées du PM (`cfg` = PMConfig)."""
    from pm_mail_routing import OWN_DOMAINS_DEFAULT, PUBLIC_DOMAINS  # liste maintenue là-bas
    own = {d.lower() for d in OWN_DOMAINS_DEFAULT}
    public = {d.lower() for d in PUBLIC_DOMAINS}
    common = {fold(w) for w in common_words}
    pat = Patterns()

    clients = []
    for slug, _path in cfg.iter_entities():
        if slug.startswith("."):
            continue                                   # dossier caché : pas une entité
        try:
            meta = cfg.client_meta(slug) or {}
        except Exception:
            meta = {}
        if (meta.get("type") or "client") != "client":
            continue                                   # produit, soi-même : publiables
        clients.append(slug)
        (pat.common_slugs if fold(slug) in common else pat.slugs).add(fold(slug))
        name = fold(str(meta.get("name") or "")).strip()
        if name and name != fold(slug) and len(name) >= 4 and name not in common:
            pat.names.add(re.sub(r"\s+", " ", name))
        for s in _walk_strings(meta):
            _add_text(s, pat, own, public)

    for ent, proj, ppath in cfg.iter_projects():
        if ent not in clients:
            continue
        try:
            for s in _walk_strings(cfg.project_meta(ent, proj) or {}):
                _add_text(s, pat, own, public)
        except Exception:
            pass
        env = Path(ppath) / "project" / "environments.md"
        if env.is_file():
            try:
                _add_text(env.read_text(encoding="utf-8", errors="ignore"), pat, own, public)
            except OSError:
                pass

    try:
        contacts = Path(cfg.path("contacts_dir"))
    except (KeyError, Exception):
        contacts = None
    if contacts and contacts.is_dir():
        for f in sorted(contacts.glob("*.yml")):
            try:
                c = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
            except (OSError, yaml.YAMLError):
                continue
            if not isinstance(c, dict) or c.get("internal"):
                continue
            first, last = str(c.get("first_name") or "").strip(), str(c.get("last_name") or "").strip()
            if first and last:
                pat.names.add(fold(f"{first} {last}"))
            for e in c.get("emails") or []:
                _add_text(str(e), pat, own, public)

    try:
        routing = Path(cfg.path("mail_routing_file"))
    except (KeyError, Exception):
        routing = None
    if routing and routing.is_file():
        try:
            r = yaml.safe_load(routing.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError):
            r = {}
        for addr in (r.get("addresses") or {}):
            _add_text(str(addr), pat, own, public)
        for dom in (r.get("domains") or {}):
            _add_host(str(dom), pat, own, public)

    return pat.compile()


# ── ce qu'on contrôle ────────────────────────────────────────────────────────

@dataclass
class Finding:
    path: str
    line: int
    kind: str
    match: str

    def __str__(self):
        return f"{self.path}:{self.line}: [{self.kind}] {self.match}"


def _exempt(path: str, globs) -> bool:
    return path == GUARD_FILE or any(fnmatch.fnmatch(path, g) for g in globs or ())


def staged_added_lines(repo_top: Path):
    """→ [(chemin, n° de ligne, texte)] des lignes AJOUTÉES dans l'index."""
    out = subprocess.run(["git", "-C", str(repo_top), "diff", "--cached", "-U0", "--no-color",
                          "--no-ext-diff", "--diff-filter=ACMR"],
                         capture_output=True, text=True, errors="replace", check=True).stdout
    res, path, lineno = [], None, 0
    for raw in out.splitlines():
        if raw.startswith("+++ "):
            p = raw[4:]
            path = None if p == "/dev/null" else (p[2:] if p.startswith("b/") else p)
        elif raw.startswith("@@"):
            m = re.search(r"\+(\d+)", raw)
            lineno = int(m.group(1)) if m else 0
        elif raw.startswith("Binary files"):
            continue
        elif raw.startswith("+") and path is not None:
            res.append((path, lineno, raw[1:]))
            lineno += 1
    return res


def check_lines(lines, pat: Patterns, exempt=()):
    found = []
    for path, n, text in lines:
        if _exempt(path, exempt):
            continue
        for kind, m in pat.scan(text):
            found.append(Finding(path, n, kind, m))
    return found


def check_staged(repo_top: Path, pat: Patterns, exempt=()):
    return check_lines(staged_added_lines(repo_top), pat, exempt)


def check_tree(repo_top: Path, pat: Patterns, exempt=(), max_bytes=2_000_000):
    """Audit de tout le versionné (HEAD de l'arbre de travail)."""
    files = subprocess.run(["git", "-C", str(repo_top), "ls-files", "-z"],
                           capture_output=True, check=True).stdout.decode("utf-8", "replace")
    found = []
    for rel in filter(None, files.split("\0")):
        if _exempt(rel, exempt):
            continue
        f = Path(repo_top) / rel
        try:
            if not f.is_file() or f.is_symlink() or f.stat().st_size > max_bytes:
                continue
            data = f.read_bytes()
        except OSError:
            continue
        if b"\0" in data[:8000]:
            continue
        for i, text in enumerate(data.decode("utf-8", "replace").splitlines(), 1):
            for kind, m in pat.scan(text):
                found.append(Finding(rel, i, kind, m))
    return found


def check_history(repo_top: Path, pat: Patterns, exempt=(), max_bytes=2_000_000):
    """Audit de TOUT l'historique : chaque version de chaque fichier, sur toutes les
    références, fichiers supprimés compris — plus les messages de commit. C'est ce
    qu'un miroir publie, pas seulement le HEAD. Une trouvaille = une version (blob) ;
    `line` est la ligne dans cette version."""
    top = str(repo_top)
    listing = subprocess.run(["git", "-C", top, "rev-list", "--objects", "--all"],
                             capture_output=True, check=True).stdout.decode("utf-8", "replace")
    paths = {}
    for row in listing.splitlines():
        sha, _, path = row.partition(" ")
        if path and sha not in paths:
            paths[sha] = path
    found = []
    proc = subprocess.Popen(["git", "-C", top, "cat-file", "--batch"],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    try:
        for sha, path in paths.items():
            if _exempt(path, exempt):
                continue
            proc.stdin.write((sha + "\n").encode())
            proc.stdin.flush()
            head = proc.stdout.readline().split()
            if len(head) < 3:
                continue
            size = int(head[2])
            data = proc.stdout.read(size)
            proc.stdout.read(1)
            if head[1] != b"blob" or size > max_bytes or b"\0" in data[:8000]:
                continue
            for i, text in enumerate(data.decode("utf-8", "replace").splitlines(), 1):
                for kind, m in pat.scan(text):
                    found.append(Finding(f"{path}@{sha[:8]}", i, kind, m))
    finally:
        proc.stdin.close()
        proc.wait()
    log = subprocess.run(["git", "-C", top, "log", "--all", "--format=%H%x00%B%x01"],
                         capture_output=True, check=True).stdout.decode("utf-8", "replace")
    for chunk in log.split("\x01"):
        sha, _, body = chunk.strip("\n").partition("\x00")
        for i, text in enumerate(body.splitlines(), 1):
            for kind, m in pat.scan(text):
                found.append(Finding(f"commit {sha[:8]}", i, kind, m))
    return found
