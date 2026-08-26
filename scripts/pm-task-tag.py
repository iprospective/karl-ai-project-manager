#!/usr/bin/env python3
"""pm-task-tag — étiquettes d'un ticket (RM2829, chantier RM2828).

Le domaine d'un ticket — `front`, `bo`, `bdd`, `refacto`, `livraison`,
`tunnel-de-commande`… — vit au frontmatter (`tags:`) ET dans le custom field
Redmine « Étiquettes » (liste, valeurs multiples, tous projets). Les deux doivent
dire la même chose : c'est le principe de parité (NORMS `redmine-sync`).

    pm-task-tag.py 2816                       # lit les étiquettes
    pm-task-tag.py 2816 --add front,refacto   # ajoute
    pm-task-tag.py 2816 --rm refacto          # retire
    pm-task-tag.py 2816 --set front           # remplace tout (vide = tout retirer)

⚠ Le CF Redmine se crée à la main (l'API ne crée pas de custom fields). Tant
qu'il n'existe pas, le frontmatter est tenu à jour et le push est annoncé comme
non fait — jamais en silence. Marche à suivre : knowledge/redmine/etiquettes.md
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
import pm_git
import pm_scope
import pm_tags

try:
    import yaml
except ImportError:
    sys.exit("PyYAML requis : pip install PyYAML")

FRONTMATTER_RE = re.compile(r"^(---\s*\n)(.*?)(\n---\s*\n)(.*)$", re.DOTALL)


def push_cf(rm_id, tags):
    """PUT du CF Redmine. (poussé?, raison) — un échec n'est jamais fatal : le
    frontmatter reste la source de travail, et le silence serait pire."""
    payload = pm_tags.cf_payload(tags)
    if payload is None:
        return False, (f"CF « {pm_tags.CF_NAME} » non configuré ({pm_tags.ENV_VAR} / "
                       "redmine.reference.yml) — voir knowledge/redmine/etiquettes.md")
    base = (os.environ.get("REDMINE_URL") or "").rstrip("/")
    key = os.environ.get("REDMINE_API_KEY") or os.environ.get("REDMINE_USER_MAIN_API_KEY")
    if not base or not key:
        return False, "REDMINE_URL / clé API absents"
    body = json.dumps({"issue": {"custom_fields": [payload]}}).encode()
    req = urllib.request.Request(f"{base}/issues/{rm_id}.json", data=body, method="PUT",
                                 headers={"X-Redmine-API-Key": key,
                                          "Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=15)
        return True, ""
    except urllib.error.HTTPError as e:
        return False, f"PUT CF {payload['id']} → HTTP {e.code}"
    except OSError as e:
        return False, f"PUT CF injoignable ({e.__class__.__name__})"


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("rm_id", type=int)
    ap.add_argument("--add", default="", help="Étiquettes à ajouter (csv)")
    ap.add_argument("--rm", dest="remove", default="", help="Étiquettes à retirer (csv)")
    ap.add_argument("--set", dest="set_", default=None,
                    help="Remplace TOUTES les étiquettes (csv ; vide = tout retirer)")
    ap.add_argument("--no-commit", action="store_true", help="Pas d'auto-commit git")
    ap.add_argument("--cross-project", action="store_true",
                    help="Autorise consciemment une écriture sur un ticket d'un AUTRE projet (garde RM2274).")
    ap.add_argument("--free", action="store_true",
                    help="Accepte une étiquette hors vocabulaire : mot-clé LOCAL, jamais poussé au CF")
    ap.add_argument("--porcelain", action="store_true", help="N'imprime que les étiquettes, une par ligne")
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
    current = pm_tags.clean(fm.get("tags") or [])

    if args.set_ is None and not args.add and not args.remove:
        for t in current:
            print(t)
        if not current and not args.porcelain:
            print(f"(aucune étiquette sur RM{args.rm_id} — "
                  f"pm-task-tag.py {args.rm_id} --add front)")
        return

    pm_scope.assert_task_scope(args.rm_id, md_path, args.cross_project, "pm-task-tag")

    # RM2836 — garde à l'écriture. Trois cas, dans cet ordre :
    #   alias      → on écrit la valeur CANONIQUE, et on le dit (une étiquette
    #                réécrite en silence donne l'impression d'un geste ignoré) ;
    #   vocabulaire→ on écrit ;
    #   inconnu    → on REFUSE, sauf --free. Sans ce refus, le vocabulaire
    #                contrôlé se remplirait de variantes en quelques semaines —
    #                c'est exactement comme ça qu'on en est arrivé à 747 mots-clés.
    entrants = pm_tags.parse_csv(args.add) + (
        [] if args.set_ is None else pm_tags.parse_csv(args.set_))
    vocab, convertis, inconnus = set(pm_tags.vocabulary()), [], []
    reecrit = {}
    for t in entrants:
        canon, origine = pm_tags.canonical(t)
        if origine:
            convertis.append((origine, canon))
            reecrit[t] = canon
        elif canon not in vocab:
            inconnus.append(canon)
    if inconnus and not args.free:
        print(f"✗ hors vocabulaire : {', '.join(sorted(set(inconnus)))}", file=sys.stderr)
        print(f"  valeurs acceptées : {', '.join(pm_tags.vocabulary()) or '—'}", file=sys.stderr)
        print(f"  · pour un mot-clé purement LOCAL (jamais poussé au CF) : --free", file=sys.stderr)
        print(f"  · pour l'ajouter au vocabulaire : UI admin Redmine, puis "
              f"{pm_tags.REGISTRY} (voir pm-tags-audit.py)", file=sys.stderr)
        sys.exit(2)

    canon_csv = lambda raw: ",".join(  # noqa: E731
        reecrit.get(t, t) for t in pm_tags.parse_csv(raw))
    new = pm_tags.apply_change(current,
                               add=pm_tags.parse_csv(canon_csv(args.add)),
                               remove=pm_tags.parse_csv(args.remove),
                               replace=None if args.set_ is None
                               else pm_tags.parse_csv(canon_csv(args.set_)))
    for origine, canon in convertis:
        print(f"  ↳ « {origine} » est un alias : écrit « {canon} »")
    if new == current:
        print(f"= RM{args.rm_id} étiquettes inchangées : {', '.join(new) or '(aucune)'}")
        return

    fm["tags"] = new
    fm["updated"] = datetime.now().strftime("%Y-%m-%dT%H:%M")
    new_fm = yaml.safe_dump(fm, allow_unicode=True, sort_keys=False, default_flow_style=False)
    md_path.write_text(f"{m.group(1)}{new_fm.rstrip()}{m.group(3)}{m.group(4)}", encoding="utf-8")

    ok, why = push_cf(args.rm_id, new)
    # RM2829 : le CF n'accepte QUE les valeurs de son registre. Celles qui n'y
    # sont pas restent au frontmatter et ne montent pas — le taire donnerait un
    # « ✓ frontmatter + Redmine » qui ment sur la moitié des étiquettes.
    connues, inconnues = pm_tags.split_known(new)
    print(f"✓ RM{args.rm_id} étiquettes : {', '.join(new) or '(aucune)'}"
          + (" (frontmatter + Redmine)" if ok else " (frontmatter)"))
    if ok and inconnues:
        # Deux raisons très différentes de ne pas monter : la valeur est décidée
        # mais pas encore créée côté Redmine, ou c'est un mot-clé local assumé.
        attente = [t for t in inconnues if t in set(pm_tags.pending_values())]
        locaux = [t for t in inconnues if t not in set(pm_tags.pending_values())]
        if attente:
            print(f"  ⏳ au vocabulaire mais pas encore créée(s) dans Redmine : "
                  f"{', '.join(attente)} — non poussée(s) (voir pm-tags-audit.py)")
        # Un alias DÉJÀ présent au frontmatter n'est pas réécrit en silence :
        # l'historique appartient au ticket. Mais le dire évite de le prendre
        # pour un mot-clé local alors qu'une valeur du vocabulaire le couvre.
        al = pm_tags.load_aliases()
        residus = [(t, al[t]) for t in locaux if t in al]
        vrais_locaux = [t for t in locaux if t not in al]
        if residus:
            print("  ↯ alias déjà présent(s) : "
                  + ", ".join(f"« {t} » → « {c} »" for t, c in residus)
                  + f" — `pm-task-tag {args.rm_id} --set …` pour normaliser")
        if vrais_locaux:
            print(f"  ⓘ mot(s)-clé(s) local(aux), non poussé(s) au CF "
                  f"« {pm_tags.CF_NAME} » : {', '.join(vrais_locaux)}")
    if not ok:
        print(f"⚠ CF Redmine non poussé : {why}", file=sys.stderr)

    log_path = md_path.parent / md_path.name.replace(".md", ".log.md")
    ts = datetime.now().strftime("%Y-%m-%dT%H:%M")
    with log_path.open("a", encoding="utf-8") as f:
        f.write(f"\n## {ts} — Étiquettes (pm-task-tag)\n"
                f"Tokens : 0 | Durée : 0 min\n\n"
                f"`{', '.join(current) or '(aucune)'}` → `{', '.join(new) or '(aucune)'}`"
                f"{'' if ok else ' — CF Redmine non poussé : ' + why}\n")
    if not args.no_commit:
        pm_git.autocommit([md_path, log_path],
                          f"pm(tags): RM{args.rm_id} {', '.join(new) or '(aucune)'}")


if __name__ == "__main__":
    main()
