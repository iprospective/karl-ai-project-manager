#!/usr/bin/env python3
"""pm-tags-backfill — reprise de l'existant des étiquettes : frontmatter `tags` → CF Redmine (RM2828).

Le socle (RM2829) pousse les étiquettes au CF **à l'écriture** : un ticket tagué avant
lui, ou tagué à la main dans le `.md`, n'est jamais monté. Mesure du 2026-09-20 :
**909 fiches portent des étiquettes, 40 tickets seulement en portent côté Redmine**. La
promesse du chantier — « visibles côté Redmine ET côté PM, sans double saisie » — n'est
donc pas tenue pour l'existant, et aucun outil ne la rattrapait.

RÈGLE — **additive, jamais destructive** (même principe que `pm_tags.push_plan`, RM2840) :

    valeur connue en local, absente du CF   → poussée
    valeur présente au CF, absente en local → RAPATRIÉE au frontmatter (parité)
    valeur hors vocabulaire                 → laissée en local, comptée, jamais poussée
    rien à changer                          → rien

Une étiquette n'est **jamais retirée** du CF par cette reprise : « absente du frontmatter »
ne veut pas dire « retirée » — c'est exactement l'erreur que RM2840 a corrigée.

Trois raisons distinctes de ne pas monter, comptées séparément parce qu'elles appellent
trois gestes différents : mot-clé purement LOCAL (assumé), ALIAS d'une valeur du
vocabulaire (à normaliser, `pm-task-tag --set`), valeur décidée mais pas encore CRÉÉE
dans Redmine (`pm-tags-audit`).

Sûretés : dry-run par défaut ; dump JSONL avant écriture (leçon RM2409) ; commit par dépôt.

Usage :
    pm-tags-backfill.py                 # rejeu à blanc (défaut)
    pm-tags-backfill.py -v              # + le détail ticket par ticket
    pm-tags-backfill.py --rm-id 2816    # un seul ticket
    pm-tags-backfill.py --go            # exécute
"""
import argparse
import collections
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pm_think import is_task_sheet   # noqa: E402
from pm_paths import PMConfig        # noqa: E402
import pm_git                        # noqa: E402
import pm_tags                       # noqa: E402

try:
    import yaml
except ImportError:
    sys.exit("PyYAML requis : pip install PyYAML")

FRONTMATTER_RE = re.compile(r"^(---\s*\n)(.*?)(\n---\s*\n)(.*)$", re.DOTALL)


def plan_tags(local, distants):
    """Ce que la reprise fait d'un ticket. Fonction PURE.

    `local` = frontmatter `tags` ; `distants` = valeurs du CF (None = lecture impossible).
    Rend {cf, frontmatter, a_pousser, a_rapatrier, locales} — `cf`/`frontmatter` sont les
    listes VOULUES, égales à l'existant quand il n'y a rien à faire.
    """
    loc = pm_tags.clean(local or [])
    connues, locales = pm_tags.split_known(loc)
    # Une valeur du vocabulaire PAS ENCORE créée dans Redmine n'a pas d'id : `cf_payload`
    # l'écarterait, et l'annoncer « poussée » serait faux. Elle reste locale et comptée.
    attente = set(pm_tags.pending_values())
    locales = locales + [t for t in connues if t in attente]
    connues = [t for t in connues if t not in attente]
    if distants is None:
        return {"cf": None, "frontmatter": loc, "a_pousser": [], "a_rapatrier": [],
                "locales": locales}
    dist = pm_tags.clean(distants)
    cf = sorted(set(dist) | set(connues))           # union : on n'enlève jamais
    fm = sorted(set(loc) | set(dist))               # ce que l'UI a ajouté redescend
    return {"cf": cf, "frontmatter": fm,
            "a_pousser": sorted(set(connues) - set(dist)),
            "a_rapatrier": sorted(set(dist) - set(loc)),
            "locales": locales}


