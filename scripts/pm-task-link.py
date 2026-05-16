#!/usr/bin/env python3
"""pm-task-link — Gestion des liens entre tickets PM (Redmine + frontmatter + log).

Sous-commandes :
    add  <from-id> <to-id> --type {relates|depends_on|blocks}
    list <id>
    rm   <from-id> <to-id> [--type T]
    sync <id>

Types supportés (NORMS v1.9.0) :
    relates       — lien latéral non-bloquant (symétrique côté PM)
    depends_on    — A.depends_on += B  ⇔  B.blocks += A     (Redmine: B blocks A)
    blocks        — A.blocks += B      ⇔  B.depends_on += A (Redmine: A blocks B)

Le script maintient :
  - la relation Redmine (POST / DELETE sur /issues/<id>/relations.json)
  - le frontmatter MD des DEUX tâches (champ correspondant + miroir côté cible)
  - une entrée dans les .log.md des deux tâches

Exemples :
    pm-task-link.py add 1708 1703 --type relates
    pm-task-link.py list 1709
    pm-task-link.py rm 1708 1703
    pm-task-link.py sync 1708        # pull depuis Redmine, reflète dans le frontmatter
"""
import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pm_paths import PMConfig

try:
    import yaml
except ImportError:
    sys.exit("PyYAML requis : pip install PyYAML")


# Mapping PM → Redmine
# - Pour "A relates B"      : POST /issues/A/relations { relation_type:relates, issue_to_id:B }
# - Pour "A depends_on B"   : POST /issues/B/relations { relation_type:blocks,  issue_to_id:A }
# - Pour "A blocks B"       : POST /issues/A/relations { relation_type:blocks,  issue_to_id:B }
PM_TYPES = ("relates", "depends_on", "blocks")
MIRROR = {"depends_on": "blocks", "blocks": "depends_on", "relates": "relates"}
FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


# ── Redmine helpers ─────────────────────────────────────────────────────────

def _redmine_creds():
    url = os.environ.get("REDMINE_URL", "").rstrip("/")
    key = os.environ.get("REDMINE_USER_MAIN_API_KEY") or os.environ.get("REDMINE_API_KEY")
    if not (url and key):
        sys.exit("ERREUR : REDMINE_URL et REDMINE_USER_MAIN_API_KEY requis (.env)")
    return url, key


def _http(method, url, key, payload=None):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json", "X-Redmine-API-Key": key},
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            body = r.read()
            return r.status, (json.loads(body) if body else {})
    except urllib.error.HTTPError as e:
        return e.code, {"_error": e.read().decode(errors="replace")[:500]}


def redmine_get_relations(rm_id):
    url, key = _redmine_creds()
    code, body = _http("GET", f"{url}/issues/{rm_id}/relations.json", key)
    if code != 200:
        sys.exit(f"ERREUR Redmine HTTP {code} : {body.get('_error')}")
    return body.get("relations", [])


def redmine_post_relation(from_id, to_id, relation_type):
    url, key = _redmine_creds()
    payload = {"relation": {"issue_to_id": to_id, "relation_type": relation_type}}
    code, body = _http("POST", f"{url}/issues/{from_id}/relations.json", key, payload)
    if code not in (200, 201):
        # Redmine renvoie 422 si la relation existe déjà — non bloquant
        # (msg variable selon locale Redmine : EN "has already been taken" / FR "déjà utilisé")
        err = body.get("_error", "")
        already = ("has already been taken" in err or "already exists" in err
                   or "déjà utilisé" in err or "déjà existante" in err)
        if already:
            return None
        sys.exit(f"ERREUR Redmine HTTP {code} : {err}")
    return body.get("relation", {}).get("id")


def redmine_delete_relation(relation_id):
    url, key = _redmine_creds()
    code, body = _http("DELETE", f"{url}/relations/{relation_id}.json", key)
    if code not in (200, 204):
        sys.exit(f"ERREUR Redmine HTTP {code} : {body.get('_error')}")


# ── Frontmatter helpers ─────────────────────────────────────────────────────

def load_task_md(cfg, rm_id):
    """Retourne (md_path, frontmatter_dict, body_str). Sys.exit si introuvable."""
    p = cfg.find_task(rm_id)
    if not p:
        sys.exit(f"ERREUR : RM{rm_id} introuvable parmi les projets PM")
    content = p.read_text(encoding="utf-8")
    m = FM_RE.match(content)
    if not m:
        sys.exit(f"ERREUR : pas de frontmatter dans {p}")
    fm = yaml.safe_load(m.group(1)) or {}
    body = content[m.end():]
    return p, fm, body


def write_task_md(md_path, fm, body):
    fm_yaml = yaml.safe_dump(fm, allow_unicode=True, sort_keys=False, default_flow_style=False).rstrip()
    md_path.write_text(f"---\n{fm_yaml}\n---\n{body}", encoding="utf-8")


