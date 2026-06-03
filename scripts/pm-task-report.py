#!/usr/bin/env python3
"""pm-task-report — Report des tokens/temps consommés (frontmatter + .log.md PM) → Redmine.

Comble le gap NORMS « Journalisation par commit » : `pm-task-tick` mesure et
accumule tokens + temps IA dans le MD/log, mais ne pousse rien vers Redmine. Ce
script est le **point de report**.

Pour chaque ticket, deux gestes complémentaires (cf. NORMS) :

1. **time_entries datées** (le détail atomique) : une saisie de temps Redmine
   par entrée datée `Tokens : N` du `.log.md` (N>0) —
   `POST /time_entries.json` { spent_on = date de l'entrée, hours = temps IA
   (delta, `hours=0` accepté par l'instance), activity_id = selon type tâche,
   CF **16** `Tokens` = tokens de l'entrée, comments = titre de l'entrée }.
   Le `time_entry.id` est la **ref en retour**, historisée dans le ledger
   `reporting.time_entries[]` (clé de dédup `<ts>#<tokens>` → re-run idempotent,
   pas de doublon).

2. **CF 17 `Tokens passés`** resync (le cumul) : PUT issue = `tokens_total`
   (valeur absolue → idempotent). Vue rapide du cumul, source = frontmatter.

Modes :
  --rm-id N      un seul ticket
  --all          tous les tickets avec tokens_total > 0
  --apply        exécute réellement (sinon DRY-RUN : n'écrit/poste rien)
  --cf17-only    ne fait QUE le resync CF17 (pas de time_entries)
  --activity ID  force l'activité Redmine pour toutes les saisies
  --force        re-PUT CF17 même si déjà à jour

Gotcha scan : `os.walk(followlinks=False)` — les symlinks `.mmi-pm` /
`projects_used` créent des cycles.
"""
import argparse
import os
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pm_paths import PMConfig
from redmine_utils import activity_for_type, cf_id_by_name, http_json, redmine_creds

try:
    import yaml
except ImportError:
    sys.exit("PyYAML requis : pip install PyYAML")


FM_RE = re.compile(r"^(---\s*\n)(.*?)(\n---\s*\n)(.*)$", re.DOTALL)
TASK_FILE_RE = re.compile(r"^RM\d+_.*(?<!\.log)\.md$")
LOG_HEADER_RE = re.compile(r"^##\s+(\d{4}-\d{2}-\d{2}T[\d:]+)\s+—\s+(.+?)\s*$")
LOG_TOKENS_RE = re.compile(r"^Tokens\s*:\s*(\d+)")
LOG_IA_RE = re.compile(r"IA\s*:\s*([\d.]+)\s*min")

CF_TOKENS_PASSES_NAME = "Tokens passés"   # CF 17 (issue) — cumul tokens
CF_TOKENS_NAME = "Tokens"                 # CF 16 (time_entry) — tokens du delta

# La convention type de tâche → activité Redmine vit dans redmine.reference.yml
# (type_to_activity), lue via redmine_utils.activity_for_type(). Surchargagle
# par saisie via --activity.


def iter_task_files(cfg):
    """Yield les Path des fichiers tâche `RM<id>_<slug>.md` (hors `.log.md`)."""
    for dirpath, _dirnames, filenames in os.walk(str(cfg.projects_root), followlinks=False):
        for name in filenames:
            if TASK_FILE_RE.match(name):
                yield Path(dirpath) / name


def load_fm(path):
    content = path.read_text(encoding="utf-8")
    m = FM_RE.match(content)
    if not m:
        return None, None
    return (yaml.safe_load(m.group(2)) or {}), m


def save_fm(path, fm, m):
    new_yaml = yaml.safe_dump(fm, allow_unicode=True, sort_keys=False,
                              default_flow_style=False)
    path.write_text(f"{m.group(1)}{new_yaml.rstrip()}{m.group(3)}{m.group(4)}",
                    encoding="utf-8")


def append_log(md_path, line):
    log_path = md_path.parent / md_path.name.replace(".md", ".log.md")
    with log_path.open("a", encoding="utf-8") as f:
        f.write(line)


