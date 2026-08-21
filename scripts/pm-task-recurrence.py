#!/usr/bin/env python3
"""pm-task-recurrence — périodicité d'un ticket RÉCURRENT (RM2772, lot 1).

Certains tickets ne se ferment pas définitivement : ils décrivent une vérification
rejouée à intervalle régulier (ex. RM2771 — mise à jour mensuelle du serveur
Vaultwarden). Le modèle retenu (arbitrage Mathieu 2026-08-21) est **un ticket unique
par sujet, rouvert et retraité à chaque passage** — pas un ticket par run.

La périodicité vit à deux endroits, tenus synchrones par cet outil :
  * le CF Redmine **« Recurrence »** (id 7, enumeration) — c'est lui que voient les
    vues Redmine et, à terme, le cockpit ;
  * le champ frontmatter **`recurrence`** de la fiche MD.

Sous-commandes :
    set   <RM-id> <quotidienne|hebdomadaire|mensuelle|annuelle>
    clear <RM-id>
    show  <RM-id>
    list  [--entity <slug>]   # tous les tickets récurrents + date de dernier update

⚠ Redmine répond **200/204 et ignore silencieusement** la valeur d'un CF non activé
pour le projet ou le tracker du ticket (piège constaté en RM2657). On relit donc le
ticket après écriture plutôt que d'annoncer un succès mensonger.

La **date de prochain run** (CF dédié) et la vue cockpit sont les lots 2 et 3 de
RM2772 : cet outil ne les couvre pas encore.

Exemples :
    pm-task-recurrence.py set 2771 mensuelle
    pm-task-recurrence.py show 2771
    pm-task-recurrence.py list
"""
import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pm_git
from pm_lock import atomic_write, ticket_lock
from pm_output import out
from pm_paths import PMConfig
from redmine_utils import (recurrence_cf, recurrence_from_cf, redmine_creds,
                           update_issue_fields)

try:
    import yaml
except ImportError:
    sys.exit("PyYAML requis : pip install PyYAML")

FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


# ── I/O tâche ─────────────────────────────────────────────────────────────

def load_task(cfg, rm_id):
    """(path, frontmatter, body) — sys.exit si la fiche est introuvable."""
    path, _ent, _proj = cfg.locate_task(rm_id)
    if not path:
        out.fail(f"RM{rm_id} introuvable parmi les projets PM")
    content = path.read_text(encoding="utf-8")
    m = FM_RE.match(content)
    if not m:
        out.fail(f"pas de frontmatter dans {path}")
    return path, (yaml.safe_load(m.group(1)) or {}), content[m.end():]


def write_task(path, fm, body, expected_updated):
    """Écrit la fiche — optimistic locking sur `updated` (NORMS § locking)."""
    current = path.read_text(encoding="utf-8")
    m = FM_RE.match(current)
    fresh = (yaml.safe_load(m.group(1)) or {}) if m else {}
    if fresh.get("updated") != expected_updated:
        out.fail(f"collision : `updated` a changé pendant l'opération "
                 f"({expected_updated} → {fresh.get('updated')}). Relance la commande.")
    fm["updated"] = datetime.now().strftime("%Y-%m-%dT%H:%M")
    fm_yaml = yaml.safe_dump(fm, allow_unicode=True, sort_keys=False,
                             default_flow_style=False).rstrip()
    atomic_write(path, f"---\n{fm_yaml}\n---\n{body}")   # T7 : atomique


def append_log(path, message):
    log_path = path.parent / path.name.replace(".md", ".log.md")
    ts = datetime.now().strftime("%Y-%m-%dT%H:%M")
    with log_path.open("a", encoding="utf-8") as f:
        f.write(f"\n## {ts} — Récurrence (pm-task-recurrence)\n"
                f"Tokens : 0 | Durée : 0 min\n\n{message}\n")


def autocommit(args, path, message):
    if getattr(args, "no_commit", False):
        return
    pm_git.autocommit([path, path.parent / path.name.replace(".md", ".log.md")],
                      message)


# ── CF Redmine ────────────────────────────────────────────────────────────

def push_cf(rm_id, recurrence):
    """Pose (ou vide) le CF « Recurrence ». Retourne (posé?, raison si non).

    `recurrence=None` vide le champ côté Redmine. La relecture est le vrai
    contrôle : un CF non activé pour le projet/tracker se fait ignorer en
    silence malgré un HTTP 2xx.
    """
    cf_id, values = recurrence_cf()
    if not cf_id:
        return False, "recurrence_cf absent de redmine.reference.yml"
    if recurrence is not None and recurrence not in values:
        return False, f"périodicité inconnue : {recurrence!r}"
    wanted = str(values[recurrence]) if recurrence else ""
    ok, err = update_issue_fields(rm_id, custom_fields=[{"id": cf_id, "value": wanted}])
    if not ok:
        return False, err
    got = read_cf(rm_id)
    if got != recurrence:
        return False, (f"Redmine a ignoré la valeur (relu : {got!r}) — le CF {cf_id} "
                       "est-il activé pour ce projet et ce tracker ?")
    return True, None


