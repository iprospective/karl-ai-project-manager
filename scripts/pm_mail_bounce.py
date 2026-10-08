"""pm_mail_bounce — reconnaître et lire un avis de non-remise (RM3319).

Un rejet (MAILER-DAEMON, postmaster…) arrive dans la boîte de karl comme n'importe quel
courrier « machine ». `karl-mail-fetch` l'écartait sans bruit : le 2026-09-28, un mail
envoyé à une adresse erronée (RM1839) a été annoncé « envoyé » alors qu'il avait été
rejeté, et c'est un humain qui l'a trouvé dans les logs. Ce module dit si un message EST
un rejet, et en extrait ce qu'il faut pour alerter : destinataire(s) en échec, code, motif,
et le mail d'origine (Message-ID, objet, ticket `[RM<id>]`).

Deux formes reconnues :
- **DSN standard** (RFC 3464) : `multipart/report; report-type=delivery-status`, avec une
  partie `message/delivery-status` (champs par destinataire) et le message d'origine en
  `message/rfc822` ou `text/rfc822-headers` ;
- **rejet non standard** (vieux serveurs, relais maison) : expéditeur système ET objet de
  rejet ; on lit alors le texte, au mieux.

Aucune écriture, aucun réseau : des fonctions pures, testées par `test_pm_mail_bounce.py`.
"""
import email
import email.policy
import re
from email.message import Message
from typing import Optional

BOUNCE_SENDER_RE = re.compile(r"^(mailer-daemon|postmaster|mail-daemon|mailerdaemon)@", re.I)
BOUNCE_SUBJECT_RE = re.compile(
    r"(undeliver|undelivered|delivery status notification|delivery (has )?failed|"
    r"mail delivery (failed|system)|returned mail|failure notice|non[- ]remis|"
    r"non[- ]distribu|échec de (la )?(remise|distribution)|delivery failure)", re.I)
RM_SUBJECT_RE = re.compile(r"\[RM(\d{1,6})\]")
# « 550 5.1.1 <x@y>: Recipient address rejected » dans un rejet en texte libre.
TEXT_RCPT_RE = re.compile(r"<([^<>\s@]+@[^<>\s]+)>")
TEXT_STATUS_RE = re.compile(r"\b([245]\.\d{1,3}\.\d{1,3})\b")
TEXT_SMTP_RE = re.compile(r"\b([45]\d\d)[ -]")


def _addr(value: str) -> str:
    """`rfc822; x@y` → `x@y` (champs Final-/Original-Recipient)."""
    v = (value or "").strip()
    if ";" in v:
        v = v.split(";", 1)[1]
    return v.strip().strip("<>").lower()


def _fields(block: str) -> list:
    """Parse un corps `message/delivery-status` en liste de groupes de champs (dicts)."""
    groups, cur, last = [], {}, None
    for line in block.splitlines():
        if not line.strip():
            if cur:
                groups.append(cur)
            cur, last = {}, None
            continue
        if line[:1] in (" ", "\t") and last:          # repli de ligne
            cur[last] += " " + line.strip()
            continue
        if ":" in line:
            k, _, v = line.partition(":")
            last = k.strip().lower()
            cur[last] = v.strip()
    if cur:
        groups.append(cur)
    return groups


def _part_text(part: Message) -> str:
    payload = part.get_payload(decode=True)
    if payload is None:
        sub = part.get_payload()
        if isinstance(sub, list):                    # message/delivery-status vu comme multipart
            return "\n\n".join(s.as_string() if isinstance(s, Message) else str(s) for s in sub)
        return str(sub or "")
    return payload.decode(part.get_content_charset() or "utf-8", errors="replace")


def is_bounce(msg: Message) -> bool:
    """Vrai si le message est un avis de non-remise (DSN ou rejet reconnaissable)."""
    ctype = (msg.get_content_type() or "").lower()
    if ctype == "multipart/report" and \
            (msg.get_param("report-type") or "").lower() == "delivery-status":
        return True
    frm = email.utils.parseaddr(msg.get("From") or "")[1]
    subject = str(msg.get("Subject") or "")
    return bool(BOUNCE_SENDER_RE.search(frm or "") and BOUNCE_SUBJECT_RE.search(subject))


