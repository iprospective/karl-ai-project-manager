#!/usr/bin/env python3
"""pm-client-contact — contacts d'un client : nom, prénom, email, téléphone (RM2702).

Les contacts vivent dans le `meta.yml` du client (`contacts[]`). Ce script est le SEUL
point d'écriture — on n'édite pas le `meta.yml` à la main (tripwire NORMS 1).

Schéma d'un contact (tous les champs sont optionnels sauf un identifiant : email ou nom) :

    contacts:
      - last_name: Dupont          # NOM
        first_name: Claire         # prénom
        email: claire@exemple.fr
        phone: "+33 6 12 34 56 78"
        role: technique            # owner | decideur | technique | facturation | autre
        internal: true             # posé AUTOMATIQUEMENT sur nos propres adresses

`internal: true` marque nos adresses maison (iprospective.fr…) : le gabarit de création
en pose une chez CHAQUE client, elle n'identifie donc aucun client et ne doit jamais
servir à router un email entrant (cf. RM2669). L'ancien champ `name` reste lu en repli
tant que des fiches ne sont pas reprises.

Usage :
    pm-client-contact.py list [<client>]
    pm-client-contact.py add calyclay --last-name Dupont --first-name Claire \\
                              --email claire@calyclay.com --phone "+33 6 12 34 56 78"
    pm-client-contact.py set calyclay claire@calyclay.com --phone "04 75 00 00 00"
                              # l'email sélectionne la fiche ; en changer un = remove + add
    pm-client-contact.py remove calyclay claire@calyclay.com
    pm-client-contact.py import-redmine calyclay          # propose, n'écrit pas
    pm-client-contact.py import-redmine calyclay --apply   # enregistre
"""
import argparse
import re
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pm_output import out                                  # noqa: E402
from pm_paths import PMConfig                              # noqa: E402

ROLES = ["owner", "decideur", "technique", "facturation", "autre"]
OWN_DOMAINS = ["iprospective.fr", "iprospective.net"]
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[a-z]{2,}$", re.I)
FIELDS = ("last_name", "first_name", "email", "phone", "role")


def is_internal(email: str) -> bool:
    return (email or "").lower().rsplit("@", 1)[-1] in OWN_DOMAINS


def meta_path(cfg, client: str) -> Path:
    """`meta.yml` du client — même résolution que `PMConfig.client_meta`."""
    client_dir = cfg.path("entity_client_dir", entity=client)
    try:
        return client_dir.resolve().parent / "meta.yml"
    except OSError:
        return client_dir.parent / "meta.yml"


def known_clients(cfg) -> list:
    return [slug for slug, _ in cfg.iter_entities()]


def require_client(cfg, client: str):
    if client not in known_clients(cfg):
        out.fail(f"client inconnu : {client}",
                 remede=f"connus : {', '.join(known_clients(cfg))}")
    f = meta_path(cfg, client)
    if not f.is_file():
        out.fail(f"{f} introuvable — le client n'a pas de meta.yml",
                 remede="vérifie la structure du client (mmi-pm client-new l'a-t-il créé ?)")
    return f


def load_meta(f: Path) -> dict:
    try:
        return yaml.safe_load(f.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as e:
        out.fail(f"{f} illisible : {e}")


def save_meta(f: Path, data: dict):
    """Écriture atomique, ordre des clés préservé (sort_keys=False)."""
    tmp = f.with_suffix(".yml.tmp")
    tmp.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False,
                                  default_flow_style=False), encoding="utf-8")
    tmp.replace(f)


def normalize_phone(raw) -> str:
    """Espaces normalisés, rien d'autre : un numéro reste une CHAÎNE (le `+` et les
    zéros de tête ne survivent pas à une conversion numérique)."""
    return re.sub(r"\s+", " ", str(raw or "").strip())


def contact_label(c: dict) -> str:
    name = " ".join(x for x in [(c.get("last_name") or "").upper(),
                                c.get("first_name") or ""] if x).strip()
    return name or c.get("name") or c.get("email") or "(sans nom)"


def is_empty(c: dict) -> bool:
    """Fiche vide laissée par le gabarit de création (`{name: '', email: '', role: owner}`)
    — présente chez plusieurs clients. Ce n'est pas un contact."""
    return not any((c.get(k) or "").strip()
                   for k in ("email", "last_name", "first_name", "name", "phone"))


def find_contact(contacts: list, email: str):
    email = (email or "").lower()
    for c in contacts:
        if (c.get("email") or "").lower() == email:
            return c
    return None