def parse_log_entries(log_path):
    """Parse un `.log.md`, retourne la liste des entrées datées consommatrices.

    Une entrée = un header `## <ts> — <titre>` suivi (avant le header suivant)
    d'une ligne `Tokens : N`. On ne garde que N>0. `ia_minutes` optionnel.
    Clé de dédup = `<ts>#<tokens>`.
    """
    if not log_path.is_file():
        return []
    entries = []
    cur = None
    for raw in log_path.read_text(encoding="utf-8").splitlines():
        mh = LOG_HEADER_RE.match(raw)
        if mh:
            cur = {"ts": mh.group(1), "title": mh.group(2).strip(),
                   "tokens": None, "ia_minutes": 0.0}
            continue
        if cur is None or cur["tokens"] is not None:
            continue
        mt = LOG_TOKENS_RE.match(raw)
        if mt:
            cur["tokens"] = int(mt.group(1))
            mia = LOG_IA_RE.search(raw)
            if mia:
                cur["ia_minutes"] = float(mia.group(1))
            if cur["tokens"] > 0:
                cur["key"] = f"{cur['ts']}#{cur['tokens']}"
                entries.append(cur)
            cur = None
    return entries


def post_time_entry(url, key, *, issue_id, spent_on, hours, activity_id,
                    comments, cf16_id, tokens):
    """POST une saisie de temps. Retourne (time_entry_id | None, err)."""
    payload = {"time_entry": {
        "issue_id": issue_id, "spent_on": spent_on, "hours": hours,
        "activity_id": activity_id, "comments": comments[:255],
        "custom_fields": [{"id": cf16_id, "value": str(tokens)}],
    }}
    code, body = http_json("POST", f"{url}/time_entries.json", key, payload)
    if code not in (200, 201):
        return None, f"HTTP {code} {body.get('_error', '')[:200]}"
    return body.get("time_entry", {}).get("id"), None


def report_ticket(md_path, *, cf16_id, cf17_id, apply, force, cf17_only,
                  activity_override):
    """Report d'un ticket. Retourne un dict résumé."""
    fm, m = load_fm(md_path)
    if fm is None:
        return {"file": md_path.name, "status": "no-fm"}
    rm_id = fm.get("redmine_id")
    if not rm_id:
        return {"file": md_path.name, "status": "no-rmid"}

    tokens_total = int(fm.get("tokens_total") or 0)
    reporting = fm.get("reporting") or {}
    cf17_before = int(reporting.get("cf17_tokens") or 0)
    ledger = reporting.get("time_entries") or []
    pushed_keys = {te.get("key") for te in ledger}

    res = {"file": md_path.name, "rm_id": rm_id, "tokens_total": tokens_total,
           "cf17_before": cf17_before, "new_te": 0, "te_tokens": 0,
           "status": "skip-no-tokens"}
    if tokens_total <= 0:
        return res

    # --- entrées de log non encore poussées ---
    new_entries = []
    if not cf17_only:
        log_path = md_path.parent / md_path.name.replace(".md", ".log.md")
        new_entries = [e for e in parse_log_entries(log_path)
                       if e["key"] not in pushed_keys]
    res["new_te"] = len(new_entries)
    res["te_tokens"] = sum(e["tokens"] for e in new_entries)

    cf17_needs = (cf17_before != tokens_total) or force
    if not new_entries and not cf17_needs:
        res["status"] = "skip-uptodate"
        return res

    if not apply:
        res["status"] = "would-push"
        return res

    # --- APPLY ---
    url, key = redmine_creds()
    task_type = fm.get("type")
    activity_id = activity_override or activity_for_type(task_type)
    now = datetime.now().strftime("%Y-%m-%dT%H:%M")
    created = []
    errors = []

    for e in new_entries:
        te_id, err = post_time_entry(
            url, key, issue_id=rm_id, spent_on=e["ts"][:10],
            hours=round(e["ia_minutes"] / 60.0, 2), activity_id=activity_id,
            comments=e["title"], cf16_id=cf16_id, tokens=e["tokens"])
        if err:
            errors.append(f"{e['key']}: {err}")
            continue
        rec = {"id": te_id, "key": e["key"], "at": e["ts"],
               "spent_on": e["ts"][:10], "tokens": e["tokens"],
               "hours": round(e["ia_minutes"] / 60.0, 2)}
        created.append(rec)
        ledger.append(rec)

    # resync CF17 (cumul absolu)
    cf17_err = None
    if cf17_needs:
        code, body = http_json(
            "PUT", f"{url}/issues/{rm_id}.json", key,
            {"issue": {"custom_fields": [{"id": cf17_id, "value": str(tokens_total)}]}})
        if code not in (200, 204):
            cf17_err = f"CF17 HTTP {code} {body.get('_error', '')[:150]}"

    # persister le ledger + CF17 dans le frontmatter
    reporting["time_entries"] = ledger
    if not cf17_err:
        reporting["cf17_tokens"] = tokens_total
    reporting["pushed_at"] = now
    fm["reporting"] = reporting
    fm["updated"] = now
    save_fm(md_path, fm, m)

    # trace .log.md
    parts = []
    if created:
        parts.append(f"{len(created)} time_entries (ids "
                     f"{', '.join(str(r['id']) for r in created)})")
    if cf17_needs and not cf17_err:
        parts.append(f"CF17 = {tokens_total}")
    if parts:
        append_log(md_path,
                   f"## {now} — report → Redmine\n{' ; '.join(parts)}\n\n")

    res["created"] = len(created)
    res["status"] = "error" if (errors or cf17_err) else "pushed"
    res["errors"] = errors + ([cf17_err] if cf17_err else [])
    return res


