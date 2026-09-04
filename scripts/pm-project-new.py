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
  2. Ajoute 3 memberships par défaut (Admin/Manager, iProspective/Intervenant,
     Agents IA/Intervenant) — idempotent
  3. Crée struct PM (project/, memory/, tasks/)
  4. Écrit overview.md (et environments.md squelette si --with-env)
  5. Crée symlinks bidirectionnels (workspace ←→ PM)
  5b. Protège les branches des dépôts créés/déclarés (pm-protect, RM2057) — jamais bloquant
  6. Lance bootstrap (--yes par défaut, --no-bootstrap pour skip, --interactive pour interactif)
"""
import argparse
import importlib.util
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import yaml
from pm_paths import PMConfig
import pm_ws_skeleton  # squelette sous racine verrouillée (RM2909)


def load_coloc():
    """Charge pm-workspace-coloc.py comme lib (tiret dans le nom → importlib).
    Source unique de la logique GitLab/-core : ensure_group, ensure_repo,
    git_core_publish (RM2228 — ne pas dupliquer)."""
    p = Path(__file__).resolve().parent / "pm-workspace-coloc.py"
    spec = importlib.util.spec_from_file_location("pm_workspace_coloc", str(p))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


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


def protect_project_repos(workspace: Path, dry: bool) -> None:
    """Applique la politique de branches protégées aux dépôts du projet (RM2057).

    Le tripwire « pas de push direct sur une branche protégée » n'a de valeur que
    s'il est posé À LA CRÉATION : posé plus tard, il arrive après les premiers
    pushes directs, et personne ne repasse. On protège donc dès que les branches
    existent — c'est-à-dire juste après la publication du dépôt `-core`.

    Deux dépôts possibles, deux politiques (pm-protect les distingue tout seul) :
      - le **core** (le workspace lui-même : `.mmi-pm/` réel à la racine) ;
      - les dépôts de **code** déjà présents au layout RM1993 (`repos/*.git`) qui
        portent un remote GitLab — un workspace existant peut en avoir avant que
        le volet PM ne soit créé.

    JAMAIS bloquant : un projet créé sans protection reste un projet créé. Un
    échec (droits, token, forge tierce) s'annonce avec la commande de rattrapage.
    """
    script = Path(__file__).resolve().parent / "pm-protect.py"
    targets = [(workspace, "core (volet PM)")]
    repos_dir = workspace / "repos"
    if repos_dir.is_dir():
        for bare in sorted(repos_dir.glob("*.git")):
            if _has_gitlab_remote(bare):
                targets.append((bare, f"code {bare.name}"))
    for repo, label in targets:
        if dry:
            print(f"  [dry] protégerait les branches de {label} ({repo})")
            continue
        cmd = [sys.executable, str(script), "--repo", str(repo)]
        r = subprocess.run(cmd, capture_output=True, text=True)
        sys.stdout.write(r.stdout)
        if r.returncode != 0:
            print(f"  ⚠ protection des branches non posée sur {label} — "
                  f"le projet reste créé. Rattrapage : "
                  f"pm-protect.py --repo {repo}", file=sys.stderr)
            if r.stderr.strip():
                print("    " + r.stderr.strip().splitlines()[-1], file=sys.stderr)


def _has_gitlab_remote(repo: Path) -> bool:
    """Le dépôt a-t-il un remote qui pointe vers la forge ? Sans remote, il n'y a
    rien à protéger — et pm-protect échouerait à résoudre le projet."""
    r = subprocess.run(["git", "-C", str(repo), "remote", "get-url", "origin"],
                       capture_output=True, text=True)
    return r.returncode == 0 and "gitlab" in r.stdout.strip().lower()


def dry_run_coloc_plan(workspace, project_root, group, core_repo):
    """Plan --dry-run du modèle co-localisé (RM2228)."""
    print(f"--dry-run : matérialiserait {workspace}/.mmi-pm (réel) : "
          f"project/ docs/ memory/ tasks/ + meta.yml + overview.md")
    print(f"--dry-run : créerait le repo GitLab {group}/{core_repo} et publierait "
          f".mmi-pm (gitignore whitelist, init, commit, push)")
    print(f"--dry-run : symlink d'index {project_root} → {workspace}/.mmi-pm ; "
          f"symlinks workspace→.. et docs→.mmi-pm/docs")
    protect_project_repos(workspace, True)          # RM2057 : annoncer, ne rien poser


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
    # Sous le modèle multi-user (RM2438 / T6 RM2502), le dossier client est en
    # `2750 pm:pm` : un dev du groupe `pm` ne peut y créer NI le workspace, NI son
    # squelette. Le verbe NOPASSWD dédié (RM2909) le fait — sinon on retombe sur
    # l'erreur historique, et l'opérateur pose le dossier à la main comme avant.
    pm_ws_skeleton.ensure_skeleton(workspace, args.dry_run)
    if not workspace.is_dir():
        sys.exit(f"ERREUR : workspace introuvable : {workspace}")

    client_root = cfg.path("entity", entity=args.client)
    if not client_root.is_dir():
        sys.exit(f"ERREUR : client '{args.client}' inexistant ({client_root}). Utiliser pm-client-new d'abord.")

    project_root = cfg.path("project", entity=args.client, project=args.slug)
    if project_root.exists() or project_root.is_symlink():
        sys.exit(f"ERREUR : projet PM {args.client}/{args.slug} existe déjà")

    # ── Garde-fous coloc (RM2228) — fail-fast AVANT toute création Redmine ──
    # Le volet PM vit CO-LOCALISÉ dans le workspace (.mmi-pm réel, repo <dossier>-core,
    # projects/ = symlink d'index) — modèle RM1942/RM1949.
    mmi_dir = workspace / ".mmi-pm"
    if mmi_dir.exists() or mmi_dir.is_symlink():
        sys.exit(f"ERREUR : {mmi_dir} existe déjà — workspace déjà relié à un projet PM ?")
    if (workspace / ".git").exists():
        sys.exit(f"ERREUR : la racine du workspace est déjà un repo git ({workspace}/.git) — "
                 f"le repo -core doit vivre à la racine (layout RM1993). Normaliser d'abord "
                 f"avec pm-env-migrate (code → repos/ + envs/), puis relancer.")
    if not re.match(r"^[a-z0-9][a-z0-9._-]*$", workspace.name):
        sys.exit(f"ERREUR : nom de dossier workspace '{workspace.name}' non conforme (slug "
                 f"attendu : minuscules/chiffres/._-). Le nom du dossier donne le repo "
                 f"'<dossier>-core' — renommer d'abord (ex. dev/fad-framework).")
    gitlab_group_ns = args.gitlab_group or args.client
    core_repo = f"{workspace.name}-core"

    url = os.environ.get("REDMINE_URL", "").rstrip("/")
    key = os.environ.get("REDMINE_API_KEY") or os.environ.get("REDMINE_USER_MAIN_API_KEY")
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
            dry_run_coloc_plan(workspace, project_root, gitlab_group_ns, core_repo)
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
            dry_run_coloc_plan(workspace, project_root, gitlab_group_ns, core_repo)
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

    # 2. Default memberships (NORMS v1.7.2 ; Agents IA ajouté RM1977) — idempotent (422 = déjà présent)
    for gid, rid, label in [(49, 3, "Admin/Manager"), (70, 7, "iProspective/Intervenant"),
                            (73, 7, "Agents IA/Intervenant")]:
        code, data = api_call("POST", f"{url}/projects/{rm_identifier}/memberships.json",
                              key, {"membership": {"user_id": gid, "role_ids": [rid]}})
        if code == 201:
            print(f"  ✓ membership {label}")
        elif code == 422:
            print(f"  · membership {label} déjà présent")
        else:
            print(f"  ⚠ membership {label} HTTP {code}", file=sys.stderr)

    # 3. PM struct — CO-LOCALISÉE (RM2228) : le volet PM vit dans <workspace>/.mmi-pm/
    #    (réel, versionné par le repo -core). project/ (canoniques), docs/ (aspects
    #    libres wiki-syncés, RM2043), memory/, tasks/. docs/ porte un .gitkeep pour
    #    persister vide tant qu'aucun aspect.
    for sub in ("project", "docs", "memory", "tasks"):
        (mmi_dir / sub).mkdir(parents=True, exist_ok=True)
    (mmi_dir / "docs" / ".gitkeep").write_text("", encoding="utf-8")
    print(f"  ✓ Struct PM co-localisée créée : {mmi_dir}/")

    # 4. meta.yml (manifeste machine) + overview.md (prose) — RM1994
    now = datetime.now().strftime("%Y-%m-%d")
    gitlab_group = args.gitlab_group or ""
    meta = {
        "schema_version": "1.7.1",
        "slug": args.slug,
        "name": args.name,
        "client": args.client,
        "status": "active",
        "created": now,
        "used_by_clients": [],
        "provided_by": None,
        "implements": [],
        "implemented_by": [],
        "bootstrap": {"skip": [], "done": []},
        "defaults": {"priority": "normal", "team": []},
        "redmine": {"instance": None, "project_id": rm_identifier, "subprojects": []},
        "gitlab": {"repo": None, "group": gitlab_group, "default_branch": "main"},
        "aspects": ["overview"] + (["environments"] if args.with_environments else []),
    }
    (mmi_dir / "meta.yml").write_text(
        yaml.safe_dump(meta, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    overview = mmi_dir / "project" / "overview.md"
    overview.write_text(f"""## Description