def print_contacts(client: str, contacts: list):
    if not contacts:
        print(f"  {client} : aucun contact")
        return
    for c in contacts:
        tag = " (interne)" if c.get("internal") else ""
        print(f"  {client:20} {contact_label(c):28.28} {(c.get('email') or ''):32.32} "
              f"{(c.get('phone') or ''):18.18} {(c.get('role') or ''):12}{tag}")


# ── Commandes ────────────────────────────────────────────────────────────────
def cmd_list(cfg, args):
    clients = [args.client] if args.client else known_clients(cfg)
    total = 0
    for slug in clients:
        if args.client:
            require_client(cfg, slug)
        meta = cfg.client_meta(slug) or {}
        contacts = meta.get("contacts") or []
        if args.only_real:
            contacts = [c for c in contacts
                        if not c.get("internal") and not is_empty(c)
                        and not is_internal(c.get("email") or "")]
        if contacts or args.client:
            print_contacts(slug, contacts)
        total += len(contacts)
    out.op("contacts", extra=f"{total} sur {len(clients)} client(s)")


def cmd_add(cfg, args):
    f = require_client(cfg, args.client)
    if not args.email and not (args.last_name or args.first_name):
        out.fail("un contact demande au moins un email ou un nom")
    if args.email and not EMAIL_RE.match(args.email):
        out.fail(f"email invalide : {args.email}")
    meta = load_meta(f)
    contacts = meta.setdefault("contacts", [])
    if args.email and find_contact(contacts, args.email):
        out.fail(f"{args.email} est déjà contact de {args.client}",
                 remede=f"pm-client-contact.py set {args.client} {args.email} --phone …")
    entry = {}
    for k in FIELDS:
        v = getattr(args, k, None)
        if v:
            entry[k] = normalize_phone(v) if k == "phone" else v
    if args.email and is_internal(args.email):
        # nos adresses ne caractérisent aucun client : marquées, jamais routables
        entry["internal"] = True
    contacts.append(entry)
    if not args.dry_run:
        save_meta(f, meta)
    out.op("contact", extra=(f"{args.client} + {contact_label(entry)} "
                             f"<{entry.get('email', '—')}>"
                             + (" [interne]" if entry.get("internal") else "")
                             + (" [dry-run]" if args.dry_run else "")))


def cmd_set(cfg, args):
    f = require_client(cfg, args.client)
    meta = load_meta(f)
    c = find_contact(meta.get("contacts") or [], args.email)
    if not c:
        out.fail(f"{args.email} n'est pas contact de {args.client}",
                 remede=f"pm-client-contact.py add {args.client} --email {args.email} …")
    changed = []
    for k in FIELDS:
        if k == "email":
            continue        # ici l'email SÉLECTIONNE la fiche, il ne se modifie pas
        v = getattr(args, k, None)
        if v:
            c[k] = normalize_phone(v) if k == "phone" else v
            changed.append(k)
    if not changed:
        out.fail("rien à modifier", remede="précise --phone / --last-name / --first-name / --role")
    if c.get("email"):
        c["internal"] = is_internal(c["email"]) or None
        if not c["internal"]:
            c.pop("internal", None)
    if not args.dry_run:
        save_meta(f, meta)
    out.op("contact", extra=(f"{args.client} ~ {contact_label(c)} ({', '.join(changed)})"
                             + (" [dry-run]" if args.dry_run else "")))


def cmd_remove(cfg, args):
    f = require_client(cfg, args.client)
    meta = load_meta(f)
    contacts = meta.get("contacts") or []
    c = find_contact(contacts, args.email)
    if not c:
        out.fail(f"{args.email} n'est pas contact de {args.client}")
    contacts.remove(c)
    meta["contacts"] = contacts
    if not args.dry_run:
        save_meta(f, meta)
    out.op("contact", extra=(f"{args.client} − {contact_label(c)}"
                             + (" [dry-run]" if args.dry_run else "")))


def cmd_mark_internal(cfg, args):
    """Marque `internal: true` les contacts portant une de NOS adresses.

    Le gabarit de création en pose un chez chaque client : sans marque, il se
    confond avec un vrai contact client (et a failli servir à router du courrier
    entrant — cf. RM2669).
    """
    clients = [args.client] if args.client else known_clients(cfg)
    touched = []
    for slug in clients:
        f = meta_path(cfg, slug)
        if not f.is_file():
            continue
        meta = load_meta(f)
        changed = False
        for c in meta.get("contacts") or []:
            if is_internal(c.get("email") or "") and not c.get("internal"):
                c["internal"] = True
                changed = True
        if changed:
            touched.append(slug)
            if args.apply and not args.dry_run:
                save_meta(f, meta)
    if not touched:
        out.op("contacts", extra="aucune adresse maison à marquer")
        return
    print("  " + ", ".join(touched))
    out.op("contacts", extra=(f"{len(touched)} client(s) marqués"
                              if args.apply and not args.dry_run else
                              f"{len(touched)} client(s) à marquer — relance avec --apply"))


