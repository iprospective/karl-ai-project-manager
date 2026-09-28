#!/usr/bin/env python3
"""Tests RM3319 — reconnaissance et lecture des avis de non-remise (pm_mail_bounce)."""
import email
import email.policy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pm_mail_bounce as B  # noqa: E402

ok = ko = 0


def check(label, cond, detail=""):
    global ok, ko
    if cond:
        ok += 1; print(f"✓ {label}")
    else:
        ko += 1; print(f"✗ {label} — {detail}")


def parse(raw):
    return email.message_from_string(raw, policy=email.policy.compat32)


# Rejet Postfix réel (forme RFC 3464), calqué sur celui du 2026-09-28 (RM1839).
POSTFIX = """From: MAILER-DAEMON@mail.iprospective.net (Mail Delivery System)
Subject: Undelivered Mail Returned to Sender
To: karl@iprospective.fr
Auto-Submitted: auto-replied
Message-ID: <20260928111901.ABC@mail.iprospective.net>
MIME-Version: 1.0
Content-Type: multipart/report; report-type=delivery-status; boundary="BND"

--BND
Content-Type: text/plain; charset=us-ascii

This is the mail system at host mail.iprospective.net.
I'm sorry to have to inform you that your message could not be delivered.

<florian@calyclay.com>: host mx.calyclay.com said: 550 5.1.1
    <florian@calyclay.com>: Recipient address rejected: User unknown

--BND
Content-Type: message/delivery-status

Reporting-MTA: dns; mail.iprospective.net
Arrival-Date: Mon, 28 Sep 2026 13:19:00 +0200

Final-Recipient: rfc822; florian@calyclay.com
Original-Recipient: rfc822;florian@calyclay.com
Action: failed
Status: 5.1.1
Remote-MTA: dns; mx.calyclay.com
Diagnostic-Code: smtp; 550 5.1.1 <florian@calyclay.com>: Recipient address
    rejected: User unknown in virtual mailbox table

--BND
Content-Type: text/rfc822-headers

From: "Karl (iProspective Agent)" <karl@iprospective.fr>
To: florian@calyclay.com
Subject: [RM1839] Serveur du bureau : remplacement d'un disque dur
Message-ID: <179059421911.257195.5333977437253070631@iprospective.fr>

--BND--
"""

m = parse(POSTFIX)
check("DSN standard reconnu", B.is_bounce(m))
info = B.parse(m)
check("forme standard", info["standard"])
check("destinataire en échec", [r["address"] for r in info["recipients"]] == ["florian@calyclay.com"], info["recipients"])
check("code de statut", info["recipients"][0]["status"] == "5.1.1")
check("motif (repli de ligne recollé, préfixe smtp; ôté)",
      info["recipients"][0]["diagnostic"].startswith("550 5.1.1") and "virtual mailbox table" in info["recipients"][0]["diagnostic"],
      info["recipients"][0]["diagnostic"])
check("échec définitif", info["failed"] is True)
check("Message-ID d'origine", info["original_message_id"] == "<179059421911.257195.5333977437253070631@iprospective.fr>")
check("ticket d'origine tiré de l'objet", info["rm_id"] == 1839)
check("MTA rapporteur", info["reporting_mta"] == "mail.iprospective.net")
check("résumé lisible", B.summary(info).startswith("florian@calyclay.com — 5.1.1 — 550") and B.summary(info).endswith("(RM1839)"), B.summary(info))

# Original joint en message/rfc822 et simple retard : on prévient, sans alarmer.
DELAYED = POSTFIX.replace("Action: failed", "Action: delayed").replace("Status: 5.1.1", "Status: 4.4.1") \
    .replace("Content-Type: text/rfc822-headers\n", "Content-Type: message/rfc822\n")
info = B.parse(parse(DELAYED))
check("retard (Action: delayed) : pas un échec définitif", info["failed"] is False, info)
check("original en message/rfc822 lu aussi", info["rm_id"] == 1839 and info["original_message_id"].startswith("<1790594"))

# Rejet non standard (texte seul) d'un vieux serveur.
LEGACY = """From: Mail Delivery Subsystem <postmaster@old.example.org>
Subject: Mail delivery failed: returning message to sender
To: karl@iprospective.fr
Content-Type: text/plain; charset=utf-8

This message was created automatically by mail delivery software.
A message that you sent could not be delivered to one or more of its recipients.

  <inconnu@example.org>
    SMTP error from remote mail server after RCPT TO:<inconnu@example.org>:
    550 5.1.1 User unknown

------ This is a copy of the message, including all the headers. ------
Subject: [RM42] Relance
"""
m = parse(LEGACY)
check("rejet non standard reconnu (expéditeur + objet)", B.is_bounce(m))
info = B.parse(m)
check("non standard : destinataire extrait du texte", [r["address"] for r in info["recipients"]] == ["inconnu@example.org"], info["recipients"])
check("non standard : statut extrait", info["recipients"][0]["status"] == "5.1.1")
check("non standard : ticket trouvé dans l'objet recopié", info["rm_id"] is None or info["rm_id"] == 42)

# Faux positifs à éviter.
HUMAIN = parse("From: Florian <florian.f@calyclay.com>\nSubject: Re: livraison undelivered ?\n\nBonjour\n")
check("un humain qui parle de « undelivered » n'est pas un rejet", not B.is_bounce(HUMAIN))
NOTIF = parse("From: MAILER-DAEMON@x.org\nSubject: Rapport hebdomadaire\n\nRien\n")
check("un robot système sans objet de rejet n'est pas un rejet", not B.is_bounce(NOTIF))
check("parse() d'un non-rejet = None", B.parse(HUMAIN) is None)

print(f"\n{ok} ok, {ko} échec(s)")
sys.exit(1 if ko else 0)
