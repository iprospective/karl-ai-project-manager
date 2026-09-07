"""pm_contacts — l'annuaire de contacts, cœur partagé (RM2703).

Deux objets, deux responsabilités. **L'identité** vit dans l'annuaire : qui est
cette personne. **La relation** reste chez le client : qui elle est POUR LUI —
son rôle, son titre. Un `meta.yml` de client reste ainsi lisible seul, et le
rôle demeure là où il a un sens.

Ce que l'ancienne forme coûtait, mesuré le 2026-08-20 : 31 contacts sur
21 clients, dont **19 lignes pour la même personne**, écrite de deux façons.
Ce n'était pas de la négligence de saisie mais la forme qui l'imposait — un
contact vivant dans le `meta.yml` de SON client, une personne présente chez
vingt clients s'écrit vingt fois et diverge vingt fois.

Ce module ne contient que des fonctions pures : le CLI (`pm-contact.py`) et les
consommateurs (routage mail, cockpit) écrivent et lisent, mais la logique de
slug, de fusion et de résolution vit ici, en un seul exemplaire.
"""
import re
import unicodedata

ROLES = ["owner", "decideur", "technique", "facturation", "autre"]
OWN_DOMAINS = ["iprospective.fr", "iprospective.net"]
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[a-z]{2,}$", re.I)
# Champs d'une fiche personne. `ref` est la clé ; le reste est optionnel.
PERSON_FIELDS = ("ref", "last_name", "first_name", "emails", "phones",
                 "internal", "redmine_user_id", "note", "created", "updated")
# Champs d'un rattachement, côté client.
LINK_FIELDS = ("ref", "role", "title", "since")


def _ascii(s):
    """Sans accents ni casse — pour comparer et pour fabriquer un slug."""
    s = unicodedata.normalize("NFKD", str(s or ""))
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


def slugify_person(last_name, first_name, pris=(), email=None):
    """Clé lisible d'une personne : `nom-prenom`, suffixée si déjà prise.

    Lisible et non opaque, délibérément : un slug se lit dans un diff, et c'est
    lui qu'on écrit à la main dans le `meta.yml` d'un client. Le prix est qu'un
    renommage devient une migration — assumé, il est rare.

    Sans nom, on retombe sur l'adresse (`webmaster@matnat.fr` →
    `webmaster-matnat`) plutôt que sur un `contact` générique : une boîte
    fonctionnelle est un correspondant réel, sa clé doit dire lequel. Sans rien,
    `contact` — le suffixe la rendra unique : mieux vaut une clé terne qu'un
    plantage au milieu d'une migration."""
    bouts = [re.sub(r"[^a-z0-9]+", "-", _ascii(x)).strip("-")
             for x in (last_name, first_name)]
    base = "-".join(b for b in bouts if b)
    if not base and email and "@" in str(email):
        local, _, domaine = str(email).partition("@")
        bouts = [re.sub(r"[^a-z0-9]+", "-", _ascii(local)).strip("-"),
                 re.sub(r"[^a-z0-9]+", "-", _ascii(domaine.split(".")[0])).strip("-")]
        base = "-".join(b for b in bouts if b)
    base = base or "contact"
    if base not in pris:
        return base
    n = 2
    while f"{base}-{n}" in pris:
        n += 1
    return f"{base}-{n}"


def norm_email(email):
    return (email or "").strip().lower()


def is_internal_email(email):
    """Une de nos adresses maison.

    Attention à ce que ça NE dit pas : le gabarit de création en pose une chez
    chaque client, donc une adresse interne n'identifie aucun client et ne doit
    jamais servir à router un email entrant (RM2669). Posée sur la PERSONNE, en
    revanche, l'information devient vraie une fois pour toutes."""
    return norm_email(email).rsplit("@", 1)[-1] in OWN_DOMAINS


