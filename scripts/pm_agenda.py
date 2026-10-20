"""pm_agenda — l'agenda pro de Mathieu, lu sur le Nextcloud (RM3229).

Un rendez-vous dit où il était. C'est la source la plus fiable pour le CLIENT d'une
journée : les traces disent sur quoi on a travaillé, l'agenda dit chez qui on était.
Les journées sur site y figurent en journée entière, au nom du client (« MatNat »,
« Pisceen », « CalyClay CalyPrint CalyMix »).

Lu en LECTURE SEULE, comme les notes : rien ici n'écrit, et un Nextcloud injoignable
ne doit jamais empêcher une journée de s'afficher — la suggestion disparaît, c'est tout.

Les récurrences sont développées PAR LE SERVEUR (`<c:expand>`) : réimplémenter RRULE,
ses UNTIL, ses exceptions et ses décalages serait une source de faux à nous seuls.
"""
import base64
import re
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta

#: Mêmes identifiants que les notes — ils ne suivent pas la convention provider.
CLES_ENV = ("NEXTCLOUD_URL", "NEXTCLOUD_USER", "NEXTCLOUD_APP_PASSWORD")

#: Agenda pro partagé. Configurable : un autre compte, un autre partage, un autre nom.
CALENDRIER_DEFAUT = "iprospective-mathieu-20251127111620_shared_by_iprospective"

_CR = re.compile(r"&#13;|\r")


def _env(chemin):
    """Les trois clés Nextcloud, lues dans le `.env` utilisateur. Jamais journalisées."""
    out = {}
    try:
        for ligne in open(chemin, encoding="utf-8"):
            if "=" in ligne and not ligne.lstrip().startswith("#"):
                k, v = ligne.split("=", 1)
                k = k.strip()
                if k in CLES_ENV:
                    out[k] = v.strip().strip('"').strip("'")
    except OSError:
        return {}
    return out if all(k in out for k in CLES_ENV) else {}


def _deplie(bloc):
    """Déplie les lignes repliées de l'iCalendar (RFC 5545 § 3.1)."""
    return _CR.sub("", bloc).replace("\n ", "").replace("\n\t", "")


def _champ(bloc, nom):
    m = re.search(rf"^{nom}([^:\r\n]*):(.*)$", bloc, re.M)
    return (m.group(1), m.group(2).strip()) if m else ("", "")


def _jour_de(valeur):
    """La date d'un DTSTART, qu'il soit une date seule ou un instant."""
    v = (valeur or "").strip()
    if len(v) >= 8 and v[:8].isdigit():
        try:
            return date(int(v[:4]), int(v[4:6]), int(v[6:8])).isoformat()
        except ValueError:
            return None
    return None


