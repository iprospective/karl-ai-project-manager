#!/usr/bin/env python3
"""pm-contact — l'annuaire de contacts, indépendant des clients (RM2703).

Une personne, une fiche : `contacts/<ref>.yml` dans le dépôt de DONNÉES. Le
rattachement à un client reste chez lui (`contacts[] : ref + rôle`), parce que
le rôle n'existe que dans la relation et qu'un `meta.yml` doit rester lisible
seul.

Ce que ça remplace : 31 contacts sur 21 clients, dont **19 lignes pour la même
personne**, en deux orthographes. La forme l'imposait — un contact vivant dans
le `meta.yml` de SON client, une personne présente chez vingt clients s'écrivait
vingt fois et divergeait vingt fois.

Ce script est le SEUL point d'écriture de l'annuaire : on n'édite pas une fiche
à la main (tripwire NORMS 1).

Usage :
    pm-contact.py list [--internal] [--client <slug>]
    pm-contact.py show <ref>
    pm-contact.py find <texte>              # nom, prénom ou adresse
    pm-contact.py add --last-name Dupont --first-name Claire \\
                      --email claire@x.fr --phone "+33 6 …" [--internal]
    pm-contact.py set <ref> [--add-email …] [--add-phone …] [--last-name …] …
    pm-contact.py merge <ref-gardée> <ref-absorbée>   # met à jour les clients
    pm-contact.py migrate [--apply]         # 31 lignes en ligne → annuaire
"""
import argparse
import re
import sys
from datetime import date
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pm_contacts as pc                                   # noqa: E402
from pm_output import out                                  # noqa: E402
from pm_paths import PMConfig                              # noqa: E402


def contacts_dir(cfg) -> Path:
    return cfg.path("contacts_dir")


def load_annuaire(cfg) -> dict:
    """{ref → fiche}. Une fiche illisible est signalée, jamais silencieusement
    ignorée : un annuaire qui perd des gens sans le dire est pire qu'absent."""
    d, out_ = contacts_dir(cfg), {}
    if not d.is_dir():
        return out_
    for f in sorted(d.glob("*.yml")):
        try:
            data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as e:
            out.warn(f"fiche illisible {f.name} : {str(e)[:120]}")
            continue
        ref = data.get("ref") or f.stem
        data["ref"] = ref
        out_[ref] = data
    return out_


def write_fiche(cfg, person: dict, dry=False) -> Path:
    d = contacts_dir(cfg)
    p = d / f"{person['ref']}.yml"
    person = {k: person[k] for k in pc.PERSON_FIELDS if person.get(k) not in (None, [], "")}
    person.setdefault("created", date.today().isoformat())
    person["updated"] = date.today().isoformat()
    if not dry:
        d.mkdir(parents=True, exist_ok=True)
        p.write_text(yaml.safe_dump(person, allow_unicode=True, sort_keys=False),
                     encoding="utf-8")
    return p


def meta_path(cfg, slug: Path) -> Path:
    """`meta.yml` d'un client — MÊME résolution que `pm-client-contact`.

    Le `client/` d'une entité est souvent un symlink vers le dépôt de données du
    client lui-même (`<workspace>/.mmi-pm-client/client`) : le `meta.yml` vit
    donc à côté de la CIBLE, pas à côté du lien. Chercher naïvement
    `<entité>/meta.yml` ne trouve que les clients non délocalisés — c'est ainsi
    qu'une migration a d'abord vu 1 contact au lieu de 31."""
    client_dir = cfg.path("entity_client_dir", entity=slug)
    try:
        return client_dir.resolve().parent / "meta.yml"
    except OSError:
        return client_dir.parent / "meta.yml"