def add_to_list(fm, field, value):
    """Ajoute value à fm[field] (initialise la liste si absente). Retourne True si modifié."""
    lst = fm.get(field) or []
    if not isinstance(lst, list):
        sys.exit(f"ERREUR : champ {field!r} n'est pas une liste : {lst!r}")
    if value in lst:
        return False
    lst.append(value)
    fm[field] = lst
    return True


def remove_from_list(fm, field, value):
    lst = fm.get(field) or []
    if not isinstance(lst, list) or value not in lst:
        return False
    lst.remove(value)
    fm[field] = lst
    return True


def touch_updated(fm):
    fm["updated"] = datetime.now().strftime("%Y-%m-%dT%H:%M")


def append_log(md_path, message):
    log_path = md_path.parent / md_path.name.replace(".md", ".log.md")
    ts = datetime.now().strftime("%Y-%m-%dT%H:%M")
    entry = f"\n## {ts} — Lien (pm-task-link)\nTokens : 0 | Durée : 0 min\n\n{message}\n"
    with log_path.open("a", encoding="utf-8") as f:
        f.write(entry)


# ── Sous-commandes ──────────────────────────────────────────────────────────

def cmd_add(args, cfg):
    if args.from_id == args.to_id:
        sys.exit("ERREUR : impossible de lier un ticket à lui-même")
    if args.type not in PM_TYPES:
        sys.exit(f"ERREUR : type invalide ({args.type}). Choix : {', '.join(PM_TYPES)}")

    from_path, from_fm, from_body = load_task_md(cfg, args.from_id)
    to_path,   to_fm,   to_body   = load_task_md(cfg, args.to_id)

    # 1. Frontmatter source
    src_changed = add_to_list(from_fm, args.type, args.to_id)
    # 2. Frontmatter cible (miroir)
    mirror_field = MIRROR[args.type]
    dst_changed = add_to_list(to_fm, mirror_field, args.from_id)

    # 3. Redmine
    if args.type == "relates":
        rm_id = redmine_post_relation(args.from_id, args.to_id, "relates")
    elif args.type == "blocks":
        rm_id = redmine_post_relation(args.from_id, args.to_id, "blocks")
    elif args.type == "depends_on":
        # A depends_on B → POST sur B : blocks A
        rm_id = redmine_post_relation(args.to_id, args.from_id, "blocks")

    # 4. Persistance
    if src_changed:
        touch_updated(from_fm)
        write_task_md(from_path, from_fm, from_body)
        append_log(from_path, f"`{args.type}` += RM{args.to_id} (relation Redmine #{rm_id or 'déjà existante'}).")
    if dst_changed:
        touch_updated(to_fm)
        write_task_md(to_path, to_fm, to_body)
        append_log(to_path, f"`{mirror_field}` += RM{args.from_id} (miroir auto, relation Redmine #{rm_id or 'déjà existante'}).")

    print(f"✓ Lien `{args.type}` créé : RM{args.from_id} → RM{args.to_id}")
    print(f"  Frontmatter source : {'maj' if src_changed else 'déjà à jour'}")
    print(f"  Frontmatter cible  : {'maj' if dst_changed else 'déjà à jour'}")
    print(f"  Redmine relation   : #{rm_id}" if rm_id else "  Redmine relation   : déjà existante")


def cmd_list(args, cfg):
    md_path, fm, _ = load_task_md(cfg, args.rm_id)
    print(f"━━━ RM{args.rm_id} — liens ━━━\n")
    print(f"Fichier : {md_path.relative_to(cfg.projects_root)}\n")

    print("Frontmatter PM :")
    for f in ("parent_task", "sub_tasks", "depends_on", "blocks", "relates"):
        v = fm.get(f)
        if v in (None, [], "", 0):
            continue
        print(f"  {f:14s} = {v}")
    refs = fm.get("refs") or []
    if refs:
        print(f"  refs           = {refs}")

    print("\nRelations Redmine :")
    rels = redmine_get_relations(args.rm_id)
    if not rels:
        print("  (aucune)")
        return
    for r in rels:
        # issue_id / issue_to_id pour distinguer le sens
        other = r["issue_to_id"] if r["issue_id"] == args.rm_id else r["issue_id"]
        direction = "→" if r["issue_id"] == args.rm_id else "←"
        print(f"  #{r['id']:>4}  {direction} RM{other:<6}  {r['relation_type']}")