def person_from_legacy(entry):
    """Fiche personne déduite d'un contact en ligne (ancienne forme).

    `name` est l'ancien champ mono-bloc : on le coupe au dernier espace, le
    dernier mot faisant le nom — convention de la saisie observée
    (« Mathieu Moulin »). « MOULIN Mathieu » y échapperait, d'où la
    normalisation de casse au moment de la fusion, pas ici."""
    e = dict(entry or {})
    last, first = e.get("last_name"), e.get("first_name")
    if not (last or first) and e.get("name"):
        mots = str(e["name"]).split()
        if len(mots) >= 2:
            first, last = " ".join(mots[:-1]), mots[-1]
        elif mots:
            last = mots[0]
    email = norm_email(e.get("email"))
    return {
        "last_name": last or None, "first_name": first or None,
        "emails": [email] if email else [],
        "phones": [str(e["phone"])] if e.get("phone") else [],
        "internal": bool(e.get("internal")) or (is_internal_email(email) if email else False),
    }


def _meilleur_nom(a, b):
    """Entre deux orthographes, garder la plus informative.

    « MOULIN Mathieu » et « Mathieu Moulin » désignent la même personne ; on
    préfère la forme qui n'est pas tout en capitales (une saisie criée est
    rarement la référence), et à défaut la plus longue."""
    a, b = (a or "").strip(), (b or "").strip()
    if not a:
        return b or None
    if not b:
        return a or None
    if a.isupper() != b.isupper():
        return b if a.isupper() else a
    return a if len(a) >= len(b) else b


def merge_person(a, b):
    """Fusionne deux fiches de la même personne, sans rien perdre.

    Les listes s'unissent (une personne a plusieurs adresses, c'est le fait à
    représenter, pas un conflit à trancher) ; `internal` est un OU — être des
    nôtres chez un seul client suffit à l'être."""
    out = dict(a or {})
    b = b or {}
    out["last_name"] = _meilleur_nom(out.get("last_name"), b.get("last_name"))
    out["first_name"] = _meilleur_nom(out.get("first_name"), b.get("first_name"))
    for champ in ("emails", "phones"):
        vus, liste = set(), []
        for v in (out.get(champ) or []) + (b.get(champ) or []):
            k = norm_email(v) if champ == "emails" else re.sub(r"\s+", "", str(v))
            if v and k not in vus:
                vus.add(k)
                liste.append(v)
        out[champ] = liste
    out["internal"] = bool(out.get("internal")) or bool(b.get("internal"))
    for champ in ("redmine_user_id", "note", "ref"):
        out[champ] = out.get(champ) or b.get(champ)
    return {k: v for k, v in out.items() if v not in (None, [], "")}


def index_by_email(annuaire):
    """{email normalisé → ref}. Une personne a plusieurs adresses ; c'est par
    n'importe laquelle qu'on doit la retrouver — ce dont le routage a besoin."""
    idx = {}
    for ref, p in (annuaire or {}).items():
        for e in p.get("emails") or []:
            idx.setdefault(norm_email(e), ref)
    return idx


def resolve_link(entry, annuaire):
    """Un élément de `contacts[]` d'un client → la fiche complète à afficher.

    Trois formes cohabitent, et c'est voulu le temps que la migration passe :
    un rattachement (`ref`), un contact en ligne (ancienne forme), et un
    rattachement dont la fiche a disparu — ce dernier ne doit pas être tu, ni
    faire perdre le rôle : on rend ce qu'on sait, marqué `orphelin`."""
    e = dict(entry or {})
    role, title = e.get("role"), e.get("title")
    ref = e.get("ref")
    if ref:
        p = (annuaire or {}).get(ref)
        if not p:
            return {"ref": ref, "role": role, "title": title, "source": "orphelin",
                    "last_name": None, "first_name": None, "emails": [], "phones": [],
                    "internal": False}
        return {"ref": ref, "role": role, "title": title, "source": "annuaire",
                "last_name": p.get("last_name"), "first_name": p.get("first_name"),
                "emails": list(p.get("emails") or []),
                "phones": list(p.get("phones") or []),
                "internal": bool(p.get("internal")),
                "redmine_user_id": p.get("redmine_user_id")}
    base = person_from_legacy(e)
    base.update({"ref": None, "role": role, "title": title, "source": "inline"})
    return base


def display_name(p):
    """« Prénom NOM », ou ce qui existe, ou l'adresse, ou la ref. Jamais vide :
    une ligne sans libellé est une ligne qu'on ne peut pas choisir."""
    bouts = [x for x in (p.get("first_name"), p.get("last_name")) if x]
    if bouts:
        return " ".join(bouts)
    for e in p.get("emails") or []:
        return e
    return p.get("ref") or "?"
