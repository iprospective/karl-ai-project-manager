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

Gotcha scan : le mode `--all` itère les projets via `PMConfig.iter_projects` +
`tasks_dir` (résolveur canonique, migration-aware) — PAS `os.walk(projects_root)` :
depuis la co-localisation (RM1949), les tâches vivent dans `<ws>/.mmi-pm/tasks/` et ne
sont plus sous `projects_root` (RM2038).
"""
import argparse
import fcntl
import hashlib
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pm_paths import PMConfig
import pm_git
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
LOG_DETAIL_RE = re.compile(r"input\s*=\s*(\d+).*?output\s*=\s*(\d+)", re.I)
# Marqueur de dédup posé dans le commentaire du time_entry — clé d'idempotence
# AUTORITATIVE côté Redmine (RM2048) : avant d'insérer, on vérifie qu'aucun TE de
# l'issue ne porte déjà ce marqueur. Ne dépend plus du seul ledger local (fragile).
TICK_MARK_RE = re.compile(r"\[tick:([^\]]+)\]")

# Modèle de tokens v2 (RM2048) : input/output SÉPARÉS, cache EXCLU du reporting.
CF_TOK_OUT_NAME = "Tokens output"          # CF 16 (time_entry) — delta output
CF_TOK_IN_NAME = "Tokens input"            # CF 28 (time_entry) — delta input
CF_TOK_OUT_TOTAL_NAME = "Tokens output total"  # CF 17 (issue) — cumul output
CF_TOK_IN_TOTAL_NAME = "Tokens input total"    # CF 29 (issue) — cumul input

# Garde-fou ABSOLU (consigne user, RM2035) : une NOTE de journal ne doit JAMAIS
# servir à annoncer du temps/tokens consommés. Le temps/tokens vivent uniquement
# dans le time_entry (silencieux) + frontmatter. Si le texte de note candidat
# correspond à ce motif, on REFUSE de le poster (avertissement).
NOTE_CONSO_RE = re.compile(
    r"\btick\b"                       # « tick »
    r"|tokens?\s*[:=]\s*\d"            # Tokens: 123  /  tokens=123
    r"|\d[\d ,.]*\s*tokens?\b"         # 123 tokens
    r"|co[uû]t\s*[:=]"                 # Coût: / cout=
    r"|\bIA\s*[:=]\s*[\d.]"            # IA: 30   (champ de tick)
    r"|pass[ée]s?\s+(de\s+)?\d"        # « passé 30 » / « passées de 12 »
    r"|\bconsomm",                     # consommé / consommation
    re.I)

# La convention type de tâche → activité Redmine vit dans redmine.reference.yml
# (type_to_activity), lue via redmine_utils.activity_for_type(). Surchargagle
# par saisie via --activity.


def iter_task_files(cfg):
    """Yield les Path des fichiers tâche `RM<id>_<slug>.md` (hors `.log.md`).

    Parcourt les projets via le résolveur canonique (`iter_projects` + `tasks_dir`),
    exactement comme `PMConfig.find_task` — donc migration-aware : trouve les tâches
    **co-localisées** dans `<ws>/.mmi-pm/tasks/` (bascule RM1949) comme les projets
    pré-bascule. Dédup par chemin résolu.

    ⚠ NE PAS revenir à `os.walk(cfg.projects_root)` : depuis la co-localisation, les
    tâches ne vivent plus sous `projects_root` (les `.mmi-pm` ne sont pas suivis) → 0
    ticket trouvé (RM2038).
    """
    seen = set()
    for ent_slug, proj_slug, _ in cfg.iter_projects():
        try:
            tasks_dir = cfg.path("tasks_dir", entity=ent_slug, project=proj_slug)
        except KeyError:
            continue
        if not tasks_dir.is_dir():
            continue
        for f in sorted(tasks_dir.glob("RM*.md")):
            if not TASK_FILE_RE.match(f.name):   # exclut les `.log.md`
                continue
            try:
                rp = f.resolve()
            except OSError:
                continue
            if rp in seen:
                continue
            seen.add(rp)
            yield f


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
    d'une ligne `Tokens : N` et, optionnellement, d'une ligne
    `Détail : input=… output=… cache_read=… cache_creation=…`. On ne garde que N>0.
    `input`/`output` viennent du Détail (cache EXCLU, RM2048) ; si le Détail manque
    (vieilles entrées), fallback `output=tokens, input=0` + flag `no_detail`.
    Clé de dédup = `<ts>#<tokens>` (stable, indépendante du split).
    """
    if not log_path.is_file():
        return []
    entries = []
    cur = None

    def _finalize(c):
        if not c or c.get("tokens") is None or c["tokens"] <= 0:
            return
        if c.get("input") is None and c.get("output") is None:
            c["output"], c["input"], c["no_detail"] = c["tokens"], 0, True
        else:
            c["input"] = c.get("input") or 0
            c["output"] = c.get("output") or 0
            c["no_detail"] = False
        c["key"] = f"{c['ts']}#{c['tokens']}"
        entries.append(c)

    for raw in log_path.read_text(encoding="utf-8").splitlines():
        mh = LOG_HEADER_RE.match(raw)
        if mh:
            _finalize(cur)
            cur = {"ts": mh.group(1), "title": mh.group(2).strip(),
                   "tokens": None, "ia_minutes": 0.0, "input": None, "output": None}
            continue
        if cur is None:
            continue
        if cur["tokens"] is None:
            mt = LOG_TOKENS_RE.match(raw)
            if mt:
                cur["tokens"] = int(mt.group(1))
                mia = LOG_IA_RE.search(raw)
                if mia:
                    cur["ia_minutes"] = float(mia.group(1))
                continue
        md = LOG_DETAIL_RE.search(raw)
        if md and cur.get("tokens"):
            cur["input"], cur["output"] = int(md.group(1)), int(md.group(2))
    _finalize(cur)
    return entries


