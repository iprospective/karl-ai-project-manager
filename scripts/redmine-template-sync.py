#!/usr/bin/env python3
"""
redmine-template-sync.py — synchronise les templates d'issue Redmine (plugin
redmine_issue_templates) depuis une source canonique unique.

Problème résolu : la structure « Demande initiale / CDC / Critères d'acceptation »
(cf. RM2016) doit exister à l'identique sur plusieurs trackers Redmine (Anomalie,
Évolution, Tâche) → autant de lignes de template à maintenir. Ce script en fait
des *miroirs* d'un seul fichier source : on édite la source, on relance, les N
templates sont mis à jour d'un coup.

Source canonique : templates/redmine/issue-body.md
Cible            : global_issue_templates (titre « Demande / CDC », trackers 1,2,4)

Le plugin n'expose pas d'API REST → on pilote l'ORM Rails via un runner
(scripts/redmine_issue_template_sync.rb) exécuté sur l'hôte Redmine par ssh
(rbenv). Idempotent : ne réécrit une ligne que si elle diffère réellement.

Usage :
    redmine-template-sync.py --dry-run      # rapport sans écrire
    redmine-template-sync.py                # applique
    redmine-template-sync.py --trackers 1,2,4 --title "Demande / CDC"

Config (defaults surchargeables par env ou flags) :
    PM_REDMINE_SSH_HOST   alias ssh de l'hôte Redmine          (défaut: mmi)
    PM_REDMINE_PATH       racine de l'install Redmine active   (défaut: /home/tasks/redmine-git)
    PM_REDMINE_RAILS_USER user système de l'app                (défaut: tasks)
    PM_REDMINE_RBENV      version rbenv                        (défaut: 3.3.7)
    PM_REDMINE_TPL_AUTHOR author_id Redmine du template        (défaut: 5)
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CANONICAL_BODY = REPO / "templates" / "redmine" / "issue-body.md"
RUNNER_RB = REPO / "scripts" / "redmine_issue_template_sync.rb"

DEFAULTS = {
    "ssh_host": os.environ.get("PM_REDMINE_SSH_HOST", "mmi"),
    "redmine_path": os.environ.get("PM_REDMINE_PATH", "/home/tasks/redmine-git"),
    "rails_user": os.environ.get("PM_REDMINE_RAILS_USER", "tasks"),
    "rbenv": os.environ.get("PM_REDMINE_RBENV", "3.3.7"),
    "author": os.environ.get("PM_REDMINE_TPL_AUTHOR", "5"),
}

REMOTE_BODY = "/tmp/pm_issue_template_body.md"
REMOTE_RB = "/tmp/pm_issue_template_sync.rb"


def sh(cmd, **kw):
    return subprocess.run(cmd, shell=True, text=True, capture_output=True, **kw)


def ship(host, local_path, remote_path, content=None):
    """Copie un contenu local vers remote via `ssh host 'cat > remote'`."""
    data = content if content is not None else Path(local_path).read_text()
    p = subprocess.run(
        ["ssh", host, f"cat > {remote_path}"],
        input=data, text=True, capture_output=True,
    )
    if p.returncode != 0:
        sys.exit(f"ERREUR transfert vers {host}:{remote_path}\n{p.stderr}")


def main():
    ap = argparse.ArgumentParser(description="Sync templates d'issue Redmine depuis la source canonique.")
    ap.add_argument("--dry-run", action="store_true", help="Rapporte CREATE/UPDATE/UNCHANGED sans écrire.")
    ap.add_argument("--trackers", default="1,2,4", help="ids trackers cibles, séparés par des virgules (défaut: 1,2,4 = Anomalie,Évolution,Tâche).")
    ap.add_argument("--title", default="Demande / CDC", help="Titre du template (clé d'unicité avec le tracker).")
    ap.add_argument("--note", default="Structure NORMS — Demande initiale (gelée) + CDC (évolutif). Réf. RM2016.", help="Mémo du template.")
    ap.add_argument("--ssh-host", default=DEFAULTS["ssh_host"])
    ap.add_argument("--redmine-path", default=DEFAULTS["redmine_path"])
    ap.add_argument("--rails-user", default=DEFAULTS["rails_user"])
    ap.add_argument("--rbenv", default=DEFAULTS["rbenv"])
    ap.add_argument("--author", default=DEFAULTS["author"])
    args = ap.parse_args()

    if not CANONICAL_BODY.exists():
        sys.exit(f"ERREUR : source canonique absente : {CANONICAL_BODY}")
    if not RUNNER_RB.exists():
        sys.exit(f"ERREUR : runner Ruby absent : {RUNNER_RB}")

    host = args.ssh_host
    # 1. expédier la source + le runner sur l'hôte Redmine
    ship(host, CANONICAL_BODY, REMOTE_BODY)
    ship(host, RUNNER_RB, REMOTE_RB)

    # 2. construire la commande rails runner (rbenv + env params)
    env_exports = " ".join([
        f"TPL_BODY_PATH={REMOTE_BODY}",
        f"TPL_TITLE={shquote(args.title)}",
        f"TPL_NOTE={shquote(args.note)}",
        f"TPL_AUTHOR={shquote(args.author)}",
        f"TPL_TRACKERS={shquote(args.trackers)}",
        f"TPL_DRY={'1' if args.dry_run else '0'}",
    ])
    inner = (
        f'export PATH="/home/{args.rails_user}/.rbenv/shims:/home/{args.rails_user}/.rbenv/bin:$PATH"; '
        f'export RBENV_VERSION={shquote(args.rbenv)}; '
        f'cd {shquote(args.redmine_path)} && '
        f'{env_exports} RAILS_ENV=production bundle exec rails runner {REMOTE_RB}'
    )
    remote_cmd = f"sudo -u {args.rails_user} bash -lc {shquote(inner)}"

    mode = "DRY-RUN (aucune écriture)" if args.dry_run else "APPLIQUE"
    print(f"→ {mode} — host={host} trackers={args.trackers} titre={args.title!r}")
    p = subprocess.run(["ssh", host, remote_cmd], text=True, capture_output=True)
    # le runner Rails est bavard (deprecations) — ne garder que nos lignes de statut
    keep = ("CREATE", "UPDATE", "UNCHANGED", "ERROR")
    out = [l for l in p.stdout.splitlines() if l.startswith(keep)]
    print("\n".join(out) if out else p.stdout.strip())
    if p.returncode != 0:
        sys.stderr.write(p.stderr)
        sys.exit(p.returncode)
    if any(l.startswith("ERROR") for l in out):
        sys.exit(2)


def shquote(s):
    return "'" + str(s).replace("'", "'\\''") + "'"


if __name__ == "__main__":
    main()
