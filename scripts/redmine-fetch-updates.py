#!/usr/bin/env python3
"""Récupérer les nouveautés Redmine sur un ticket depuis le dernier check.

Lit `redmine_last_journal_id` du frontmatter de la tâche MD, fetch le ticket,
affiche les journaux postérieurs (notes + changements d'attributs), et met à
jour `redmine_last_journal_id` + `redmine_last_checked_at`.

Usage :
    ./scripts/redmine-fetch-updates.py --issue 1658
    ./scripts/redmine-fetch-updates.py --issue 1658 --dry-run
    ./scripts/redmine-fetch-updates.py --issue 1658 --since 5061   # explicite
    ./scripts/redmine-fetch-updates.py --issue 1658 --all          # tout l'historique
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib import error, request

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pm_paths import PMConfig
from redmine_utils import issue_is_ia_tagged, get_ia_cf_id

try:
    import yaml
except ImportError:
    print("ERREUR : PyYAML requis", file=sys.stderr)
    sys.exit(2)


FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def parse_frontmatter(content):
    m = FM_RE.match(content)
    if not m:
        raise ValueError("Frontmatter manquant")
    return yaml.safe_load(m.group(1)) or {}, m.end()


def write_frontmatter(file_path, fm, body):
    yaml_fm = yaml.safe_dump(fm, allow_unicode=True, sort_keys=False, width=120, default_flow_style=False)
    file_path.write_text(f"---\n{yaml_fm}---\n{body}", encoding="utf-8")


def fetch_issue_full(url, key, issue_id):
    full = (f"{url.rstrip('/')}/issues/{issue_id}.json?key={key}"
            "&include=journals,attachments,relations,allowed_statuses")
    req = request.Request(full, headers={"Accept": "application/json"})
    with request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())["issue"]


def fmt_journal(j):
    lines = [f"--- Journal #{j['id']} — {j['user']['name']} — {j['created_on']} ---"]
    for d in j.get("details", []):
        prop = d.get("property")
        name = d.get("name", "?")
        old = d.get("old_value")
        new = d.get("new_value")
        if prop == "attr":
            lines.append(f"  · {name}: {old!r} → {new!r}")
        elif prop == "cf":
            lines.append(f"  · custom_field({name}): {old!r} → {new!r}")
        elif prop == "attachment":
            lines.append(f"  · attachment: {new}")
        else:
            lines.append(f"  · {prop}/{name}: {old!r} → {new!r}")
    notes = (j.get("notes") or "").strip()
    if notes:
        lines.append("")
        for nl in notes.splitlines():
            lines.append(f"    {nl}")
    return "\n".join(lines)


def fmt_journal_for_log(j):
    """Format Markdown destiné au .log.md (entrée par journal)."""
    when = (j.get("created_on") or "").replace("Z", "")[:16]
    lines = [
        f"## {when} — Redmine #{j['id']} — {j['user']['name']}",
        "Source : Redmine (sync via redmine-fetch-updates)",
        "",
    ]
    details = j.get("details") or []
    if details:
        lines.append("Changements :")
        for d in details:
            prop = d.get("property")
            name = d.get("name", "?")
            old = d.get("old_value")
            new = d.get("new_value")
            if prop == "attr":
                lines.append(f"- `{name}` : `{old}` → `{new}`")
            elif prop == "cf":
                lines.append(f"- custom_field `{name}` : `{old}` → `{new}`")
            elif prop == "attachment":
                lines.append(f"- pièce jointe : {new}")
            else:
                lines.append(f"- `{prop}/{name}` : `{old}` → `{new}`")
        lines.append("")
    notes = (j.get("notes") or "").strip()
    if notes:
        lines.append("Note (verbatim) :")
        for nl in notes.splitlines():
            lines.append(f"> {nl}" if nl else ">")
        lines.append("")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--issue", type=int, required=True)
    ap.add_argument("--since", type=int, help="ID journal de départ (sinon lu depuis le MD)")
    ap.add_argument("--all", action="store_true", help="Afficher tout l'historique (équivaut à --since 0)")
    ap.add_argument("--dry-run", action="store_true", help="Ne pas mettre à jour le MD")
    ap.add_argument("--force", action="store_true",
                    help="Bypasse le filtre tag IA (syncer même si non tagué)")
    args = ap.parse_args()

    cfg = PMConfig.load()
    url = os.environ.get("REDMINE_URL")
    key = os.environ.get("REDMINE_USER_MAIN_API_KEY") or os.environ.get("REDMINE_API_KEY")
    if not (url and key):
        print("ERREUR : $REDMINE_URL et $REDMINE_API_KEY requis (.env)", file=sys.stderr)
        sys.exit(1)

    md_path = cfg.find_task(args.issue)
    if not md_path:
        print(f"ERREUR : aucun MD pour RM{args.issue} dans {cfg.projects_root}", file=sys.stderr)
        sys.exit(1)

    content = md_path.read_text(encoding="utf-8")
    try:
        fm, after = parse_frontmatter(content)
    except ValueError as e:
        print(f"ERREUR : {e} dans {md_path}", file=sys.stderr)
        sys.exit(1)

    if args.all:
        last_seen = 0
    elif args.since is not None:
        last_seen = args.since
    else:
        last_seen = fm.get("redmine_last_journal_id") or 0

    try:
        issue = fetch_issue_full(url, key, args.issue)
    except error.HTTPError as e:
        print(f"ERREUR Redmine : HTTP {e.code} {e.reason}", file=sys.stderr)
        sys.exit(1)

    # Filtre IA : skip si le ticket n'est pas tagué (sauf --force / CF non configuré).
    # Le MD existe localement mais le ticket Redmine a été dé-tagué entre temps : drift à signaler.
    if not args.force and get_ia_cf_id() is not None and not issue_is_ia_tagged(issue):
        print(f"⚠ Ticket #{args.issue} non tagué 'IA' côté Redmine — sync skip.", file=sys.stderr)
        print(f"  MD local présent : {md_path.relative_to(cfg.projects_root)}", file=sys.stderr)
        print(f"  Drift : re-tagger côté Redmine, ou utiliser --force, ou archiver le MD.", file=sys.stderr)
        sys.exit(0)

    # En-tête : état courant côté Redmine
    print(f"Ticket #{args.issue} — {issue.get('subject')}")
    print(f"  Statut    : {issue['status']['name']} (id {issue['status']['id']})")
    assignee = issue.get("assigned_to")
    print(f"  Assigné à : {assignee['name']} (id {assignee['id']})" if assignee else "  Assigné à : (personne)")
    print(f"  Priorité  : {issue.get('priority', {}).get('name', '?')}")
    print(f"  MàJ le    : {issue.get('updated_on')}")
    print()
    print(f"Côté MD     : status={fm.get('status')}  last_journal_id={fm.get('redmine_last_journal_id') or 'none'}")
    print()

    journals = sorted(issue.get("journals") or [], key=lambda j: j["id"])
    new = [j for j in journals if j["id"] > last_seen]

    if not new:
        print(f"Aucune nouveauté depuis le journal #{last_seen}.")
        if not args.dry_run:
            fm["redmine_last_checked_at"] = datetime.now().strftime("%Y-%m-%dT%H:%M")
            write_frontmatter(md_path, fm, content[after:])
        return

    print(f"=== {len(new)} nouveauté(s) depuis le journal #{last_seen} ===\n")
    for j in new:
        print(fmt_journal(j))
        print()

    latest = new[-1]["id"]
    print(f"Dernier journal lu : #{latest}")

    if args.dry_run:
        print("(dry-run : MD et log non modifiés)")
        return

    fm["redmine_last_journal_id"] = latest
    fm["redmine_last_checked_at"] = datetime.now().strftime("%Y-%m-%dT%H:%M")
    write_frontmatter(md_path, fm, content[after:])
    print(f"→ MD mis à jour : {md_path.name}")

    # Persister les journaux dans le .log.md (append-only, conforme NORMS).
    # Permet au worker de retrouver l'historique Redmine sur ses prochaines reprises.
    log_path = md_path.with_name(md_path.stem + ".log.md")
    if not log_path.exists():
        log_path.write_text(f"# Journal RM{args.issue}\n\n", encoding="utf-8")
    with log_path.open("a", encoding="utf-8") as f:
        for j in new:
            f.write("\n")
            f.write(fmt_journal_for_log(j))
    print(f"→ Log appendé    : {log_path.name} ({len(new)} entrée(s) ajoutée(s))")


if __name__ == "__main__":
    main()