def parse(msg: Message) -> Optional[dict]:
    """Détail d'un rejet, ou None si ce n'est pas un rejet.

    {"recipients": [{"address", "action", "status", "diagnostic"}], "failed": bool,
     "original_message_id", "original_subject", "rm_id", "reporting_mta", "standard": bool}
    `failed` est faux pour un simple avis de retard (Action: delayed) : on prévient, on
    n'alarme pas."""
    if not is_bounce(msg):
        return None
    out = {"recipients": [], "original_message_id": "", "original_subject": "",
           "rm_id": None, "reporting_mta": "", "standard": False}
    original = None
    text_parts = []
    for part in msg.walk():
        ct = part.get_content_type().lower()
        if ct == "message/delivery-status":
            out["standard"] = True
            groups = _fields(_part_text(part))
            if groups:
                out["reporting_mta"] = _addr(groups[0].get("reporting-mta", ""))
            for g in groups:
                rcpt = g.get("final-recipient") or g.get("original-recipient")
                if not rcpt:
                    continue
                out["recipients"].append({
                    "address": _addr(rcpt),
                    "action": (g.get("action") or "").lower(),
                    "status": g.get("status", ""),
                    "diagnostic": _addr_diag(g.get("diagnostic-code", "")),
                })
        elif ct == "message/rfc822":
            sub = part.get_payload()
            if isinstance(sub, list) and sub:
                original = sub[0]
        elif ct == "text/rfc822-headers":
            original = email.message_from_string(_part_text(part), policy=email.policy.compat32)
        elif ct == "text/plain" and not part.is_multipart():
            text_parts.append(_part_text(part))

    if original is not None:
        out["original_message_id"] = (original.get("Message-ID") or "").strip()
        out["original_subject"] = str(original.get("Subject") or "").strip()

    if not out["recipients"]:                        # rejet non standard : le texte, au mieux
        texte = "\n".join(text_parts)
        statut = TEXT_STATUS_RE.search(texte) or TEXT_SMTP_RE.search(texte)
        diag = next((l.strip() for l in texte.splitlines()
                     if TEXT_SMTP_RE.search(l) or "rejected" in l.lower() or "unknown" in l.lower()), "")
        for a in dict.fromkeys(a.lower() for a in TEXT_RCPT_RE.findall(texte)):
            if BOUNCE_SENDER_RE.search(a):
                continue
            out["recipients"].append({"address": a, "action": "failed",
                                      "status": statut.group(1) if statut else "",
                                      "diagnostic": diag[:300]})

    m = RM_SUBJECT_RE.search(out["original_subject"]) or RM_SUBJECT_RE.search(str(msg.get("Subject") or ""))
    out["rm_id"] = int(m.group(1)) if m else None
    actions = {r["action"] for r in out["recipients"]}
    out["failed"] = not out["recipients"] or bool(actions - {"delayed", "relayed", "delivered", "expanded"})
    return out


def _addr_diag(v: str) -> str:
    """`smtp; 550 5.1.1 …` → `550 5.1.1 …`."""
    v = (v or "").strip()
    if ";" in v:
        v = v.split(";", 1)[1].strip()
    return v[:300]


def summary(info: dict) -> str:
    """Une ligne lisible : « x@y — 5.1.1 — 550 … (RM1839) »."""
    rcpts = ", ".join(r["address"] for r in info["recipients"]) or "destinataire inconnu"
    first = info["recipients"][0] if info["recipients"] else {}
    parts = [rcpts]
    if first.get("status"):
        parts.append(first["status"])
    if first.get("diagnostic"):
        parts.append(first["diagnostic"])
    s = " — ".join(parts)
    if info.get("rm_id"):
        s += f" (RM{info['rm_id']})"
    return s
