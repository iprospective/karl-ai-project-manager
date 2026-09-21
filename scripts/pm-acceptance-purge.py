#!/usr/bin/env python3
"""pm-acceptance-purge — retire la section « Critères d'acceptation » des descriptions
une fois ses critères repris dans le CF 33 (RM3241).

Après la reprise RM2882/RM3240, les critères vivent dans leur champ dédié (CF 33,
miroir local `acceptance`) **et** restent dans la section de la description Redmine et
du corps du MD. Deux copies divergent : mesure du 2026-09-19, sur 783 tickets en double,
15 avaient déjà divergé — dont RM3173, en MEP, 4/4 coché dans le champ et 0/4 dans la
description. Qui lit la fiche Redmine y voit un ticket non recetté.

RÈGLE — `pm_acceptance.purge_decision`, orientée (on ne perd jamais de matière) :

    CF 33 vide                                    → gardée (c'est la seule copie)
    un item de la section absent du CF            → gardée (on perdrait un critère)
    coché dans la section, pas dans le CF         → gardée (la description est en avance)
    texte hors cases dans la section              → gardée (prose, tableau)
    sinon — CF identique ou EN AVANCE             → retirée

Chaque copie est jugée pour elle-même : la description Redmine contre le CF 33, le corps
du MD contre son miroir `acceptance`. Un miroir local vide alors que le CF est plein est
d'abord REMPLI (jamais l'inverse : on ne remplace pas du contenu par du vide) ; un miroir
qui diffère du CF laisse le corps en place — c'est `cf-mirror-backfill` qui les accorde.

Sûretés :
- **dry-run par défaut** : sans `--go`, aucune écriture (ni API, ni fichier, ni commit) ;
- **dump JSONL avant écriture** (leçon RM2409) : description et corps d'avant, CF lu ;
- **relecture fraîche** de chaque ticket juste avant son PUT, et décision rejouée dessus :
  le chargement en masse peut dater de plusieurs minutes, quelqu'un a pu cocher entre-temps ;
- tickets **fermés exclus** par défaut (`--include-closed` pour les prendre) : l'étude
  RM2882 § 5 le recommandait — une fiche close n'a rien à gagner à bouger.

Usage :
    pm-acceptance-purge.py                    # rejeu à blanc, tickets ouverts
    pm-acceptance-purge.py --rm-id 1587       # un seul ticket
    pm-acceptance-purge.py --include-closed   # fermés compris
    pm-acceptance-purge.py --go               # exécute
"""
import argparse
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pm_think import is_task_sheet  # noqa: E402
from pm_paths import PMConfig        # noqa: E402
import pm_acceptance                 # noqa: E402
import pm_cf_mirror                  # noqa: E402
import pm_git                        # noqa: E402

try:
    import yaml
except ImportError:
    sys.exit("PyYAML requis : pip install PyYAML")

FRONTMATTER_RE = re.compile(r"^(---\s*\n)(.*?)(\n---\s*\n)(.*)$", re.DOTALL)


