#!/usr/bin/env python3
"""karl-mail-fetch — relève IMAP de la boîte de karl → file de triage (RM2668).

Lot T1 du chantier RM2666 (CDC `docs/cdc-rm2666-emails-vers-tickets.md`) : lire la
boîte, écarter ce qui n'est pas une demande humaine, et déposer le reste dans une
**file de travail** que le triage (RM2669/RM2670) et le cockpit (RM2671) consomment.

Ce script LIT, il ne décide rien : aucun ticket n'est créé ici.

Principes (CDC § 4.2/4.3) :

- **Le serveur trie d'abord.** Les dossiers « de confiance » (classement Sieve, RM2667)
  sont relevés en priorité — mais `INBOX` est relevée AUSSI, en file secondaire : un
  correspondant inconnu du carnet y tombe par construction, et c'est justement le mail
  qui mérite un ticket. Le classement serveur est un accélérateur, pas une garantie.
- **Non destructif.** Jamais de DELETE ni de MOVE ; `\\Seen` seulement avec `--mark-seen`.
- **Hors git.** La file vit sous `$XDG_STATE_HOME/karl-agent/mail/` (jamais dans le repo
  de données PM, qui est poussé sur GitLab — pas de courrier client dans l'historique).
- **Idempotent.** Un index des `Message-ID` déjà vus évite toute re-proposition ; deux
  relèves d'affilée ne produisent rien la seconde fois.

Usage :
    karl-mail-fetch.py --list-folders            # inventaire réel de la boîte
    karl-mail-fetch.py                           # relève (dossiers de confiance + INBOX)
    karl-mail-fetch.py --days 7 --limit 20
    karl-mail-fetch.py --folder clients --folder INBOX
    karl-mail-fetch.py --dry-run --json          # ce qui SERAIT mis en file
    karl-mail-fetch.py --queue                   # file courante, sans connexion IMAP

Configuration (`.env` du repo PM ou variables d'environnement) :
    KARL_MAIL_SECRET_URI        item Vaultwarden (défaut : compte karl, cf. karl-mail-send)
    KARL_MAIL_IMAP_HOST / _PORT hôte/port IMAP (défaut mail.iprospective.net:993)
    KARL_MAIL_TRUSTED_FOLDERS   csv des dossiers de confiance (défaut : aucun — cf. RM2667)
    KARL_MAIL_EXCLUDE_FOLDERS   csv des dossiers jamais relevés (Sent, Junk, virtual.*, …)
    KARL_MAIL_MACHINE_SENDERS   csv de motifs additionnels d'expéditeurs machine
    KARL_AGENT_STATE_DIR        racine d'état (défaut : ~/.local/state/karl-agent)

Pré-requis : vault déverrouillé (`scripts/unlock-vault.sh`) — sauf `--queue` et
`--list-folders --dry-run`.
"""
import argparse
import email
import email.utils
import fnmatch
import hashlib
import imaplib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta
from email.header import decode_header, make_header
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pm_output import out                                  # noqa: E402
from pm_paths import PMConfig                              # noqa: E402

IMAP_HOST_DEFAULT = "mail.iprospective.net"
IMAP_PORT_DEFAULT = 993
VAULT_URI_DEFAULT = "vaultwarden://iprospective/iprospective-agents/karl@mail.iprospective.net"

# Dossiers jamais relevés : ce qu'on a écrit soi-même, les corbeilles, et les
# dossiers `virtual.*` (vues agrégées du plugin Dovecot « virtual » — leurs messages
# sont déjà dans un vrai dossier ; les relever ferait un doublon).
EXCLUDE_FOLDERS_DEFAULT = [
    "Sent", "INBOX.Sent", "Drafts", "INBOX.Drafts", "Junk", "INBOX.Junk",
    "Trash", "INBOX.Trash", "Archives", "INBOX.Archives", "Spam", "virtual*",
]

# Expéditeurs « machine » : notifications, robots, listes. Écartés de la file — ils ne
# donnent jamais lieu à un ticket client. Complétable par KARL_MAIL_MACHINE_SENDERS.
MACHINE_SENDER_PATTERNS = [
    r"^(no-?reply|donotreply|do-not-reply|ne[-_.]?pas[-_.]?repondre|nepasrepondre)@",
    r"^(mailer-daemon|postmaster|bounce[sd]?|abuse|root|cron|daemon|www-data)@",
    r"^(notifications?|alerte?s?|monitoring|nagios|zabbix|newsletter)@",
    r"@(gitlab|zabbix|vaultwarden|bitwarden|sentry|atlassian)\.",
    r"@(github\.com|gitlab\.com|noreply\.[a-z]+)$",
]

