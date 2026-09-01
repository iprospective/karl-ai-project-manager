#!/usr/bin/env python3
"""karl-mail-send — Envoie un email depuis karl@iprospective.fr via SMTP iProspective.

Après envoi SMTP réussi, le message est aussi ré-appendé (IMAP APPEND) dans le
dossier Sent du compte, pour que la boîte reflète les envois de Karl. Pas de
fetch IMAP ni de threading entrant par ailleurs — voir tâches sœurs
(RM1724/1725/1726) et roadmap V2 pour réception.

Credentials résolus à la volée depuis le vault déclaré, via scripts/resolve-secret.sh
(jamais loggués, jamais persistés). Si le vault est locked, abort propre.

Append automatique au .log.md du ticket si --rm-id fourni.

Usage :
    karl-mail-send.py --to client@x.fr --subject "Avancement" --body "Texte"
    echo "Corps multilignes" | karl-mail-send.py --to a@b.fr --subject S --body -
    karl-mail-send.py --to a@b.fr --subject "Q sur infra" --body "..." --rm-id 1234
    karl-mail-send.py --to a@b.fr --cc m@x.fr --bcc archive@x.fr --subject S --body -

Pré-requis :
- vault-agentd actif (lance unlock-vault.sh sinon)
- Item : secret://vw-ipro/iprospective-agents/karl@mail.iprospective.net
  (surchargeable par KARL_MAIL_SECRET_URI ; la forme vaultwarden:// reste valide)
  (username = karl@iprospective.fr, password = mot de passe Postfix)
  Surchargeable par la variable KARL_MAIL_SECRET_URI.
  (username = karl@iprospective.fr, password = mot de passe Postfix)
"""
import argparse
import email.utils
import imaplib
import smtplib
import ssl
import subprocess
import os
import sys
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pm_paths import PMConfig

SMTP_HOST = "mail.iprospective.net"
SMTP_PORT = 465
IMAP_HOST = "mail.iprospective.net"
IMAP_PORT = 993
IMAP_SENT_FOLDER = "Sent"
# Item du vault portant les identifiants SMTP. Nom EXACT de l'item :
# "karl@mail.iprospective.net" (convention <compte>@<service>)
# Viser le nom EXACT est impératif : si le nom ne correspond a aucun item, bw bascule
# en recherche FLOUE. Tant qu'un seul item correspond ca passe — et masque le probleme —
# mais des qu'un second item contient la meme sous-chaine (ex. atlas@mail.iprospective.net),
# l'appel echoue sur "More than one result was found". Vecu deux fois le 2026-08-01.
# Surchargeable par KARL_MAIL_SECRET_URI (ex. dans le .env du repo PM).
VAULT_URI = os.environ.get(
    "KARL_MAIL_SECRET_URI",
    "secret://vw-ipro/iprospective-agents/karl@mail.iprospective.net",
)
FROM_NAME = "Karl (iProspective Agent)"


def resolve_secret(uri, field):
    """Appelle resolve-secret.sh. Sys.exit avec un message clair si vault locked."""
    helper = Path(__file__).resolve().parent / "resolve-secret.sh"
    if not helper.is_file():
        sys.exit(f"ERREUR : {helper} manquant")
    r = subprocess.run([str(helper), uri, field], capture_output=True, text=True)
    if r.returncode == 2:
        sys.exit("ERREUR : vault verrouillé. Lance `scripts/unlock-vault.sh` puis recommence.")
    if r.returncode == 3:
        sys.exit("ERREUR : vault-agentd non actif. Lance `scripts/unlock-vault.sh`.")
    if r.returncode != 0:
        sys.exit(
            f"ERREUR resolve-secret ({r.returncode}) sur {uri} : {r.stderr.strip()}\n"
            f"  → si 'More than one result': l'item n'existe pas sous ce nom exact,\n"
            f"    le backend bascule en recherche floue. Vérifier le nom dans le vault ou\n"
            f"    surcharger KARL_MAIL_SECRET_URI."
        )
    return r.stdout.rstrip("\n")


def build_message(args, body, from_addr):
    msg = EmailMessage()
    subject = args.subject
    if args.rm_id and not subject.startswith(f"[RM{args.rm_id}]"):
        subject = f"[RM{args.rm_id}] {subject}"
    msg["Subject"] = subject
    msg["From"] = email.utils.formataddr((FROM_NAME, from_addr))
    msg["To"] = ", ".join(args.to)
    if args.cc:
        msg["Cc"] = ", ".join(args.cc)
    msg["Date"] = email.utils.formatdate(localtime=True)
    msg["Message-ID"] = email.utils.make_msgid(domain="iprospective.fr")
    if args.reply_to:
        msg["Reply-To"] = args.reply_to
    if args.in_reply_to:
        msg["In-Reply-To"] = args.in_reply_to
        msg["References"] = args.in_reply_to
    msg.set_content(body)
    return msg


