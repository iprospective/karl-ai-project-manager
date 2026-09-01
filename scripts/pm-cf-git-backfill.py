#!/usr/bin/env python3
"""pm-cf-git-backfill — rétro-remplit les CF « GIT Branche » / « GIT PR » (RM2592).

Les CF 3 et 4 n'étaient pas rattachés à tous les trackers : `pm-mr create` les
posait, Redmine les jetait, et l'information n'a survécu que dans le frontmatter
`git:` du MD local. Le rattachement est corrigé — restait le passif.

**Tout ou rien, délibérément.** Un rattrapage partiel serait pire que pas de
rattrapage : un CF vide voudrait dire soit « pas de branche », soit « fermé
avant le passage », ambiguïté que personne ne lèverait jamais. En remplissant
tout, « CF vide ⇒ pas de branche » redevient une lecture fiable.

Garde-fous :
  · n'écrit QUE dans un CF vide — une valeur déjà posée n'est jamais écrasée ;
  · RELIT après écriture. Sans le droit « Edit issues », ou si le workflow
    verrouille un ticket fermé, Redmine répond 204 et jette silencieusement les
    attributs (cf. knowledge/redmine/api.md) : sans relecture, on annoncerait
    91 succès pour 0 écriture ;
  · dry-run par DÉFAUT ; `--apply` écrit.

Usage :
    pm-cf-git-backfill.py                  # dry-run : ce qui serait écrit
    pm-cf-git-backfill.py --repair-generic # + répare les `dev` écrits par les
                                           #   promotions d'avant RM2701
    pm-cf-git-backfill.py --apply          # écrit, et vérifie
    pm-cf-git-backfill.py --apply --limit 5   # essai sur 5 tickets d'abord
"""
import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pm_output import out                                     # noqa: E402
import redmine_utils                                          # noqa: E402
from pm_paths import PMConfig                                 # noqa: E402

CF_BRANCH, CF_PR = 3, 4
BATCH = 100
_NULLISH = {"", "null", "~", "none", "None"}


def val(v):
    """Valeur exploitable, ou None. Les YAML du PM portent des `null` textuels."""
    s = str(v or "").strip().strip("'\"")
    return None if s in _NULLISH else s


def local_git_info(tasks_root: Path) -> dict:
    """{redmine_id: {branch, pr}} d'après le frontmatter `git:` des MD."""
    out_ = {}
    for f in tasks_root.glob("*/projects/*/tasks/RM*.md"):
        if f.name.endswith(".log.md"):
            continue
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        m = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
        if not m:
            continue
        fm = m.group(1)
        rid = re.search(r"^redmine_id:\s*(\d+)", fm, re.M)
        branch = re.search(r"^\s{2}branch:\s*(\S.*)$", fm, re.M)
        if not (rid and branch):
            continue
        b = val(branch.group(1))
        if not b:
            continue
        # `mr_url` est le scalaire courant ; `mr_urls[]` la liste (RM2541) — on
        # prend la DERNIÈRE de la liste : c'est la MR de promotion, celle qui
        # porte la livraison.
        urls = re.findall(r"^\s{2}-\s+(https?://\S+)$", fm, re.M)
        pr = val(urls[-1]) if urls else None
        if not pr:
            m2 = re.search(r"^\s{2}mr_url:\s*(\S.*)$", fm, re.M)
            pr = val(m2.group(1)) if m2 else None
        out_[int(rid.group(1))] = {"branch": b, "pr": pr, "file": f.name}
    return out_


def fetch_issues(url, key, ids):
    """Issues Redmine par lots, tous statuts confondus."""
    got = {}
    for i in range(0, len(ids), BATCH):
        lot = ids[i:i + BATCH]
        q = "%s/issues.json?status_id=*&issue_id=%s&limit=%d" % (
            url.rstrip("/"), ",".join(map(str, lot)), BATCH)
        req = urllib.request.Request(q, headers={"X-Redmine-API-Key": key})
        try:
            d = json.load(urllib.request.urlopen(req, timeout=40))
        except Exception as e:
            out.fail("lecture Redmine impossible : %s" % e)
        for iss in d.get("issues", []):
            got[iss["id"]] = iss
    return got


def cf_map(issue):
    return {c["id"]: str(c.get("value") or "") for c in (issue.get("custom_fields") or [])}


def branche_de_ticket(rid, branch):
    """Vrai si `branch` est bien LA branche de ce ticket (`<id>-<slug>`).

    Dix tickets portent `branch: main` en frontmatter — un reliquat, pas une
    branche de travail. L'écrire dans « GIT Branche » affirmerait que leur code
    vit sur `main` : une information fausse, et une information fausse est pire
    qu'un champ vide, parce qu'on la croit."""
    return bool(re.match(r"^%d-" % int(rid), str(branch or "")))