# En-têtes qui signent un envoi automatique (RFC 3834 / usage courant). Un humain qui
# écrit depuis son client mail n'en pose aucun.
AUTO_HEADERS = {
    "auto-submitted": lambda v: v.strip().lower() != "no",
    "precedence": lambda v: v.strip().lower() in ("bulk", "list", "junk", "auto_reply"),
    "list-unsubscribe": lambda v: True,
    "list-id": lambda v: True,
    "x-auto-response-suppress": lambda v: True,
}

RM_SUBJECT_RE = re.compile(r"\[RM(\d{1,6})\]")


# ── Chemins d'état (hors git) ────────────────────────────────────────────────
def state_dir() -> Path:
    root = os.environ.get("KARL_AGENT_STATE_DIR") or os.environ.get("KARL_AGENT_LOG_DIR")
    if not root:
        base = os.environ.get("XDG_STATE_HOME") or (Path.home() / ".local" / "state")
        root = Path(base) / "karl-agent"
    return Path(root) / "mail"


def queue_dir() -> Path:
    return state_dir() / "queue"


def index_file() -> Path:
    return state_dir() / "index.json"


def _ensure_dirs():
    queue_dir().mkdir(parents=True, exist_ok=True)
    # Courrier client : lisible par le seul propriétaire.
    for d in (state_dir(), queue_dir()):
        try:
            d.chmod(0o700)
        except OSError:
            pass


def load_index() -> dict:
    f = index_file()
    if not f.is_file():
        return {}
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (ValueError, OSError):
        out.warn(f"index illisible ({f}) — reparti à vide, doublons possibles")
        return {}


def save_index(index: dict):
    _ensure_dirs()
    tmp = index_file().with_suffix(".json.tmp")
    tmp.write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(index_file())
    try:
        index_file().chmod(0o600)
    except OSError:
        pass


def msg_key(message_id: str) -> str:
    """Clé stable et courte d'un message — nom de fichier et entrée d'index."""
    return hashlib.sha1(message_id.encode("utf-8", "replace")).hexdigest()[:16]


# ── Secrets ──────────────────────────────────────────────────────────────────
def resolve_secret(uri, field):
    """Appelle resolve-secret.sh. Message clair (et sortie non nulle) si vault fermé."""
    helper = Path(__file__).resolve().parent / "resolve-secret.sh"
    if not helper.is_file():
        out.fail(f"{helper} manquant")
    r = subprocess.run([str(helper), uri, field], capture_output=True, text=True)
    if r.returncode in (2, 3):
        out.fail("vault verrouillé ou vault-agentd absent",
                 remede="lance `scripts/unlock-vault.sh` puis relance la relève")
    if r.returncode != 0:
        out.fail(f"resolve-secret ({r.returncode}) sur {uri} : {r.stderr.strip()}",
                 remede="vérifie le nom EXACT de l'item Vaultwarden (ou KARL_MAIL_SECRET_URI)")
    return r.stdout.rstrip("\n")


# ── Décodage des messages ────────────────────────────────────────────────────
def dec(raw) -> str:
    """Décode un en-tête MIME (RFC 2047) en texte lisible, sans jamais lever."""
    if not raw:
        return ""
    try:
        return str(make_header(decode_header(raw))).strip()
    except (UnicodeDecodeError, LookupError, ValueError):
        return str(raw).strip()


def body_text(msg, limit: int) -> tuple:
    """Retourne (texte, tronqué?). Préfère text/plain ; repli grossier sur text/html."""
    plain, html = [], []
    for part in msg.walk():
        if part.get_content_maintype() == "multipart":
            continue
        disp = (part.get("Content-Disposition") or "").lower()
        if "attachment" in disp:
            continue
        ctype = part.get_content_type()
        if ctype not in ("text/plain", "text/html"):
            continue
        try:
            payload = part.get_payload(decode=True) or b""
            charset = part.get_content_charset() or "utf-8"
            text = payload.decode(charset, errors="replace")
        except (LookupError, ValueError):
            continue
        (plain if ctype == "text/plain" else html).append(text)
    text = "\n".join(plain).strip()
    if not text and html:
        raw = "\n".join(html)
        raw = re.sub(r"(?is)<(script|style).*?</\1>", " ", raw)
        raw = re.sub(r"(?is)<br\s*/?>|</p>", "\n", raw)
        raw = re.sub(r"(?s)<[^>]+>", " ", raw)
        text = re.sub(r"[ \t]{2,}", " ", raw)
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
    truncated = len(text) > limit
    return (text[:limit], truncated)