def client_metas(cfg):
    """(slug, chemin, données) de chaque `meta.yml` de client."""
    for ent in sorted(cfg.path("entities_dir").glob("*")):
        if not ent.is_dir():
            continue
        m = meta_path(cfg, ent.name)
        if not m.is_file():
            continue
        try:
            data = yaml.safe_load(m.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            continue
        yield ent.name, m, data


def cmd_list(cfg, args):
    ann = load_annuaire(cfg)
    liens = {}
    if args.client:
        for slug, _, data in client_metas(cfg):
            if slug == args.client:
                liens = {c.get("ref"): c for c in (data.get("contacts") or []) if c.get("ref")}
    refs = sorted(ann)
    if args.client:
        refs = [r for r in refs if r in liens]
    if args.internal:
        refs = [r for r in refs if ann[r].get("internal")]
    if not refs:
        out.info("aucun contact")
        return 0
    for r in refs:
        p = ann[r]
        marque = " ·interne" if p.get("internal") else ""
        role = f" [{liens[r].get('role')}]" if liens.get(r, {}).get("role") else ""
        print(f"{r:28} {pc.display_name(p):32}{role}{marque} "
              f"{', '.join(p.get('emails') or [])}")
    return 0


def cmd_show(cfg, args):
    ann = load_annuaire(cfg)
    p = ann.get(args.ref)
    if not p:
        out.fail(f"aucune fiche « {args.ref} »")
    print(yaml.safe_dump(p, allow_unicode=True, sort_keys=False).rstrip())
    rattach = []
    for slug, _, data in client_metas(cfg):
        for c in data.get("contacts") or []:
            if c.get("ref") == args.ref:
                rattach.append(f"{slug} ({c.get('role') or '—'})")
    print("\nrattachements : " + (", ".join(rattach) if rattach else "aucun"))
    return 0


def cmd_find(cfg, args):
    ann = load_annuaire(cfg)
    q = pc._ascii(args.texte)
    hits = [r for r, p in ann.items()
            if q in pc._ascii(f"{r} {pc.display_name(p)} {' '.join(p.get('emails') or [])}")]
    for r in sorted(hits):
        print(f"{r:28} {pc.display_name(ann[r]):32} {', '.join(ann[r].get('emails') or [])}")
    if not hits:
        out.info("aucun résultat")
    return 0


def cmd_add(cfg, args):
    ann = load_annuaire(cfg)
    email = pc.norm_email(args.email)
    if email and not pc.EMAIL_RE.match(email):
        out.fail(f"adresse invalide : {email}")
    if email:
        deja = pc.index_by_email(ann).get(email)
        if deja:
            out.fail(f"cette adresse est déjà celle de « {deja} » — "
                     f"utilise `set {deja} --add-email` ou `merge`")
    ref = args.ref or pc.slugify_person(args.last_name, args.first_name, set(ann))
    if ref in ann:
        out.fail(f"la ref « {ref} » existe déjà")
    p = {"ref": ref, "last_name": args.last_name, "first_name": args.first_name,
         "emails": [email] if email else [], "phones": [args.phone] if args.phone else [],
         "internal": bool(args.internal) or (pc.is_internal_email(email) if email else False),
         "redmine_user_id": args.redmine_user_id, "note": args.note}
    chemin = write_fiche(cfg, p, args.dry_run)
    out.info(f"{'(dry-run) ' if args.dry_run else ''}fiche {ref} → {chemin}")
    if args.porcelain:
        print(ref)
    return 0


def cmd_set(cfg, args):
    ann = load_annuaire(cfg)
    p = ann.get(args.ref)
    if not p:
        out.fail(f"aucune fiche « {args.ref} »")
    idx = pc.index_by_email(ann)
    for e in args.add_email or []:
        e = pc.norm_email(e)
        if not pc.EMAIL_RE.match(e):
            out.fail(f"adresse invalide : {e}")
        if idx.get(e) and idx[e] != args.ref:
            out.fail(f"{e} est déjà celle de « {idx[e]} »")
        p.setdefault("emails", [])
        if e not in [pc.norm_email(x) for x in p["emails"]]:
            p["emails"].append(e)
    for t in args.add_phone or []:
        p.setdefault("phones", [])
        if t not in p["phones"]:
            p["phones"].append(t)
    for champ in ("last_name", "first_name", "note", "redmine_user_id"):
        v = getattr(args, champ)
        if v is not None:
            p[champ] = v
    if args.internal is not None:
        p["internal"] = args.internal
    write_fiche(cfg, p, args.dry_run)
    out.info(f"{'(dry-run) ' if args.dry_run else ''}fiche {args.ref} mise à jour")
    return 0


def cmd_merge(cfg, args):
    """Absorbe une fiche dans une autre, et RÉPARE les rattachements.

    Fusionner sans réécrire les clients laisserait des `ref` orphelines : la
    moitié du travail, et la moitié qui se voit le plus tard."""
    ann = load_annuaire(cfg)
    garde, absorbe = ann.get(args.garde), ann.get(args.absorbe)
    if not garde:
        out.fail(f"aucune fiche « {args.garde} »")
    if not absorbe:
        out.fail(f"aucune fiche « {args.absorbe} »")
    if args.garde == args.absorbe:
        out.fail("une fiche ne s'absorbe pas elle-même")
    fusion = pc.merge_person(garde, absorbe)
    fusion["ref"] = args.garde
    touches = []
    for slug, m, data in client_metas(cfg):
        cs = data.get("contacts") or []
        change = False
        for c in cs:
            if c.get("ref") == args.absorbe:
                c["ref"] = args.garde
                change = True
        if change:
            touches.append(slug)
            if not args.dry_run:
                m.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
                             encoding="utf-8")
    if not args.dry_run:
        write_fiche(cfg, fusion)
        (contacts_dir(cfg) / f"{args.absorbe}.yml").unlink(missing_ok=True)
    out.info(f"{'(dry-run) ' if args.dry_run else ''}{args.absorbe} absorbée dans "
           f"{args.garde} · {len(touches)} client(s) réaiguillé(s)"
           + (" : " + ", ".join(touches) if touches else ""))
    return 0


