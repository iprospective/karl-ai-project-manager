#!/usr/bin/env python3
"""pm-project-new — Pipeline complet : Redmine + struct PM + symlinks + bootstrap.

Usage :
    pm-project-new.py --client nextcloud --slug nc-clients --name "Nextcloud — clients" \\
                      --workspace /zfs/workspaces/nextcloud/nc-clients \\
                      --redmine-parent outils

    pm-project-new.py --client iprospective --slug pm-foo --name "PM Foo" \\
                      --workspace /zfs/workspaces/ai/foo \\
                      --redmine-parent iprospective --no-bootstrap

    # Rattacher à un projet Redmine déjà existant (skip création) :
    pm-project-new.py --client lydiemariller --slug lydiemariller-com \\
                      --name "Lydie Mariller — site web" \\
                      --workspace /zfs/workspaces/lydiemariller/lydiemariller.com \\
                      --existing-redmine-id lydie-mariller

Étapes :
  1. Crée projet Redmine sous parent (id ou identifier) — utilise REDMINE_USER_MAIN_API_KEY
     OU rattache à un projet Redmine existant (--existing-redmine-id)
  2. Ajoute 2 memberships par défaut (Admin/Manager, iProspective/Intervenant) — idempotent
  3. Crée struct PM (project/, memory/, tasks/)
  4. Écrit overview.md (et environments.md squelette si --with-env)
  5. Crée symlinks bidirectionnels (workspace ←→ PM)
  6. Lance bootstrap (--yes par défaut, --no-bootstrap pour skip, --interactive pour interactif)
"""
import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pm_paths import PMConfig


