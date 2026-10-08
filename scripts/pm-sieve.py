#!/usr/bin/env python3
"""pm-sieve — piloter les filtres Sieve d'une boîte par ManageSieve (RFC 5804) : lire, comparer, écrire sous garde (RM3171).

Toute modification de filtre passait par l'interface Roundcube : à la main, sans trace, sans
test, sans retour arrière. En RM2667, poser une condition d'authenticité a demandé un client
ManageSieve jetable écrit dans un dossier temporaire. Cet outil le remplace.

Il PILOTE, il ne pense pas : ni génération de règles depuis le carnet (RM2517), ni politique
de filtrage. Il lit, compare, écrit, active et supprime — et, pour écrire, passe trois gardes :

  1. **Identité de la boîte** : l'identifiant authentifié doit être la boîte demandée
     (`--account`). Écrire le filtre de la mauvaise boîte est irréparable en silence.
  2. **Validation par le serveur avant d'écrire** : `CHECKSCRIPT` (RFC 5804 §2.12), ou à
     défaut `PUTSCRIPT` sous un nom temporaire aussitôt supprimé. Un script refusé par
     Pigeonhole laisse l'original intact.
  3. **Sauvegarde octet pour octet** de l'ancien script dans `<state_dir>/sieve-backups/`
     (durable, hors git — un filtre porte des adresses de clients), avant de remplacer.
     Puis relecture indépendante : le script relu doit être celui envoyé.

Aucun secret en argv, environ ni sortie : l'identifiant et le mot de passe sont lus du vault
(`resolve-secret.sh`) et ne transitent que dans l'`AUTHENTICATE PLAIN`.

Usage :
    pm-sieve list                               [--account karl@iprospective.fr]
    pm-sieve get roundcube                      # le script sur la sortie standard
    pm-sieve diff roundcube --from-file f.sieve
    pm-sieve put roundcube --from-file f.sieve --dry-run
    pm-sieve put roundcube --from-file f.sieve  # gardes 1-2-3, puis relecture
    pm-sieve activate roundcube
    pm-sieve delete ancien                      # refusé si c'est le script actif
    pm-sieve backups [roundcube]                # sauvegardes locales, la plus récente en dernier
    pm-sieve restore roundcube [--backup <f>]   # remet une sauvegarde en place (gardes du put)

Config : `pm.config.yml :: sieve` — `host`, `port`, `accounts` (boîte → URI du vault).
"""
import argparse
import base64
import difflib
import re
import socket
import ssl
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pm_paths import PMConfig  # noqa: E402

DEFAULT_HOST = "mail.iprospective.net"
DEFAULT_PORT = 4190
DEFAULT_ACCOUNT = "karl@iprospective.fr"
DEFAULT_ACCOUNTS = {
    "karl@iprospective.fr": "vaultwarden://iprospective/iprospective-agents/karl@mail.iprospective.net",
}
RE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


class SieveError(Exception):
    """Refus ou échec : le message dit ce qui n'a PAS été fait."""


# ── Protocole : fonctions pures ──────────────────────────────────────────

def quote(s):
    """Chaîne ManageSieve entre guillemets (\\ et " échappés). Refuse CR/LF (→ littéral)."""
    if "\r" in s or "\n" in s:
        raise ValueError("chaîne multi-ligne : utiliser un littéral")
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def literal(data):
    """Littéral non synchronisant {n+} (RFC 5804 §4) — le serveur n'attend pas de relance."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    return b"{%d+}\r\n" % len(data) + data


RE_LIT = re.compile(rb"\{(\d+)\+?\}$")
RE_STATUS = re.compile(r'^(OK|NO|BYE)(?:\s+\(([^)]*)\))?(?:\s+(.*))?$', re.I)


def tokens(line):
    """Découpe une ligne de réponse en jetons : chaînes entre guillemets (déséchappées) et atomes."""
    out, i, n = [], 0, len(line)
    while i < n:
        c = line[i]
        if c == " ":
            i += 1
        elif c == '"':
            j, buf = i + 1, []
            while j < n and line[j] != '"':
                if line[j] == "\\" and j + 1 < n:
                    j += 1
                buf.append(line[j])
                j += 1
            out.append("".join(buf))
            i = j + 1
        else:
            j = i
            while j < n and line[j] != " ":
                j += 1
            out.append(line[i:j])
            i = j
    return out


def parse_status(line):
    """« OK (CODE) "texte" » → (statut, code, texte) ; None si ce n'est pas une ligne de statut."""
    m = RE_STATUS.match(line.strip())
    if not m:
        return None
    text = m.group(3) or ""
    t = tokens(text)
    return m.group(1).upper(), (m.group(2) or "").strip(), (t[0] if len(t) == 1 else text).strip()


