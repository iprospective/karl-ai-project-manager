#!/usr/bin/env python3
"""pm-protect — applique la politique NORMS de branches protégées (RM2052).

Enforcement du tripwire #3 (aucun push direct sur une branche protégée) :
  - prod (`main`, ou `master` si elle existe) : push = personne,   merge = Maintainer
  - intégration (`dev`)                        : push = Maintainer, merge = Maintainer
  - `preprod` (si présente, flux 3 branches)   : push = personne,   merge = Maintainer
`allow_force_push=false`. Branche absente ⇒ ignorée. **Idempotent** (delete → recreate).

Token : **manager** (Maintainer requis). Projet résolu via `pm_forge` (RM2498) —
donc résolution STRICTE par match exact path_with_namespace (RM2219), comme pm-mr.
GitLab uniquement en v1 (modèle de protection Gitea/GitHub hors périmètre).
"""
import argparse
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pm_paths import PMConfig  # charge aussi .env
from pm_forge import get_forge

# Niveaux d'accès GitLab : 0=personne, 30=Developer, 40=Maintainer, 60=Admin
NONE, MAINT = 0, 40
LABEL = {0: "personne", 30: "Developer", 40: "Maintainer", 60: "Admin"}


def branch_exists(forge, pid, name, token):
    st, _, _ = forge.api("GET",
        f"/projects/{pid}/repository/branches/{urllib.parse.quote(name, safe='')}", token)
    return st == 200


def desired_policy(forge, pid, token):
    """(name, push, merge) pour chaque branche cible PRÉSENTE sur le projet."""
    prod = ("main" if branch_exists(forge, pid, "main", token)
            else "master" if branch_exists(forge, pid, "master", token) else None)
    pol = []
    if prod:
        pol.append((prod, NONE, MAINT))
    if branch_exists(forge, pid, "dev", token):
        pol.append(("dev", MAINT, MAINT))
    if branch_exists(forge, pid, "preprod", token):
        pol.append(("preprod", NONE, MAINT))
    return pol


def apply_one(forge, pid, name, push, merge, token, dry):
    if dry:
        print(f"  → [dry-run] {name:8} push={LABEL[push]}  merge={LABEL[merge]}")
        return True
    enc = urllib.parse.quote(name, safe='')
    st, _, _ = forge.api("GET", f"/projects/{pid}/protected_branches/{enc}", token)
    if st == 200:  # déjà protégée → on repose proprement au bon niveau
        forge.api("DELETE", f"/projects/{pid}/protected_branches/{enc}", token)
    st, res, _ = forge.api("POST", f"/projects/{pid}/protected_branches", token, {
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

    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=".", type=lambda s: Path(s).resolve(),
                    help="dépôt dont le remote donne le projet (défaut : cwd)")
    ap.add_argument("--project-id", type=int, help="court-circuite la résolution via le remote")
    ap.add_argument("--dry-run", action="store_true", help="montre sans appliquer")
    args = ap.parse_args()

    forge = get_forge(args.repo)
    if forge.capabilities.access_level_model != "gitlab":
        sys.exit(f"pm-protect : modèle de protection GitLab requis "
                 f"(forge '{forge.name}' hors périmètre v1).")
    token = forge.token("manager")
    pid = args.project_id or forge.resolve_project(token).id
    pol = desired_policy(forge, pid, token)
    if not pol:
        sys.exit("Aucune branche cible (prod/dev/preprod) présente sur ce projet.")

    print(f"Protection des branches — projet {pid} :")
    ok = all(apply_one(forge, pid, n, p, m, token, args.dry_run) for (n, p, m) in pol)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