def evenements_periode(debut, fin, conf=None, env_path=None, timeout=20):
    """Les événements d'une PÉRIODE, indexés par jour. `fin` est exclusive.

    Une seule requête pour tout un mois : interroger l'agenda trente fois pour
    afficher un calendrier coûterait trente allers-retours réseau.

    Un échec N'EST PAS une erreur : l'agenda est un confort, pas une dépendance —
    un Nextcloud injoignable fait disparaître la suggestion, pas la journée.
    """
    conf = conf or {}
    env = _env(env_path or (conf.get("env_path") or ""))
    if not env or conf.get("actif") is False:
        return {}
    cal = conf.get("calendrier") or CALENDRIER_DEFAUT
    compte = conf.get("compte") or env["NEXTCLOUD_USER"]
    base = env["NEXTCLOUD_URL"].rstrip("/")
    url = f"{base}/remote.php/dav/calendars/{compte}/{cal}/"
    try:
        d0 = date.fromisoformat(str(debut))
        d1 = date.fromisoformat(str(fin))
    except (TypeError, ValueError):
        return {}
    if d1 <= d0:
        d1 = d0 + timedelta(days=1)
    s, e = d0.strftime("%Y%m%d"), d1.strftime("%Y%m%d")
    corps = (
        '<?xml version="1.0"?>'
        '<c:calendar-query xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">'
        f'<d:prop><c:calendar-data><c:expand start="{s}T000000Z" end="{e}T000000Z"/>'
        '</c:calendar-data></d:prop>'
        '<c:filter><c:comp-filter name="VCALENDAR"><c:comp-filter name="VEVENT">'
        f'<c:time-range start="{s}T000000Z" end="{e}T000000Z"/>'
        '</c:comp-filter></c:comp-filter></c:filter></c:calendar-query>'
    ).encode()
    auth = base64.b64encode(
        f"{compte}:{env['NEXTCLOUD_APP_PASSWORD']}".encode()).decode()
    req = urllib.request.Request(
        url, data=corps, method="REPORT",
        headers={"Authorization": f"Basic {auth}", "Depth": "1",
                 "Content-Type": "application/xml; charset=utf-8"})
    try:
        body = urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8", "replace")
    except (urllib.error.URLError, OSError, ValueError):
        return {}
    out = {}
    for m in re.finditer(r"BEGIN:VEVENT(.*?)END:VEVENT", body, re.S):
        bloc = _deplie(m.group(1))
        p_debut, v_debut = _champ(bloc, "DTSTART")
        _p_fin, v_fin = _champ(bloc, "DTEND")
        _p, resume = _champ(bloc, "SUMMARY")
        if not resume:
            continue
        jour_ev = _jour_de(v_debut)
        if not jour_ev:
            continue
        out.setdefault(jour_ev, []).append({
            "resume": resume.replace("\\,", ",").replace("\\n", " ").strip(),
            "debut": v_debut, "fin": v_fin,
            # Une journée entière vaut plus qu'un rendez-vous d'une heure pour dire
            # chez QUI on était : elle est marquée, le classement s'en sert.
            "journee": "VALUE=DATE" in p_debut or (len(v_debut) == 8 and v_debut.isdigit()),
            "lieu": _champ(bloc, "LOCATION")[1],
        })
    return out


def evenements(jour, conf=None, env_path=None, timeout=20):
    """Les événements d'UNE journée — un cas particulier de la période."""
    d0 = str(jour)
    try:
        d1 = (date.fromisoformat(d0) + timedelta(days=1)).isoformat()
    except (TypeError, ValueError):
        return []
    return evenements_periode(d0, d1, conf, env_path, timeout).get(d0, [])


def _normalise(texte):
    sans = unicodedata.normalize("NFKD", texte or "")
    sans = "".join(c for c in sans if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", sans.lower()).strip()


def client_du_jour(evs, clients, alias=None):
    """Le client que l'agenda désigne pour cette journée, et pourquoi.

    Un nom de client reconnu dans le titre d'un événement suffit : c'est ainsi que
    l'agenda est tenu (« MatNat », « Pisceen »). Une journée entière l'emporte sur un
    rendez-vous ponctuel — être chez quelqu'un toute la journée pèse plus qu'un appel.

    Rend `None` quand rien n'est sûr : mieux vaut ne rien proposer qu'induire en
    erreur sur une facture.
    """
    alias = {_normalise(k): v for k, v in (alias or {}).items()}
    connus = {_normalise(c): c for c in (clients or [])}
    trouves = []
    for ev in evs or []:
        mots = _normalise(ev.get("resume"))
        for n, brut in list(connus.items()) + list(alias.items()):
            if n and re.search(rf"\b{re.escape(n)}\b", mots):
                trouves.append((1 if ev.get("journee") else 0, brut, ev.get("resume")))
                break
    if not trouves:
        return None
    trouves.sort(key=lambda t: -t[0])
    poids, client, resume = trouves[0]
    # Deux clients en journée entière le même jour : on ne tranche pas à sa place.
    entiers = {t[1] for t in trouves if t[0] == 1}
    if poids == 1 and len(entiers) > 1:
        return None
    return {"client": client, "source": resume, "journee": bool(poids)}