def cmd_rm(args, cfg):
    if args.from_id == args.to_id:
        sys.exit("ERREUR : from-id et to-id identiques")
    from_path, from_fm, from_body = load_task_md(cfg, args.from_id)
    to_path,   to_fm,   to_body   = load_task_md(cfg, args.to_id)

    # 1. Trouver le type à supprimer
    types_to_try = [args.type] if args.type else PM_TYPES
    removed_pm = []
    for t in types_to_try:
        if remove_from_list(from_fm, t, args.to_id):
            removed_pm.append((t, "from"))
            remove_from_list(to_fm, MIRROR[t], args.from_id)
    # Inverse : on a peut-être le lien posé depuis B
    for t in types_to_try:
        if remove_from_list(to_fm, t, args.from_id):
            if (MIRROR[t], "from") not in removed_pm:
                removed_pm.append((t, "to"))
                remove_from_list(from_fm, MIRROR[t], args.to_id)

    if not removed_pm:
        print(f"⚠ Aucun lien PM trouvé entre RM{args.from_id} et RM{args.to_id}")

    # 2. Redmine — supprimer toutes les relations entre les deux
    rels = redmine_get_relations(args.from_id)
    deleted_ids = []
    for r in rels:
        other = r["issue_to_id"] if r["issue_id"] == args.from_id else r["issue_id"]
        if other != args.to_id:
            continue
        if args.type and r["relation_type"] != _pm_to_redmine_type(args.type):
            continue
        redmine_delete_relation(r["id"])
        deleted_ids.append(r["id"])

    # 3. Persistance MD
    if removed_pm:
        touch_updated(from_fm)
        touch_updated(to_fm)
        write_task_md(from_path, from_fm, from_body)
        write_task_md(to_path, to_fm, to_body)
        append_log(from_path, f"Lien supprimé vers RM{args.to_id} (types: {removed_pm}, Redmine #{deleted_ids}).")
        append_log(to_path,   f"Lien supprimé vers RM{args.from_id} (types: {removed_pm}, Redmine #{deleted_ids}).")

    print(f"✓ Supprimé : PM={removed_pm or 'rien'} | Redmine relations={deleted_ids or 'rien'}")


def _pm_to_redmine_type(pm_type):
    """Mapping PM type → Redmine relation_type (sans tenir compte de la direction)."""
    return {"relates": "relates", "depends_on": "blocks", "blocks": "blocks"}[pm_type]


def cmd_sync(args, cfg):
    """Pull les relations Redmine, reflète dans le frontmatter PM (et miroirs)."""
    md_path, fm, body = load_task_md(cfg, args.rm_id)
    rels = redmine_get_relations(args.rm_id)

    # Reconstruire les listes PM depuis Redmine (ne touche pas parent/sub qui sont des
    # attributs d'issue, pas des relations).
    inferred = {"relates": [], "depends_on": [], "blocks": []}
    for r in rels:
        rt = r["relation_type"]
        if r["issue_id"] == args.rm_id:
            other = r["issue_to_id"]
            if rt == "relates":
                inferred["relates"].append(other)
            elif rt == "blocks":
                inferred["blocks"].append(other)
        else:
            other = r["issue_id"]
            if rt == "relates":
                inferred["relates"].append(other)
            elif rt == "blocks":
                # autre bloque celui-ci → celui-ci depends_on autre
                inferred["depends_on"].append(other)

    # Merge dans le frontmatter (préserve les valeurs locales pour ne pas perdre les
    # liens MD-only) — on ajoute seulement ce qui manque.
    changed = []
    for field, vals in inferred.items():
        existing = fm.get(field) or []
        for v in sorted(set(vals)):
            if v not in existing:
                existing.append(v)
                changed.append((field, v))
        fm[field] = existing

    # Drifts : champ PM qui pointe vers un RM-id absent côté Redmine
    drifts = []
    for field, vals in inferred.items():
        for v in (fm.get(field) or []):
            if v not in vals:
                drifts.append((field, v))

    if changed:
        touch_updated(fm)
        write_task_md(md_path, fm, body)
        append_log(md_path, f"Sync depuis Redmine : ajouté {changed}.")
        print(f"✓ Frontmatter RM{args.rm_id} synchronisé depuis Redmine :")
        for field, v in changed:
            print(f"    + {field} RM{v}")
    else:
        print(f"✓ RM{args.rm_id} déjà à jour vs Redmine")

    if drifts:
        print("\n⚠ Drifts détectés (présent côté PM, absent côté Redmine) :")
        for field, v in drifts:
            print(f"    - {field} RM{v}  ← à vérifier manuellement")


# ── Argparse ────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    s_add = sub.add_parser("add", help="Créer un lien")
    s_add.add_argument("from_id", type=int)
    s_add.add_argument("to_id", type=int)
    s_add.add_argument("--type", default="relates", choices=PM_TYPES)

    s_list = sub.add_parser("list", help="Lister les liens d'une tâche")
    s_list.add_argument("rm_id", type=int)

    s_rm = sub.add_parser("rm", help="Supprimer un lien")
    s_rm.add_argument("from_id", type=int)
    s_rm.add_argument("to_id", type=int)
    s_rm.add_argument("--type", default=None, choices=PM_TYPES,
                      help="Si omis, supprime tout lien entre les deux")

    s_sync = sub.add_parser("sync", help="Synchroniser le frontmatter PM depuis Redmine")
    s_sync.add_argument("rm_id", type=int)

    args = ap.parse_args()
    cfg = PMConfig.load()

    if args.cmd == "add":
        cmd_add(args, cfg)
    elif args.cmd == "list":
        cmd_list(args, cfg)
    elif args.cmd == "rm":
        cmd_rm(args, cfg)
    elif args.cmd == "sync":
        cmd_sync(args, cfg)


if __name__ == "__main__":
    main()