def attachments(msg) -> list:
    items = []
    for part in msg.walk():
        disp = (part.get("Content-Disposition") or "").lower()
        name = part.get_filename()
        if "attachment" not in disp and not name:
            continue
        try:
            size = len(part.get_payload(decode=True) or b"")
        except (ValueError, TypeError):
            size = None
        items.append({"name": dec(name) or "(sans nom)",
                      "type": part.get_content_type(), "size": size})
    return items


def sender_address(msg) -> str:
    _, addr = email.utils.parseaddr(msg.get("From") or "")
    return addr.lower().strip()


def machine_reason(msg, addr: str, extra_patterns: list) -> str:
    """Motif pour lequel ce message est « machine », ou '' s'il a l'air humain."""
    for h, is_auto in AUTO_HEADERS.items():
        v = msg.get(h)
        if v and is_auto(v):
            return f"en-tête {h}"
    for pat in MACHINE_SENDER_PATTERNS + extra_patterns:
        try:
            if addr and re.search(pat, addr, re.I):
                return f"expéditeur {pat}"
        except re.error:
            out.warn(f"motif d'expéditeur machine invalide, ignoré : {pat!r}")
    return ""


def build_entry(msg, folder: str, uid: str, account: str, body_chars: int) -> dict:
    addr = sender_address(msg)
    subject = dec(msg.get("Subject"))
    date_hdr = msg.get("Date") or ""
    try:
        dt = email.utils.parsedate_to_datetime(date_hdr)
        date_iso = dt.isoformat()
    except (TypeError, ValueError):
        date_iso = ""
    text, truncated = body_text(msg, body_chars)
    m = RM_SUBJECT_RE.search(subject or "")
    mid = (msg.get("Message-ID") or f"<no-id-{folder}-{uid}@karl-mail-fetch>").strip()
    return {
        "key": msg_key(mid),
        "message_id": mid,
        "account": account,
        "folder": folder,
        "uid": uid,
        "from_name": dec(email.utils.parseaddr(msg.get("From") or "")[0]),
        "from": addr,
        "to": dec(msg.get("To")),
        "cc": dec(msg.get("Cc")),
        "subject": subject,
        "date": date_iso,
        "in_reply_to": (msg.get("In-Reply-To") or "").strip(),
        "references": (msg.get("References") or "").strip(),
        # Sujet portant [RM<id>] : c'est une réponse dans un fil existant — le triage
        # proposera une NOTE sur ce ticket, pas un nouveau ticket (CDC D6).
        "rm_id": int(m.group(1)) if m else None,
        "kind": "reply" if m else "new",
        "body": text,
        "body_truncated": truncated,
        "attachments": attachments(msg),
        "fetched_at": datetime.now().strftime("%Y-%m-%dT%H:%M"),
        "status": "queued",
    }


# ── IMAP ─────────────────────────────────────────────────────────────────────
def imap_connect(host, port, user, password):
    try:
        m = imaplib.IMAP4_SSL(host, port, timeout=30)
        m.login(user, password)
        return m
    except imaplib.IMAP4.error as e:
        out.fail(f"IMAP auth/protocole sur {host}:{port} : {e}",
                 remede="vérifie l'item Vaultwarden et l'état du compte")
    except OSError as e:
        out.fail(f"réseau IMAP {host}:{port} : {e}")


def list_folders(m) -> list:
    typ, data = m.list()
    if typ != "OK":
        out.fail(f"IMAP LIST : réponse {typ}")
    names = []
    for raw in data or []:
        line = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else str(raw)
        # Format : (\HasNoChildren) "." "INBOX.clients"  — le nom est le dernier champ.
        m2 = re.match(r'^\((?P<flags>[^)]*)\)\s+"?(?P<sep>[^"]*)"?\s+(?P<name>.+)$', line)
        if not m2:
            continue
        name = m2.group("name").strip().strip('"')
        names.append({"name": name, "flags": m2.group("flags").split()})
    return names


def excluded(name: str, patterns: list) -> bool:
    return any(fnmatch.fnmatch(name, p) or fnmatch.fnmatch(name.lower(), p.lower())
               for p in patterns)


