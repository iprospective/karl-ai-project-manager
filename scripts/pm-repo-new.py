#!/usr/bin/env python3
"""pm-repo-new — crée un dépôt sur la forge, conforme aux NORMS, sans étape manuelle.

Le PM outillait la vie d'un dépôt (`pm-mr`, `pm-promote`, `pm-protect`…) mais pas sa
naissance : créer un projet se faisait à la main, à l'UI ou au `curl`. C'est le cas visé
par le tripwire #1 du KERNEL — pas d'outil = trou à combler, pas exception manuelle.

Enchaînement (celui qui a marché en one-off sur RM2638, désormais outillé) :

    1. résolution du GROUPE par chemin exact          (tripwire #14, jamais par basename)
    2. refus si le projet existe déjà                 (aucun écrasement)
    3. POST /projects                                 (privé par défaut, default_branch)
    4. --push-from : remote en alias SSH canonique `gitlab:` + push --tags   (RM2328)
    5. pm-protect --project-id <id> --no-core         (réutilisé, pas réimplémenté)

L'id du projet créé n'est JAMAIS deviné : il sort de la réponse de l'API et ressort par
`--porcelain` (tripwire #13).

Exemples :

    pm-repo-new --path prestashop/prestashop-module-staticblock \\
                --description "Module StaticBlock (FMM) patché MMI"

    pm-repo-new --path prestashop/prestashop-module-mmi-discount \\
                --push-from repos/mmi_discount.git --porcelain

    pm-repo-new --path prestashop/x --dry-run
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pm_paths import PMConfig  # noqa: E402  — charge le .env (et dépouille les quotes)
from pm_forge import ForgeError, get_forge  # noqa: E402
from pm_output import out  # noqa: E402

SCRIPTS = Path(__file__).resolve().parent
PATH_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._\-]*$")


def die(msg, remede=None):
    out.fail(msg, remede)


def say(msg):
    """Ligne TOUJOURS émise — dry-run, confirmation de push.

    `out.info` est verbose-only : parfait pour du détail, inutilisable pour un
    `--dry-run`, dont l'unique raison d'être est de montrer ce qui serait fait.
    Sur `--porcelain`, tout part sur stderr pour que stdout ne porte que la valeur.
    """
    (sys.stderr if out.porcelain else sys.stdout).write(str(msg) + "\n")


def split_path(full):
    """`groupe/sous-groupe/nom` → (chemin_du_groupe, nom). Refuse le reste."""
    parts = [p for p in (full or "").strip("/").split("/") if p]
    if len(parts) < 2:
        die(f"--path attend `<groupe>/<nom>` (reçu : '{full}'). "
            "Un projet hors groupe n'est pas prévu : les NORMS rangent tout par groupe.")
    for p in parts:
        if not PATH_RE.match(p):
            die(f"segment de chemin invalide : '{p}'")
    return "/".join(parts[:-1]), parts[-1]


def resolve_group(forge, token, group_path):
    """ID du groupe par match EXACT de `full_path` — jamais par basename (tripwire #14).

    L'incident RM2219/RM2410 vient précisément de là : deux groupes peuvent partager un
    basename, et `?search=` en renvoie plusieurs. On ne garde que l'égalité stricte.
    """
    leaf = group_path.rsplit("/", 1)[-1]
    st, data, raw = forge.api("GET", f"/groups?search={leaf}&per_page=100"
                                     "&all_available=true", token)
    if st != 200 or not isinstance(data, list):
        die(f"recherche du groupe (HTTP {st}) : {raw[:200]}")
    exact = [g for g in data if g.get("full_path") == group_path]
    if not exact:
        vus = ", ".join(sorted(g.get("full_path", "?") for g in data)[:6]) or "aucun"
        die(f"groupe '{group_path}' introuvable (ou invisible pour ce token). "
            f"Groupes vus pour '{leaf}' : {vus}")
    if len(exact) > 1:                      # ne devrait pas arriver : full_path est unique
        die(f"groupe '{group_path}' ambigu ({len(exact)} résultats) — refus.")
    return exact[0]["id"]


def project_exists(forge, token, full_path):
    """Le projet existe-t-il déjà ? Match EXACT de `path_with_namespace`."""
    leaf = full_path.rsplit("/", 1)[-1]
    st, data, raw = forge.api("GET", f"/projects?search={leaf}&per_page=100"
                                     "&simple=true", token)
    if st != 200 or not isinstance(data, list):
        die(f"recherche du projet (HTTP {st}) : {raw[:200]}")
    for p in data:
        if p.get("path_with_namespace") == full_path:
            return p
    return None


def create_project(forge, token, name, group_id, args):
    fields = {
        "name": name,
        "path": name,
        "namespace_id": group_id,
        "visibility": args.visibility,
        "default_branch": args.default_branch,
        "initialize_with_readme": "false",
    }
    if args.description:
        fields["description"] = args.description
    st, data, raw = forge.api("POST", "/projects", token, fields=fields)
    if st not in (200, 201) or not isinstance(data, dict):
        die(f"création refusée (HTTP {st}) : {raw[:300]}")
    return data


def push_from(local, full_path, default_branch, dry):
    """Pousse un dépôt local existant. Remote en alias SSH canonique — jamais HTTPS.

    RM2328 : on ne convertit pas un remote en HTTPS. L'alias `gitlab:` reste la forme
    stockée ; un `url.…insteadOf` global fait le repli token là où la clé manque.
    """
    local = Path(local).resolve()
    if not (local / "HEAD").is_file() and not (local / ".git").exists():
        die(f"--push-from : '{local}' n'est pas un dépôt git (ni bare, ni worktree).")
    url = f"gitlab:{full_path}.git"
    cmds = [["git", "-C", str(local), "remote", "remove", "origin"],
            ["git", "-C", str(local), "remote", "add", "origin", url],
            ["git", "-C", str(local), "push", "-u", "origin", default_branch, "--tags"]]
    if dry:
        for c in cmds[1:]:
            say("[dry] " + " ".join(c))
        return
    subprocess.run(cmds[0], capture_output=True, text=True)     # absent = très bien
    for c in cmds[1:]:
        r = subprocess.run(c, capture_output=True, text=True)
        if r.returncode != 0:
            die(f"`{' '.join(c)}` a échoué : {(r.stderr or r.stdout).strip()[:300]}")
    say(f"poussé depuis {local} → {url} (branche {default_branch} + tags)")


def protect(project_id, dry):
    """Protections de branche : on APPELLE pm-protect, on ne le réimplémente pas."""
    cmd = [sys.executable, str(SCRIPTS / "pm-protect.py"),
           "--project-id", str(project_id), "--no-core"]
    if dry:
        cmd.append("--dry-run")
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        out.warn("pm-protect a échoué (le projet EST créé) : "
                 + (r.stderr or r.stdout).strip()[:300])
        return False
    for line in (r.stdout or "").splitlines():
        if line.strip():
            out.info("  " + line.strip())
    return True


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    out.add_args(ap)
    ap.add_argument("--path", required=True, metavar="GROUPE/NOM",
                    help="chemin complet du projet, groupe résolu par chemin EXACT")
    ap.add_argument("--description", default="")
    ap.add_argument("--visibility", default="private",
                    choices=["private", "internal", "public"])
    ap.add_argument("--default-branch", default="main")
    ap.add_argument("--push-from", metavar="CHEMIN",
                    help="dépôt local (bare ou worktree) à pousser tel quel")
    ap.add_argument("--no-protect", action="store_true",
                    help="ne pas appliquer les protections de branche")
    ap.add_argument("--porcelain", action="store_true",
                    help="n'imprime que `<id> <path_with_namespace>` sur stdout")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    out.configure(args)

    PMConfig.load()                              # charge le .env (quotes dépouillées)
    group_path, name = split_path(args.path)
    full_path = f"{group_path}/{name}"
    try:
        forge = get_forge(url=f"gitlab:{full_path}.git", forge="gitlab")
        token = forge.token("manager")
    except ForgeError as e:
        die(str(e))

    existing = project_exists(forge, token, full_path)
    if existing:
        die(f"le projet '{full_path}' existe déjà (id {existing['id']}) — refus.",
            "pm-repo-new ne réécrit jamais un dépôt existant. Pour le recâbler : "
            "`pm-git-recable`. Pour le renommer : `pm-gitlab-rename`.")
    group_id = resolve_group(forge, token, group_path)

    if args.dry_run:
        say(f"[dry] POST /projects  path={full_path}  namespace_id={group_id}  "
                 f"visibility={args.visibility}  default_branch={args.default_branch}")
        if args.push_from:
            push_from(args.push_from, full_path, args.default_branch, True)
        if not args.no_protect:
            say("[dry] pm-protect --project-id <id-à-venir> --no-core")
        return

    proj = create_project(forge, token, name, group_id, args)
    pid, ppath = proj["id"], proj["path_with_namespace"]

    if args.push_from:
        push_from(args.push_from, ppath, args.default_branch, False)
    if not args.no_protect:
        protect(pid, False)

    if args.porcelain:
        print(f"{pid} {ppath}")
    out.op("repo", extra=f"{ppath} (id {pid}, {args.visibility}, "
                         f"défaut {args.default_branch})")


if __name__ == "__main__":
    main()