def fold_plan(issue, fm, body, convert=None):
    """Ce que le repliement écrirait dans le champ, ou (None, motif) s'il ne faut pas replier.

    Fonction PURE. Deux cas sont EXCLUS parce qu'ils demandent un arbitrage et que replier
    les trancherait en silence (RM3285) :
      · divergence croisée — chaque côté porte un critère exclusif (groupe B de la revue) ;
      · coche contradictoire — le même critère coché d'un côté seulement (groupe D).
    """
    cf = pm_acceptance.cf_text_of_issue(issue)
    sec_rm = pm_acceptance.extract_section((issue or {}).get("description") or "") or ""
    sec_md = pm_acceptance.extract_section(body) or ""
    if not (sec_rm.strip() or sec_md.strip()):
        return None, "aucune section à replier"
    md_items = pm_acceptance.parse_items(sec_md)
    rm_items = pm_acceptance.parse_items(sec_rm)
    _, diffs = pm_acceptance.union(md_items, rm_items)
    if any(d["type"] == "only_md" for d in diffs) and any(d["type"] == "only_redmine" for d in diffs):
        return None, "divergence croisée fiche/Redmine — arbitrage humain"
    if any(d["type"] == "check_differs" for d in diffs):
        return None, "coche contradictoire entre la fiche et Redmine — arbitrage humain"
    cf_items = pm_acceptance.parse_items(cf)
    for src in (md_items, rm_items):
        for ok, lab in src:
            en_cf = [c for c in cf_items if pm_acceptance.norm_label(c[1]) == pm_acceptance.norm_label(lab)]
            if ok and en_cf and not en_cf[0][0]:
                return None, "coche présente dans la section, absente du champ — arbitrage humain"
    # La section la plus fournie sert d'ossature (elle porte la structure : sous-titres,
    # prose) ; ce que l'autre côté a en plus est ajouté, jamais perdu.
    base, autre = (sec_rm, sec_md) if len(sec_rm) >= len(sec_md) else (sec_md, sec_rm)
    neuf = pm_acceptance.fold_into_field(cf, base, convert)
    if not neuf:
        return None, "rien de repliable (section vide de contenu)"
    if not pm_acceptance.parse_items(neuf):
        # Section faite de paragraphes : le champ n'y gagnerait aucun critère, et un champ
        # sans case reste « vide » pour tout l'outillage. Ces cas s'écrivent à la main.
        return None, "critères en paragraphes — aucune case à replier, à écrire à la main"
    # Toutes les sections des DEUX côtés : la purge les retire toutes, le champ doit donc
    # les porter toutes. RM2763 est le seul ticket du parc à en avoir deux vraies (relevé
    # par l'audit RM2882) — sans ceci, la seconde était perdue.
    connus = {pm_acceptance.norm_label(l) for _, l in pm_acceptance.parse_items(neuf)}
    autres = [autre] + [t for _, t in pm_acceptance.extract_sections((issue or {}).get("description") or "")] \
        + [t for _, t in pm_acceptance.extract_sections(body)]
    manquants, vus = [], set()
    for texte in autres:
        for ok, lab in pm_acceptance.parse_items(texte):
            k = pm_acceptance.norm_label(lab)
            if k not in connus and k not in vus:
                vus.add(k)
                manquants.append((ok, lab))
    if manquants:
        neuf = neuf + "\n" + pm_acceptance.render_items(manquants)
    if pm_cf_mirror.normalize_text(neuf) == pm_cf_mirror.normalize_text(cf):
        return None, "le champ porte déjà la section (rien à replier)"
    return neuf, ""


def plan_ticket(issue, fm, body):
    """Ce qu'il faut faire d'un ticket. Fonction PURE.

    Rend un dict : `redmine` / `md` ∈ {"rien", "retire", "garde"}, leurs motifs,
    `new_desc` / `new_body` quand on retire, `fill_mirror` (texte du CF à recopier
    dans le frontmatter vide, sinon None).
    """
    cf = pm_acceptance.cf_text_of_issue(issue)
    desc = (issue or {}).get("description") or ""
    rm_action, rm_motifs = pm_acceptance.purge_decision(cf, desc)

    local = pm_cf_mirror.normalize_text((fm or {}).get(pm_acceptance.FM_KEY)) or ""
    fill = None
    if not local and cf:
        local, fill = cf, cf                  # miroir vide, CF plein : on le remplit d'abord
    if local and cf and local != cf:
        md_action, md_motifs = ("garde", ["miroir `acceptance` ≠ CF 33 — "
                                          "à accorder avec cf-mirror-backfill"]) \
            if pm_acceptance.extract_sections(body) else ("rien", [])
    else:
        md_action, md_motifs = pm_acceptance.purge_decision(local, body)
    return {
        "redmine": rm_action, "redmine_motifs": rm_motifs,
        "new_desc": pm_acceptance.strip_sections(desc) if rm_action == "retire" else None,
        "md": md_action, "md_motifs": md_motifs,
        "new_body": pm_acceptance.strip_sections(body) if md_action == "retire" else None,
        "fill_mirror": fill if md_action == "retire" else None,
    }


