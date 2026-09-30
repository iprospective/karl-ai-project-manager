#!/usr/bin/env python3
"""pm-task-type-update — requalifie un ticket : type NORMS + tracker Redmine (RM3368).

Le `type` d'un ticket n'est pas décoratif : il décide du **tracker** Redmine,
donc des champs personnalisés que le ticket peut porter. Un ticket ouvert en
Assistance qui se met à livrer du code n'a nulle part où mettre sa branche, sa
MR, sa proposition d'implémentation — l'API accepte l'écriture et la jette.
C'est arrivé à RM3224 : 2 459 caractères d'étude invisibles neuf jours.

La norme (module `methodes-travail` § « Assistance → répondre, pas livrer »)
ouvre deux issues, et cet outil sert la première :

    pm-task-type-update.py 3224 --type feature      # requalifier
    pm-task-add.py --parent 3224 …                  # ou porter le dev ailleurs

Ce qui est fait, dans cet ordre : frontmatter local (`type`, `updated`), tracker
Redmine, CF « Task type » quand la taxonomie fine s'applique, note sur le
ticket, entrée au journal, commit PM.

**Le garde-fou de sortie** : une requalification peut RÉTRÉCIR la liste des
champs disponibles (Tâche → Assistance). L'outil dit alors ce qui sera perdu, et
refuse sans `--force`. Requalifier ne doit pas devenir la nouvelle façon de
perdre du contenu en silence.

    pm-task-type-update.py 3224                     # lit le type et le tracker
    pm-task-type-update.py 3224 --type feature --reason "livre du code"
    pm-task-type-update.py 3224 --type assistance --force   # accepte la perte
"""
import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from pm_paths import PMConfig                     # noqa: E402
from pm_task_md import TYPE_LABELS, TYPE_TO_TRACKER   # noqa: E402
import pm_cf_scope                                # noqa: E402
import pm_git                                     # noqa: E402
import pm_scope                                   # noqa: E402
import redmine_utils                              # noqa: E402

try:
    import yaml
except ImportError:
    sys.exit("PyYAML requis : pip install PyYAML")

FRONTMATTER_RE = re.compile(r"^(---\s*\n)(.*?)(\n---\s*\n)(.*)$", re.DOTALL)
TRACKER_NAMES = {1: "Anomalie", 2: "Evolution", 3: "Assistance", 4: "Tâche"}


