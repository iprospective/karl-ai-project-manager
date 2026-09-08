#!/usr/bin/env python3
"""pm_client_notify — cœur de la notification client à la MEP (RM3026).

À l'entrée en `en_mep` (MEP prod effective), un ticket d'un projet dont l'option
`notif_client_mep` est active entre dans une FILE (frontmatter `client_notify`).
Quand l'humain estime la MEP finie, `pm-client-notify.py send <projet>` agrège la
file en UN email récap envoyé aux CONTACTS du client (résolus depuis l'annuaire par
leur `ref`), puis vide la file (pose `sent_at`).

Ce module ne contient que la LOGIQUE PURE (testée par test_pm_client_notify.py) :
option projet, état de file, résolution des destinataires, composition de l'email.
Les I/O (lecture meta/annuaire/tickets, écriture frontmatter, envoi mail) vivent
dans pm-client-notify.py et le hook de pm-task-status-update.py.
"""

OPTION_KEY = "notif_client_mep"   # bloc du meta PROJET : {actif: bool, contacts: [ref]}
QUEUE_KEY = "client_notify"        # bloc du frontmatter TICKET : {queued_at, sent_at}


# ── Option projet ────────────────────────────────────────────────────────────
def parse_option(project_meta):
    """{actif: bool, contacts: [ref, ...]} depuis le meta projet (tolérant :
    bloc absent, `contacts` scalaire ou None)."""
    opt = (project_meta or {}).get(OPTION_KEY) or {}
    contacts = opt.get("contacts")
    if contacts is None:
        contacts = []
    elif isinstance(contacts, str):
        contacts = [contacts]
    return {"actif": bool(opt.get("actif")), "contacts": [str(c) for c in contacts]}


def is_option_active(project_meta):
    """Actif ET au moins un contact : sinon rien à notifier (pas de mise en file)."""
    o = parse_option(project_meta)
    return o["actif"] and bool(o["contacts"])


# ── État de file (frontmatter ticket) ────────────────────────────────────────
def queue_state(fm):
    """(queued_at, sent_at) — l'un ou l'autre None si absent."""
    cn = (fm or {}).get(QUEUE_KEY) or {}
    return cn.get("queued_at"), cn.get("sent_at")


def dismissed_at(fm):
    """Date de mise à l'écart — le client n'a PAS besoin d'être notifié pour ce ticket
    (RM3052 « dismiss ») : il sort de la file sans email. None si non écarté."""
    return ((fm or {}).get(QUEUE_KEY) or {}).get("dismissed_at")


def is_pending(fm):
    """En file d'attente d'envoi : queued_at posé, NI envoyé NI écarté."""
    q, s = queue_state(fm)
    return bool(q) and not s and not dismissed_at(fm)


def set_queued(fm, now):
    """Met le ticket en file (queued_at=now) SI pas déjà en attente. Idempotent : re-jouer
    une transition en_mep ne réinitialise pas une file déjà posée. Un NOUVEAU cycle (déjà
    envoyé OU écarté, puis redéployé) ré-entre en file et repart propre (sent_to/dismissed
    effacés). Renvoie (fm, changed:bool)."""
    fm = dict(fm or {})
    q, s = queue_state(fm)
    if q and not s and not dismissed_at(fm):
        return fm, False                      # déjà en file, ne rien changer
    fm[QUEUE_KEY] = {"queued_at": now, "sent_at": None}
    return fm, True


def mark_sent(fm, now, emails=None):
    """Pose sent_at=now et, RM3052, `sent_to` = les emails réellement notifiés (savoir QUI
    a été prévenu, pas seulement quand). Conserve queued_at ; vide la file pour ce ticket."""
    fm = dict(fm or {})
    cn = dict(fm.get(QUEUE_KEY) or {})
    cn.setdefault("queued_at", now)
    cn["sent_at"] = now
    if emails:
        cn["sent_to"] = list(emails)
    fm[QUEUE_KEY] = cn
    return fm


def mark_dismissed(fm, now):
    """RM3052 — sort le ticket de la file SANS notification (le client n'a pas besoin d'être
    prévenu pour celui-là). Conserve queued_at ; pas d'email, pas de sent_at."""
    fm = dict(fm or {})
    cn = dict(fm.get(QUEUE_KEY) or {})
    cn.setdefault("queued_at", now)
    cn["dismissed_at"] = now
    fm[QUEUE_KEY] = cn
    return fm


# ── Résolution des destinataires (annuaire) ──────────────────────────────────
def resolve_recipients(annuaire, refs):
    """[{ref,label,email,tel,orphan}] pour des `ref` d'annuaire. Une ref sans fiche
    est rendue `orphan` (à signaler, pas à taire) ; l'email/tel = la 1re valeur."""
    try:
        import pm_contacts as pc
        display = pc.display_name
    except Exception:                          # noqa: BLE001 — repli sans dépendance
        display = lambda p: (p.get("ref") or "?")  # noqa: E731
    out = []
    for ref in refs or []:
        p = (annuaire or {}).get(ref)
        if not p:
            out.append({"ref": ref, "label": ref, "email": None, "tel": None, "orphan": True})
            continue
        emails = list(p.get("emails") or [])
        phones = list(p.get("phones") or [])
        out.append({
            "ref": ref,
            "label": display(p),
            "email": emails[0] if emails else None,   # 1er email (compat/affichage)
            "emails": emails,                         # TOUS les emails du contact (destinataires)
            "tel": phones[0] if phones else None,
            "orphan": False,
        })
    return out


def recipient_emails(recipients):
    """Emails non vides, dédoublonnés en conservant l'ordre. Un contact peut porter
    PLUSIEURS emails (ex. mathieu@ + contact@) : tous deviennent destinataires."""
    seen, out = set(), []
    for r in recipients or []:
        r = r or {}
        emails = r.get("emails")
        if emails is None:                            # tolérant : fiche pré-`emails`
            e = r.get("email")
            emails = [e] if e else []
        for e in emails:
            if e and e not in seen:
                seen.add(e)
                out.append(e)
    return out


# ── Composition de l'email récap ─────────────────────────────────────────────
def _plural(n):
    return "s" if n > 1 else ""


def compose_email(project_name, tickets):
    """tickets = [{id, title, url, criteria:[str], protocol:str}]. Renvoie
    (subject, body) texte. Un seul email pour N tickets (pas un par déploiement)."""
    n = len(tickets)
    subject = "{} — {} évolution{} mise{} en ligne".format(
        project_name, n, _plural(n), _plural(n))
    L = ["Bonjour,", ""]
    L.append("Les évolutions suivantes viennent d'être mises en ligne sur {} :".format(project_name))
    L.append("")
    for t in tickets:
        L.append("— #{} — {}".format(t.get("id"), t.get("title") or ""))
        if t.get("url"):
            L.append("  {}".format(t["url"]))
        crit = [c.strip() for c in (t.get("criteria") or []) if c and c.strip()]
        if crit:
            L.append("  Ce qui change :")
            L.extend("    • {}".format(c) for c in crit)
        proto = (t.get("protocol") or "").strip()
        if proto:
            L.append("  Comment le vérifier :")
            L.extend("    {}".format(pl) for pl in proto.splitlines())
        L.append("")
    L.append("Bien cordialement,")
    return subject, "\n".join(L)