def append_to_log(rm_id, msg, bcc_list, dry_run=False):
    """Append une entrée au .log.md du ticket si trouvable."""
    cfg = PMConfig.load()
    md_path = cfg.find_task(rm_id)
    if not md_path:
        print(f"⚠ RM{rm_id} non trouvé localement — pas de log appendé", file=sys.stderr)
        return None
    log_path = md_path.parent / md_path.name.replace(".md", ".log.md")
    ts = datetime.now().strftime("%Y-%m-%dT%H:%M")
    lines = [
        f"\n## {ts} — Mail envoyé (karl-mail-send)",
        "Tokens : 0 | Durée : 0 min",
        "",
        f"To: {msg['To']}",
    ]
    if msg["Cc"]:
        lines.append(f"Cc: {msg['Cc']}")
    if bcc_list:
        lines.append(f"Bcc: {', '.join(bcc_list)}")
    lines.append(f"Subject: {msg['Subject']}")
    lines.append(f"Message-ID: {msg['Message-ID']}")
    if msg["In-Reply-To"]:
        lines.append(f"In-Reply-To: {msg['In-Reply-To']}")
    lines.append("")
    body = msg.get_content().rstrip()
    for ln in body.splitlines():
        lines.append(f"> {ln}" if ln else ">")
    lines.append("")
    if dry_run:
        return log_path
    with log_path.open("a", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return log_path


def append_to_sent(username, password, msg):
    """IMAP APPEND du message dans le dossier Sent. Non bloquant : le SMTP a
    déjà réussi, une erreur ici ne doit pas faire échouer l'envoi — juste
    prévenir sur stderr."""
    try:
        with imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT, timeout=20) as m:
            m.login(username, password)
            typ, _ = m.append(
                IMAP_SENT_FOLDER, "(\\Seen)", None, msg.as_bytes()
            )
            if typ != "OK":
                print(f"⚠ IMAP APPEND vers {IMAP_SENT_FOLDER} : réponse {typ}", file=sys.stderr)
                return False
            return True
    except Exception as e:
        print(f"⚠ IMAP APPEND vers {IMAP_SENT_FOLDER} échoué (mail envoyé quand même) : {e}", file=sys.stderr)
        return False


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--to", action="append", required=True, help="Destinataire (répétable)")
    ap.add_argument("--cc", action="append", default=[], help="Copie (répétable)")
    ap.add_argument("--bcc", action="append", default=[], help="Copie cachée (répétable)")
    ap.add_argument("--subject", required=True)
    ap.add_argument("--body", required=True, help="Corps texte (ou '-' pour stdin)")
    ap.add_argument("--rm-id", type=int, help="Si fourni : préfixe subject + append au .log.md")
    ap.add_argument("--reply-to", help="Reply-To header")
    ap.add_argument("--in-reply-to", help="Message-ID auquel ce mail répond (chainage RFC)")
    ap.add_argument("--dry-run", action="store_true", help="N'envoie pas, affiche le mail formaté")
    args = ap.parse_args()

    body = sys.stdin.read() if args.body == "-" else args.body
    body = body.rstrip() + "\n"
    if not body.strip():
        sys.exit("ERREUR : body vide")

    # Charge .env pour permettre éventuels overrides futurs (host/port)
    PMConfig.load()

    # Résolution credentials (2 calls : username + password).
    # Skip si --dry-run (permet de valider la génération du message sans vault).
    if args.dry_run:
        username = "karl@iprospective.fr"
        password = None
    else:
        username = resolve_secret(VAULT_URI, "username")
        password = resolve_secret(VAULT_URI, "password")
        if not username or not password:
            sys.exit("ERREUR : credentials du vault vides")

    from_addr = username  # SMTP impose typiquement From = compte auth
    msg = build_message(args, body, from_addr)

    # Récap pré-envoi
    print(f"From    : {msg['From']}")
    print(f"To      : {msg['To']}")
    if msg["Cc"]:    print(f"Cc      : {msg['Cc']}")
    if args.bcc:     print(f"Bcc     : {', '.join(args.bcc)} (non visible dans les headers)")
    print(f"Subject : {msg['Subject']}")
    print(f"Mid     : {msg['Message-ID']}")
    print(f"Corps   : {len(body)} octets, {body.count(chr(10))} ligne(s)")

    if args.dry_run:
        print("\n--- DRY RUN — RFC822 message ---\n")
        print(msg.as_string())
        if args.rm_id:
            lp = append_to_log(args.rm_id, msg, args.bcc, dry_run=True)
            if lp:
                print(f"\n(append simulé → {lp.name})")
        return

    # Envoi
    ctx = ssl.create_default_context()
    rcpts = list(args.to) + list(args.cc) + list(args.bcc)
    try:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=ctx, timeout=20) as s:
            s.login(username, password)
            s.send_message(msg, from_addr=from_addr, to_addrs=rcpts)
    except smtplib.SMTPAuthenticationError as e:
        sys.exit(f"ERREUR SMTP auth ({e.smtp_code}) : {e.smtp_error.decode(errors='replace')}")
    except smtplib.SMTPException as e:
        sys.exit(f"ERREUR SMTP : {e}")
    except OSError as e:
        sys.exit(f"ERREUR réseau : {e}")

    print(f"\n✓ Mail envoyé via {SMTP_HOST}:{SMTP_PORT}")

    if append_to_sent(username, password, msg):
        print(f"✓ Copié dans {IMAP_SENT_FOLDER} ({IMAP_HOST}:{IMAP_PORT})")

    if args.rm_id:
        lp = append_to_log(args.rm_id, msg, args.bcc)
        if lp:
            cfg = PMConfig.load()
            print(f"✓ Log local appendé : {lp.relative_to(cfg.projects_root)}")


if __name__ == "__main__":
    main()