def existing_tick_keys(url, key, issue_id):
    """Mappe `tick_key -> time_entry_id` pour les TE Redmine de l'issue portant un
    marqueur `[tick:…]` (tous users — on dédoublonne sur le contenu, pas l'auteur).
    Idempotence autoritative : on ne fait pas confiance au seul ledger local (RM2048).
    Retourne None si le GET échoue (→ l'appelant s'abstient d'insérer, anti-doublon)."""
    found = {}
    offset = 0
    while True:
        code, body = http_json(
            "GET", f"{url}/time_entries.json?issue_id={issue_id}&limit=100&offset={offset}",
            key, None)
        if code not in (200, 201):
            return None
        items = body.get("time_entries", [])
        for t in items:
            mk = TICK_MARK_RE.search(t.get("comments") or "")
            if mk:
                found[mk.group(1)] = t.get("id")
        if len(items) < 100:
            break
        offset += 100
    return found


def post_time_entry(url, key, *, issue_id, spent_on, hours, activity_id,
                    comments, cf_out_id, cf_in_id, out_tokens, in_tokens, tick_key):
    """POST une saisie de temps (modèle v2 : output + input séparés, cache exclu).
    Le marqueur `[tick:<tick_key>]` est apposé pour l'idempotence Redmine."""
    comment = f"{comments} [tick:{tick_key}]"
    payload = {"time_entry": {
        "issue_id": issue_id, "spent_on": spent_on, "hours": hours,
        "activity_id": activity_id, "comments": comment[:255],
        "custom_fields": [{"id": cf_out_id, "value": str(out_tokens)},
                          {"id": cf_in_id, "value": str(in_tokens)}],
    }}
    code, body = http_json("POST", f"{url}/time_entries.json", key, payload)
    if code not in (200, 201):
        return None, f"HTTP {code} {body.get('_error', '')[:200]}"
    return body.get("time_entry", {}).get("id"), None


def post_note(url, key, *, issue_id, text, commit_hash=None):
    """PUT une note de journal substantielle sur l'issue. Retourne (ok, err|raison).

    Garde-fou : refuse une note dont le propos est la conso (NOTE_CONSO_RE) — le
    temps/tokens ne passent JAMAIS par une note (consigne RM2035). Marqueur de
    commit ajouté pour l'association molle avec le(s) time_entry du même commit.
    """
    text = (text or "").strip()
    if not text:
        return False, "vide"
    if NOTE_CONSO_RE.search(text):
        return False, "refusée (motif conso : une note ne reporte pas le temps/tokens)"
    if commit_hash:
        text = f"{text}\n\n— commit `{commit_hash[:10]}`"
    code, body = http_json("PUT", f"{url}/issues/{issue_id}.json", key,
                           {"issue": {"notes": text}})
    if code not in (200, 204):
        return False, f"HTTP {code} {body.get('_error', '')[:150]}"
    return True, None


