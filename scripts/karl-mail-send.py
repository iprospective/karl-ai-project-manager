#!/usr/bin/env python3
"""karl-mail-send — Envoie un email depuis karl@iprospective.fr via SMTP iProspective (texte, HTML, markdown rendu, pièces jointes).

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
    karl-mail-send.py --to a@b.fr --subject S --body - --html-file corps.html   # multipart
    karl-mail-send.py --to a@b.fr --subject S --markdown rapport.md             # texte + HTML rendu
    karl-mail-send.py --to a@b.fr --subject S --body - --attach a.csv --attach b.pdf

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
import mimetypes
import smtplib
import ssl
import subprocess
import os
import sys
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pm_contacts as pc                                   # noqa: E402
import yaml                                                # noqa: E402
from pm_paths import PMConfig


def resolve_refs(cfg, refs):
    """`--to-ref moulin-mathieu` → son adresse (RM3024).

    Écrire un destinataire par sa `ref` plutôt que de recopier une adresse : la
    recopie se périme en silence le jour où la personne change de boîte, et
    c'est précisément ce que l'annuaire est là pour éviter. Une ref inconnue, ou
    sans adresse, est une ERREUR bruyante — un mail envoyé à un destinataire
    deviné ne se rattrape pas."""
    if not refs:
        return []
    try:
        d = cfg.path("contacts_dir")
    except Exception:  # noqa: BLE001
        sys.exit("ERREUR : --to-ref/--cc-ref exige un annuaire (paths.contacts_dir)")
    out, manquants = [], []
    for ref in refs:
        f = d / f"{ref}.yml"
        data = {}
        if f.is_file():
            try:
                data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
            except (OSError, yaml.YAMLError):
                data = {}
        emails = [pc.norm_email(e) for e in (data.get("emails") or []) if e]
        if not emails:
            manquants.append(ref + (" (fiche absente)" if not f.is_file()
                                    else " (aucune adresse)"))
            continue
        out.append(emails[0])          # la première est l'adresse de référence
    if manquants:
        sys.exit("ERREUR : ref(s) non résolue(s) : " + ", ".join(manquants)
                 + "\n  → pm-contact.py list")
    return out

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
# Plafond du total des pièces jointes (RM3440) : au-delà, les serveurs de réception
# refusent souvent le message, et l'erreur revient en différé (mailer-daemon). On refuse
# donc AVANT d'envoyer. Surchargeable : PM_MAIL_ATTACH_MAX_MB.
ATTACH_MAX_MB_DEFAULT = 20


def preferences_mail():
    """Préférences de l'utilisateur qui fait partir le mail (RM3318), lues dans l'environnement —
    donc dans son `<core>/var/users/<user>/.env`, chargé par `PMConfig.load()` :

      PM_MAIL_FROM_NAME   nom d'affichage de l'expéditeur (défaut : FROM_NAME)
      PM_MAIL_SIGNATURE   signature ajoutée en fin de corps ; `\\n` = saut de ligne

    L'adresse, elle, reste celle du compte SMTP authentifié (karl) : le serveur l'impose."""
    sig = os.environ.get("PM_MAIL_SIGNATURE", "").replace("\\n", "\n").strip()
    nom = os.environ.get("PM_MAIL_FROM_NAME", "").strip() or FROM_NAME
    return nom, sig


def signer(body, signature):
    """Ajoute la signature, séparée par le délimiteur standard `-- `, sauf si le corps la porte
    déjà (un agent qui l'a écrite lui-même ne doit pas la voir en double)."""
    if not signature or signature in body:
        return body
    return body.rstrip() + "\n\n-- \n" + signature + "\n"


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


def load_attachments(paths, max_mb=None):
    """Lit les pièces jointes (RM3440) : [(nom, octets, maintype, subtype)].
    Fichier absent ou illisible, total au-delà du plafond : ERREUR avant tout envoi —
    un mail parti sans sa pièce jointe, ou refusé en différé, ne se rattrape pas."""
    if max_mb is None:
        try:
            max_mb = float(os.environ.get("PM_MAIL_ATTACH_MAX_MB", ATTACH_MAX_MB_DEFAULT))
        except ValueError:
            max_mb = ATTACH_MAX_MB_DEFAULT
    out, total = [], 0
    for p in paths or []:
        f = Path(p)
        if not f.is_file():
            sys.exit(f"ERREUR : pièce jointe introuvable : {p}")
        try:
            data = f.read_bytes()
        except OSError as e:
            sys.exit(f"ERREUR : pièce jointe illisible : {p} ({e})")
        total += len(data)
        ctype, encoding = mimetypes.guess_type(f.name)
        if ctype is None or encoding is not None:
            ctype = "application/octet-stream"
        maintype, subtype = ctype.split("/", 1)
        out.append((f.name, data, maintype, subtype))
    if total > max_mb * 1024 * 1024:
        sys.exit(f"ERREUR : pièces jointes trop lourdes ({total / 1048576:.1f} Mo > {max_mb:g} Mo) "
                 f"— plafond PM_MAIL_ATTACH_MAX_MB")
    return out


def render_markdown_email(text, title):
    """Markdown → page HTML d'email, même rendu que les notifications client (RM3052) :
    styles en ligne, tableaux, cases ✔/☐, aucun HTML brut qui traverse."""
    import pm_client_notify as cn
    return cn._wrap_html(title, cn.render_markdown(text))


def mime_structure(msg):
    """Arborescence MIME lisible (pour --dry-run) : type, nom de fichier, taille."""
    lines = []

    def walk(part, depth):
        size = "" if part.is_multipart() else f" — {len(part.get_payload(decode=True) or b'')} octets"
        name = part.get_filename()
        lines.append("  " * depth + f"· {part.get_content_type()}" + (f" « {name} »" if name else "") + size)
        if part.is_multipart():
            for sub in part.iter_parts():
                walk(sub, depth + 1)

    walk(msg, 0)
    return "\n".join(lines)


def build_message(args, body, from_addr, html=None, attachments=None):
    """`html` (RM3052) : ajoute une alternative HTML — le message part en
    multipart/alternative, le texte restant le repli (lecteurs sans HTML, archives).
    `attachments` (RM3440) : [(nom, octets, maintype, subtype)] — le message devient
    multipart/mixed ; le nom de fichier accentué est encodé selon RFC 2231."""
    msg = EmailMessage()
    subject = args.subject
    if args.rm_id and not subject.startswith(f"[RM{args.rm_id}]"):
        subject = f"[RM{args.rm_id}] {subject}"
    msg["Subject"] = subject
    msg["From"] = email.utils.formataddr((getattr(args, "from_name", None) or FROM_NAME, from_addr))
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
    if html:
        msg.add_alternative(html, subtype="html")
    for name, data, maintype, subtype in attachments or []:
        msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=name)
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
    pjs = [f"{p.get_filename()} ({len(p.get_payload(decode=True) or b'')} octets)"
           for p in msg.iter_attachments()] if msg.is_multipart() else []
    if pjs:
        lines.append("Pièces jointes: " + ", ".join(pjs))
    lines.append("")
    # multipart (RM3052) : c'est la partie TEXTE qu'on journalise, pas le HTML
    part = msg.get_body(preferencelist=("plain",)) if msg.is_multipart() else msg
    body = (part.get_content() if part else "").rstrip()
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
    ap.add_argument("--to", action="append", default=[], help="Destinataire (répétable)")
    ap.add_argument("--to-ref", action="append", default=[], dest="to_ref", metavar="REF",
                    help="Destinataire par sa ref d'annuaire (répétable) — "
                         "l'adresse est résolue au moment de l'envoi, jamais recopiée.")
    ap.add_argument("--cc", action="append", default=[], help="Copie (répétable)")
    ap.add_argument("--cc-ref", action="append", default=[], dest="cc_ref", metavar="REF",
                    help="Copie par sa ref d'annuaire (répétable)")
    ap.add_argument("--bcc", action="append", default=[], help="Copie cachée (répétable)")
    ap.add_argument("--subject", required=True)
    ap.add_argument("--body", help="Corps texte (ou '-' pour stdin)")
    ap.add_argument("--html-file", help="Fichier HTML joint en alternative (multipart/alternative). "
                    "Le --body texte reste le repli.")
    ap.add_argument("--markdown", metavar="FICHIER",
                    help="Corps en markdown (RM3440) : le texte est le markdown, la version HTML "
                         "en est le rendu (tableaux compris). Exclusif de --body et --html-file.")
    ap.add_argument("--attach", action="append", default=[], metavar="FICHIER",
                    help="Pièce jointe (répétable) ; type deviné depuis l'extension ; "
                         "total plafonné par PM_MAIL_ATTACH_MAX_MB (défaut 20).")
    ap.add_argument("--rm-id", type=int, help="Si fourni : préfixe subject + append au .log.md")
    ap.add_argument("--reply-to", help="Reply-To header")
    ap.add_argument("--in-reply-to", help="Message-ID auquel ce mail répond (chainage RFC)")
    ap.add_argument("--dry-run", action="store_true", help="N'envoie pas, affiche le mail formaté")
    ap.add_argument("--no-signature", action="store_true",
                    help="N'ajoute pas la signature PM_MAIL_SIGNATURE de l'utilisateur")
    args = ap.parse_args()
    if not (args.to or args.to_ref):
        ap.error("au moins un --to ou --to-ref")
    # Résolution AVANT toute autre chose : une ref inconnue doit arrêter le
    # programme avant qu'il n'ouvre le vault, pas au milieu d'un envoi.
    if args.to_ref or args.cc_ref:
        _cfg_refs = PMConfig.load()
        args.to = list(args.to) + resolve_refs(_cfg_refs, args.to_ref)
        args.cc = list(args.cc) + resolve_refs(_cfg_refs, args.cc_ref)

    if args.markdown and (args.body or args.html_file):
        ap.error("--markdown est exclusif de --body et --html-file")
    if not (args.body or args.markdown):
        ap.error("--body ou --markdown requis")
    attachments = load_attachments(args.attach)
    if args.markdown:
        try:
            body = Path(args.markdown).read_text(encoding="utf-8")
        except OSError as e:
            sys.exit(f"ERREUR : --markdown illisible : {e}")
    else:
        body = sys.stdin.read() if args.body == "-" else args.body
    body = body.rstrip() + "\n"
    if not body.strip():
        sys.exit("ERREUR : body vide")

    # Charge les .env (dont celui de l'utilisateur : préférences PM_MAIL_*, RM3318)
    PMConfig.load()
    args.from_name, signature = preferences_mail()
    if not args.no_signature:
        body = signer(body, signature)

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

    html = None
    if args.markdown:
        # rendu APRÈS la signature : la version HTML la porte aussi
        html = render_markdown_email(body, args.subject)
    if args.html_file:
        try:
            html = Path(args.html_file).read_text(encoding="utf-8")
        except OSError as e:
            sys.exit(f"ERREUR : --html-file illisible : {e}")
        if not html.strip():
            sys.exit("ERREUR : --html-file vide")

    from_addr = username  # SMTP impose typiquement From = compte auth
    msg = build_message(args, body, from_addr, html, attachments)

    # Récap pré-envoi
    print(f"From    : {msg['From']}")
    print(f"To      : {msg['To']}")
    if msg["Cc"]:    print(f"Cc      : {msg['Cc']}")
    if args.bcc:     print(f"Bcc     : {', '.join(args.bcc)} (non visible dans les headers)")
    print(f"Subject : {msg['Subject']}")
    print(f"Mid     : {msg['Message-ID']}")
    print(f"Corps   : {len(body)} octets, {body.count(chr(10))} ligne(s)"
          + (f" + HTML {len(html)} octets" if html else ""))
    for name, data, maintype, subtype in attachments:
        print(f"PJ      : {name} ({maintype}/{subtype}, {len(data)} octets)")

    if args.dry_run:
        print("\n--- DRY RUN — structure MIME ---\n")
        print(mime_structure(msg))
        if attachments:
            # le message complet serait surtout du base64 : on montre le texte, pas le binaire
            part = msg.get_body(preferencelist=("plain",))
            print("\n--- DRY RUN — corps texte ---\n")
            print(part.get_content() if part else "")
        else:
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