{args.description or "_(à compléter)_"}

## Workspace

| Chemin | Rôle |
|---|---|
| `{workspace}` | Workspace de code |

Volet PM **co-localisé** (RM1942/RM1949) : `.mmi-pm/` réel à la racine du workspace,
versionné par le repo `{gitlab_group_ns}/{core_repo}` ; côté repo PM,
`{project_root}` n'est qu'un symlink d'index vers ce dossier.
Symlinks : `.mmi-pm/workspace` → `..` ; `docs` → `.mmi-pm/docs`.

## Aspects documentés
- [overview.md](overview.md)
{'- [environments.md](environments.md)' if args.with_environments else ''}
""", encoding="utf-8")
    print(f"  ✓ meta.yml + overview.md (prose) écrits")

    if args.with_environments:
        env_path = mmi_dir / "project" / "environments.md"
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

    # 4b. Repo -core GitLab + publication du volet PM (source unique : pm-workspace-coloc)
    coloc = load_coloc()
    gid = coloc.ensure_group(gitlab_group_ns, False)
    coloc.ensure_repo(gid, core_repo, False)
    ok = coloc.git_core_publish(
        workspace, ".mmi-pm", gitlab_group_ns, core_repo, False,
        msg=f"init {core_repo} : structure PM (.mmi-pm reel) — pm-project-new (RM2228)")
    if not ok:
        sys.exit("ERREUR : publication du repo -core échouée (voir ci-dessus)")

    # 4c. Branches protégées (RM2057) — dès que la branche existe, pas plus tard.
    protect_project_repos(workspace, False)

    # 5. Symlinks (modèle co-localisé, RM2228) :
    #    - projects/<C>/projects/<S> = symlink d'INDEX → <ws>/.mmi-pm (résolveur)
    #    - .mmi-pm/workspace → .. (relatif : suit le workspace s'il est déplacé)
    #    - docs → .mmi-pm/docs (confort, RM2043)
    project_root.parent.mkdir(parents=True, exist_ok=True)
    project_root.symlink_to(mmi_dir)
    ws_link = mmi_dir / "workspace"
    if not (ws_link.exists() or ws_link.is_symlink()):
        ws_link.symlink_to(Path(".."))
    docs_link = workspace / "docs"
    if docs_link.exists() or docs_link.is_symlink():
        print(f"  · {docs_link} existe déjà, skip")
    else:
        docs_link.symlink_to(Path(".mmi-pm") / "docs")
    print(f"  ✓ symlink d'index {project_root} → {mmi_dir} (+ workspace→.., docs/)")

    # 5b. Hook git post-commit (RM2035) : report auto de la conso → Redmine à chaque commit.
    #     Délégué au script idempotent pm-hooks-install (source unique de la logique d'install).
    hooks_install = Path(__file__).resolve().parent / "pm-hooks-install.py"
    subprocess.run([sys.executable, str(hooks_install), "--repo", str(workspace)], check=False)

    # 6. Bootstrap
    if not args.no_bootstrap:
        bootstrap_script = Path(__file__).parent / "pm-project-bootstrap.py"
        cmd = [sys.executable, str(bootstrap_script), str(project_root)]
        if not args.interactive_bootstrap:
            cmd.append("--yes")
        print(f"\n  ► Lancement bootstrap ({'interactif' if args.interactive_bootstrap else '--yes'}) …\n")
        subprocess.run(cmd, check=False)

    # 6b. Publier le delta (tâches du bootstrap + symlink workspace) dans le repo -core.
    coloc.git_core_publish(
        workspace, ".mmi-pm", gitlab_group_ns, core_repo, False,
        msg="pm(bootstrap): tâches initiales + liens — pm-project-new (RM2228)")

    # Verbe symétrique de `ws-init` : tout ce qui précède a écrit sous l'identité de
    # l'appelant (.mmi-pm/, tâches du bootstrap, .git du repo -core) — on repasse le
    # modèle de perms pour refermer proprement. No-op sur un workspace hors modèle.
    pm_ws_skeleton.apply_perms(workspace, args.dry_run)

    print(f"\n✓ Projet PM {args.client}/{args.slug} prêt.")
    print(f"  → cd {workspace}  # workspace de code")
    print(f"  → pm-task-list.py  # depuis le workspace, auto-detect")


if __name__ == "__main__":
    main()