def _acquire_lock(rm_id):
    """Verrou exclusif par ticket (sérialise les reports concurrents — hooks
    post-commit détachés. RM2048). Best-effort : si le verrou traîne >30s on
    continue quand même (le GET Redmine reste le garde-fou anti-doublon)."""
    f = open(f"/tmp/pm-report-RM{rm_id}.lock", "w")
    deadline = time.time() + 30
    while True:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return f
        except BlockingIOError:
            if time.time() > deadline:
                return f
            time.sleep(0.3)


def _release_lock(f):
    try:
        fcntl.flock(f, fcntl.LOCK_UN)
        f.close()
    except Exception:
        pass


def report_ticket(md_path, *, cf_out_id, cf_in_id, cf_out_total_id, cf_in_total_id,
                  apply, force, cf17_only, activity_override, note_text=None,
                  commit_hash=None):
    """Report d'un ticket (modèle tokens v2, RM2048).

    - time_entry : CF output (16) + CF input (28), cache EXCLU, recalculés depuis
      la ligne `Détail :` du log ;
    - cumuls issue : CF output total (17) + CF input total (29) ;
    - **idempotence autoritative côté Redmine** (marqueur `[tick:key]`) + verrou par
      ticket → un report rejoué N fois ne crée jamais de doublon ;
    - note_text/commit_hash : poste UNE note substantielle (message de commit), une
      fois (dédup ledger). Jamais de conso dans la note (garde-fou post_note).
    """
    fm, m = load_fm(md_path)
    if fm is None:
        return {"file": md_path.name, "status": "no-fm"}
    rm_id = fm.get("redmine_id")
    if not rm_id:
        return {"file": md_path.name, "status": "no-rmid"}

    tokens_total = int(fm.get("tokens_total") or 0)
    breakdown = fm.get("tokens_breakdown") or {}
    out_total = int(breakdown.get("output") or 0)
    in_total = int(breakdown.get("input") or 0)
    reporting = fm.get("reporting") or {}
    cf_out_before = int(reporting.get("cf_out_total") or reporting.get("cf17_tokens") or 0)
    cf_in_before = int(reporting.get("cf_in_total") or 0)
    ledger = reporting.get("time_entries") or []
    pushed_keys = {te.get("key") for te in ledger}
    notes_ledger = reporting.get("notes") or []
    pushed_note_keys = {n.get("key") for n in notes_ledger}
    note_key = None
    if note_text:
        note_key = (commit_hash[:40] if commit_hash
                    else "txt:" + hashlib.sha1(note_text.encode("utf-8")).hexdigest()[:16])
    has_pending_note = bool(note_text) and note_key not in pushed_note_keys

    res = {"file": md_path.name, "rm_id": rm_id, "tokens_total": tokens_total,
           "out_total": out_total, "in_total": in_total,
           "cf17_before": cf_out_before, "new_te": 0, "te_tokens": 0,
           "note_pending": has_pending_note, "status": "skip-no-tokens"}
    if tokens_total <= 0 and not has_pending_note:
        return res

    # --- entrées de log non encore poussées (filtre ledger LOCAL, 1er niveau) ---
    new_entries = []
    if not cf17_only:
        log_path = md_path.parent / md_path.name.replace(".md", ".log.md")
        new_entries = [e for e in parse_log_entries(log_path)
                       if e["key"] not in pushed_keys]
    res["new_te"] = len(new_entries)
    res["te_tokens"] = sum(e["output"] + e["input"] for e in new_entries)

    cf_needs = (cf_out_before != out_total) or (cf_in_before != in_total) or force
    if not new_entries and not cf_needs and not has_pending_note:
        res["status"] = "skip-uptodate"
        return res

    if not apply:
        res["status"] = "would-push"
        return res

    # --- APPLY (sérialisé par ticket) ---
    url, key = redmine_creds()
    task_type = fm.get("type")
    activity_id = activity_override or activity_for_type(task_type)
    now = datetime.now().strftime("%Y-%m-%dT%H:%M")
    created = []
    errors = []

    lock = _acquire_lock(rm_id)
    try:
        # Idempotence AUTORITATIVE : retirer les entrées déjà présentes côté Redmine
        # (marqueur [tick:key]). GET en échec → on s'abstient (anti-doublon).
        if new_entries:
            seen = existing_tick_keys(url, key, rm_id)   # {tick_key: te_id} | None
            if seen is None:
                errors.append("GET time_entries échoué — insertion suspendue (anti-doublon)")
                new_entries = []
            else:
                to_create = []
                for e in new_entries:
                    if e["key"] in seen:
                        # déjà côté Redmine → soigner le ledger local, NE PAS re-poster
                        ledger.append({"id": seen[e["key"]], "key": e["key"], "at": e["ts"],
                                       "spent_on": e["ts"][:10], "output": e["output"],
                                       "input": e["input"],
                                       "hours": round(e["ia_minutes"] / 60.0, 2)})
                    else:
                        to_create.append(e)
                new_entries = to_create

        for e in new_entries:
            te_id, err = post_time_entry(
                url, key, issue_id=rm_id, spent_on=e["ts"][:10],
                hours=round(e["ia_minutes"] / 60.0, 2), activity_id=activity_id,
                comments=e["title"], cf_out_id=cf_out_id, cf_in_id=cf_in_id,
                out_tokens=e["output"], in_tokens=e["input"], tick_key=e["key"])
            if err:
                errors.append(f"{e['key']}: {err}")
                continue
            rec = {"id": te_id, "key": e["key"], "at": e["ts"], "spent_on": e["ts"][:10],
                   "output": e["output"], "input": e["input"],
                   "hours": round(e["ia_minutes"] / 60.0, 2)}
            created.append(rec)
            ledger.append(rec)
    finally:
        _release_lock(lock)

    # recale les compteurs sur le RÉEL (après filtre idempotence Redmine) — sinon on
    # affiche les entrées candidates, pas celles effectivement créées.
    res["new_te"] = len(created)
    res["te_tokens"] = sum(r["output"] + r["input"] for r in created)

    # resync cumuls : CF output total (17) + CF input total (29)
    cf_err = None
    if cf_needs:
        code, body = http_json(
            "PUT", f"{url}/issues/{rm_id}.json", key,
            {"issue": {"custom_fields": [
                {"id": cf_out_total_id, "value": str(out_total)},
                {"id": cf_in_total_id, "value": str(in_total)}]}})
        if code not in (200, 204):
            cf_err = f"CF cumul HTTP {code} {body.get('_error', '')[:150]}"

    # note de journal SUBSTANTIELLE (jamais de conso — garde-fou dans post_note)
    note_status = None
    if has_pending_note:
        ok, why = post_note(url, key, issue_id=rm_id, text=note_text,
                            commit_hash=commit_hash)
        if ok:
            notes_ledger.append({"key": note_key, "at": now, "commit": commit_hash})
            note_status = "posted"
        else:
            note_status = f"skip ({why})"
    res["note_status"] = note_status

    # persister ledger + cumuls dans le frontmatter
    reporting["time_entries"] = ledger
    reporting["notes"] = notes_ledger
    if not cf_err:
        reporting["cf_out_total"] = out_total
        reporting["cf_in_total"] = in_total
        reporting["cf17_tokens"] = out_total   # compat lecture ancienne clé
    reporting["pushed_at"] = now
    fm["reporting"] = reporting
    fm["updated"] = now
    save_fm(md_path, fm, m)

    # trace .log.md
    parts = []
    if created:
        parts.append(f"{len(created)} time_entries (ids "
                     f"{', '.join(str(r['id']) for r in created)})")
    if cf_needs and not cf_err:
        parts.append(f"CF out_total={out_total} in_total={in_total}")
    if note_status == "posted":
        parts.append(f"note (commit {commit_hash[:8]})")
    if parts:
        append_log(md_path,
                   f"## {now} — report → Redmine\n{' ; '.join(parts)}\n\n")

    res["created"] = len(created)
    res["status"] = "error" if (errors or cf_err) else "pushed"
    res["errors"] = errors + ([cf_err] if cf_err else [])
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
    cf17 = f"out={r.get('out_total',0):>10,} in={r.get('in_total',0):>10,}"
    ns = r.get("note_status")
    if ns == "posted":
        note = "  +note✓"
    elif ns and ns.startswith("skip"):
        note = "  +note⊘"          # refusée par le garde-fou (conso) ou vide
    elif r.get("note_pending"):
        note = "  +note(à poster)"
    else:
        note = ""
    err = f"  ✗ {'; '.join(r.get('errors', []))}" if s == "error" else ""
    return f"  {icon} RM{rm:<5} {te_part}  {cf17}{note}{err}"


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
    ap.add_argument("--no-commit", action="store_true", help="Pas d'auto-commit git (RM1834)")
    ap.add_argument("--note", help="note de journal SUBSTANTIELLE à poster (ex. message de "
                    "commit). Refusée si elle annonce de la conso (garde-fou). Requiert --rm-id.")
    ap.add_argument("--commit", help="hash du commit déclencheur (marqueur sur les time_entries "
                    "+ clé de dédup de la note)")
    args = ap.parse_args()
    if args.note and not args.rm_id:
        ap.error("--note nécessite --rm-id (une note cible un ticket précis)")

    cfg = PMConfig.load()
    cf_out_id = cf_id_by_name(CF_TOK_OUT_NAME)              # 16
    cf_in_id = cf_id_by_name(CF_TOK_IN_NAME)                # 28
    cf_out_total_id = cf_id_by_name(CF_TOK_OUT_TOTAL_NAME)  # 17
    cf_in_total_id = cf_id_by_name(CF_TOK_IN_TOTAL_NAME)    # 29
    missing = [n for n, v in [(CF_TOK_OUT_NAME, cf_out_id), (CF_TOK_IN_NAME, cf_in_id),
                              (CF_TOK_OUT_TOTAL_NAME, cf_out_total_id),
                              (CF_TOK_IN_TOTAL_NAME, cf_in_total_id)] if v is None]
    if missing:
        sys.exit(f"ERREUR : CF introuvables dans redmine.reference.yml : {missing}")

    if args.rm_id:
        md_path = cfg.find_task(args.rm_id)
        if not md_path:
            sys.exit(f"ERREUR : RM{args.rm_id} introuvable")
        targets = [md_path]
    else:
        targets = sorted(iter_task_files(cfg))

    mode = "APPLY" if args.apply else "DRY-RUN"
    scope = "cumuls seuls" if args.cf17_only else "time_entries + cumuls"
    print(f"== pm-task-report — {scope} — {mode} (out=CF{cf_out_id}/in=CF{cf_in_id}, "
          f"cumuls out=CF{cf_out_total_id}/in=CF{cf_in_total_id}) ==\n")

    results = [report_ticket(p, cf_out_id=cf_out_id, cf_in_id=cf_in_id,
                             cf_out_total_id=cf_out_total_id, cf_in_total_id=cf_in_total_id,
                             apply=args.apply, force=args.force,
                             cf17_only=args.cf17_only,
                             activity_override=args.activity,
                             note_text=args.note, commit_hash=args.commit)
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

    # Auto-commit atomique des fichiers écrits (RM1834 piste A). Le batch `--all`
    # couvre PLUSIEURS workspaces/repos (co-localisation RM1949/RM2038) → on groupe
    # par racine de repo et on committe chacun séparément (autocommit ne gère qu'un
    # repo à la fois et ignorerait les chemins hors de paths[0]).
    if args.apply and not args.no_commit:
        written = [p for p, r in zip(targets, results) if r["status"] in ("pushed", "error")]
        by_root = {}
        for p in written:
            root = pm_git.repo_root(p)
            if root is None:
                continue
            by_root.setdefault(root, []).extend([p, p.parent / p.name.replace(".md", ".log.md")])
        for root, paths in by_root.items():
            n = sum(1 for x in paths if not x.name.endswith(".log.md"))
            pm_git.autocommit(paths, f"pm(report): {n} ticket(s) -> Redmine "
                                     f"(time_entries + CF17)")

    verb = "créées" if args.apply else "à créer"
    print(f"\n-- {pushed} ticket(s) poussé(s), {would} à pousser, {skipped} à jour, "
          f"{errors} erreur(s) ; {sum_te} time_entries {verb} "
          f"({sum_tok:,} tokens) --")
    if not args.apply and (would or sum_te):
        print("   (dry-run : relancer avec --apply pour exécuter)")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
