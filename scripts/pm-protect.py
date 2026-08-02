#!/usr/bin/env python3
"""pm-protect — applique la politique NORMS de branches protégées à un projet GitLab (RM2052).

DEUX POLITIQUES, selon la nature du dépôt (RM2440).

**Dépôt de CODE** — enforcement du tripwire #3 (aucun push direct sur une branche
protégée ; la livraison passe par une MR) :
  - prod (`main`, ou `master` si elle existe) : push = personne,   merge = Maintainer
  - intégration (`dev`)                        : push = Maintainer, merge = Maintainer
  - `preprod` (si présente, flux 3 branches)   : push = personne,   merge = Maintainer

**Dépôt CORE** (données PM : `.mmi-pm/` ou `.mmi-pm-client/` à la racine) :
  - prod (`main`/`master`) : push = **Developer**, merge = Maintainer

Pourquoi un core est traité à part : il ne contient aucun code, aucune revue n'a de
sens sur des tickets et des journaux, et l'historique git est déjà la trace d'audit.
Imposer une MR y produisait un objet GitLab que personne ne lit — et, en pratique, un
arriéré silencieux sur `dev` (RM2440 : 127 commits bloqués sur 9 dépôts au 2026-07-30).

Le niveau **30** n'est pas arbitraire : l'identité qui pousse est `karl-dev` (clé
`~/.ssh/id_ed25519_gitlab`, rôle *worker* = Developer). Un `push=40` — l'état trouvé sur
les 66 cores avant ce ticket — est donc équivalent à un `push=0` pour elle. Le filet de
sécurité utile reste posé dans les deux cas : `allow_force_push=false` + interdiction de
suppression ⇒ l'historique ne peut que **croître**.

Branche absente ⇒ ignorée. **Idempotent** (delete → recreate au bon niveau).

Token : **manager** (Maintainer requis pour protéger). Résout l'ID projet depuis le
remote du repo (`--repo`, défaut cwd) comme `pm-mr`, ou `--project-id`.

Usage :
    pm-protect.py                          # dépôt courant, politique auto-détectée
    pm-protect.py --repo PATH [--dry-run]
    pm-protect.py --project-id 138 --core   # force la politique core (pas de repo local)
    pm-protect.py --all-cores [--dry-run]   # tous les cores connus de l'instance
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pm_paths import PMConfig  # charge aussi .env
# Source unique de la détection « core » : pm_git. Dupliquer le test ici ferait
# diverger un jour la politique posée (pm-protect) du comportement au push (pm_git).
from pm_git import CORE_MARKERS, is_core_repo, repo_root  # noqa: E402

DEFAULT_HOST = "gitlab.iprospective.fr"
# Niveaux d'accès GitLab : 0=personne, 30=Developer, 40=Maintainer, 60=Admin
NONE, DEV, MAINT = 0, 30, 40
LABEL = {0: "personne", 30: "Developer", 40: "Maintainer", 60: "Admin"}


def base_url():
    return (os.environ.get("GITLAB_URL") or f"https://{DEFAULT_HOST}").rstrip("/")


def token_for_manager():
    tok = os.environ.get("GITLAB_MANAGER_TOKEN")
    if not tok:
        sys.exit("ERREUR : GITLAB_MANAGER_TOKEN absent du .env du PM (PAT karl manager, Maintainer).")
    return tok


def api(method, path, token, fields=None):
    url = path if path.startswith("http") else API_BASE + path
    data = urllib.parse.urlencode(fields).encode() if fields else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("PRIVATE-TOKEN", token)
    if data:
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read().decode("utf-8", "replace")
            status = r.status
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        status = e.code
    except Exception as e:
        return 0, None, str(e)
    try:
        return status, json.loads(raw), raw
    except Exception:
        return status, None, raw


def repo_path_from_remote(repo, remote="origin"):
    import subprocess
    r = subprocess.run(["git", "-C", str(repo), "remote", "get-url", remote],
                       capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"ERREUR : remote '{remote}' introuvable dans {repo}")
    url = r.stdout.strip()
    if url.endswith(".git"):
        url = url[:-4]
    if url.startswith("http"):
        path = urllib.parse.urlparse(url).path.lstrip("/")
    elif ":" in url:
        path = url.split(":", 1)[1]
    else:
        path = url
    return path.lstrip("/")


def resolve_project_id(token, repo_path):
    seg = repo_path.rstrip("/").split("/")[-1]
    st, data, raw = api("GET", f"/projects?search={urllib.parse.quote(seg)}&per_page=50&membership=true", token)
    if st != 200 or not isinstance(data, list):
        sys.exit(f"ERREUR résolution projet (HTTP {st}) : {raw[:200]}")
    for p in data:
        if p.get("path_with_namespace") == repo_path:
            return p["id"]
    for p in data:
        if str(p.get("path_with_namespace", "")).endswith(repo_path) or p.get("path") == seg:
            return p["id"]
    sys.exit(f"ERREUR : projet '{repo_path}' introuvable (search '{seg}').")


def branch_exists(pid, name, token):
    st, _, _ = api("GET", f"/projects/{pid}/repository/branches/{urllib.parse.quote(name, safe='')}", token)
    return st == 200


def desired_policy(pid, token, core=False):
    """(name, push, merge) pour chaque branche cible PRÉSENTE sur le projet.

    `core=True` ⇒ politique données PM : push direct autorisé au niveau Developer
    sur la branche de prod (cf. docstring du module). Les branches `dev` des cores
    sont **conservées** (décision Mathieu, 2026-08-01 : utiles pour dénouer un merge
    occasionnel) mais ne reçoivent plus de trafic — on les laisse au même niveau que
    pour un dépôt de code, ce qui n'a aucun effet tant que personne n'y pousse.
    """
    prod = ("main" if branch_exists(pid, "main", token)
            else "master" if branch_exists(pid, "master", token) else None)
    pol = []
    if prod:
        pol.append((prod, DEV if core else NONE, MAINT))
    if branch_exists(pid, "dev", token):
        pol.append(("dev", MAINT, MAINT))
    if branch_exists(pid, "preprod", token):
        pol.append(("preprod", NONE, MAINT))
    return pol


def iter_core_repos():
    """Chemins des dépôts core de l'instance, dédupliqués.

    Source : les workspaces déclarés dans la config PM. On part des projets connus
    (`PMConfig.iter_projects`) et on remonte au dépôt git qui porte réellement le
    dossier `.mmi-pm` — c'est le core. Les cores CLIENT (`.mmi-pm-client`) sont
    atteints en remontant d'un cran depuis le core projet quand ils existent.
    """
    cfg = PMConfig.load()
    seen = set()
    for ent, proj, _ in cfg.iter_projects():
        try:
            tasks_dir = cfg.path("tasks_dir", entity=ent, project=proj)
        except Exception:
            continue
        # `tasks_dir` passe par les symlinks PM → resolve() donne le vrai core.
        root = repo_root(tasks_dir.resolve()) if tasks_dir.exists() else None
        if root is None:
            continue
        for cand in (root, root.parent):
            if cand in seen:
                continue
            if any((cand / m).is_dir() and not (cand / m).is_symlink()
                   for m in CORE_MARKERS):
                seen.add(cand)
                yield cand
    return


def apply_one(pid, name, push, merge, token, dry):
    if dry:
        print(f"  → [dry-run] {name:8} push={LABEL[push]}  merge={LABEL[merge]}")
        return True
    enc = urllib.parse.quote(name, safe='')
    st, _, _ = api("GET", f"/projects/{pid}/protected_branches/{enc}", token)
    if st == 200:  # déjà protégée → on repose proprement au bon niveau
        api("DELETE", f"/projects/{pid}/protected_branches/{enc}", token)
    st, res, _ = api("POST", f"/projects/{pid}/protected_branches", token, {
        "name": name,
        "push_access_level": push,
        "merge_access_level": merge,
        "allow_force_push": "false",
    })
    if st in (200, 201) and isinstance(res, dict):
        pl = res.get("push_access_levels", [{}])[0].get("access_level")
        ml = res.get("merge_access_levels", [{}])[0].get("access_level")
        print(f"  ✓ {name:8} push={LABEL.get(pl, pl)}  merge={LABEL.get(ml, ml)}  force_push=off")
        return True
    print(f"  ✗ {name:8} échec (HTTP {st}) {str(res)[:160]}", file=sys.stderr)
    return False


def protect_repo(repo, token, dry, core=None, project_id=None, label=None):
    """Applique la politique à UN dépôt. Retourne True si tout est passé."""
    pid = project_id or resolve_project_id(token, repo_path_from_remote(repo))
    if core is None:
        core = is_core_repo(repo)
    pol = desired_policy(pid, token, core=core)
    if not pol:
        print(f"  ⚠ {label or pid} : aucune branche cible (prod/dev/preprod) — ignoré",
              file=sys.stderr)
        return True
    kind = "CORE (données PM)" if core else "code"
    print(f"Protection des branches — {label or ''} projet {pid} [{kind}] :")
    return all(apply_one(pid, n, p, m, token, dry) for (n, p, m) in pol)


def main():
    PMConfig.load()  # charge .env (GITLAB_*)
    global API_BASE
    API_BASE = base_url() + "/api/v4"

    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=".", type=lambda s: Path(s).resolve(),
                    help="dépôt dont le remote donne le projet (défaut : cwd)")
    ap.add_argument("--project-id", type=int, help="court-circuite la résolution via le remote")
    ap.add_argument("--all-cores", action="store_true",
                    help="applique la politique core à TOUS les dépôts core de l'instance")
    core_grp = ap.add_mutually_exclusive_group()
    core_grp.add_argument("--core", dest="core", action="store_true", default=None,
                          help="force la politique core (utile avec --project-id)")
    core_grp.add_argument("--no-core", dest="core", action="store_false",
                          help="force la politique code même si le dépôt porte un .mmi-pm")
    ap.add_argument("--dry-run", action="store_true", help="montre sans appliquer")
    args = ap.parse_args()

    token = token_for_manager()

    if args.all_cores:
        if args.project_id:
            sys.exit("ERREUR : --all-cores et --project-id sont exclusifs.")
        repos = sorted(iter_core_repos())
        if not repos:
            sys.exit("Aucun dépôt core trouvé (config PM vide ?).")
        print(f"── {len(repos)} dépôt(s) core ──")
        ok, failed = True, []
        for r in repos:
            label = str(r).replace("/zfs/workspaces/", "")
            try:
                if not protect_repo(r, token, args.dry_run, core=True, label=label):
                    ok = False
                    failed.append(label)
            except SystemExit as e:   # resolve_project_id sort en erreur : on continue
                print(f"  ✗ {label} : {e}", file=sys.stderr)
                ok, _ = False, failed.append(label)
        print(f"\n{len(repos) - len(failed)}/{len(repos)} dépôt(s) traité(s)"
              + (f" — échecs : {', '.join(failed)}" if failed else ""))
        sys.exit(0 if ok else 1)

    ok = protect_repo(args.repo, token, args.dry_run,
                      core=args.core, project_id=args.project_id)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
