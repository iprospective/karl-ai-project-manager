#!/usr/bin/env python3
"""pm-task-sync — Synchronise une tâche MD locale avec son état actuel Redmine.

Fait un fetch complet du ticket Redmine et met à jour les champs frontmatter
locaux qui ont changé (status, priority, title, due, updated, team) + appende
les nouveaux journaux au .log.md (équivalent redmine-fetch-updates).

Différence avec `redmine-fetch-updates.py` :
- celui-là met à jour aussi les **champs frontmatter** (status, priority, etc.)
  pas seulement le pointeur de journal et le log
- log entry distincte indique "synchro depuis Redmine"

Usage :
    pm-task-sync.py <RM-id>                 # sync ce ticket
    pm-task-sync.py <RM-id> --dry-run       # affiche les diffs sans toucher
    pm-task-sync.py <RM-id> --no-journals   # sync frontmatter seulement (pas les notes)
    pm-task-sync.py --all-tasks             # sync tous les MD existants (long !)
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
import pm_hierarchy

try:
    import yaml
except ImportError:
    sys.exit("PyYAML requis")


FM_RE = re.compile(r"^(---\s*\n)(.*?)(\n---\s*\n)(.*)$", re.DOTALL)

REDMINE_TO_NORMS_STATUS = {
    8:  "a_etudier_chiffrer",
    14: "etude_chiffrage_en_cours",
    12: "a_faire",
    2:  "en_cours",
    19: "a_tester_dev",
    9:  "a_tester_demandeur",        # ex-a_tester_verifier (déprécié)
    3:  "a_mep",                     # Résolu/Validé/A MEP (non terminal)
    20: "en_mep",                    # MEP/Tester en preprod
    13: "en_pause",                  # Attente retour / en pause
    11: "a_corriger",
    18: "ferme",                     # terminal réel — raison via CF "Raison Fermé" (id 11)
    # --- statuts Redmine dépréciés (rétrocompat lecture seule) ---
    5:  ("ferme", "resolu"),
    10: ("ferme", "abandonne"),
    6:  ("ferme", "wont_fix"),       # ou hors_perimetre — ambigu
    7:  ("ferme", "invalide"),       # ou doublon — ambigu
}

# CF "Raison Fermé" (id=11, enumeration) → close_reason NORMS, par value_id.
# La valeur arrive en id (string), pas en label. Cf. NORMS § Mapping NORMS → Redmine.
CF_RAISON_FERME_ID = 11
CLOSE_REASON_FROM_CF = {
    "10": "resolu",
    "11": "wont_fix",     # Rejeté (ou hors_perimetre)
    "12": "abandonne",
    "13": "doublon",      # Déjà existant
    "14": "invalide",     # Pas un bug / rien à faire
}


def cf_value(issue, cf_id):
    """Valeur d'un custom field de l'issue (ou None)."""
    for c in issue.get("custom_fields") or []:
        if c.get("id") == cf_id:
            return c.get("value")
    return None

REDMINE_TO_NORMS_PRIORITY = {1: "low", 2: "normal", 3: "high", 4: "urgent"}


def fetch_issue(url, key, issue_id):
    full = (f"{url.rstrip('/')}/issues/{issue_id}.json?key={key}"
            "&include=journals,attachments,relations")
    req = urllib.request.Request(full, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())["issue"]


def fmt_journal_md(j):
    when = (j.get("created_on") or "").replace("Z", "")[:16]
    lines = [f"## {when} — Redmine #{j['id']} — {j['user']['name']}",
             "Source : Redmine (sync via pm-task-sync)", ""]
    for d in (j.get("details") or []):
        prop, name = d.get("property"), d.get("name", "?")
        old, new = d.get("old_value"), d.get("new_value")
        if prop == "attr":
            lines.append(f"- `{name}` : `{old}` → `{new}`")
        elif prop == "cf":
            lines.append(f"- custom `{name}` : `{old}` → `{new}`")
        elif prop == "attachment":
            lines.append(f"- pièce jointe : {new}")
        else:
            lines.append(f"- `{prop}/{name}` : `{old}` → `{new}`")
    notes = (j.get("notes") or "").strip()
    if notes:
        lines.append("")
        lines.append("Note :")
        for nl in notes.splitlines():
            lines.append(f"> {nl}" if nl else ">")
    return "\n".join(lines) + "\n"


def diff_fields(fm, issue):
    """Retourne un dict {field: (old, new)} des changements à appliquer côté MD."""
    diffs = {}

    # Subject ↔ title
    new_title = issue.get("subject")
    if new_title and fm.get("title") != new_title:
        diffs["title"] = (fm.get("title"), new_title)

    # Status
    rm_sid = (issue.get("status") or {}).get("id")
    mapping = REDMINE_TO_NORMS_STATUS.get(rm_sid)
    if mapping:
        if isinstance(mapping, tuple):
            new_status, new_close = mapping
        else:
            new_status, new_close = mapping, None
        # a_tester_verifier (déprécié) est traité comme a_tester_demandeur :
        # ne pas re-diff si le MD porte encore l'ancien alias équivalent.
        cur = fm.get("status")
        if cur == "a_tester_verifier" and new_status == "a_tester_demandeur":
            cur = new_status
        if cur != new_status:
            diffs["status"] = (fm.get("status"), new_status)
        # close_reason : seulement si on bascule en ferme (et qu'il n'y en a pas déjà).
        # Pour le terminal réel (id 18), la raison vient du CF "Raison Fermé".
        if new_status == "ferme" and not fm.get("close_reason"):
            if new_close is None:
                new_close = CLOSE_REASON_FROM_CF.get(str(cf_value(issue, CF_RAISON_FERME_ID)))
            if new_close:
                diffs["close_reason"] = (fm.get("close_reason"), new_close)

    # Assigned_to (id Redmine du responsable courant)
    rm_assignee = (issue.get("assigned_to") or {}).get("id")
    if rm_assignee is not None and fm.get("assigned_to") != rm_assignee:
        diffs["assigned_to"] = (fm.get("assigned_to"), rm_assignee)

    # Priority
    rm_pid = (issue.get("priority") or {}).get("id")
    new_prio = REDMINE_TO_NORMS_PRIORITY.get(rm_pid)
    if new_prio and fm.get("priority") != new_prio:
        diffs["priority"] = (fm.get("priority"), new_prio)

    # Due date
    new_due = issue.get("due_date")
    if new_due and fm.get("due") != new_due:
        diffs["due"] = (fm.get("due"), new_due)

    # Parent (attribut natif Redmine parent_issue_id ↔ frontmatter parent_task).
    # issue["parent"]["id"] absent => pas de parent => None.
    rm_parent = (issue.get("parent") or {}).get("id")
    if fm.get("parent_task") != rm_parent:
        diffs["parent_task"] = (fm.get("parent_task"), rm_parent)

    # Updated timestamp (always refresh)
    new_updated = (issue.get("updated_on") or "").replace("Z", "")[:16]
    if new_updated and fm.get("updated") != new_updated:
        diffs["updated"] = (fm.get("updated"), new_updated)

    return diffs


def apply_to_fm(fm, diffs, now):
    for k, (old, new) in diffs.items():
        fm[k] = new
    # Ajout au status_history si le status a changé
    if "status" in diffs:
        hist = fm.get("status_history") or []
        hist.append({
            "status": diffs["status"][1],
            "at": now, "by": "pm-task-sync",
            "model": None, "tokens": None, "duration_minutes": None,
        })
        fm["status_history"] = hist


def write_md(path, fm, body):
    yaml_fm = yaml.safe_dump(fm, allow_unicode=True, sort_keys=False,
                             default_flow_style=False, width=120).rstrip()
    path.write_text(f"---\n{yaml_fm}\n---\n{body}", encoding="utf-8")


def sync_one(cfg, url, key, rm_id, args):
    md_path = cfg.find_task(rm_id)
    if not md_path:
        print(f"  ⚠ RM{rm_id} : pas de MD local, skip (utiliser redmine-fetch-task.py pour importer)")
        return False

    content = md_path.read_text(encoding="utf-8")
    m = FM_RE.match(content)
    if not m:
        print(f"  ⚠ RM{rm_id} : pas de frontmatter dans {md_path.name}")
        return False
    fm = yaml.safe_load(m.group(2)) or {}
    body = m.group(4)

    try:
        issue = fetch_issue(url, key, rm_id)
    except urllib.error.HTTPError as e:
        print(f"  ⚠ RM{rm_id} HTTP {e.code} : {e.reason}")
        return False

    diffs = diff_fields(fm, issue)

    # Journaux nouveaux
    last_seen = fm.get("redmine_last_journal_id") or 0
    journals = sorted(issue.get("journals") or [], key=lambda j: j["id"])
    new_journals = [] if args.no_journals else [j for j in journals if j["id"] > last_seen]

    if not diffs and not new_journals:
        print(f"  · RM{rm_id} : à jour ({fm.get('status')}, last_journal={last_seen})")
        if not args.dry_run:
            fm["redmine_last_checked_at"] = datetime.now().strftime("%Y-%m-%dT%H:%M")
            write_md(md_path, fm, body)
        return True

    print(f"  → RM{rm_id} : {len(diffs)} champ(s) + {len(new_journals)} journal(aux)")
    for field, (old, new) in diffs.items():
        print(f"      • {field} : {old!r} → {new!r}")

    if args.dry_run:
        print("    (--dry-run, pas de modif)")
        return True

    now = datetime.now().strftime("%Y-%m-%dT%H:%M")
    apply_to_fm(fm, diffs, now)
    fm["redmine_last_checked_at"] = now
    if new_journals:
        fm["redmine_last_journal_id"] = new_journals[-1]["id"]
    write_md(md_path, fm, body)

    # Hiérarchie : si parent_task a changé, maintenir les sub_tasks de l'ancien et
    # du nouveau parent (MD locaux uniquement ; le champ enfant est déjà écrit
    # ci-dessus via apply_to_fm). Cf. pm_hierarchy.
    if "parent_task" in diffs:
        old_parent, new_parent = diffs["parent_task"]
        pm_hierarchy.maintain_parent_subtasks(
            cfg, rm_id, old_parent=old_parent, new_parent=new_parent,
            source="pm-task-sync")

    log_path = md_path.with_name(md_path.stem + ".log.md")
    with log_path.open("a", encoding="utf-8") as f:
        if diffs:
            diff_lines = "\n".join(f"- `{k}` : `{old}` → `{new}`" for k, (old, new) in diffs.items())
            f.write(f"\n## {now} — Synchro Redmine (champs)\nSource : pm-task-sync\n\n{diff_lines}\n")
        for j in new_journals:
            f.write("\n" + fmt_journal_md(j))

    return True


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("rm_id", nargs="?", type=int, help="ID du ticket à synchroniser (ou --all-tasks)")
    ap.add_argument("--all-tasks", action="store_true", help="Synchronise toutes les tâches MD existantes")
    ap.add_argument("--no-journals", action="store_true", help="Sync frontmatter seulement (pas les notes)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not args.rm_id and not args.all_tasks:
        sys.exit("ERREUR : passer un <RM-id> ou --all-tasks")

    cfg = PMConfig.load()
    url = os.environ.get("REDMINE_URL")
    key = os.environ.get("REDMINE_USER_MAIN_API_KEY") or os.environ.get("REDMINE_API_KEY")
    if not (url and key):
        sys.exit("ERREUR : REDMINE_URL + REDMINE_USER_MAIN_API_KEY requis (.env)")

    if args.all_tasks:
        # Scanne tous les tasks_dir pour récupérer les RM ids
        ids = []
        rm_re = re.compile(r"^RM(\d+)_.*\.md$")
        for ent, proj, _ in cfg.iter_projects():
            tasks_dir = cfg.path("tasks_dir", entity=ent, project=proj)
            if not tasks_dir.is_dir():
                continue
            for f in tasks_dir.iterdir():
                if f.name.endswith(".log.md"):
                    continue
                m = rm_re.match(f.name)
                if m:
                    ids.append(int(m.group(1)))
        ids = sorted(set(ids))
        print(f"Sync {len(ids)} tâche(s)…")
        for rm_id in ids:
            sync_one(cfg, url, key, rm_id, args)
    else:
        sync_one(cfg, url, key, args.rm_id, args)


if __name__ == "__main__":
    main()