def read_cf(rm_id):
    """Périodicité NORMS portée par le ticket Redmine (ou None)."""
    import json
    import urllib.request
    cf_id, _ = recurrence_cf()
    if not cf_id:
        return None
    url, key = redmine_creds()
    req = urllib.request.Request(f"{url.rstrip('/')}/issues/{rm_id}.json?key={key}",
                                 headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        issue = json.load(r).get("issue") or {}
    for c in issue.get("custom_fields") or []:
        if c.get("id") == cf_id:
            return recurrence_from_cf(c.get("value"))
    return None


# ── Sous-commandes ────────────────────────────────────────────────────────

def cmd_set(cfg, args, recurrence):
    rm_id = args.rm_id
    path, fm, body = load_task(cfg, rm_id)
    before = fm.get("recurrence")
    if before == recurrence:
        out.info(f"RM{rm_id} porte déjà recurrence={recurrence or '—'} (rien à faire)")
        return
    with ticket_lock(cfg.state_dir, rm_id):   # sérialise CF + MD + log
        ok, err = push_cf(rm_id, recurrence)
        if not ok:
            out.fail(f"CF Recurrence non posé sur RM{rm_id} : {err}")
        path, fm, body = load_task(cfg, rm_id)   # relecture sous verrou
        expected = fm.get("updated")
        fm["recurrence"] = recurrence
        write_task(path, fm, body, expected)
        label = recurrence or "—"
        append_log(path, f"Récurrence : `{before or '—'}` → `{label}` "
                         f"(CF Redmine 7 « Recurrence » + frontmatter `recurrence`).")
        autocommit(args, path, f"pm(recurrence): RM{rm_id} {before or '—'} → {label}")
    out.op("recurrence", rm_id, recurrence or "—")


def cmd_show(cfg, args):
    rm_id = args.rm_id
    _path, fm, _body = load_task(cfg, rm_id)
    local = fm.get("recurrence") or "—"
    remote = read_cf(rm_id) or "—"
    flag = "" if local == remote else "   ⚠ MD et Redmine divergent (pm-task-sync)"
    out.op("recurrence", rm_id, f"MD={local} · CF7={remote}{flag}")


def cmd_list(cfg, args):
    rows = []
    for ent, proj, _p in cfg.iter_projects(entity=args.entity):
        tasks_dir = cfg.path("tasks_dir", entity=ent, project=proj)
        if not tasks_dir.is_dir():
            continue
        for f in sorted(tasks_dir.glob("RM*.md")):
            if f.name.endswith(".log.md"):
                continue
            m = FM_RE.match(f.read_text(encoding="utf-8"))
            if not m:
                continue
            fm = yaml.safe_load(m.group(1)) or {}
            if not fm.get("recurrence"):
                continue
            rows.append((str(fm.get("recurrence")), str(fm.get("updated") or "?"),
                         f"RM{fm.get('redmine_id')}", str(fm.get("status") or "?"),
                         f"{ent}/{proj}", str(fm.get("title") or "")))
    if not rows:
        out.op("recurrents", extra="aucun")
        return
    # Le plus ancien update en tête : c'est celui qui est le plus probablement dû.
    out.op("recurrents", extra=f"{len(rows)} ticket(s)")
    for rec, upd, rm, status, proj, title in sorted(rows, key=lambda r: r[1]):
        print(f"{rm:<8} {rec:<13} maj {upd:<16} {status:<20} {proj:<28} {title[:60]}")


def main():
    ap = argparse.ArgumentParser(
        description="Périodicité d'un ticket récurrent (CF Redmine « Recurrence »).")
    ap.add_argument("--no-commit", action="store_true",
                    help="Pas d'auto-commit git des fichiers PM modifiés")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_set = sub.add_parser("set", help="Pose la périodicité")
    p_set.add_argument("rm_id", type=int)
    p_set.add_argument("recurrence", choices=["quotidienne", "hebdomadaire",
                                              "mensuelle", "annuelle"])

    p_clear = sub.add_parser("clear", help="Retire la périodicité (ticket non récurrent)")
    p_clear.add_argument("rm_id", type=int)

    p_show = sub.add_parser("show", help="Affiche la périodicité (MD + Redmine)")
    p_show.add_argument("rm_id", type=int)

    p_list = sub.add_parser("list", help="Liste les tickets récurrents")
    p_list.add_argument("--entity", help="Limiter à un client / entité")

    args = ap.parse_args()
    cfg = PMConfig.load()
    if args.cmd == "set":
        cmd_set(cfg, args, args.recurrence)
    elif args.cmd == "clear":
        cmd_set(cfg, args, None)
    elif args.cmd == "show":
        cmd_show(cfg, args)
    elif args.cmd == "list":
        cmd_list(cfg, args)


if __name__ == "__main__":
    main()
