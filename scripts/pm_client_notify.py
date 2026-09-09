#!/usr/bin/env python3
"""pm_client_notify — cœur de la notification client à la MEP (RM3026).

À l'entrée en `en_mep` (MEP prod effective), un ticket d'un projet dont l'option
`notif_client_mep` est active entre dans une FILE (frontmatter `client_notify`).
Quand l'humain estime la MEP finie, `pm-client-notify.py send <projet>` agrège la
file en UN email récap envoyé aux CONTACTS du client (résolus depuis l'annuaire par
leur `ref`), puis vide la file (pose `sent_at`).

Ce module ne contient que la LOGIQUE PURE (testée par test_pm_client_notify.py) :
option projet, état de file, résolution des destinataires, composition de l'email —
en texte ET en HTML (RM3052 : le protocole de test est du markdown à tableaux, illisible
en texte brut chez le client ; l'email part donc en multipart).
Les I/O (lecture meta/annuaire/tickets, écriture frontmatter, envoi mail) vivent
dans pm-client-notify.py et le hook de pm-task-status-update.py.
"""
import re

OPTION_KEY = "notif_client_mep"   # bloc du meta PROJET : {actif: bool, contacts: [ref]}
QUEUE_KEY = "client_notify"        # bloc du frontmatter TICKET : {queued_at, sent_at}


# ── Option projet ────────────────────────────────────────────────────────────
def parse_option(project_meta):
    """{actif: bool, contacts: [ref, ...], protocole: bool} depuis le meta projet (tolérant :
    bloc absent, `contacts` scalaire ou None).

    `protocole` (RM3052) : inclure le PROTOCOLE DE TEST de chaque ticket dans l'email client.
    Défaut **True** — c'est le comportement demandé ; un projet dont le protocole est trop
    interne peut le couper (`protocole: false`)."""
    opt = (project_meta or {}).get(OPTION_KEY) or {}
    contacts = opt.get("contacts")
    if contacts is None:
        contacts = []
    elif isinstance(contacts, str):
        contacts = [contacts]
    proto = opt.get("protocole")
    return {"actif": bool(opt.get("actif")), "contacts": [str(c) for c in contacts],
            "protocole": True if proto is None else bool(proto)}


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


def _ticket_lines(t):
    """Le bloc texte d'UN ticket : id + titre, lien, ce qui change, comment le vérifier.
    Partagé par le récap projet et le compte-rendu client (une seule vérité de rendu)."""
    L = ["— #{} — {}".format(t.get("id"), t.get("title") or "")]
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
    return L


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
        L.extend(_ticket_lines(t))
    L.append("Bien cordialement,")
    return subject, "\n".join(L)


def compose_client_email(client_name, groups):
    """RM3052 — LE compte-rendu d'un CLIENT, qui peut couvrir PLUSIEURS de ses projets.

    `groups` = [{"project": <nom lisible>, "tickets": [...]}, …] — l'ordre est celui donné.
    Les groupes vides sont ignorés. **Le nom du projet n'apparaît que s'il y en a plusieurs** :
    sur un client mono-projet, le client lit exactement le même email qu'avant (pas de
    ferraille d'organisation interne dans un mail sortant)."""
    gs = [g for g in (groups or []) if (g or {}).get("tickets")]
    n = sum(len(g["tickets"]) for g in gs)
    subject = "{} — {} évolution{} mise{} en ligne".format(
        client_name, n, _plural(n), _plural(n))
    L = ["Bonjour,", ""]
    L.append("Les évolutions suivantes viennent d'être mises en ligne :")
    L.append("")
    multi = len(gs) > 1
    for g in gs:
        if multi:
            L.append("== {} ==".format(g.get("project") or ""))
            L.append("")
        for t in g["tickets"]:
            L.extend(_ticket_lines(t))
    L.append("Bien cordialement,")
    return subject, "\n".join(L)


# ── Rendu HTML de l'email (RM3052) ───────────────────────────────────────────
# Pourquoi : le protocole de test d'un ticket est du markdown RICHE — titres, listes et
# surtout des TABLEAUX. Recopié tel quel dans un corps texte, il arrive chez le client en
# bouillie. L'email part donc en multipart : le texte reste (lecteurs sans HTML, archives),
# et la version HTML rend les tableaux comme des tableaux.

_ESC = (("&", "&amp;"), ("<", "&lt;"), (">", "&gt;"), ('"', "&quot;"))


def esc(s):
    """Échappe pour du HTML. Utilisé AUSSI sur le markdown source : nos fiches n'ont
    jamais de HTML voulu, et on n'en laisse donc pas passer un seul dans un mail sortant."""
    out = str("" if s is None else s)
    for a, b in _ESC:
        out = out.replace(a, b)
    return out


# Styles posés EN LIGNE : la plupart des clients mail ignorent (ou nettoient) une feuille
# <style>. Chaque balise produite par le rendu markdown reçoit donc son style ici.
_TAG_STYLE = {
    "table": 'border-collapse:collapse;width:100%;margin:8px 0;font-size:13px',
    "th": 'border:1px solid #d9d9de;padding:6px 9px;background:#f4f4f5;text-align:left;font-weight:600',
    "td": 'border:1px solid #d9d9de;padding:6px 9px;vertical-align:top',
    "h1": 'font-size:16px;margin:14px 0 6px',
    "h2": 'font-size:15px;margin:14px 0 6px',
    "h3": 'font-size:14px;margin:12px 0 4px',
    "h4": 'font-size:13px;margin:10px 0 4px',
    "ul": 'margin:6px 0;padding-left:20px',
    "ol": 'margin:6px 0;padding-left:20px',
    "li": 'margin:2px 0',
    "p": 'margin:6px 0',
    "blockquote": 'margin:8px 0;padding:6px 10px;border-left:3px solid #d9d9de;color:#555',
    "code": 'font-family:ui-monospace,Menlo,Consolas,monospace;font-size:12px;background:#f4f4f5;padding:1px 4px;border-radius:3px',
    "pre": 'font-family:ui-monospace,Menlo,Consolas,monospace;font-size:12px;background:#f7f7f8;padding:8px;border-radius:4px;overflow-x:auto',
}


