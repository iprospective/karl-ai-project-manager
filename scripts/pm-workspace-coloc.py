#!/usr/bin/env python3
"""pm-workspace-coloc — Co-localise les données PM d'un client dans ses workspaces (RM1942 C2/C3).

Pour un client (entité PM), exécute la conversion validée par le pilote calicote :
  - niveau client : crée le repo `<group>/<entity>-core`, matérialise
    `.mmi-pm-client/` (copie de `client/`, `memory/`, `projects_used/` depuis
    ai-projects), git init + .gitignore whitelist + commit + push ;
  - niveau projet : pour chaque `.mmi-pm` **symlink** trouvé dans le workspace,
    crée `<group>/<dossier>-core`, remplace le symlink par un **dossier réel**
    (copie de `project/`, `tasks/`, `memory/` depuis la cible), gitignore + commit + push.

Garanties :
  - **Non destructif** : ne supprime QUE le symlink `.mmi-pm` (jamais sa cible) ;
    `ai-projects` reste intact (« on garde les deux » jusqu'à la bascule C3).
  - **Idempotent** : un `.mmi-pm` déjà converti (dossier) ou un repo déjà créé est
    sauté.
  - **Anti-fuite** : refuse de committer si autre chose que `.mmi-pm[-client]/` +
    `.gitignore` est stagé (le code ne doit jamais entrer dans le repo `-core`).
  - Le **nom du dossier prime** (repo `<dossier>-core`) ; la donnée vient de la cible
    du symlink (gère les divergences nom-dossier↔slug-PM, ex. dpsync↔prestasync).

Usage :
    pm-workspace-coloc.py <entity> [--workspace DIR] [--group GROUP] [--dry-run]

`--group` = namespace GitLab (défaut : <entity>) ; créé en top-level s'il manque.
`--workspace` = dossier du workspace client (défaut : /zfs/workspaces/<entity>).
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

GITLAB_HOST = "gitlab.iprospective.fr"
GIT_ALIAS = "gitlab"  # alias SSH (~/.ssh/config) → gitlab:<path>.git
WS_ROOT = Path("/zfs/workspaces")
# .resolve() : le chemin historique est un alias symlink de .mmi-pm-core (RM1994/RM2216) ;
# les cibles des .mmi-pm résolvent vers le canonique → relative_to exige la même base.
PM_CLIENTS = Path("/zfs/workspaces/ai/project-management/projects/clients").resolve()
GITIGNORE = "/*\n!/.gitignore\n!/{name}/\n"


def run(args, **kw):
    return subprocess.run(args, capture_output=True, text=True, **kw)


_LAST_ERROR = None


def _gitlab_env():
    """Environnement pour glab : injecte GITLAB_TOKEN depuis le token manager PM
    (env, ou .env canonique via pm_paths) si la session glab n'est pas authentifiée.
    RM2228 — autonomie karl : le token OAuth interactif de glab expire, le token
    manager du .env est la source stable."""
    env = os.environ.copy()
    if not env.get("GITLAB_TOKEN"):
        tok = env.get("GITLAB_MANAGER_TOKEN")
        if not tok:
            try:
                sys.path.insert(0, str(Path(__file__).resolve().parent))
                from pm_paths import PMConfig
                PMConfig.load()  # charge le .env canonique dans os.environ
                tok = os.environ.get("GITLAB_MANAGER_TOKEN")
            except Exception:
                tok = None  # pas de .env résolvable → glab se débrouille (session)
        if tok:
            env["GITLAB_TOKEN"] = tok
    return env


def glab(path, method="GET", fields=None):
    """Appel API GitLab. Retourne les données parsées, ou None sur erreur (le
    message GitLab est stocké dans `_LAST_ERROR`). Détecte les réponses d'erreur
    structurées ({message}/{error}) que glab peut renvoyer avec un exit 0."""
    global _LAST_ERROR
    cmd = ["glab", "api", "--hostname", GITLAB_HOST, "--method", method, path]
    for k, v in (fields or {}).items():
        cmd += ["-f", f"{k}={v}"]
    r = run(cmd, env=_gitlab_env())
    data = None
    try:
        data = json.loads(r.stdout) if r.stdout.strip() else None
    except json.JSONDecodeError:
        data = None
    # Réponse d'erreur GitLab (forme {message:…} ou {error:…} sans 'id')
    if isinstance(data, dict) and ("message" in data or "error" in data) and "id" not in data:
        _LAST_ERROR = str(data.get("message") or data.get("error"))
        return None
    if r.returncode != 0:
        _LAST_ERROR = (r.stderr or r.stdout).strip()[:200] or f"exit {r.returncode}"
        return None
    return data


def current_user_id():
    u = glab("user")
    return u.get("id") if u else None


def group_id(group_path):
    res = glab(f"groups?search={group_path.split('/')[-1]}") or []
    for g in res:
        if g.get("full_path") == group_path:
            return g["id"]
    return None


def my_access(gid, uid):
    """Niveau d'accès de l'utilisateur courant sur le groupe (None si non membre)."""
    for m in (glab(f"groups/{gid}/members/all?per_page=100") or []):
        if m.get("id") == uid:
            return m.get("access_level")
    return None


def ensure_group(group_path, dry):
    gid = group_id(group_path)
    if gid:
        return gid
    if dry:
        print(f"  [dry] créerait le groupe top-level '{group_path}'")
        return "DRY"
    # top-level uniquement (pas de parent_id) — sinon adapter
    glab("groups", "POST",
         {"name": group_path, "path": group_path, "visibility": "private"})
    gid = group_id(group_path)  # re-fetch : robuste quelle que soit la réponse POST
    if gid is None:
        sys.exit(f"  ✗ création du groupe '{group_path}' impossible : {_LAST_ERROR}\n"
                 f"    (le chemin est peut-être déjà pris par un user/projet GitLab — "
                 f"choisir un autre namespace : --group <autre>)")
    print(f"  ✓ groupe top-level créé : {group_path}")
    return gid


def ensure_repo(gid, name, dry):
    """Crée le projet GitLab <gid>/<name> s'il n'existe pas. Retourne le path."""
    full = None
    if gid != "DRY":
        res = glab(f"groups/{gid}/projects?search={name}&per_page=100") or []
        for p in res:
            if p["path"] == name:
                full = p["path_with_namespace"]
                break
    if full:
        print(f"  · repo déjà présent : {full}")
        return
    if dry:
        print(f"  [dry] créerait le repo <{gid}>/{name}")
        return
    res = glab("projects", "POST",
               {"name": name, "path": name, "namespace_id": gid,
                "visibility": "private",
                "description": "Repo de structure PM (.mmi-pm) — RM1942 co-location"})
    if not res:
        sys.exit(f"  ✗ création du repo {name} impossible : {_LAST_ERROR}")
    print(f"  ✓ repo créé : {res['path_with_namespace']}")


def git(repo, *args):
    return run(["git", "-C", str(repo)] + list(args))


def coloc_dir(folder, mmi_name, src_dir, sub_dirs, group, repo, dry):
    """Matérialise <folder>/<mmi_name>/ depuis src_dir, gitignore, commit, push."""
    mmi = folder / mmi_name
    if mmi.is_dir() and not mmi.is_symlink():
        print(f"  · {folder.name}/{mmi_name} déjà matérialisé — skip")
        return
    print(f"  → {folder.relative_to(WS_ROOT)} : {mmi_name} ← {src_dir.relative_to(PM_CLIENTS.parent)}")
    if dry:
        present = [d for d in sub_dirs if (src_dir / d).is_dir()]
        print(f"    [dry] copierait {present} ; repo {group}/{repo} ; gitignore whitelist {mmi_name}")
        return
    if mmi.is_symlink():
        mmi.unlink()  # retire le symlink SEUL — la cible (ai-projects) reste
    mmi.mkdir(exist_ok=True)
    for d in sub_dirs:
        s = src_dir / d
        if s.is_dir():
            run(["cp", "-a", str(s), str(mmi) + "/"])
    # meta.yml vit à la racine du volet PM depuis RM1994 (frontmatter → meta.yml) :
    # sans lui, pm-env-init & co. ne trouvent plus le manifeste (RM2216).
    meta = src_dir / "meta.yml"
    if meta.is_file():
        run(["cp", "-a", str(meta), str(mmi) + "/"])
    git_core_publish(folder, mmi_name, group, repo, dry,
                     msg=f"init {repo} : structure PM ({mmi_name} reel) — RM1942 co-location")


def git_core_publish(folder, mmi_name, group, repo, dry, msg=None):
    """Publie <folder>/<mmi_name>/ dans le repo -core : .gitignore whitelist,
    git init + remote origin, stage EXPLICITE (.gitignore + <mmi_name>), anti-fuite,
    commit + push. Idempotent (re-appelable pour committer un delta, ex. bootstrap).
    Réutilisée par pm-project-new (RM2228). Retourne True si OK / rien à faire."""
    if dry:
        print(f"    [dry] publierait {mmi_name} → {group}/{repo} "
              f"(gitignore whitelist, init, commit, push)")
        return True
    gi = folder / ".gitignore"
    whitelist = GITIGNORE.format(name=mmi_name)
    if gi.is_file() and gi.read_text(encoding="utf-8", errors="replace") != whitelist:
        # Préserver un .gitignore existant (ex. code redmine, 44 lignes) avant d'écrire la whitelist
        bak = folder / ".gitignore.pre-coloc"
        if not bak.exists():
            gi.rename(bak)
            print(f"    · .gitignore existant sauvegardé → {bak.name}")
    if not gi.is_file() or gi.read_text(encoding="utf-8", errors="replace") != whitelist:
        gi.write_text(whitelist, encoding="utf-8")
    if not (folder / ".git").exists():
        git(folder, "init", "-q", "-b", "main")
    if git(folder, "remote", "get-url", "origin").returncode != 0:
        git(folder, "remote", "add", "origin", f"{GIT_ALIAS}:{group}/{repo}.git")
    else:
        git(folder, "remote", "set-url", "origin", f"{GIT_ALIAS}:{group}/{repo}.git")
    # Stage EXPLICITE (tripwire git-mep #2 : jamais -A) ; la whitelist fait le reste.
    git(folder, "add", "--", ".gitignore", mmi_name)
    staged = git(folder, "diff", "--cached", "--name-only").stdout.split()
    leaked = [f for f in staged if not (f == ".gitignore" or f.startswith(mmi_name + "/"))]
    if leaked:
        print(f"    ⚠⚠ CODE STAGÉ ({leaked[:3]}…) — ABANDON de ce repo")
        return False
    if not staged:
        print(f"    · rien à committer ({mmi_name} à jour)")
        return True
    git(folder, "commit", "-q", "-m",
        (msg or f"pm(core): publie {mmi_name}") +
        "\n\nCo-Authored-By: Claude Fable 5 <noreply@anthropic.com>")
    git(folder, "branch", "-M", "main")
    p = git(folder, "push", "-u", "origin", "main")
    sha = git(folder, "rev-parse", "--short", "HEAD").stdout.strip()
    print(f"    ✓ {len(staged)} fichiers PM, push {sha} "
          f"({'OK' if p.returncode == 0 else 'ÉCHEC: ' + p.stderr.strip()[:80]})")
    return p.returncode == 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("entity")
    ap.add_argument("--workspace", help="Dossier workspace client (défaut /zfs/workspaces/<entity>)")
    ap.add_argument("--group", help="Namespace GitLab (défaut <entity>)")
    ap.add_argument("--skip", action="append", default=[],
                    help="Nom de dossier projet à NE PAS migrer (ex. projet actif). Répétable.")
    ap.add_argument("--no-client", action="store_true",
                    help="Ne pas créer le client-core / .mmi-pm-client (entité produit à projet unique, Q4).")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    ws = Path(args.workspace) if args.workspace else WS_ROOT / args.entity
    group = args.group or args.entity
    pm_client = PM_CLIENTS / args.entity
    if not ws.is_dir():
        sys.exit(f"ERREUR : workspace introuvable : {ws}")
    if not pm_client.is_dir():
        sys.exit(f"ERREUR : données PM introuvables : {pm_client}")

    print(f"== co-location de '{args.entity}' (workspace {ws}, groupe GitLab {group}) ==")
    gid = ensure_group(group, args.dry_run)

    # Préflight droits : créer un repo dans un groupe exige Maintainer (40).
    # (Un groupe qu'on vient de créer nous donne Owner d'office.)
    if gid not in (None, "DRY"):
        uid = current_user_id()
        lvl = my_access(gid, uid)
        if lvl is not None and lvl < 40:
            names = {30: "Developer", 20: "Reporter", 10: "Guest"}
            sys.exit(
                f"  ✗ Droits insuffisants : tu es {names.get(lvl, lvl)} (niveau {lvl}) "
                f"sur le groupe '{group}', or créer un repo exige Maintainer (40).\n"
                f"    → fais-toi passer Maintainer/Owner sur '{group}' (ou fais créer "
                f"les repos par root), puis relance.")

    # Niveau client (sauf --no-client : entités produit à projet unique, Q4)
    if args.no_client:
        print("-- client -- (sauté : --no-client)")
    else:
        print("-- client --")
        ensure_repo(gid, f"{args.entity}-core", args.dry_run)
        coloc_dir(ws, ".mmi-pm-client", pm_client, ["client", "memory", "projects_used"],
                  group, f"{args.entity}-core", args.dry_run)

    # Niveau projet : chaque .mmi-pm symlink du workspace
    print("-- projets --")
    links = sorted(p for p in ws.rglob(".mmi-pm")
                   if p.is_symlink() and len(p.relative_to(ws).parts) <= 3)
    if not links:
        print("  (aucun .mmi-pm symlink restant — déjà co-localisé ?)")
    for link in links:
        folder = link.parent
        if folder.name in args.skip:
            print(f"  · {folder.name} SKIP (--skip ; projet actif ?)")
            continue
        src = link.resolve()  # cible ai-projects (donnée PM réelle)
        repo = f"{folder.name}-core"
        ensure_repo(gid, repo, args.dry_run)
        coloc_dir(folder, ".mmi-pm", src, ["project", "tasks", "memory", "docs"],
                  group, repo, args.dry_run)

    print("== terminé ==" + (" (DRY-RUN, rien écrit)" if args.dry_run else ""))


if __name__ == "__main__":
    main()