# Valeurs qui ne désignent aucun ticket : toutes les livraisons y passent.
GENERIQUES = {"dev", "main", "master", "preprod"}


def to_write(rid, issue, info, repair=False):
    """CF à poser sur ce ticket.

    Par défaut : uniquement les VIDES, jamais un écrasement. Avec `repair`
    (RM2701), on remplace en plus les valeurs GÉNÉRIQUES — `pm-mr` écrivait
    `dev` à chaque MR de promotion, écrasant la branche du ticket. Remplacer
    une valeur fausse par la vraie n'est pas le même geste qu'écraser une
    valeur renseignée : la première ment, la seconde informe."""
    cur = cf_map(issue)
    todo = []
    actuel = cur.get(CF_BRANCH, "").strip()
    remplaçable = (not actuel) or (repair and actuel in GENERIQUES)
    if CF_BRANCH in cur and remplaçable and branche_de_ticket(rid, info["branch"]):
        todo.append({"id": CF_BRANCH, "value": info["branch"]})
    if CF_PR in cur and not cur[CF_PR].strip() and info["pr"]:
        todo.append({"id": CF_PR, "value": info["pr"]})
    return todo


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="écrit (défaut : dry-run)")
    ap.add_argument("--limit", type=int, help="ne traiter que les N premiers (essai)")
    ap.add_argument("--repair-generic", dest="repair", action="store_true",
                    help="remplace aussi les valeurs génériques (dev/main…) écrites "
                         "par les MR de promotion d'avant RM2701")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    # `entities_dir` = {projects_root}/clients : la racine des données PM, quelle
    # que soit la machine (l'arborescence est relocalisable, cf. RM2580).
    try:
        tasks_root = Path(PMConfig.load().path("entities_dir"))
    except Exception:
        tasks_root = Path(__file__).resolve().parent.parent / "projects" / "clients"
    if not tasks_root.is_dir():
        out.fail("racine des données PM introuvable : %s" % tasks_root)
    url, key = redmine_utils.redmine_creds()

    locaux = local_git_info(tasks_root)
    out.info("%d ticket(s) portent une branche git en local" % len(locaux))
    issues = fetch_issues(url, key, sorted(locaux))

    plan = []
    absents_tracker = generiques = 0
    for rid, info in sorted(locaux.items()):
        iss = issues.get(rid)
        if not iss:
            continue
        cur = cf_map(iss)
        if CF_BRANCH not in cur:
            absents_tracker += 1        # tracker ne portant pas le CF : hors sujet ici
            continue
        if not branche_de_ticket(rid, info["branch"]):
            generiques += 1        # `main` en frontmatter : pas une branche de ticket
        todo = to_write(rid, iss, info, args.repair)
        if todo:
            plan.append((rid, iss, todo))
    if args.limit:
        plan = plan[:args.limit]

    if generiques:
        out.info("%d ticket(s) écartés : branche générique en frontmatter (`main`), "
                 "pas une branche de ticket — champ laissé vide plutôt que faux" % generiques)
    if absents_tracker:
        out.warn("%d ticket(s) sur un tracker qui ne porte pas le CF — rattachement "
                 "à corriger dans l'UI Redmine avant de les rattraper" % absents_tracker)
    if not plan:
        out.info("aucun CF à rétro-remplir : rien à faire")
        return

    écrits = jetés = 0
    for rid, iss, todo in plan:
        quoi = ", ".join("%s=%s" % ("branche" if c["id"] == CF_BRANCH else "PR",
                                    c["value"][:60]) for c in todo)
        if not args.apply:
            sys.stdout.write("  → #%-5d [%s] %s\n" % (rid, iss["status"]["name"], quoi))
            continue
        ok, err = redmine_utils.update_issue_fields(rid, custom_fields=todo)
        # RELECTURE : un 204 ne prouve rien (droits, workflow d'un ticket fermé).
        relu = fetch_issues(url, key, [rid]).get(rid) or {}
        cur = cf_map(relu)
        posé = all(cur.get(c["id"], "").strip() == c["value"] for c in todo)
        if ok and posé:
            écrits += 1
            if args.verbose:
                sys.stdout.write("  ✓ #%-5d %s\n" % (rid, quoi))
        else:
            jetés += 1
            sys.stdout.write("  ✗ #%-5d [%s] NON écrit%s\n" % (
                rid, iss["status"]["name"], (" : %s" % err) if err else " (silencieusement)"))

    if args.apply:
        out.op("cf-backfill", extra="%d écrit(s), %d rejeté(s)" % (écrits, jetés))
        if jetés:
            out.warn("les rejets silencieux viennent des droits « Edit issues » ou du "
                     "workflow du statut — relancer après correction, l'outil est idempotent")
    else:
        sys.stdout.write("\n%d ticket(s) à rétro-remplir → relancer avec --apply\n" % len(plan))


if __name__ == "__main__":
    main()