def load_issues(rm_id):
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


def is_closed(issue, fm):
    st = (issue or {}).get("status") or {}
    if "is_closed" in st:
        return bool(st["is_closed"])
    return (fm or {}).get("status") == "ferme"


def write_md(path, fm_changes, new_body):
    m = FRONTMATTER_RE.match(path.read_text(encoding="utf-8"))
    fm = yaml.safe_load(m.group(2)) or {}
    fm.update(fm_changes)
    fm["updated"] = datetime.now().strftime("%Y-%m-%dT%H:%M")
    new_fm = yaml.safe_dump(fm, allow_unicode=True, sort_keys=False, default_flow_style=False)
    path.write_text(f"{m.group(1)}{new_fm.rstrip()}{m.group(3)}{new_body}", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rm-id", type=int, help="Limiter à un ticket")
    ap.add_argument("--include-closed", action="store_true",
                    help="Traiter aussi les tickets fermés (exclus par défaut)")
    ap.add_argument("--backup", default=None,
                    help="dump JSONL d'avant écriture (défaut : var/acceptance-purge-<ts>.jsonl)")
    ap.add_argument("--fold", action="store_true",
                    help="RM3285 : replier la section GARDÉE dans le champ (texte et sous-titres "
                         "compris, coches fusionnées) puis la retirer. Divergence croisée et "
                         "coche contradictoire restent exclues : elles demandent un arbitrage.")
    ap.add_argument("--convert-bullets", choices=["coche", "decoche"], default=None,
                    help="Avec --fold : convertir en cases les critères écrits en puces simples "
                         "(sections sans aucune case), dans l'état demandé")
    ap.add_argument("--go", action="store_true", help="Exécute (défaut : dry-run)")
    ap.add_argument("--no-commit", action="store_true", help="Pas d'auto-commit git")
    ap.add_argument("-v", "--verbose", action="store_true",
                    help="Liste aussi chaque ticket retiré (pas seulement les gardés)")
    args = ap.parse_args()

    cfg = PMConfig.load()
    if pm_cf_mirror.resolve_cf_id(pm_acceptance.ENV_VAR, pm_acceptance.CF_NAME) is None:
        sys.exit("ERREUR : CF « Critères d'acceptation » non résolu "
                 "(REDMINE_CF_ACCEPTANCE_ID / redmine.reference.yml). Rien n'a été lu.")
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
    issues = load_issues(args.rm_id)
    print(f"({len(paths)} fiche(s) · {len(issues)} ticket(s) Redmine chargés)")

    stats = {"fermes_ignores": 0, "sans_section": 0, "rm_retire": 0, "rm_garde": 0,
             "md_retire": 0, "md_garde": 0, "miroir_rempli": 0, "replie": 0, "fold_refuse": 0}
    gardes, todo = [], []
    for path in paths:
        try:
            m = FRONTMATTER_RE.match(path.read_text(encoding="utf-8"))
            fm = yaml.safe_load(m.group(2)) or {}
        except Exception:  # noqa: BLE001 — fiche illisible : on la saute
            continue
        rm_id = fm.get("redmine_id")
        if not isinstance(rm_id, int) or rm_id not in issues:
            continue
        issue = issues[rm_id]
        if not args.include_closed and is_closed(issue, fm):
            stats["fermes_ignores"] += 1
            continue
        plan = plan_ticket(issue, fm, m.group(4))
        if plan["redmine"] == "rien" and plan["md"] == "rien":
            stats["sans_section"] += 1
            continue
        # RM3285 : la section gardée peut devenir la valeur du champ — alors plus rien ne
        # s'oppose à son retrait, et c'est le MÊME chemin de retrait qui l'exécute.
        fold_val = None
        if args.fold and "garde" in (plan["redmine"], plan["md"]):
            convert = None if args.convert_bullets is None else (args.convert_bullets == "coche")
            fold_val, motif = fold_plan(issue, fm, m.group(4), convert)
            if fold_val:
                simule = dict(issue or {})
                simule["custom_fields"] = [{"id": pm_cf_mirror.resolve_cf_id(
                    pm_acceptance.ENV_VAR, pm_acceptance.CF_NAME), "value": fold_val}]
                apres = plan_ticket(simule, dict(fm, **{pm_acceptance.FM_KEY: fold_val}), m.group(4))
                if "garde" in (apres["redmine"], apres["md"]):
                    fold_val, motif = None, ("replié, la section resterait gardée : "
                                             + "; ".join(apres["redmine_motifs"] + apres["md_motifs"])[:120])
                else:
                    plan = apres
                    stats["replie"] += 1
            if not fold_val:
                stats["fold_refuse"] += 1
                gardes.append((rm_id, [f"non replié : {motif}"]))
                continue
        for side in ("redmine", "md"):
            if plan[side] in ("retire", "garde"):
                stats[f"{'rm' if side == 'redmine' else 'md'}_{plan[side]}"] += 1
        if plan["fill_mirror"]:
            stats["miroir_rempli"] += 1
        motifs = ([f"description : {x}" for x in plan["redmine_motifs"]
                   if plan["redmine"] == "garde"]
                  + [f"MD : {x}" for x in plan["md_motifs"] if plan["md"] == "garde"])
        if motifs:
            gardes.append((rm_id, motifs))
        if "retire" in (plan["redmine"], plan["md"]):
            plan = dict(plan, fold=fold_val)
            todo.append((rm_id, path, issue, fm, m.group(4), plan))

    print(f"  fermés ignorés : {stats['fermes_ignores']}"
          + ("" if args.include_closed else " (--include-closed pour les prendre)")
          + f" · sans section : {stats['sans_section']}")
    print(f"  description Redmine : {stats['rm_retire']} à retirer · {stats['rm_garde']} gardée(s)")
    print(f"  corps du MD         : {stats['md_retire']} à retirer · {stats['md_garde']} gardé(s)"
          f" · miroir local rempli depuis le CF : {stats['miroir_rempli']}")
    if gardes:
        print(f"\n⚠ {len(gardes)} ticket(s) dont une section est GARDÉE — à trancher à la main "
              f"(pm-task-acceptance --set / --append, puis relancer) :")
        for rm_id, motifs in gardes:
            print(f"  RM{rm_id}")
            for x in motifs[:4]:
                print(f"      · {x}")
            if len(motifs) > 4:
                print(f"      · … (+{len(motifs) - 4})")
    if stats["replie"] or stats["fold_refuse"]:
        print(f"  repliées dans le champ : {stats['replie']} · non repliables (arbitrage) : {stats['fold_refuse']}")
    if args.verbose:
        print()
        for rm_id, _, _, _, _, plan in todo:
            cotes = [c for c, k in (("description", "redmine"), ("MD", "md")) if plan[k] == "retire"]
            en_avance = [x for x in plan["redmine_motifs"] + plan["md_motifs"] if "en avance" in x]
            print(f"  {'REPLIE' if plan.get('fold') else 'RETIRE'} RM{rm_id:<5} {' + '.join(cotes)}"
                  + (f"  ({en_avance[0]})" if en_avance else ""))
            if plan.get("fold"):
                for ln in str(plan["fold"]).split("\n")[:4]:
                    print(f"        │ {ln[:100]}")
    if not todo:
        print("\n(rien à retirer)")
        return 0
    if not args.go:
        print(f"\n(dry-run : {len(todo)} ticket(s) — relancer avec --go pour exécuter)")
        return 0

    # ── Dump AVANT écriture (leçon RM2409) ──────────────────────────────────────
    dump = Path(args.backup) if args.backup else (
        cfg.state_dir / f"acceptance-purge-{datetime.now():%Y%m%d-%H%M%S}.jsonl")
    dump.parent.mkdir(parents=True, exist_ok=True)
    with dump.open("a", encoding="utf-8") as fh:
        for rm_id, path, issue, fm, body, plan in todo:
            fh.write(json.dumps({
                "ts": datetime.now().isoformat(timespec="seconds"), "rm_id": rm_id,
                "path": str(path), "cf_33": pm_acceptance.cf_text_of_issue(issue),
                "acceptance_local": fm.get(pm_acceptance.FM_KEY),
                "description_avant": issue.get("description") or "", "corps_avant": body,
                "plan": {k: plan[k] for k in ("redmine", "md")},
                "replie": plan.get("fold"),
            }, ensure_ascii=False) + "\n")
    print(f"  ↳ dump avant écriture : {dump} ({len(todo)} entrée(s))")

    # ── Exécution ───────────────────────────────────────────────────────────────
    import redmine_utils
    creds = redmine_utils.redmine_creds()
    base, key = creds[0].rstrip("/"), creds[1]
    touched, echecs = [], 0
    for rm_id, path, issue, fm, body, plan in todo:
        if plan.get("fold"):
            # Le champ d'abord : tant qu'il ne porte pas la section, la retirer perdrait
            # du contenu. L'ordre est le même que celui de l'étude RM2882 § 5.
            ok = pm_cf_mirror.push_text_cf(rm_id, plan["fold"], env_var=pm_acceptance.ENV_VAR,
                                           cf_name=pm_acceptance.CF_NAME)
            if not ok:
                echecs += 1
                print(f"  ✗ RM{rm_id} : champ non poussé — section laissée en place")
                continue
            write_md(path, {pm_acceptance.FM_KEY: plan["fold"]}, body)
            touched.append(path)
            fm = dict(fm, **{pm_acceptance.FM_KEY: plan["fold"]})
            print(f"  ✓ RM{rm_id} section repliée dans le champ "
                  f"({len(pm_acceptance.parse_items(plan['fold']))} critère(s))")
        if plan["redmine"] == "retire":
            # Relecture fraîche : la décision est rejouée sur l'état du moment.
            try:
                frais = redmine_utils.fetch_issue(rm_id) or {}
            except (Exception, SystemExit) as e:   # noqa: BLE001 — un ticket, pas le lot
                frais = None
                echecs += 1
                print(f"  ✗ RM{rm_id} : relecture impossible ({e}) — description laissée")
            p2 = plan_ticket(frais, fm, body) if frais else {"redmine": "illisible"}
            if p2["redmine"] == "illisible":
                pass
            elif p2["redmine"] != "retire":
                print(f"  ↷ RM{rm_id} : a changé depuis le chargement — description laissée")
            else:
                st, _ = redmine_utils.http_json(
                    "PUT", f"{base}/issues/{rm_id}.json", key,
                    {"issue": {"description": p2["new_desc"]}}, basic=creds.basic)
                ok = st in (200, 204)
                echecs += 0 if ok else 1
                print(f"  {'✓' if ok else '✗'} RM{rm_id} description"
                      + ("" if ok else f" (HTTP {st})"))
        if plan["md"] == "retire":
            changes = {pm_acceptance.FM_KEY: plan["fill_mirror"]} if plan["fill_mirror"] else {}
            write_md(path, changes, plan["new_body"])
            touched.append(path)
            print(f"  ✓ RM{rm_id} corps MD" + (" + miroir rempli" if plan["fill_mirror"] else ""))
    if echecs:
        print(f"\n⚠ {echecs} PUT en échec — relancer : les tickets déjà faits sortent en « sans section »")

    # Commit PAR DÉPÔT (même raison que cf-mirror-backfill : `autocommit` déduit le dépôt
    # du premier chemin et ignorerait en silence les fiches des autres dépôts).
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
                files, f"pm(acceptance): section de critères retirée de {len(files)} fiche(s), "
                       f"reprise dans le CF 33 (RM3241)")
            print(f"  ✓ commit {root} ({len(files)} fiche(s)){' ' + sha if sha else ''}")
    return 1 if echecs else 0


if __name__ == "__main__":
    sys.exit(main())