def search_uids(m, folder: str, since_days: int, unseen_only: bool) -> list:
    typ, _ = m.select(f'"{folder}"', readonly=True)
    if typ != "OK":
        out.warn(f"dossier absent ou illisible, ignoré : {folder}")
        return []
    crit = []
    if since_days:
        since = (datetime.now() - timedelta(days=since_days)).strftime("%d-%b-%Y")
        crit += ["SINCE", since]
    if unseen_only:
        crit += ["UNSEEN"]
    typ, data = m.uid("SEARCH", None, *(crit or ["ALL"]))
    if typ != "OK":
        out.warn(f"SEARCH {folder} : réponse {typ}")
        return []
    return (data[0].split() if data and data[0] else [])


def fetch_message(m, uid: bytes, mark_seen: bool):
    """RFC822.PEEK : lire NE MARQUE PAS lu (sauf --mark-seen explicite)."""
    item = "(RFC822)" if mark_seen else "(BODY.PEEK[])"
    typ, data = m.uid("FETCH", uid, item)
    if typ != "OK" or not data or not isinstance(data[0], tuple):
        return None
    return email.message_from_bytes(data[0][1])


# ── Relève ───────────────────────────────────────────────────────────────────
def csv_env(name: str, default: list) -> list:
    raw = os.environ.get(name)
    if raw is None:
        return list(default)
    return [x.strip() for x in raw.split(",") if x.strip()]


def collect(m, folders, args, account, index, extra_machine) -> dict:
    stats = {"new": 0, "known": 0, "machine": 0, "self": 0, "scanned": 0}
    entries = []
    for folder in folders:
        uids = search_uids(m, folder, args.days, args.unseen_only)
        if args.limit:
            uids = uids[-args.limit:]          # les plus récents d'abord servis
        out.info(f"{folder} : {len(uids)} message(s) dans la fenêtre")
        for uid in reversed(uids):
            stats["scanned"] += 1
            msg = fetch_message(m, uid, args.mark_seen)
            if msg is None:
                out.warn(f"FETCH {folder}/{uid.decode()} : réponse inattendue, ignoré")
                continue
            addr = sender_address(msg)
            mid = (msg.get("Message-ID") or f"<no-id-{folder}-{uid.decode()}@karl-mail-fetch>").strip()
            key = msg_key(mid)
            if key in index:
                stats["known"] += 1
                continue
            if addr and addr == account.lower():
                # Copie d'un envoi de karl (Sent relevé par erreur, Bcc à soi-même).
                stats["self"] += 1
                index[key] = {"status": "self", "at": datetime.now().strftime("%Y-%m-%dT%H:%M")}
                continue
            reason = machine_reason(msg, addr, extra_machine)
            if reason:
                stats["machine"] += 1
                index[key] = {"status": "machine", "reason": reason, "from": addr,
                              "at": datetime.now().strftime("%Y-%m-%dT%H:%M")}
                continue
            entry = build_entry(msg, folder, uid.decode(), account, args.body_chars)
            entries.append(entry)
            index[key] = {"status": "queued", "from": addr, "folder": folder,
                          "subject": entry["subject"], "rm_id": entry["rm_id"],
                          "at": entry["fetched_at"]}
            stats["new"] += 1
    return {"stats": stats, "entries": entries}


def write_queue(entries: list):
    _ensure_dirs()
    for e in entries:
        f = queue_dir() / f"{e['key']}.json"
        f.write_text(json.dumps(e, ensure_ascii=False, indent=1), encoding="utf-8")
        try:
            f.chmod(0o600)
        except OSError:
            pass


def read_queue() -> list:
    d = queue_dir()
    if not d.is_dir():
        return []
    items = []
    for f in sorted(d.glob("*.json")):
        try:
            items.append(json.loads(f.read_text(encoding="utf-8")))
        except (ValueError, OSError):
            out.warn(f"entrée de file illisible, ignorée : {f.name}")
    items.sort(key=lambda e: e.get("date") or "", reverse=True)
    return items


