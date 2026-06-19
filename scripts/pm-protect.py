#!/usr/bin/env python3
"""pm-protect — applique la politique NORMS de branches protégées à un projet GitLab (RM2052).

Enforcement du tripwire #3 (aucun commit/push direct sur une branche protégée) :
  - prod (`main`, ou `master` si elle existe) : push = personne,   merge = Maintainer
  - intégration (`dev`)                        : push = Maintainer, merge = Maintainer
  - `preprod` (si présente, flux 3 branches)   : push = personne,   merge = Maintainer
`allow_force_push=false`. Branche absente ⇒ ignorée. **Idempotent** (delete → recreate
au bon niveau).

Token : **manager** (Maintainer requis pour protéger). Résout l'ID projet depuis le
remote du repo (`--repo`, défaut cwd) comme `pm-mr`, ou `--project-id`.
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

DEFAULT_HOST = "gitlab.iprospective.fr"
# Niveaux d'accès GitLab : 0=personne, 30=Developer, 40=Maintainer, 60=Admin
NONE, MAINT = 0, 40
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


def desired_policy(pid, token):
    """(name, push, merge) pour chaque branche cible PRÉSENTE sur le projet."""
    prod = ("main" if branch_exists(pid, "main", token)
            else "master" if branch_exists(pid, "master", token) else None)
    pol = []
    if prod:
        pol.append((prod, NONE, MAINT))
    if branch_exists(pid, "dev", token):
        pol.append(("dev", MAINT, MAINT))
    if branch_exists(pid, "preprod", token):
        pol.append(("preprod", NONE, MAINT))
    return pol


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


def main():
    PMConfig.load()  # charge .env (GITLAB_*)
    global API_BASE
    API_BASE = base_url() + "/api/v4"

    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=".", type=lambda s: Path(s).resolve(),
                    help="dépôt dont le remote donne le projet (défaut : cwd)")
    ap.add_argument("--project-id", type=int, help="court-circuite la résolution via le remote")
    ap.add_argument("--dry-run", action="store_true", help="montre sans appliquer")
    args = ap.parse_args()

    token = token_for_manager()
    pid = args.project_id or resolve_project_id(token, repo_path_from_remote(args.repo))
    pol = desired_policy(pid, token)
    if not pol:
        sys.exit("Aucune branche cible (prod/dev/preprod) présente sur ce projet.")

    print(f"Protection des branches — projet {pid} :")
    ok = all(apply_one(pid, n, p, m, token, args.dry_run) for (n, p, m) in pol)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
