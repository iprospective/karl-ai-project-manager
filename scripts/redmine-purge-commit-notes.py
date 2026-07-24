#!/usr/bin/env python3
"""redmine-purge-commit-notes — purge des notes de journal « commit d'outillage ».

Nettoie le bruit historique produit par pm-post-commit avant RM2409 : les notes
Redmine dont le texte est un message de commit d'outillage PM (`pm(desc): …`,
`pm(status): …`, `chore(…): …`) suffixé « — commit `sha` ». Ces notes sont du
housekeeping pur (la norme `traceability` niveau `work` ne les poste plus).

Filtre STRICT (les deux conditions) :
  1. première ligne = préfixe outillage `pm(<mot>):` ou `chore(…):` ;
  2. dernière ligne = « — commit `sha` » (suffixe apposé par pm-task-report).
Une note substantielle (message de commit de travail) ne matche pas → conservée.

Suppression = PUT /journals/<id>.json avec notes vide (Redmine supprime le
journal s'il ne porte pas d'autres changements ; sinon il garde les détails de
propriétés et vide juste le texte). AVANT toute suppression, dump JSON complet
des notes visées (--backup, défaut ~/.local/state/pm-purge-notes/<ts>.json).

Dry-run par défaut ; --apply pour exécuter.

Usage :
    ./scripts/redmine-purge-commit-notes.py                # dry-run, tous projets
    ./scripts/redmine-purge-commit-notes.py --rm-id 2267   # un seul ticket
    ./scripts/redmine-purge-commit-notes.py --apply        # purge réelle + backup
"""
import argparse
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pm_paths import PMConfig
from pm_output import out
from redmine_utils import http_json, redmine_creds

# Mêmes familles de préfixes que pm-post-commit.TOOLING_RE (+ tick/report/chore,
# postés par les versions historiques du hook).
TOOLING_FIRST_LINE_RE = re.compile(r"^(chore(\([^)]*\))?:|pm\([a-z-]+\):)")
COMMIT_SUFFIX_RE = re.compile(r"^— commit `?[0-9a-f]{6,40}`?\s*$", re.M)

RMID_RE = re.compile(r"^redmine_id:\s*(\d+)\s*$", re.M)


def iter_rm_ids(cfg, only_rm=None):
    """RM-ids de tous les tickets locaux (résolveur canonique, cf. pm-task-report)."""
    if only_rm:
        yield only_rm
        return
    seen = set()
    for entity, project, _pdir in cfg.iter_projects():
        try:
            tasks_dir = cfg.path("tasks_dir", entity=entity, project=project)
        except Exception:
            continue
        if not tasks_dir.is_dir():
            continue
        for f in sorted(tasks_dir.glob("RM*.md")):
            if f.name.endswith(".log.md"):
                continue
            m = RMID_RE.search(f.read_text(encoding="utf-8", errors="replace")[:2000])
            if m:
                rid = int(m.group(1))
                if rid not in seen:
                    seen.add(rid)
                    yield rid


def noise_journals(url, key, issue_id):
    """Journaux « bruit outillage » d'une issue : liste de dicts journal Redmine."""
    code, body = http_json("GET", f"{url}/issues/{issue_id}.json?include=journals", key, None)
    if code != 200:
        return None, f"HTTP {code}"
    hits = []
    for j in body.get("issue", {}).get("journals", []):
        notes = (j.get("notes") or "").strip()
        if not notes:
            continue
        first = notes.splitlines()[0]
        if TOOLING_FIRST_LINE_RE.match(first) and COMMIT_SUFFIX_RE.search(notes):
            hits.append(j)
    return hits, None


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--rm-id", type=int, help="limite à un seul ticket")
    ap.add_argument("--apply", action="store_true", help="exécute (défaut : dry-run)")
    ap.add_argument("--backup", help="chemin du dump JSON des notes supprimées "
                                     "(défaut : ~/.local/state/pm-purge-notes/<ts>.json)")
    out.add_args(ap)
    args = ap.parse_args()
    out.configure(args)

    url, key = redmine_creds()
    cfg = PMConfig.load()

    scanned = purged = failed = 0
    tickets_hit = 0
    backup_entries = []
    for rid in iter_rm_ids(cfg, args.rm_id):
        scanned += 1
        hits, err = noise_journals(url, key, rid)
        if hits is None:
            out.warn(f"RM{rid} : lecture journaux impossible ({err}) — ignoré")
            continue
        if not hits:
            continue
        tickets_hit += 1
        out.info(f"RM{rid} : {len(hits)} note(s) bruit — "
                 + " ; ".join((j.get("notes") or "").splitlines()[0][:60] for j in hits[:3]))
        for j in hits:
            backup_entries.append({
                "issue_id": rid, "journal_id": j.get("id"),
                "user": (j.get("user") or {}).get("name"),
                "created_on": j.get("created_on"), "notes": j.get("notes"),
            })
        if not args.apply:
            purged += len(hits)
            continue
        for j in hits:
            code, body = http_json("PUT", f"{url}/journals/{j['id']}.json", key,
                                   {"journal": {"notes": ""}})
            if code in (200, 204):
                purged += 1
            else:
                failed += 1
                out.warn(f"RM{rid} journal {j['id']} : HTTP {code} "
                         f"{str(body.get('_error', ''))[:120]}")
            time.sleep(0.05)   # ménage l'instance

    if args.apply and backup_entries:
        backup = Path(args.backup) if args.backup else (
            Path.home() / ".local/state/pm-purge-notes"
            / f"{datetime.now().strftime('%Y%m%d-%H%M%S')}.json")
        backup.parent.mkdir(parents=True, exist_ok=True)
        backup.write_text(json.dumps(backup_entries, ensure_ascii=False, indent=1),
                          encoding="utf-8")
        out.info(f"backup : {backup}")

    mode = "purgée(s)" if args.apply else "à purger (dry-run)"
    extra = f"{purged} note(s) {mode} sur {tickets_hit} ticket(s) ({scanned} scannés)"
    if failed:
        out.fail(f"{extra} — {failed} échec(s) PUT", code=1)
    out.op("purge-notes", extra=extra)


if __name__ == "__main__":
    main()