def parse_capabilities(items):
    """Lignes de capacités ("SIEVE" "fileinto …") → {NOM: valeur}."""
    caps = {}
    for it in items:
        t = tokens(it)
        if t:
            caps[t[0].upper()] = t[1] if len(t) > 1 else ""
    return caps


def parse_listscripts(items):
    """Lignes de LISTSCRIPTS → ([noms], actif|None)."""
    names, active = [], None
    for it in items:
        t = tokens(it)
        if not t:
            continue
        names.append(t[0])
        if len(t) > 1 and t[1].upper() == "ACTIVE":
            active = t[0]
    return names, active


def auth_plain(user, password):
    """Charge utile SASL PLAIN (RFC 4616) : \\0user\\0password, en base64."""
    return base64.b64encode(b"\0" + user.encode() + b"\0" + password.encode()).decode()


def unified(old, new, name):
    return "".join(difflib.unified_diff(
        old.splitlines(keepends=True), new.splitlines(keepends=True),
        fromfile=f"{name} (serveur)", tofile=f"{name} (fichier)"))


def same_account(authenticated, requested):
    return (authenticated or "").strip().lower() == (requested or "").strip().lower()


def backup_name(script, now=None):
    return f"{script}.{time.strftime('%Y%m%d-%H%M%S', time.localtime(now))}.sieve"


def libre(backup_dir, nom):
    """Chemin de sauvegarde non pris. L'horodatage est à la seconde : deux écritures dans la
    même seconde (une restauration juste après un put) écraseraient la première."""
    f = backup_dir / nom
    i = 2
    while f.exists():
        f = backup_dir / f"{nom[:-len('.sieve')]}-{i}.sieve"
        i += 1
    return f


def backups_of(backup_dir, script):
    """Sauvegardes d'un script, de la plus ancienne à la plus récente (le nom porte l'horodatage)."""
    if not backup_dir.is_dir():
        return []
    return sorted(backup_dir.glob(f"{script}.*.sieve"))


def pick_backup(backup_dir, script, choisie=None):
    """Sauvegarde à restaurer : celle demandée, sinon la plus récente. Refus explicite si rien."""
    if choisie:
        f = Path(choisie)
        if not f.is_file():
            raise SieveError(f"sauvegarde introuvable : {f}")
        return f
    dispo = backups_of(backup_dir, script)
    if not dispo:
        raise SieveError(f"aucune sauvegarde de {script} sous {backup_dir} — rien restauré")
    return dispo[-1]


def lire(path):
    """Lit un script SANS traduire les fins de ligne : un script Sieve est en CRLF, et
    `read_text()` le rendrait en LF — la promesse « octet pour octet » se perdrait ici."""
    return Path(path).read_bytes().decode("utf-8")


def check_name(name):
    if not RE_NAME.match(name or ""):
        raise SieveError(f"nom de script invalide : {name!r}")


# ── Transport & client ───────────────────────────────────────────────────

class Conn:
    """Lecture ligne/littéral sur un flux binaire ; `write` brut. Injectable pour les tests."""

    def __init__(self, rfile, wfile):
        self.rfile, self.wfile = rfile, wfile

    def readline(self):
        line = self.rfile.readline()
        if not line:
            raise SieveError("connexion fermée par le serveur")
        return line.rstrip(b"\r\n")

    def read(self, n):
        buf = b""
        while len(buf) < n:
            chunk = self.rfile.read(n - len(buf))
            if not chunk:
                raise SieveError("connexion fermée au milieu d'un littéral")
            buf += chunk
        return buf

    def write(self, data):
        self.wfile.write(data)
        self.wfile.flush()