def load_issues(cfg, rm_id):
    """{id: issue} — une liste paginée plutôt qu'un GET par ticket (~1500 appels sinon)."""
    import redmine_utils
    if rm_id:
        return {rm_id: redmine_utils.fetch_issue(rm_id) or {}}
    creds = redmine_utils.redmine_creds()
    base, key = creds[0].rstrip("/"), creds[1]
    issues, off, total = {}, 0, None
    while total is None or off < total:
        for attempt in range(3):
            try:
                st, d = redmine_utils.http_json(
                    "GET", f"{base}/issues.json?status_id=*&limit=100&offset={off}",
                    key, basic=creds.basic)
                if st != 200:
                    raise RuntimeError(f"HTTP {st}")
                break
            except Exception as e:  # noqa: BLE001
                if attempt == 2:
                    sys.exit(f"ERREUR : lecture Redmine impossible à l'offset {off} "
                             f"({e}). Rien n'a été écrit.")
        total = d.get("total_count", 0)
        for i in d.get("issues", []):
            issues[i["id"]] = i
        off += 100
    return issues


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rm-id", type=int, help="Limiter à un ticket")
    ap.add_argument("--backup", default=None,
                    help="dump JSONL d'avant écriture (défaut : var/tags-backfill-<ts>.jsonl)")
    ap.add_argument("--go", action="store_true", help="Exécute (défaut : dry-run)")
    ap.add_argument("--no-commit", action="store_true", help="Pas d'auto-commit git")
    ap.add_argument("-v", "--verbose", action="store_true", help="Détail ticket par ticket")
    args = ap.parse_args()

    cfg = PMConfig.load()
    if pm_tags.cf_id() is None:
        sys.exit(f"ERREUR : CF « {pm_tags.CF_NAME} » non configuré ({pm_tags.ENV_VAR} / "
                 "redmine.reference.yml) — rien n'a été lu. "
                 "Marche à suivre : knowledge/redmine/etiquettes.md")
    if not pm_tags.known_values():
        sys.exit(f"ERREUR : registre d'étiquettes vide ou introuvable ({pm_tags.REGISTRY}) — "
                 "sans vocabulaire, impossible de savoir ce qui est poussable.")

    if args.rm_id:
        p = cfg.find_task(args.rm_id)
        if not p:
            sys.exit(f"ERREUR : aucun fichier RM{args.rm_id}_*.md")
        paths = [p]
    else:
        paths = []
        for ent, proj, _ in cfg.iter_projects():
            d = cfg.path("tasks_dir", entity=ent, project=proj)
            if d.is_dir():
                paths += [f for f in sorted(d.glob("RM*.md")) if is_task_sheet(f)]
    issues = load_issues(cfg, args.rm_id)
    print(f"({len(paths)} fiche(s) · {len(issues)} ticket(s) Redmine chargés)")

    alias = pm_tags.load_aliases()
    attente = set(pm_tags.pending_values())
    stats = collections.Counter()
    todo, locales = [], collections.Counter()
    for path in paths:
        try:
            m = FRONTMATTER_RE.match(path.read_text(encoding="utf-8"))
            fm = yaml.safe_load(m.group(2)) or {}
        except Exception:  # noqa: BLE001 — fiche illisible : on la saute
            continue
        rm_id = fm.get("redmine_id")
        if not isinstance(rm_id, int) or rm_id not in issues:
            continue
        tags = fm.get("tags") or []
        if not tags:
            stats["sans_etiquette"] += 1
            continue
        plan = plan_tags(tags, pm_tags.from_issue(issues[rm_id]))
        for t in plan["locales"]:
            locales[t] += 1
        if plan["a_pousser"] or plan["a_rapatrier"]:
            todo.append((rm_id, path, fm, plan))
            stats["a_pousser"] += bool(plan["a_pousser"])
            stats["a_rapatrier"] += bool(plan["a_rapatrier"])
        elif plan["cf"]:
            stats["deja_conforme"] += 1
        else:
            # Aucune étiquette poussable : que des mots-clés locaux. Le compter avec les
            # « conformes » ferait croire que la parité est faite là où il n'y a rien à faire.
            stats["rien_de_poussable"] += 1

    print(f"  fiches sans étiquette : {stats['sans_etiquette']} · déjà conformes : {stats['deja_conforme']}"
          f" · sans étiquette poussable (que du local) : {stats['rien_de_poussable']}")
    print(f"  à POUSSER (PM → Redmine) : {stats['a_pousser']}"
          f"   · à RAPATRIER (Redmine → PM) : {stats['a_rapatrier']}")
    if locales:
        al = [(t, n) for t, n in locales.items() if t in alias]
        att = [(t, n) for t, n in locales.items() if t in attente]
        loc = [(t, n) for t, n in locales.items() if t not in alias and t not in attente]
        print(f"\n  étiquettes NON poussables : {sum(locales.values())} occurrence(s), "
              f"{len(locales)} valeur(s) — trois cas, trois gestes :")
        if att:
            print(f"    ⏳ au vocabulaire, pas encore créées dans Redmine ({len(att)}) : "
                  + ", ".join(t for t, _ in sorted(att)[:12]) + " → pm-tags-audit")
        if al:
            print(f"    ↯ alias d'une valeur du vocabulaire ({len(al)}) : "
                  + ", ".join(f"{t}→{alias[t]}" for t, _ in sorted(al)[:8])
                  + " → pm-task-tag <id> --set …")
        if loc:
            top = ", ".join(f"{t} ({n})" for t, n in sorted(loc, key=lambda x: -x[1])[:12])
            print(f"    ⓘ mots-clés locaux, assumés ({len(loc)} valeurs) : {top}")
    if args.verbose:
        print()
        for rm_id, _, _, plan in todo:
            bits = []
            if plan["a_pousser"]:
                bits.append("↑ " + ", ".join(plan["a_pousser"]))
            if plan["a_rapatrier"]:
                bits.append("↓ " + ", ".join(plan["a_rapatrier"]))
            print(f"  RM{rm_id:<5} " + " · ".join(bits))
    if not todo:
        print("\n(rien à faire)")
        return 0
    if not args.go:
        print(f"\n(dry-run : {len(todo)} ticket(s) — relancer avec --go pour exécuter)")
        return 0

    # ── Dump AVANT écriture (leçon RM2409) ──────────────────────────────────────
    dump = Path(args.backup) if args.backup else (
        cfg.state_dir / f"tags-backfill-{datetime.now():%Y%m%d-%H%M%S}.jsonl")
    dump.parent.mkdir(parents=True, exist_ok=True)
    with dump.open("a", encoding="utf-8") as fh:
        for rm_id, path, fm, plan in todo:
            fh.write(json.dumps({
                "ts": datetime.now().isoformat(timespec="seconds"), "rm_id": rm_id,
                "path": str(path), "tags_avant": list(fm.get("tags") or []),
                "cf_avant": pm_tags.from_issue(issues[rm_id]),
                "cf_apres": plan["cf"], "frontmatter_apres": plan["frontmatter"],
            }, ensure_ascii=False) + "\n")
    print(f"  ↳ dump avant écriture : {dump} ({len(todo)} entrée(s))")

    import importlib.util
    _spec = importlib.util.spec_from_file_location(
        "_tag", Path(__file__).resolve().parent / "pm-task-tag.py")
    _TAG = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_TAG)          # push_cf : le MÊME PUT que le geste unitaire

    touched, echecs = [], 0
    for rm_id, path, fm, plan in todo:
        if plan["a_pousser"]:
            ok, why = _TAG.push_cf(rm_id, plan["cf"])
            if not ok:
                echecs += 1
                print(f"  ✗ RM{rm_id} : {why}")
                continue
        if plan["frontmatter"] != pm_tags.clean(fm.get("tags") or []):
            m = FRONTMATTER_RE.match(path.read_text(encoding="utf-8"))
            f2 = yaml.safe_load(m.group(2)) or {}
            f2["tags"] = plan["frontmatter"]
            f2["updated"] = datetime.now().strftime("%Y-%m-%dT%H:%M")
            new_fm = yaml.safe_dump(f2, allow_unicode=True, sort_keys=False,
                                    default_flow_style=False)
            path.write_text(f"{m.group(1)}{new_fm.rstrip()}{m.group(3)}{m.group(4)}",
                            encoding="utf-8")
            touched.append(path)
        print(f"  ✓ RM{rm_id} "
              + (("↑ " + ", ".join(plan["a_pousser"])) if plan["a_pousser"] else "")
              + ((" ↓ " + ", ".join(plan["a_rapatrier"])) if plan["a_rapatrier"] else ""))
    if echecs:
        print(f"\n⚠ {echecs} PUT en échec — relancer : ce qui est déjà poussé sort en « déjà conforme »")

    # Commit PAR DÉPÔT (les fiches sont réparties sur un dépôt de données par projet ;
    # `autocommit` déduit le dépôt du PREMIER chemin et ignorerait les autres).
    if touched and not args.no_commit:
        by_repo = {}
        for f in sorted(set(touched)):
            r = subprocess.run(["git", "-C", str(Path(f).parent), "rev-parse", "--show-toplevel"],
                               capture_output=True, text=True)
            root = r.stdout.strip()
            if not root:
                print(f"  ⚠ {f} hors dépôt git — à committer à la main", file=sys.stderr)
                continue
            by_repo.setdefault(root, []).append(f)
        for root, files in by_repo.items():
            sha = pm_git.autocommit(
                files, f"pm(tags): reprise de {len(files)} fiche(s) — parité frontmatter↔CF (RM2828)")
            print(f"  ✓ commit {root} ({len(files)} fiche(s)){' ' + sha if sha else ''}")
    return 1 if echecs else 0


if __name__ == "__main__":
    sys.exit(main())