def cmd_migrate(cfg, args):
    """Les contacts en ligne → l'annuaire, en dédoublonnant par adresse.

    Toujours un rapport d'abord : la migration touche tous les `meta.yml` du
    parc, et un dédoublonnage qui se trompe fusionne deux personnes réelles."""
    ann = load_annuaire(cfg)
    par_email, sans_email, plan = pc.index_by_email(ann), [], []
    personnes = dict(ann)
    liens = {}          # slug → nouvelle liste contacts[]
    for slug, m, data in client_metas(cfg):
        cs = data.get("contacts") or []
        if not cs:
            continue
        nouveaux, change = [], False
        for c in cs:
            if c.get("ref"):
                nouveaux.append(c)
                continue
            base = pc.person_from_legacy(c)
            email = (base["emails"] or [None])[0]
            ref = par_email.get(email) if email else None
            if ref:
                personnes[ref] = pc.merge_person(personnes[ref], base)
            else:
                ref = pc.slugify_person(base["last_name"], base["first_name"],
                                        set(personnes), email=email)
                base["ref"] = ref
                personnes[ref] = base
                if email:
                    par_email[email] = ref
                else:
                    sans_email.append((slug, ref))
            lien = {"ref": ref}
            for champ in ("role", "title", "since"):
                if c.get(champ):
                    lien[champ] = c[champ]
            nouveaux.append(lien)
            change = True
            plan.append((slug, ref, pc.display_name(personnes[ref]), email or "—"))
        if change:
            liens[slug] = (m, data, nouveaux)

    print(f"{len(plan)} contact(s) en ligne → {len(personnes)} personne(s) "
          f"({len(ann)} déjà en annuaire)")
    for slug, ref, nom, email in plan:
        print(f"  {slug:22} → {ref:26} {nom:28} {email}")
    if sans_email:
        print("\n⚠ sans adresse (dédoublonnage impossible, une fiche par ligne) :")
        for slug, ref in sans_email:
            print(f"    {slug} → {ref}")
    if not args.apply:
        print("\n(dry-run — rien écrit ; relancer avec --apply)")
        return 0
    for ref, p in personnes.items():
        p["ref"] = ref
        write_fiche(cfg, p)
    for slug, (m, data, nouveaux) in liens.items():
        data["contacts"] = nouveaux
        m.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
                     encoding="utf-8")
    out.info(f"{len(personnes)} fiche(s) écrites, {len(liens)} client(s) rattachés")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dry-run", action="store_true")
    out.add_args(ap)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("list"); p.add_argument("--internal", action="store_true")
    p.add_argument("--client")
    p = sub.add_parser("show"); p.add_argument("ref")
    p = sub.add_parser("find"); p.add_argument("texte")
    p = sub.add_parser("add")
    p.add_argument("--ref"); p.add_argument("--last-name"); p.add_argument("--first-name")
    p.add_argument("--email"); p.add_argument("--phone"); p.add_argument("--note")
    p.add_argument("--redmine-user-id", type=int)
    p.add_argument("--internal", action="store_true"); p.add_argument("--porcelain", action="store_true")
    p = sub.add_parser("set"); p.add_argument("ref")
    p.add_argument("--add-email", action="append"); p.add_argument("--add-phone", action="append")
    p.add_argument("--last-name"); p.add_argument("--first-name"); p.add_argument("--note")
    p.add_argument("--redmine-user-id", type=int)
    p.add_argument("--internal", dest="internal", action="store_true", default=None)
    p.add_argument("--no-internal", dest="internal", action="store_false")
    p = sub.add_parser("merge"); p.add_argument("garde"); p.add_argument("absorbe")
    p = sub.add_parser("migrate"); p.add_argument("--apply", action="store_true")

    args = ap.parse_args()
    out.configure(args)
    cfg = PMConfig.load()
    return {"list": cmd_list, "show": cmd_show, "find": cmd_find, "add": cmd_add,
            "set": cmd_set, "merge": cmd_merge, "migrate": cmd_migrate}[args.cmd](cfg, args)


if __name__ == "__main__":
    sys.exit(main())