class Client:
    def __init__(self, conn):
        self.conn = conn
        self.caps = {}

    def response(self):
        """Lit jusqu'à OK/NO/BYE → (statut, code, texte, [lignes|littéraux])."""
        items = []
        while True:
            raw = self.conn.readline()
            m = RE_LIT.search(raw)
            if m and not raw.upper().startswith((b"OK", b"NO", b"BYE")):
                items.append(self.conn.read(int(m.group(1))))
                self.conn.readline()                    # fin de ligne après le littéral
                continue
            line = raw.decode("utf-8", "replace")
            st = parse_status(line)
            if st:
                return st + (items,)
            items.append(line)

    def command(self, *parts):
        """Envoie une commande (atomes, chaînes déjà quotées, littéraux bytes) et lit la réponse."""
        data = b" ".join(p if isinstance(p, bytes) else p.encode() for p in parts) + b"\r\n"
        self.conn.write(data)
        return self.response()

    def ok(self, *parts, what=""):
        st, code, text, items = self.command(*parts)
        if st != "OK":
            raise SieveError(f"{what or parts[0]} refusé par le serveur : {st} {code} {text}".strip())
        return items

    def greeting(self):
        st, _, text, items = self.response()
        if st != "OK":
            raise SieveError(f"accueil refusé : {text}")
        self.caps = parse_capabilities(items)
        return self.caps

    def login(self, user, password):
        st, code, text, _ = self.command("AUTHENTICATE", quote("PLAIN"), quote(auth_plain(user, password)))
        if st != "OK":
            raise SieveError(f"authentification refusée ({code or text})")
        # Certains serveurs renvoient les capacités après AUTH ; on les relit si besoin.

    def listscripts(self):
        return parse_listscripts(self.ok("LISTSCRIPTS"))

    def getscript(self, name):
        items = self.ok("GETSCRIPT", quote(name), what=f"GETSCRIPT {name}")
        blobs = [i for i in items if isinstance(i, bytes)]
        return (blobs[0] if blobs else b"").decode("utf-8")

    def checkscript(self, text):
        st, code, msg, _ = self.command("CHECKSCRIPT", literal(text))
        return st == "OK", f"{code} {msg}".strip()

    def putscript(self, name, text):
        self.ok("PUTSCRIPT", quote(name), literal(text), what=f"PUTSCRIPT {name}")

    def deletescript(self, name):
        self.ok("DELETESCRIPT", quote(name), what=f"DELETESCRIPT {name}")

    def setactive(self, name):
        self.ok("SETACTIVE", quote(name), what=f"SETACTIVE {name}")

    def logout(self):
        try:
            self.command("LOGOUT")
        except (SieveError, OSError):
            pass


def validate_on_server(cli, text):
    """Garde 2 : le serveur doit accepter le script AVANT qu'on touche à l'original.

    CHECKSCRIPT si le serveur parle ManageSieve 1.0 ; sinon PUTSCRIPT sous un nom temporaire,
    supprimé aussitôt. → (accepté, message du serveur)."""
    if cli.caps.get("VERSION"):
        return cli.checkscript(text)
    tmp = f"pm-sieve-check-{int(time.time())}"
    try:
        cli.putscript(tmp, text)
    except SieveError as e:
        return False, str(e)
    cli.deletescript(tmp)
    return True, ""


def put(cli, name, text, *, account, authenticated, backup_dir, dry_run, log=print):
    """Écriture gardée. Renvoie le chemin de sauvegarde (ou None s'il n'y avait rien à sauver)."""
    check_name(name)
    if not same_account(authenticated, account):
        raise SieveError(f"boîte authentifiée {authenticated!r} ≠ boîte demandée {account!r} — rien écrit")
    names, active = cli.listscripts()
    old = cli.getscript(name) if name in names else None
    if old == text:
        log(f"= {name} : identique sur le serveur, rien à faire")
        return None
    log(unified(old or "", text, name) or f"(nouveau script {name})")
    ok, msg = validate_on_server(cli, text)
    if not ok:
        raise SieveError(f"script refusé par le serveur ({msg}) — l'original n'a pas bougé")
    log(f"✓ validé par le serveur")
    if dry_run:
        log("[dry-run] rien écrit")
        return None
    saved = None
    if old is not None:
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup_dir.chmod(0o700)
        saved = libre(backup_dir, backup_name(name))
        saved.write_bytes(old.encode("utf-8"))
        saved.chmod(0o600)
        if saved.read_bytes() != old.encode("utf-8"):
            raise SieveError(f"sauvegarde {saved} incomplète — rien écrit sur le serveur")
        log(f"✓ sauvegarde : {saved} ({len(old.encode())} octets)")
    cli.putscript(name, text)
    if cli.getscript(name) != text:
        raise SieveError(f"relecture de {name} différente de ce qui a été envoyé — "
                         f"restaurer depuis {saved}" if saved else "relecture différente")
    log(f"✓ {name} écrit et relu" + (" — toujours ACTIF" if active == name else ""))
    return saved


def delete(cli, name, *, account, authenticated):
    check_name(name)
    if not same_account(authenticated, account):
        raise SieveError(f"boîte authentifiée {authenticated!r} ≠ boîte demandée {account!r} — rien supprimé")
    names, active = cli.listscripts()
    if name not in names:
        raise SieveError(f"{name} n'existe pas")
    if name == active:
        raise SieveError(f"{name} est le script ACTIF — activer d'abord un autre script ; rien supprimé")
    cli.deletescript(name)


# ── Connexion réelle & secrets ───────────────────────────────────────────