def fmt_row(r):
    s = r["status"]
    if s in ("no-fm", "no-rmid", "skip-no-tokens"):
        return None
    rm = r.get("rm_id", "?")
    icon = {"pushed": "✓", "would-push": "→", "skip-uptodate": "·",
            "error": "✗"}.get(s, "?")
    te = r.get("new_te", 0)
    te_part = f"{te:>3} TE / {r.get('te_tokens', 0):>11,} tok" if te else "  (TE à jour)"
    cf17 = f"CF17 {r.get('cf17_before',0):>11,}→{r.get('tokens_total',0):>11,}"
    err = f"  ✗ {'; '.join(r.get('errors', []))}" if s == "error" else ""
    return f"  {icon} RM{rm:<5} {te_part}  {cf17}{err}"


def main():
    ap = argparse.ArgumentParser(description="Report tokens/temps consommés → Redmine")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--rm-id", type=int)
    g.add_argument("--all", action="store_true")
    ap.add_argument("--apply", action="store_true", help="exécute (sinon dry-run)")
    ap.add_argument("--cf17-only", action="store_true",
                    help="seulement resync CF17 (pas de time_entries)")
    ap.add_argument("--activity", type=int, help="force l'activité Redmine")
    ap.add_argument("--force", action="store_true", help="re-PUT CF17 même si à jour")
    args = ap.parse_args()

    cfg = PMConfig.load()
    cf16_id = cf_id_by_name(CF_TOKENS_NAME)
    cf17_id = cf_id_by_name(CF_TOKENS_PASSES_NAME)
    if cf16_id is None or cf17_id is None:
        sys.exit("ERREUR : CF 'Tokens'(16)/'Tokens passés'(17) introuvables "
                 "dans redmine.reference.yml")

    if args.rm_id:
        md_path = cfg.find_task(args.rm_id)
        if not md_path:
            sys.exit(f"ERREUR : RM{args.rm_id} introuvable")
        targets = [md_path]
    else:
        targets = sorted(iter_task_files(cfg))

    mode = "APPLY" if args.apply else "DRY-RUN"
    scope = "CF17 seul" if args.cf17_only else "time_entries + CF17"
    print(f"== pm-task-report — {scope} — {mode} "
          f"(CF16={cf16_id}, CF17={cf17_id}) ==\n")

    results = [report_ticket(p, cf16_id=cf16_id, cf17_id=cf17_id,
                             apply=args.apply, force=args.force,
                             cf17_only=args.cf17_only,
                             activity_override=args.activity)
               for p in targets]

    pushed = would = skipped = errors = 0
    sum_te = sum_tok = 0
    for r in results:
        row = fmt_row(r)
        if row:
            print(row)
        st = r["status"]
        if st in ("pushed", "would-push"):
            sum_te += r.get("new_te", 0)
            sum_tok += r.get("te_tokens", 0)
            pushed += st == "pushed"
            would += st == "would-push"
        elif st == "skip-uptodate":
            skipped += 1
        elif st == "error":
            errors += 1

    verb = "créées" if args.apply else "à créer"
    print(f"\n-- {pushed} ticket(s) poussé(s), {would} à pousser, {skipped} à jour, "
          f"{errors} erreur(s) ; {sum_te} time_entries {verb} "
          f"({sum_tok:,} tokens) --")
    if not args.apply and (would or sum_te):
        print("   (dry-run : relancer avec --apply pour exécuter)")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