def _inline_styles(html_text):
    """Ajoute le style de chaque balise connue. Balise déjà stylée : laissée telle quelle."""
    out = html_text
    for tag, style in _TAG_STYLE.items():
        out = re.sub(r"<{0}>".format(tag), '<{0} style="{1}">'.format(tag, style), out)
        out = re.sub(r"<{0} (?![^>]*style=)".format(tag), '<{0} style="{1}" '.format(tag, style), out)
    return out


def _checkboxes(text):
    """`[x]` / `[ ]` sont du jargon d'atelier : dans un email client, un signe vaut mieux."""
    return re.sub(r"\[[xX]\]", "✔", text).replace("[ ]", "☐")


def render_markdown(text):
    """Markdown → HTML stylé pour l'email. S'appuie sur python-markdown quand il est
    présent (extension `tables` : c'est tout l'enjeu) ; sinon rend le texte tel quel dans
    un bloc préformaté — dégradé mais lisible, jamais une erreur d'envoi."""
    src = _checkboxes(esc(text or "").replace("\r\n", "\n"))
    if not src.strip():
        return ""
    try:
        import markdown as _md
    except ImportError:
        return '<pre style="{0}">{1}</pre>'.format(_TAG_STYLE["pre"], src)
    body = _md.markdown(src, extensions=["tables", "sane_lists"])
    return _inline_styles(body)


def _ticket_html(t):
    """Un ticket : son numéro et son titre, ce qui change, comment le vérifier."""
    tid, title = t.get("id"), t.get("title") or ""
    head = "#{0} — {1}".format(tid, esc(title))
    if t.get("url"):
        head = '<a href="{0}" style="color:#1a56b8;text-decoration:none">{1}</a>'.format(esc(t["url"]), head)
    L = ['<div style="margin:16px 0;padding:10px 14px;border-left:3px solid #1a56b8;background:#fafafa">',
         '<div style="font-size:15px;font-weight:600;margin-bottom:4px">{0}</div>'.format(head)]
    crit = [c.strip() for c in (t.get("criteria") or []) if c and c.strip()]
    if crit:
        L.append('<div style="font-size:13px;font-weight:600;margin-top:8px">Ce qui change</div>')
        L.append('<ul style="{0}">{1}</ul>'.format(
            _TAG_STYLE["ul"], "".join('<li style="{0}">{1}</li>'.format(_TAG_STYLE["li"], esc(c)) for c in crit)))
    proto = (t.get("protocol") or "").strip()
    if proto:
        L.append('<div style="font-size:13px;font-weight:600;margin-top:10px">Comment le vérifier</div>')
        L.append(render_markdown(proto))
    L.append("</div>")
    return "".join(L)


def _wrap_html(title, inner):
    return ("""<!DOCTYPE html><html><head><meta charset="utf-8">"""
            """<meta name="viewport" content="width=device-width,initial-scale=1"><title>{0}</title></head>"""
            """<body style="margin:0;padding:0;background:#f0f0f2">"""
            """<div style="max-width:760px;margin:0 auto;padding:18px 20px;background:#ffffff;"""
            """font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;"""
            """font-size:14px;line-height:1.5;color:#1c1c1e">{1}</div></body></html>""").format(esc(title), inner)


def compose_client_email_html(client_name, groups):
    """(subject, html) — même contenu et même découpage que `compose_client_email`, rendu
    en HTML. Le sujet est IDENTIQUE : les deux parties d'un multipart ne se contredisent pas."""
    gs = [g for g in (groups or []) if (g or {}).get("tickets")]
    n = sum(len(g["tickets"]) for g in gs)
    subject = "{0} — {1} évolution{2} mise{3} en ligne".format(
        client_name, n, _plural(n), _plural(n))
    multi = len(gs) > 1
    L = ['<p style="margin:0 0 10px">Bonjour,</p>',
         '<p style="margin:0 0 6px">Les évolutions suivantes viennent d\'être mises en ligne :</p>']
    for g in gs:
        if multi:
            L.append('<h2 style="font-size:15px;margin:18px 0 2px;padding-bottom:4px;'
                     'border-bottom:1px solid #e3e3e6">{0}</h2>'.format(esc(g.get("project") or "")))
        L.extend(_ticket_html(t) for t in g["tickets"])
    L.append('<p style="margin:18px 0 0">Bien cordialement,</p>')
    return subject, _wrap_html(subject, "".join(L))


def compose_email_html(project_name, tickets):
    """Pendant HTML de `compose_email` (périmètre projet)."""
    n = len(tickets or [])
    subject = "{0} — {1} évolution{2} mise{3} en ligne".format(
        project_name, n, _plural(n), _plural(n))
    L = ['<p style="margin:0 0 10px">Bonjour,</p>',
         '<p style="margin:0 0 6px">Les évolutions suivantes viennent d\'être mises en ligne '
         'sur <b>{0}</b> :</p>'.format(esc(project_name))]
    L.extend(_ticket_html(t) for t in (tickets or []))
    L.append('<p style="margin:18px 0 0">Bien cordialement,</p>')
    return subject, _wrap_html(subject, "".join(L))
