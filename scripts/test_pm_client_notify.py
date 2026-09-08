#!/usr/bin/env python3
"""Tests RM3026 — notification client à la MEP (logique pure de pm_client_notify).

Ce qui est protégé ici :
  1. l'option projet se lit tolérante (bloc absent, contacts scalaire/None) et
     n'est ACTIVE que si `actif` ET au moins un contact — sinon rien à notifier ;
  2. la mise en file est IDEMPOTENTE : re-jouer `→ en_mep` ne réinitialise pas une
     file déjà posée et ne ré-ouvre pas une notif déjà envoyée ; un NOUVEAU cycle
     (déjà envoyé puis redéployé) ré-entre bien en file ;
  3. la résolution annuaire rend l'email/tel de la ref, signale les refs orphelines
     (jamais tues), et l'email agrégé est dédoublonné ;
  4. l'email récap est UN seul mail pour N tickets, avec id/titre/lien, critères et
     protocole, et un sujet accordé en nombre.

Lancer : python3 scripts/test_pm_client_notify.py
"""
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import pm_client_notify as cn  # noqa: E402

fails = []


def check(name, cond):
    print(("✓ " if cond else "✗ ") + name)
    if not cond:
        fails.append(name)


# ── 1. option projet ─────────────────────────────────────────────────────────
check("option absente => inactif, sans contact",
      cn.parse_option({}) == {"actif": False, "contacts": []})
check("contacts scalaire normalisé en liste",
      cn.parse_option({"notif_client_mep": {"actif": True, "contacts": "sandrine"}})
      == {"actif": True, "contacts": ["sandrine"]})
check("contacts None toléré",
      cn.parse_option({"notif_client_mep": {"actif": True, "contacts": None}})["contacts"] == [])
check("active ssi actif ET au moins un contact",
      cn.is_option_active({"notif_client_mep": {"actif": True, "contacts": ["sandrine"]}}))
check("actif mais sans contact => inactif",
      not cn.is_option_active({"notif_client_mep": {"actif": True, "contacts": []}}))
check("contacts mais actif=false => inactif",
      not cn.is_option_active({"notif_client_mep": {"actif": False, "contacts": ["sandrine"]}}))

# ── 2. file (frontmatter ticket) — idempotence ───────────────────────────────
check("frontmatter vierge => pas en file",
      not cn.is_pending({}))
fm1, ch1 = cn.set_queued({}, "2026-09-08T10:00")
check("1re mise en file => changed + pending",
      ch1 and cn.is_pending(fm1))
fm2, ch2 = cn.set_queued(fm1, "2026-09-08T11:00")
check("re-mise en file d'un ticket déjà en attente => no-op (idempotent)",
      (not ch2) and cn.queue_state(fm2)[0] == "2026-09-08T10:00")
fm_sent = cn.mark_sent(fm1, "2026-09-08T12:00")
check("après envoi => plus en file (sent_at posé, queued_at conservé)",
      (not cn.is_pending(fm_sent)) and cn.queue_state(fm_sent) == ("2026-09-08T10:00", "2026-09-08T12:00"))
fm3, ch3 = cn.set_queued(fm_sent, "2026-09-08T13:00")
check("nouveau cycle (déjà envoyé puis redéployé) => ré-entre en file",
      ch3 and cn.is_pending(fm3) and cn.queue_state(fm3) == ("2026-09-08T13:00", None))
check("mark_sent sans queued_at préalable pose les deux",
      cn.queue_state(cn.mark_sent({}, "2026-09-08T14:00")) == ("2026-09-08T14:00", "2026-09-08T14:00"))

# ── 3. résolution annuaire + emails ──────────────────────────────────────────
ANN = {
    "sandrine-roche-pizzo": {"ref": "sandrine-roche-pizzo", "first_name": "Sandrine",
                             "last_name": "Roche-Pizzo", "emails": ["sandrine@calicote.com"],
                             "phones": ["+33 6 00 00 00 00"]},
    "sans-mail": {"ref": "sans-mail", "first_name": "Bob", "emails": [], "phones": []},
}
r = cn.resolve_recipients(ANN, ["sandrine-roche-pizzo", "sans-mail", "inconnu"])
check("ref connue => email/tel/label résolus",
      r[0]["email"] == "sandrine@calicote.com" and r[0]["tel"] == "+33 6 00 00 00 00"
      and "Sandrine" in r[0]["label"] and not r[0]["orphan"])
check("ref sans email => email None (pas d'envoi pour elle)",
      r[1]["email"] is None and not r[1]["orphan"])
check("ref inconnue => orphan signalé (jamais tue)",
      r[2]["orphan"] and r[2]["email"] is None)
check("emails agrégés = non vides, dédoublonnés, ordre conservé",
      cn.recipient_emails(r + r) == ["sandrine@calicote.com"])

# un contact peut porter PLUSIEURS emails : tous deviennent destinataires (RM3026)
ANN_MULTI = {"ipro": {"ref": "ipro", "first_name": "Mathieu",
                      "emails": ["mathieu@iprospective.fr", "contact@iprospective.fr"]}}
rm = cn.resolve_recipients(ANN_MULTI, ["ipro"])
check("contact multi-emails => 1er en email, tous en emails",
      rm[0]["email"] == "mathieu@iprospective.fr"
      and rm[0]["emails"] == ["mathieu@iprospective.fr", "contact@iprospective.fr"])
check("recipient_emails prend TOUS les emails du contact (ordre + dédup)",
      cn.recipient_emails(rm + rm)
      == ["mathieu@iprospective.fr", "contact@iprospective.fr"])

# ── 4. composition de l'email ────────────────────────────────────────────────
subj1, body1 = cn.compose_email("Calicote", [
    {"id": 3025, "title": "Fix paliers", "url": "https://redmine/issues/3025",
     "criteria": ["Prix barré sur la fiche", ""], "protocol": "1. Ouvrir 438\n2. Ajouter"},
])
check("sujet singulier pour 1 ticket",
      "1 évolution mise en ligne" in subj1)
check("corps porte id + titre + lien + critère + protocole",
      "#3025" in body1 and "Fix paliers" in body1 and "issues/3025" in body1
      and "Prix barré" in body1 and "1. Ouvrir 438" in body1)
check("critère vide filtré du corps",
      "    • \n" not in body1)
subj2, _ = cn.compose_email("Calicote", [{"id": 1, "title": "A"}, {"id": 2, "title": "B"}])
check("sujet pluriel pour 2 tickets",
      "2 évolutions mises en ligne" in subj2)
_, body3 = cn.compose_email("Calicote", [{"id": 9, "title": "Sans détail"}])
check("ticket sans critère/protocole => pas de sections vides",
      "Ce qui change" not in body3 and "Comment le vérifier" not in body3)

print()
if fails:
    print(f"✗ {len(fails)} échec(s) : " + ", ".join(fails))
    sys.exit(1)
print("== OK ==")
