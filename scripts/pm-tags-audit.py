#!/usr/bin/env python3
"""pm-tags-audit — écarts entre le CF Redmine « Tags », le registre et les usages.

Trois sources qui doivent dire la même chose, et qui dérivent dès qu'on ne
regarde pas (RM2836, chantier RM2828) :

  1. la définition Redmine du CF (`possible_values`) — modifiable seulement dans
     l'UI admin : l'API expose les custom fields en LECTURE SEULE ;
  2. `tags.registry.yml` — la table `slug ↔ label ↔ id` dont l'outillage a besoin
     pour pousser (le CF est en format `enumeration` : il veut des ids) ;
  3. les étiquettes réellement portées par les tickets (frontmatter `tags:`).

L'audit ne corrige rien de lui-même : il dit **ce qu'il faut faire, et où**.
Créer une valeur est un geste humain dans l'UI ; recopier son id ici en est un
autre. Une commande qui écrirait en base sous prétexte de synchroniser serait
plus rapide et bien plus dangereuse.

    pm-tags-audit.py               # rapport complet
    pm-tags-audit.py --json        # sortie machine
    pm-tags-audit.py --top 30      # profondeur du palmarès des non couverts
    pm-tags-audit.py --no-redmine  # sans appel API (registre ↔ usages seulement)
"""
import argparse
import collections
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pm_tags
from pm_paths import PMConfig

try:
    import yaml
except ImportError:
    sys.exit("PyYAML requis : pip install PyYAML")


def cf_live(cf_id):
    """{slug: (id, label)} depuis Redmine, ou None si l'API n'est pas joignable.

    None ≠ {} : « je n'ai pas pu regarder » n'est pas « le CF est vide », et le
    rapport doit distinguer les deux plutôt que d'annoncer 7 valeurs à recréer.
    """
    base = (os.environ.get("REDMINE_URL") or "").rstrip("/")
    key = os.environ.get("REDMINE_API_KEY") or os.environ.get("REDMINE_USER_MAIN_API_KEY")
    if not base:
        try:
            import redmine_utils
            base = (redmine_utils.load_reference().get("instance") or "").rstrip("/")
        except Exception:       # noqa: BLE001
            base = ""
    if not base or not key:
        return None
    req = urllib.request.Request(f"{base}/custom_fields.json",
                                 headers={"X-Redmine-API-Key": key})
    try:
        data = json.load(urllib.request.urlopen(req, timeout=20))
    except (urllib.error.URLError, OSError, ValueError):
        return None
    for cf in data.get("custom_fields") or []:
        if cf.get("id") == cf_id:
            # Indexé par ID, pas par libellé : l'id est la clé STABLE côté
            # Redmine, et le registre autorise un slug différent du libellé
            # (« Debug/Bugfix » s'écrit `debug`). Comparer par libellé ferait
            # voir un écart là où il n'y en a pas — et raterait un renommage.
            return {str(v.get("value")): v.get("label") for v in cf.get("possible_values") or []}
    return {}


def usages(cfg):
    """{slug: (tickets, projets)} — ce que les frontmatters portent réellement."""
    n = collections.Counter()
    proj = collections.defaultdict(set)
    fm_re = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.S)
    for ent, project, _ in cfg.iter_projects():
        tasks = cfg.path("tasks_dir", entity=ent, project=project)
        if not tasks.is_dir():
            continue
        for f in tasks.glob("RM*_*.md"):
            if f.name.endswith(".log.md"):
                continue
            try:
                m = fm_re.match(f.read_text(encoding="utf-8"))
            except OSError:
                continue
            if not m:
                continue
            try:
                fm = yaml.safe_load(m.group(1)) or {}
            except yaml.YAMLError:
                continue
            for t in fm.get("tags") or []:
                s = pm_tags.normalize(t)
                if s:
                    n[s] += 1
                    proj[s].add(f"{ent}/{project}")
    return {s: (c, len(proj[s])) for s, c in n.items()}