def perdus_par_requalification(issue, tracker_cible):
    """Les champs REMPLIS que le tracker cible ne porte pas.

    C'est la question qui compte avant de requalifier : ce qui est écrit va-t-il
    survivre ? Redmine ne prévient pas — il enlève le champ de la fiche et la
    valeur cesse d'être visible.
    """
    scope = pm_cf_scope.load_scope()
    cible = TRACKER_NAMES.get(tracker_cible, "")
    out = []
    for cf in (issue or {}).get("custom_fields") or []:
        valeur = cf.get("value")
        rempli = bool(valeur) if not isinstance(valeur, list) else any(valeur)
        if not rempli:
            continue
        if not pm_cf_scope.field_allowed(scope, cf.get("id"), cible):
            texte = valeur if isinstance(valeur, str) else str(valeur)
            out.append({"id": cf.get("id"), "name": cf.get("name") or f"CF {cf.get('id')}",
                        "chars": len(texte)})
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("rm_id", type=int)
    ap.add_argument("--type", dest="new_type", choices=list(TYPE_TO_TRACKER),
                    help="Nouveau type NORMS (décide le tracker Redmine)")
    ap.add_argument("--reason", default="", help="Motif de la requalification (note Redmine)")
    ap.add_argument("--force", action="store_true",
                    help="Accepte de perdre les champs que le tracker cible ne porte pas")
    ap.add_argument("--no-commit", action="store_true", help="Pas d'auto-commit git PM")
    ap.add_argument("--cross-project", action="store_true",
                    help="Autorise une écriture sur un ticket d'un AUTRE projet (garde RM2274)")
    ap.add_argument("--dry-run", action="store_true", help="Montre ce qui serait fait")
    args = ap.parse_args()

    cfg = PMConfig.load()
    md_path = cfg.find_task(args.rm_id)
    if not md_path:
        sys.exit(f"ERREUR : aucun fichier RM{args.rm_id}_*.md")
    content = md_path.read_text(encoding="utf-8")
    m = FRONTMATTER_RE.match(content)
    if not m:
        sys.exit(f"ERREUR : frontmatter illisible dans {md_path.name}")
    fm = yaml.safe_load(m.group(2)) or {}
    actuel = str(fm.get("type") or "")

    try:
        issue = redmine_utils.fetch_issue(args.rm_id)
    except Exception as e:      # noqa: BLE001 — on peut travailler sans, mais on le dit
        issue, tracker_actuel = None, None
        print(f"⚠ ticket Redmine illisible ({e}) — le tracker ne sera pas vérifié.",
              file=sys.stderr)
    else:
        tracker_actuel = ((issue or {}).get("tracker") or {}).get("name")

    if not args.new_type:
        print(f"RM{args.rm_id} : type « {actuel or '?'} »"
              f" ({TYPE_LABELS.get(actuel, '—')})"
              f" · tracker Redmine « {tracker_actuel or '?'} »")
        attendu = TRACKER_NAMES.get(TYPE_TO_TRACKER.get(actuel, 0))
        if tracker_actuel and attendu and tracker_actuel != attendu:
            print(f"  ⚠ désaccord : le type « {actuel} » attend le tracker « {attendu} »")
        print(f"  types : {', '.join(TYPE_TO_TRACKER)}")
        return 0

    if args.new_type == actuel:
        print(f"= RM{args.rm_id} déjà de type « {actuel} » — rien à faire")
        return 0

    pm_scope.assert_task_scope(args.rm_id, md_path, args.cross_project, "pm-task-type-update")

    tracker_cible = TYPE_TO_TRACKER[args.new_type]
    perdus = perdus_par_requalification(issue, tracker_cible) if issue else []
    if perdus and not args.force:
        print(f"✗ requalifier RM{args.rm_id} en « {args.new_type} » "
              f"(tracker « {TRACKER_NAMES.get(tracker_cible, '?')} ») ferait disparaître "
              f"{len(perdus)} champ(s) REMPLI(S) :", file=sys.stderr)
        for p in perdus:
            print(f"    · {p['name']} — {p['chars']} caractère(s)", file=sys.stderr)
        print("  Redmine retire le champ de la fiche sans rien dire : la valeur cesse\n"
              "  d'être visible. Deux options :\n"
              "    · garder le type actuel et porter le reste dans un ticket lié\n"
              f"      (pm-task-add.py --parent {args.rm_id})\n"
              "    · assumer la perte, après avoir recopié ce qui compte : --force",
              file=sys.stderr)
        return 2

    ligne = (f"type « {actuel or '?'} » → « {args.new_type} » · tracker "
             f"« {tracker_actuel or '?'} » → « {TRACKER_NAMES.get(tracker_cible, '?')} »")
    if args.dry_run:
        print(f"(dry-run) RM{args.rm_id} : {ligne}")
        if perdus:
            print(f"(dry-run) et perdrait : "
                  + ", ".join(f"{p['name']} ({p['chars']} c.)" for p in perdus))
        return 0

    # 1. Redmine d'abord : si le tracker refuse, on n'a pas menti au frontmatter.
    note = (f"Requalification : {ligne}."
            + (f"\n\nMotif : {args.reason}" if args.reason else "")
            + "\n\n(pm-task-type-update — NORMS, module methodes-travail)")
    payload = {"issue": {"tracker_id": tracker_cible, "notes": note}}
    cf_id, valeurs = redmine_utils.task_type_cf()
    if cf_id and args.new_type in valeurs and pm_cf_scope.field_allowed(
            pm_cf_scope.load_scope(), cf_id, TRACKER_NAMES.get(tracker_cible, "")):
        payload["issue"]["custom_fields"] = [{"id": cf_id, "value": valeurs[args.new_type]}]
    url, key = redmine_utils.redmine_creds()
    code, body = redmine_utils.http_json("PUT", f"{url}/issues/{args.rm_id}.json", key,
                                         payload, timeout=20)
    if code not in (200, 204):
        sys.exit(f"ERREUR : PUT tracker → HTTP {code} : {str(body.get('_error', ''))[:200]}")

    # 2. Relecture : un PUT accepté n'est pas un PUT appliqué (le piège des droits).
    try:
        relu = ((redmine_utils.fetch_issue(args.rm_id) or {}).get("tracker") or {}).get("name")
    except Exception:           # noqa: BLE001
        relu = None
    if relu and relu != TRACKER_NAMES.get(tracker_cible):
        sys.exit(f"ERREUR : tracker toujours « {relu} » après le PUT — droits « Edit issues » ?")

    # 3. Frontmatter local, une fois Redmine confirmé.
    fm["type"] = args.new_type
    fm["updated"] = datetime.now().strftime("%Y-%m-%dT%H:%M")
    new_fm = yaml.safe_dump(fm, allow_unicode=True, sort_keys=False, default_flow_style=False)
    md_path.write_text(f"{m.group(1)}{new_fm.rstrip()}{m.group(3)}{m.group(4)}",
                       encoding="utf-8")

    log_path = md_path.parent / md_path.name.replace(".md", ".log.md")
    ts = datetime.now().strftime("%Y-%m-%dT%H:%M")
    with log_path.open("a", encoding="utf-8") as f:
        f.write(f"\n## {ts} — Requalification (pm-task-type-update)\n"
                f"Tokens : 0 | Durée : 0 min\n\n{ligne}"
                + (f"\n\nMotif : {args.reason}" if args.reason else "")
                + (f"\n\nChamps perdus (--force) : "
                   + ", ".join(f"{p['name']} ({p['chars']} c.)" for p in perdus)
                   if perdus else "") + "\n")
    if not args.no_commit:
        pm_git.autocommit([md_path, log_path],
                          f"pm(type): RM{args.rm_id} {actuel or '?'} → {args.new_type}")
    print(f"✓ RM{args.rm_id} requalifié : {ligne}")
    if perdus:
        print(f"⚠ {len(perdus)} champ(s) ne sont plus portés par la fiche : "
              + ", ".join(p["name"] for p in perdus), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