def api_call(method, url, key, payload=None):
    data = json.dumps(payload).encode("utf-8") if payload else None
    headers = {"X-Redmine-API-Key": key, "Accept": "application/json"}
    if payload:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, (json.loads(r.read()) if r.length != 0 and method != "PUT" else None)
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        return e.code, body


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--client", required=True, help="Slug du client existant")
    ap.add_argument("--slug", required=True, help="Slug du projet (= identifier Redmine)")
    ap.add_argument("--name", required=True)
    ap.add_argument("--workspace", required=True, help="Chemin absolu du workspace de code")
    rm_group = ap.add_mutually_exclusive_group(required=True)
    rm_group.add_argument("--redmine-parent",
                          help="Identifier ou ID Redmine du projet parent (créera un nouveau projet)")
    rm_group.add_argument("--existing-redmine-id",
                          help="Identifier d'un projet Redmine déjà créé (skip création, attache le PM dessus)")
    ap.add_argument("--description", default="")
    ap.add_argument("--gitlab-group", default=None)
    ap.add_argument("--no-bootstrap", action="store_true")
    ap.add_argument("--interactive-bootstrap", action="store_true",
                    help="Lance bootstrap en mode interactif (sinon: --yes)")
    ap.add_argument("--with-environments", action="store_true",
                    help="Crée aussi un environments.md squelette (env prod planned)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    cfg = PMConfig.load()
    workspace = Path(args.workspace).resolve()
    if not workspace.is_dir():
        sys.exit(f"ERREUR : workspace introuvable : {workspace}")

    client_root = cfg.path("entity", entity=args.client)
    if not client_root.is_dir():
        sys.exit(f"ERREUR : client '{args.client}' inexistant ({client_root}). Utiliser pm-client-new d'abord.")

    project_root = cfg.path("project", entity=args.client, project=args.slug)
    if project_root.exists():
        sys.exit(f"ERREUR : projet PM {args.client}/{args.slug} existe déjà")

    url = os.environ.get("REDMINE_URL", "").rstrip("/")
    key = os.environ.get("REDMINE_USER_MAIN_API_KEY") or os.environ.get("REDMINE_API_KEY")
    if not (url and key):
        sys.exit("ERREUR : REDMINE_URL + REDMINE_USER_MAIN_API_KEY requis (.env)")

    # Résoudre projet Redmine — création (--redmine-parent) ou attachement (--existing-redmine-id)
    if args.existing_redmine_id:
        rm_identifier = args.existing_redmine_id
        code, data = api_call("GET", f"{url}/projects/{rm_identifier}.json", key)
        if code != 200:
            sys.exit(f"ERREUR : projet Redmine existant '{rm_identifier}' introuvable (HTTP {code})")
        rm_id = data["project"]["id"]
        parent_label = (data["project"].get("parent") or {}).get("identifier") or "—"
        print(f"  · Projet Redmine existant résolu : '{rm_identifier}' → id={rm_id} (parent={parent_label})")
        if args.dry_run:
            print(f"--dry-run : attacherait PM à Redmine '{rm_identifier}' (id={rm_id}, skip création)")
            print(f"--dry-run : créerait struct {project_root.relative_to(cfg.projects_root)}/")
            print(f"--dry-run : symlinks {workspace}/.mmi-pm ↔ {project_root}/workspace")
            return
        print(f"  · Skip création Redmine (mode --existing-redmine-id)")
    else:
        parent = args.redmine_parent
        if parent.isdigit():
            parent_id = int(parent)
        else:
            code, data = api_call("GET", f"{url}/projects/{parent}.json", key)
            if code != 200:
                sys.exit(f"ERREUR : parent Redmine '{parent}' introuvable (HTTP {code})")
            parent_id = data["project"]["id"]
        print(f"  · Parent Redmine résolu : '{parent}' → id={parent_id}")
        parent_label = parent

        if args.dry_run:
            print(f"--dry-run : créerait Redmine project '{args.slug}' (parent={parent_id})")
            print(f"--dry-run : créerait struct {project_root.relative_to(cfg.projects_root)}/")
            print(f"--dry-run : symlinks {workspace}/.mmi-pm ↔ {project_root}/workspace")
            return

        # 1. Create Redmine project
        payload = {"project": {
            "name": args.name, "identifier": args.slug,
            "description": args.description, "parent_id": parent_id,
            "is_public": False, "inherit_members": False,
        }}
        code, data = api_call("POST", f"{url}/projects.json", key, payload)
        if code != 201:
            sys.exit(f"ERREUR création Redmine project (HTTP {code}) : {data!r}")
        rm_id = data["project"]["id"]
        rm_identifier = args.slug
        print(f"  ✓ Redmine project id={rm_id} créé")

    # 2. Default memberships (NORMS v1.7.2) — idempotent (422 = déjà présent)
    for gid, rid, label in [(49, 3, "Admin/Manager"), (70, 7, "iProspective/Intervenant")]:
        code, data = api_call("POST", f"{url}/projects/{rm_identifier}/memberships.json",
                              key, {"membership": {"user_id": gid, "role_ids": [rid]}})
        if code == 201:
            print(f"  ✓ membership {label}")
        elif code == 422:
            print(f"  · membership {label} déjà présent")
        else:
            print(f"  ⚠ membership {label} HTTP {code}", file=sys.stderr)

    # 3. PM struct
    for sub in ("project", "memory", "tasks"):
        (project_root / sub).mkdir(parents=True, exist_ok=True)
    print(f"  ✓ Struct PM créée : {project_root.relative_to(cfg.projects_root)}/")

    # 4. overview.md
    now = datetime.now().strftime("%Y-%m-%d")
    gitlab_group = args.gitlab_group or ""
    overview = project_root / "project" / "overview.md"
    overview.write_text(f"""---
schema_version: 1.7.1
slug: {args.slug}
name: {args.name}
client: {args.client}
status: active
created: {now}

used_by_clients: []
provided_by: null

bootstrap:
  skip: []
  done: []

defaults:
  priority: normal
  team: []

redmine:
  instance: null
  project_id: {rm_identifier}         # Redmine id={rm_id}, parent={parent_label}
  subprojects: []
gitlab:
  repo: null
  group: {gitlab_group}
  default_branch: main

aspects:
  - overview{'''
  - environments''' if args.with_environments else ''}
---

## Description

{args.description or "_(à compléter)_"}

## Workspace

| Chemin | Rôle |
|---|---|
| `{workspace}` | Workspace de code |

Symlinks bidirectionnels :
- `{workspace}/.mmi-pm` → ce dossier PM
- `workspace/` (à la racine de ce dossier PM) → `{workspace}`

## Aspects documentés
- [overview.md](overview.md)
{'- [environments.md](environments.md)' if args.with_environments else ''}
""", encoding="utf-8")
    print(f"  ✓ overview.md écrit")

    if args.with_environments:
        env_path = project_root / "project" / "environments.md"
        env_path.write_text(f"""---
schema_version: "1.7.0"
environments:
  - name: prod
    status: planned
    url: null
    host: null
    user: null
    app_path: null
    branch: null
    fpm_pool: null
    logs:
      app: null
      fpm: null
    secrets_source: null
    notes: ""

env_vars: []
---

## Procédure de déploiement par env

### prod
(à compléter)

## Accès et credentials

(à pousser dans Vaultwarden — cf. bootstrap-task 001-secrets-vaultwarden)
""", encoding="utf-8")
        print(f"  ✓ environments.md squelette écrit")

    # 5. Symlinks bidirectionnels
    ws_link = project_root / "workspace"
    if ws_link.exists() or ws_link.is_symlink():
        ws_link.unlink()
    ws_link.symlink_to(workspace)
    reverse = workspace / ".mmi-pm"
    if reverse.exists() or reverse.is_symlink():
        # Don't overwrite existing user link without warning
        print(f"  · {reverse} existe déjà, skip")
    else:
        reverse.symlink_to(project_root)
    print(f"  ✓ symlinks bidirectionnels")

    # 6. Bootstrap
    if not args.no_bootstrap:
        bootstrap_script = Path(__file__).parent / "pm-project-bootstrap.py"
        cmd = [sys.executable, str(bootstrap_script), str(project_root)]
        if not args.interactive_bootstrap:
            cmd.append("--yes")
        print(f"\n  ► Lancement bootstrap ({'interactif' if args.interactive_bootstrap else '--yes'}) …\n")
        subprocess.run(cmd, check=False)

    print(f"\n✓ Projet PM {args.client}/{args.slug} prêt.")
    print(f"  → cd {workspace}  # workspace de code")
    print(f"  → pm-task-list.py  # depuis le workspace, auto-detect")


if __name__ == "__main__":
    main()