def audit(top=20, with_redmine=True):
    cfg = PMConfig.load()
    reg = pm_tags.load_registry()            # actives (id connu)
    pend = set(pm_tags.pending_values())     # décidées, pas encore créées
    alias = pm_tags.load_aliases()
    live = cf_live(pm_tags.cf_id()) if with_redmine else None
    us = usages(cfg)

    # 1. décidées au registre mais absentes du CF → à créer dans l'UI
    a_creer = []
    for slug in sorted(pend):
        n, p = us.get(slug, (0, 0))
        via = sum(us.get(a, (0, 0))[0] for a, c in alias.items() if c == slug)
        a_creer.append({"slug": slug, "tickets": n, "via_alias": via, "projets": p})
    ids_registre = {spec["id"]: slug for slug, spec in reg.items()}
    # 2. créées côté Redmine mais absentes du registre → id à recopier
    a_recopier = []
    if live:
        for vid, label in sorted(live.items(), key=lambda kv: int(kv[0])):
            if vid not in ids_registre:
                a_recopier.append({"slug": pm_tags.normalize(label), "label": label, "id": vid})
    # 3. au registre (avec id) mais plus dans le CF → valeur supprimée côté Redmine
    orphelines = []
    if live is not None:
        for slug, spec in sorted(reg.items()):
            if spec["id"] not in live:
                orphelines.append({"slug": slug, "id": spec["id"], "label": spec["label"]})
    # 4. même id, libellé DIFFÉRENT → renommage côté Redmine à répercuter. Sans
    # ce contrôle, le registre afficherait éternellement l'ancien libellé et
    # personne ne saurait pourquoi l'UI dit autre chose.
    renommees = []
    if live:
        for slug, spec in sorted(reg.items()):
            vif = live.get(spec["id"])
            if vif is not None and vif != spec["label"]:
                renommees.append({"slug": slug, "id": spec["id"],
                                  "registre": spec["label"], "redmine": vif})
    # 4. usages non couverts (ni valeur ni alias) — le vocabulaire libre
    vocab = set(pm_tags.vocabulary())
    libres = sorted(((s, n, p) for s, (n, p) in us.items()
                     if s not in vocab and s not in alias),
                    key=lambda x: (-x[1], x[0]))
    return {
        "cf_id": pm_tags.cf_id(), "cf_name": pm_tags.CF_NAME,
        "redmine_lu": live is not None,
        "a_creer": a_creer, "a_recopier": a_recopier, "orphelines": orphelines,
        "renommees": renommees,
        "libres": [{"slug": s, "tickets": n, "projets": p} for s, n, p in libres[:top]],
        "libres_total": len(libres),
        "couverture": {
            "usages_total": sum(n for n, _ in us.values()),
            "usages_couverts": sum(n for s, (n, _) in us.items()
                                   if s in vocab or s in alias),
        },
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--top", type=int, default=20, help="Mots-clés libres listés (défaut 20)")
    ap.add_argument("--no-redmine", action="store_true", help="Sans appel API")
    args = ap.parse_args()
    r = audit(top=args.top, with_redmine=not args.no_redmine)
    if args.json:
        print(json.dumps(r, ensure_ascii=False, indent=1))
        return

    print(f"CF « {r['cf_name']} » (id {r['cf_id']}) — audit du registre {pm_tags.REGISTRY}")
    if not r["redmine_lu"]:
        print("⚠ définition Redmine NON lue (API injoignable ou --no-redmine) : "
              "les écarts CF↔registre ne sont pas contrôlés.")
    c = r["couverture"]
    pct = (100 * c["usages_couverts"] // c["usages_total"]) if c["usages_total"] else 0
    print(f"couverture : {c['usages_couverts']}/{c['usages_total']} usages ({pct} %) "
          f"par le vocabulaire + ses alias\n")

    if r["a_creer"]:
        print(f"→ À CRÉER dans l'UI admin Redmine ({len(r['a_creer'])}) — "
              "Administration › Champs personnalisés › Tags › Valeurs possibles :")
        for e in r["a_creer"]:
            print(f"   {e['slug']:<16} {e['tickets']:>4} ticket(s) directs, "
                  f"{e['via_alias']:>4} via alias")
        print("   puis recopier chaque id dans le registre (cf. ligne suivante).\n")
    if r["a_recopier"]:
        print(f"→ À RECOPIER dans {pm_tags.REGISTRY} ({len(r['a_recopier'])}) — "
              "valeurs qui existent côté Redmine mais que le registre ignore "
              "(donc impossibles à pousser) :")
        for e in r["a_recopier"]:
            print(f"   - {{slug: {e['slug']}, label: \"{e['label']}\", id: {e['id']}}}")
        print()
    if r["orphelines"]:
        print(f"→ ORPHELINES ({len(r['orphelines'])}) — au registre avec un id, mais "
              "absentes du CF : la valeur a été supprimée ou renommée côté Redmine.")
        for e in r["orphelines"]:
            print(f"   {e['slug']} (id {e['id']}, « {e['label']} »)")
        print()
    if r["renommees"]:
        print(f"→ RENOMMÉES côté Redmine ({len(r['renommees'])}) — libellé à mettre à jour "
              f"dans {pm_tags.REGISTRY} :")
        for e in r["renommees"]:
            print(f"   {e['slug']} (id {e['id']}) : registre « {e['registre']} » "
                  f"≠ Redmine « {e['redmine']} »")
        print()
    if not (r["a_creer"] or r["a_recopier"] or r["orphelines"] or r["renommees"]):
        print("✓ registre et CF Redmine sont synchrones.\n")

    print(f"mots-clés LIBRES les plus utilisés ({r['libres_total']} au total, "
          "hors vocabulaire et hors alias — ils restent locaux) :")
    for e in r["libres"]:
        print(f"   {e['tickets']:>4} · {e['slug']}  ({e['projets']} projet(s))")


if __name__ == "__main__":
    main()