def resolve_secret(uri, field):
    helper = Path(__file__).resolve().parent / "resolve-secret.sh"
    r = subprocess.run([str(helper), uri, field], capture_output=True, text=True)
    if r.returncode in (2, 3):
        raise SieveError("vault verrouillé ou vault-agentd absent — scripts/unlock-vault.sh puis relancer")
    if r.returncode != 0:
        raise SieveError(f"resolve-secret ({r.returncode}) sur {uri} : {r.stderr.strip()[:200]}")
    return r.stdout.rstrip("\n")


def connect(host, port, timeout=20):
    sock = socket.create_connection((host, port), timeout=timeout)
    cli = Client(Conn(sock.makefile("rb"), sock.makefile("wb")))
    cli.greeting()
    if "STARTTLS" not in cli.caps:
        sock.close()
        raise SieveError("le serveur n'annonce pas STARTTLS — refus d'envoyer des identifiants en clair")
    cli.ok("STARTTLS")
    tls = ssl.create_default_context().wrap_socket(sock, server_hostname=host)
    cli.conn = Conn(tls.makefile("rb"), tls.makefile("wb"))
    cli.greeting()                                   # capacités renvoyées après STARTTLS
    return cli


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("action",
                    choices=("list", "get", "diff", "put", "activate", "delete", "backups", "restore"))
    ap.add_argument("script", nargs="?")
    ap.add_argument("--account", default=None, help=f"boîte (défaut {DEFAULT_ACCOUNT})")
    ap.add_argument("--from-file", type=Path, help="script Sieve local (diff, put)")
    ap.add_argument("--backup", help="restore : sauvegarde précise (défaut : la plus récente)")
    ap.add_argument("--dry-run", action="store_true", help="put : diff + validation serveur, rien écrit")
    args = ap.parse_args(argv)

    cfg = PMConfig.load()
    conf = getattr(cfg, "sieve", {}) or {}
    account = (args.account or conf.get("account") or DEFAULT_ACCOUNT).lower()
    accounts = {k.lower(): v for k, v in {**DEFAULT_ACCOUNTS, **(conf.get("accounts") or {})}.items()}
    backup_root = Path(cfg.state_dir) / "sieve-backups" / account

    try:
        if args.action == "backups":
            files = backups_of(backup_root, args.script or "*")
            for f in files:
                print(f"{f}  ({f.stat().st_size} octets)")
            if not files:
                print(f"(aucune sauvegarde sous {backup_root})")
            return 0
        if args.action in ("get", "diff", "put", "activate", "delete", "restore"):
            if not args.script:
                ap.error(f"{args.action} exige un nom de script")
            check_name(args.script)
        if args.action in ("diff", "put") and not args.from_file:
            ap.error(f"{args.action} exige --from-file")
        text = lire(args.from_file) if args.from_file else None
        if account not in accounts:
            raise SieveError(f"boîte {account} inconnue — déclarer son URI de vault dans "
                             "pm.config.yml :: sieve.accounts")
        uri = accounts[account]
        user = resolve_secret(uri, "username")
        password = resolve_secret(uri, "password")
        cli = connect(conf.get("host") or DEFAULT_HOST, int(conf.get("port") or DEFAULT_PORT))
        try:
            cli.login(user, password)
            del password
            if args.action == "list":
                names, active = cli.listscripts()
                for n in names:
                    print(f"{n}{'  ACTIVE' if n == active else ''}")
            elif args.action == "get":
                sys.stdout.write(cli.getscript(args.script))
            elif args.action == "diff":
                names, _ = cli.listscripts()
                old = cli.getscript(args.script) if args.script in names else ""
                d = unified(old, text, args.script)
                print(d or f"= {args.script} identique")
                return 1 if d else 0
            elif args.action == "put":
                put(cli, args.script, text, account=account, authenticated=user,
                    backup_dir=backup_root, dry_run=args.dry_run)
            elif args.action == "activate":
                if not same_account(user, account):
                    raise SieveError(f"boîte authentifiée {user!r} ≠ {account!r} — rien activé")
                cli.setactive(args.script)
                print(f"✓ {args.script} actif")
            elif args.action == "restore":
                src = pick_backup(backup_root, args.script, args.backup)
                print(f"↩ restauration de {src.name}", file=sys.stderr)
                # La sauvegarde repasse par put : mêmes gardes (boîte, validation serveur,
                # sauvegarde de l'état COURANT avant de le remplacer, relecture).
                put(cli, args.script, lire(src), account=account,
                    authenticated=user, backup_dir=backup_root, dry_run=args.dry_run)
            elif args.action == "delete":
                delete(cli, args.script, account=account, authenticated=user)
                print(f"✓ {args.script} supprimé")
        finally:
            cli.logout()
    except (SieveError, OSError, ssl.SSLError) as e:
        print(f"✗ pm-sieve : {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