def redmine_people(cfg, client: str) -> list:
    """Comptes Redmine rattachés aux projets du client (hors comptes maison).

    Redmine porte déjà nom, prénom et email des intervenants d'un client : c'est
    l'amorçage le moins coûteux. Le téléphone, lui, n'y est pas.
    """
    from redmine_utils import http_json, redmine_creds
    url, key = redmine_creds()
    people, seen = [], set()
    for _, proj, _ in cfg.iter_projects(entity=client):
        pmeta = cfg.project_meta(client, proj) or {}
        ident = (pmeta.get("redmine") or {}).get("project_id")
        if not ident:
            continue
        st, data = http_json("GET", f"{url}/projects/{ident}/memberships.json?limit=100", key)
        if st != 200:
            out.warn(f"Redmine {st} sur les membres de {ident} — projet ignoré")
            continue
        for m in data.get("memberships") or []:
            user = m.get("user")
            if not user or user["id"] in seen:
                continue
            seen.add(user["id"])
            st2, u = http_json("GET", f"{url}/users/{user['id']}.json", key)
            if st2 != 200:
                continue
            u = u.get("user", {})
            mail = (u.get("mail") or "").lower()
            if not mail or is_internal(mail):
                continue           # nos propres comptes : pas des contacts clients
            people.append({"last_name": u.get("lastname") or "",
                           "first_name": u.get("firstname") or "",
                           "email": mail,
                           "role": "technique",
                           "_projects": [proj]})
    return people


def cmd_import_redmine(cfg, args):
    f = require_client(cfg, args.client)
    meta = load_meta(f)
    contacts = meta.setdefault("contacts", [])
    found = redmine_people(cfg, args.client)
    new = [p for p in found if not find_contact(contacts, p["email"])]
    for p in found:
        known = "déjà connu" if find_contact(contacts, p["email"]) else "à ajouter"
        print(f"  {contact_label(p):28.28} {p['email']:32.32} {known}")
    if not new:
        out.op("import", extra=f"{args.client} : rien de nouveau ({len(found)} compte(s) vus)")
        return
    if not args.apply:
        out.op("import", extra=(f"{args.client} : {len(new)} contact(s) à ajouter — "
                                f"relance avec --apply pour enregistrer"))
        return
    for p in new:
        p.pop("_projects", None)
        contacts.append(p)
    save_meta(f, meta)
    out.op("import", extra=f"{args.client} + {len(new)} contact(s) depuis Redmine")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    out.add_args(ap)
    ap.add_argument("--dry-run", action="store_true", help="N'écrit pas le meta.yml")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("list", help="Liste les contacts (d'un client, ou de tous)")
    p.add_argument("client", nargs="?")
    p.add_argument("--only-real", action="store_true",
                   help="Masque les contacts internes (nos propres adresses)")

    def add_fields(parser, required_email=False):
        parser.add_argument("--last-name", dest="last_name", help="NOM de famille")
        parser.add_argument("--first-name", dest="first_name", help="Prénom")
        parser.add_argument("--phone", help="Téléphone (chaîne : le + est conservé)")
        parser.add_argument("--role", choices=ROLES, help=f"Rôle ({', '.join(ROLES)})")

    p = sub.add_parser("add", help="Ajoute un contact")
    p.add_argument("client")
    p.add_argument("--email", help="Adresse email")
    add_fields(p)

    p = sub.add_parser("set", help="Modifie un contact existant (repéré par son email)")
    p.add_argument("client")
    p.add_argument("email")
    add_fields(p)

    p = sub.add_parser("remove", help="Retire un contact")
    p.add_argument("client")
    p.add_argument("email")

    p = sub.add_parser("mark-internal",
                       help="Marque nos propres adresses comme internes (non routables)")
    p.add_argument("client", nargs="?")
    p.add_argument("--apply", action="store_true", help="Écrit (sinon : proposition seule)")

    p = sub.add_parser("import-redmine",
                       help="Propose les comptes Redmine rattachés aux projets du client")
    p.add_argument("client")
    p.add_argument("--apply", action="store_true", help="Enregistre (sinon : proposition seule)")

    args = ap.parse_args()
    out.configure(args)
    cfg = PMConfig.load()

    if args.cmd == "set" and not hasattr(args, "email"):
        out.fail("email attendu")
    {"list": cmd_list, "add": cmd_add, "set": cmd_set, "remove": cmd_remove,
     "mark-internal": cmd_mark_internal,
     "import-redmine": cmd_import_redmine}[args.cmd](cfg, args)


if __name__ == "__main__":
    main()
