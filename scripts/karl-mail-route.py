#!/usr/bin/env python3
"""karl-mail-route — routage des emails de la file : qui est le client, quel projet (RM2669).

Lot T2 du chantier RM2666 (CDC `docs/cdc-rm2666-emails-vers-tickets.md`). Consomme la
file produite par `karl-mail-fetch.py` (RM2668) et écrit, dans chaque entrée, un bloc
`routing` : client, projet, **confiance**, **source** et motif lisible.

Rien n'est deviné : quand aucune source fiable ne répond, l'entrée reste « à classer ».
Chaque correction humaine (`--set`) est **apprise** dans `mail-routing.yml` (repo de
données, aucun contenu d'email) et sert dès la relève suivante.

Usage :
    karl-mail-route.py                       # route la file (sources hors-ligne)
    karl-mail-route.py --redmine             # + comptes Redmine des expéditeurs
    karl-mail-route.py --json                # sortie machine
    karl-mail-route.py --set <clé> --to calyclay/dolibarr     # correction (apprise)
    karl-mail-route.py --set <clé> --to calyclay --domain     # apprend le DOMAINE
    karl-mail-route.py --explain <clé>       # pourquoi cette proposition

`<clé>` = identifiant court affiché par `karl-mail-fetch.py --queue` (ou l'adresse).
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pm_mail_routing as routing                          # noqa: E402
from pm_output import out                                  # noqa: E402
from pm_paths import PMConfig                              # noqa: E402

_kmf = None


def kmf():
    """Charge karl-mail-fetch (nom à tirets → import par chemin) pour la file."""
    global _kmf
    if _kmf is None:
        import importlib.util
        p = Path(__file__).resolve().parent / "karl-mail-fetch.py"
        spec = importlib.util.spec_from_file_location("karl_mail_fetch", p)
        _kmf = importlib.util.module_from_spec(spec)
        sys.modules["karl_mail_fetch"] = _kmf
        spec.loader.exec_module(_kmf)
    return _kmf


def redmine_lookup_factory(cfg):
    """(client, projet) des projets Redmine où l'expéditeur est membre.

    Un échec réseau/API ne doit PAS casser le routage : la source est simplement
    absente ce jour-là (les autres sources répondent, ou l'entrée reste à classer).
    """
    from redmine_utils import find_users, http_json, redmine_creds

    ident_cache = {}

    def identifier_of(project_id, url, key):
        """id numérique → `identifier` Redmine. Les appartenances d'un utilisateur
        ne portent que l'id et le nom ; c'est l'`identifier` qui relie au projet PM
        (`redmine.project_id`), et jamais le nom (tripwire NORMS 14)."""
        if project_id not in ident_cache:
            st, data = http_json("GET", f"{url}/projects/{project_id}.json", key)
            ident_cache[project_id] = (data.get("project", {}).get("identifier")
                                       if st == 200 else None)
        return ident_cache[project_id]

    def lookup(addr):
        try:
            users = find_users(addr) or []
            user = next((u for u in users if (u.get("mail") or "").lower() == addr), None)
            if not user:
                return []
            url, key = redmine_creds()
            # http_json retourne (status, body) — pas le body seul
            status, data = http_json(
                "GET", f"{url}/users/{user['id']}.json?include=memberships", key)
            if status != 200:
                out.warn(f"Redmine {status} sur l'utilisateur {user['id']} — source ignorée")
                return []
            pairs = []
            for m in (data.get("user", {}).get("memberships") or []):
                proj = m.get("project") or {}
                ident = proj.get("identifier") or identifier_of(proj.get("id"), url, key)
                if not ident:
                    continue
                ent_path, proj_path = cfg.find_project_by_redmine_id(ident)
                if ent_path and proj_path:      # (Path, Path) → slugs
                    pairs.append((ent_path.name, proj_path.name))
            return pairs
        except Exception as e:                              # noqa: BLE001
            out.warn(f"source Redmine indisponible pour {addr} ({type(e).__name__}) — ignorée")
            return []
    return lookup


def find_entry(items, key):
    """Retrouve une entrée par sa clé courte, sa clé complète ou son adresse."""
    key = (key or "").strip().lower()
    for e in items:
        if e.get("key", "").lower() == key or (e.get("from") or "").lower() == key:
            return e
    matches = [e for e in items if e.get("key", "").lower().startswith(key)]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        out.fail(f"clé ambiguë : {key}",
                 remede="donne la clé complète (karl-mail-fetch.py --queue)")
    return None


def write_entry(e):
    f = kmf().queue_dir() / f"{e['key']}.json"
    f.write_text(json.dumps(e, ensure_ascii=False, indent=1), encoding="utf-8")
    try:
        f.chmod(0o600)
    except OSError:
        pass


def fmt(e) -> str:
    r = e.get("routing") or {}
    target = "—"
    if r.get("client"):
        target = r["client"] + ("/" + r["project"] if r.get("project") else "/?")
    conf = f"{r.get('confidence', 0):.0%}"
    return (f"  {e['key']}  {(e.get('from') or ''):32.32}  {target:26.26} "
            f"{conf:>4}  {r.get('source', '—'):10} {r.get('reason', '')[:60]}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    out.add_args(ap)
    ap.add_argument("--redmine", action="store_true",
                    help="Interroge Redmine (compte de l'expéditeur → ses projets)")
    ap.add_argument("--set", dest="set_key", metavar="CLÉ",
                    help="Corrige le routage d'une entrée (et l'apprend)")
    ap.add_argument("--to", metavar="CIBLE", help="'client' ou 'client/projet' (avec --set)")
    ap.add_argument("--domain", action="store_true",
                    help="Avec --set : apprend le DOMAINE de l'expéditeur, pas l'adresse seule")
    ap.add_argument("--explain", metavar="CLÉ", help="Détaille la décision pour une entrée")
    ap.add_argument("--json", action="store_true", help="Sortie machine")
    ap.add_argument("--dry-run", action="store_true", help="N'écrit ni la file ni la table")
    args = ap.parse_args()
    out.configure(args)

    cfg = PMConfig.load()
    items = kmf().read_queue()
    if not items:
        out.op("routage", extra="file vide — lance d'abord karl-mail-fetch.py")
        return
    lookup = redmine_lookup_factory(cfg) if args.redmine else None

    # — correction humaine : elle fait autorité, et elle s'apprend —
    if args.set_key:
        if not args.to:
            out.fail("--set exige --to <client[/projet]>")
        e = find_entry(items, args.set_key)
        if not e:
            out.fail(f"entrée inconnue dans la file : {args.set_key}")
        client, project = routing.parse_target(args.to)
        known = [c for c, _ in cfg.iter_entities()]
        if client not in known:
            out.fail(f"client inconnu : {client}", remede=f"connus : {', '.join(known)}")
        if project:
            projects = [p for _, p, _ in cfg.iter_projects(entity=client)]
            if project not in projects:
                out.fail(f"projet inconnu chez {client} : {project}",
                         remede=f"connus : {', '.join(projects) or '(aucun)'}")
        e["routing"] = {"client": client, "project": project, "source": "humain",
                        "confidence": 1.0, "reason": "corrigé par le demandeur",
                        "candidates": []}
        if not args.dry_run:
            write_entry(e)
            try:
                routing.learn(cfg, e.get("from") or "", args.to, domain=args.domain)
            except ValueError as err:
                out.fail(str(err), remede="relance sans --domain pour n'apprendre que cette adresse")
        scope = "domaine" if args.domain else "adresse"
        out.op("routage", extra=(f"{e['key']} → {args.to} (appris par {scope} : "
                                 f"{routing.routing_file(cfg).name})"
                                 + (" [dry-run]" if args.dry_run else "")))
        return

    # — routage (ou explication) —
    routed = 0
    for e in items:
        e["routing"] = routing.route(e, cfg, redmine_lookup=lookup)
        if e["routing"].get("client"):
            routed += 1
        if not args.dry_run:
            write_entry(e)

    if args.explain:
        e = find_entry(items, args.explain)
        if not e:
            out.fail(f"entrée inconnue dans la file : {args.explain}")
        r = e["routing"]
        print(f"  entrée   {e['key']}  ({e.get('folder')})")
        print(f"  de       {e.get('from_name')} <{e.get('from')}>")
        print(f"  sujet    {(e.get('subject') or '')[:70]}")
        print(f"  → client {r.get('client') or '(à classer)'}")
        print(f"  → projet {r.get('project') or '(à confirmer)'}")
        print(f"  source   {r.get('source')} · confiance {r.get('confidence'):.0%}")
        print(f"  motif    {r.get('reason')}")
        if r.get("candidates"):
            print(f"  pistes   {', '.join(r['candidates'])}")
        return

    if args.json:
        print(json.dumps([{"key": e["key"], "from": e.get("from"),
                           "subject": e.get("subject"), "routing": e["routing"]}
                          for e in items], ensure_ascii=False, indent=1))
    else:
        for e in items:
            print(fmt(e))
    out.op("routage", extra=(f"{routed}/{len(items)} routé(s) · "
                             f"{len(items) - routed} à classer"
                             + (" [dry-run]" if args.dry_run else "")))
    if routed < len(items):
        out.info("corriger : karl-mail-route.py --set <clé> --to <client[/projet]> "
                 "(la correction est apprise)")


if __name__ == "__main__":
    main()
