#!/usr/bin/env python3
"""pm-task-cf-resync — répare un miroir frontmatter ↔ CF Redmine qui a divergé (RM3366).

Les quatre champs à miroir (critères d'acceptation, protocole de test, proposition
d'implémentation, actions au déploiement) sont écrits en deux temps : le
frontmatter d'abord, le CF Redmine ensuite. Un script interrompu entre les deux —
un `timeout` de shell, un Ctrl-C, un cron tué pendant que l'API traîne — laisse le
miroir en avance sur le champ. Personne n'est prévenu, et l'écart ne se voit qu'au
prochain garde-fou de statut, sous une forme trompeuse : « aucun critère coché »
sur un ticket dont tout est fait.

Ce script fait les deux gestes qui manquaient : DIRE où ça diverge, et REMETTRE
d'accord. Le miroir local fait foi (c'est là qu'on vient d'écrire).

Usage :
    pm-task-cf-resync.py 3330                 # répare les champs divergents
    pm-task-cf-resync.py 3330 --check         # dit seulement ce qui diverge
    pm-task-cf-resync.py --project pisceen/dolibarr --check    # tout un projet
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pm_cf_mirror
import pm_paths
import redmine_utils

try:
    import yaml
except ImportError:
    sys.exit("PyYAML requis (apt install python3-yaml).")

# Les quatre miroirs, dans l'ordre où on les rencontre sur une fiche.
MIRRORS = (
    ("acceptance", "REDMINE_CF_ACCEPTANCE_ID", "Critères d'acceptation"),
    ("test_protocol", "REDMINE_CF_TEST_PROTOCOL_ID", "Protocole de test"),
    ("implementation", "REDMINE_CF_IMPLEMENTATION_ID", "Proposition d'implémentation"),
    ("deploy_actions", "REDMINE_CF_DEPLOY_ACTIONS_ID", "Actions au déploiement"),
)

CHECKED_RE = re.compile(r"^\s*[-*]\s*\[[xX]\]", re.M)
UNCHECKED_RE = re.compile(r"^\s*[-*]\s*\[ \]", re.M)


def ratio(text):
    """Résumé lisible d'un texte à cases : « 5/9 coché(s) », ou sa longueur."""
    text = text or ""
    checked = len(CHECKED_RE.findall(text))
    unchecked = len(UNCHECKED_RE.findall(text))
    if checked + unchecked:
        return f"{checked}/{checked + unchecked} coché(s)"

    return f"{len(text)} caractère(s)" if text else "vide"


def local_value(fm, key):
    """Valeur du miroir local : texte, ou liste sérialisée pour deploy_actions."""
    raw = (fm or {}).get(key)
    if isinstance(raw, list):
        return pm_cf_mirror.list_to_text(raw) if hasattr(pm_cf_mirror, "list_to_text") else "\n".join(map(str, raw))

    return pm_cf_mirror.normalize_text(raw)


def task_files(cfg, rm_id=None, project=None):
    """Fichiers de tâche à examiner.

    Le filtre `--project` prend une référence EXACTE « client/projet » : plusieurs
    clients ont un projet de même nom (dolibarr chez pisceen ET chez calicote), et
    un filtre sur le seul nom de projet examinerait les tickets du voisin.
    """
    root = Path(cfg.projects_root)
    fragment = None
    if project:
        if "/" not in project:
            sys.exit("--project attend « client/projet » (ex. pisceen/dolibarr) : "
                     "un nom de projet seul est ambigu, plusieurs clients le partagent.")
        client, proj = project.split("/", 1)
        fragment = f"/clients/{client}/projects/{proj}/tasks/"
    found = []
    for path in sorted(root.glob("clients/*/projects/*/tasks/RM*.md")):
        if path.name.endswith(".log.md") or path.name.endswith(".think.md"):
            continue
        if rm_id and not path.name.startswith(f"RM{rm_id}_"):
            continue
        if fragment and fragment not in str(path):
            continue
        found.append(path)

    return found


def cf_offered(rm_id, env_var, cf_name):
    """Le champ est-il PROPOSÉ sur ce ticket (projet/tracker) ?

    Un champ non activé pour le projet ne peut pas être écrit : le PUT répond OK
    et la valeur est ignorée. Le dire évite de chercher une panne réseau là où il
    faut cocher une case dans l'administration de Redmine.
    """
    cid = pm_cf_mirror.resolve_cf_id(env_var, cf_name)
    if cid is None:
        return None
    try:
        issue = redmine_utils.fetch_issue(rm_id)
    except Exception:  # noqa: BLE001 — diagnostic d'appoint
        return None
    if not issue:
        return None

    return any(cf.get("id") == cid for cf in issue.get("custom_fields", []))


def examine(path, do_fix):
    """Compare les quatre miroirs d'une tâche à leurs CF, et répare au besoin."""
    raw = path.read_text(encoding="utf-8")
    m = re.match(r"^(---\n)(.*?)(\n---\n)", raw, re.S)
    if not m:
        return []
    fm = yaml.safe_load(m.group(2)) or {}
    rm_id = fm.get("redmine_id")
    if not rm_id:
        return []

    results = []
    for key, env_var, cf_name in MIRRORS:
        local = local_value(fm, key)
        if not local:
            continue
        remote = pm_cf_mirror.normalize_text(
            pm_cf_mirror.pull_text_cf(rm_id, env_var=env_var, cf_name=cf_name, verbose=False))
        if local == remote:
            continue

        line = (f"RM{rm_id} · {cf_name} : miroir {ratio(local)} ≠ champ {ratio(remote)}")
        if not do_fix:
            results.append((rm_id, cf_name, line, None))
            continue

        if cf_offered(rm_id, env_var, cf_name) is False:
            results.append((rm_id, cf_name,
                            line + " — champ NON ACTIVÉ sur ce projet dans Redmine", "config"))
            continue

        pushed = pm_cf_mirror.push_text_cf(rm_id, local, env_var=env_var, cf_name=cf_name)
        results.append((rm_id, cf_name, line, pushed))

    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("rm_id", nargs="?", type=int, help="ticket à vérifier (défaut : selon --project)")
    parser.add_argument("--project", help="limiter à un projet (ex. pisceen/dolibarr)")
    parser.add_argument("--check", action="store_true", help="ne rien écrire : dire seulement ce qui diverge")
    args = parser.parse_args()

    if not args.rm_id and not args.project:
        parser.error("préciser un ticket, ou --project pour balayer un projet")

    cfg = pm_paths.PMConfig.load()
    paths = task_files(cfg, rm_id=args.rm_id, project=args.project)
    if not paths:
        sys.exit("Aucune tâche trouvée pour ces critères.")

    divergences = []
    repaired = 0
    failed = 0
    for path in paths:
        for rm_id, cf_name, line, pushed in examine(path, do_fix=not args.check):
            divergences.append(line)
            if pushed is True:
                repaired += 1
                print(f"✓ {line} → champ remis d'accord")
            elif pushed == "config":
                failed += 1
                print(f"✗ {line}\n     → à activer dans Redmine (Administration › Champs "
                      f"personnalisés › projets concernés) ; rien à réparer ici")
            elif pushed is False:
                failed += 1
                print(f"✗ {line} → réparation impossible (API en échec — réessayer)")
            else:
                print(f"≠ {line}")

    if not divergences:
        print(f"Tout est cohérent ({len(paths)} tâche(s) examinée(s)).")
        return 0

    if args.check:
        print(f"\n{len(divergences)} divergence(s) — relancer sans --check pour réparer.")
        return 1

    print(f"\n{repaired} réparée(s), {failed} en échec.")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