def print_queue(items: list, as_json: bool):
    if as_json:
        print(json.dumps(items, ensure_ascii=False, indent=1))
        return
    if not items:
        out.op("file", extra="vide")
        return
    for e in items:
        tag = f"RM{e['rm_id']} ↩" if e.get("rm_id") else "nouveau"
        date = (e.get("date") or "")[:16].replace("T", " ")
        print(f"  {e['key']}  {date:16}  {tag:10}  {e.get('from', ''):32.32}  "
              f"{(e.get('subject') or '(sans objet)')[:60]}")
    out.op("file", extra=f"{len(items)} email(s) en attente de triage")


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    out.add_args(ap)          # --verbose / --help-full (et raccourcit --help)
    ap.add_argument("--list-folders", action="store_true",
                    help="Inventaire des dossiers de la boîte (et rien d'autre)")
    ap.add_argument("--queue", action="store_true",
                    help="Affiche la file de triage courante, sans connexion IMAP")
    ap.add_argument("--folder", action="append", default=[],
                    help="Dossier à relever (répétable). Défaut : dossiers de confiance + INBOX")
    ap.add_argument("--days", type=int, default=30,
                    help="Fenêtre de relève en jours (0 = tout l'historique du dossier)")
    ap.add_argument("--limit", type=int, default=50,
                    help="Nombre maximum de messages examinés par dossier (0 = pas de limite)")
    ap.add_argument("--body-chars", type=int, default=4000,
                    help="Taille maximale du corps conservé par message")
    ap.add_argument("--unseen-only", action="store_true",
                    help="Ne relever que les messages non lus")
    ap.add_argument("--mark-seen", action="store_true",
                    help="Marque \\Seen les messages relevés (DÉSACTIVÉ par défaut)")
    ap.add_argument("--json", action="store_true",
                    help="Sortie machine : les entrées relevées (ou la file) en JSON")
    ap.add_argument("--dry-run", action="store_true",
                    help="N'écrit ni la file ni l'index — montre ce qui serait mis en file")
    args = ap.parse_args()
    out.configure(args)

    PMConfig.load()                       # charge .env (overrides host/dossiers/URI)

    if args.queue:
        print_queue(read_queue(), args.json)
        return

    host = os.environ.get("KARL_MAIL_IMAP_HOST", IMAP_HOST_DEFAULT)
    port = int(os.environ.get("KARL_MAIL_IMAP_PORT", IMAP_PORT_DEFAULT))
    uri = os.environ.get("KARL_MAIL_SECRET_URI", VAULT_URI_DEFAULT)
    trusted = csv_env("KARL_MAIL_TRUSTED_FOLDERS", [])
    excludes = csv_env("KARL_MAIL_EXCLUDE_FOLDERS", EXCLUDE_FOLDERS_DEFAULT)
    extra_machine = csv_env("KARL_MAIL_MACHINE_SENDERS", [])

    user = resolve_secret(uri, "username")
    password = resolve_secret(uri, "password")
    if not user or not password:
        out.fail("identifiants Vaultwarden vides",
                 remede=f"vérifie l'item {uri}")
    m = imap_connect(host, port, user, password)
    try:
        available = [f["name"] for f in list_folders(m)]
        if args.list_folders:
            for name in available:
                mark = "·"
                if name in trusted:
                    mark = "★"                       # dossier de confiance (RM2667)
                elif excluded(name, excludes):
                    mark = "✗"                       # jamais relevé
                print(f"  {mark} {name}")
            out.op("dossiers", extra=f"{len(available)} sur {host} ({user})")
            return

        if args.folder:
            folders = [f for f in args.folder]
            unknown = [f for f in folders if f not in available]
            if unknown:
                out.warn(f"dossier(s) inconnu(s) de la boîte : {', '.join(unknown)}")
        else:
            # Confiance d'abord, INBOX ensuite — jamais l'un SANS l'autre (CDC § 4.2) :
            # un correspondant inconnu du carnet n'est classé nulle part.
            folders = [f for f in trusted if f in available]
            inbox = next((f for f in available if f.upper() == "INBOX"), None)
            if inbox:
                folders.append(inbox)
            folders = [f for f in folders if not excluded(f, excludes)]
        if not folders:
            out.fail("aucun dossier à relever",
                     remede="précise --folder, ou renseigne KARL_MAIL_TRUSTED_FOLDERS")

        index = load_index()
        before = len(index)
        res = collect(m, folders, args, user, index, extra_machine)
    finally:
        try:
            m.logout()
        except (imaplib.IMAP4.error, OSError):
            pass

    st = res["stats"]
    if not args.dry_run:
        write_queue(res["entries"])
        save_index(index)
    if args.json:
        print(json.dumps(res["entries"], ensure_ascii=False, indent=1))
    out.op("relève", extra=(f"{st['new']} nouveau(x) · {st['known']} déjà vu(s) · "
                            f"{st['machine']} machine · {st['self']} de karl · "
                            f"dossiers : {', '.join(folders)}"
                            + (" [dry-run]" if args.dry_run else "")))
    out.info(f"index : {before} → {len(index)} entrées ({index_file()})")
    if res["entries"] and not args.dry_run:
        out.info(f"file : {queue_dir()}")


if __name__ == "__main__":
    main()
