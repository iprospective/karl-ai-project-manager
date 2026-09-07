#!/usr/bin/env python3
"""pm-repo-new — crée un dépôt sur la forge, conforme aux NORMS, sans étape manuelle.

Depuis RM3016 : `--forge github` (organisation ou utilisateur, `owner/repo`), `--branches`
pour ne pousser que certaines branches, `--remote` pour ne pas toucher à `origin`.

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

    pm-repo-new --forge github --path iprospective/atombox --description "AtomBox" \\
                --push-from repos/atombox-webmail.git --branches main,dev --remote github
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pm_paths import PMConfig  # noqa: E402  — charge le .env (et dépouille les quotes)
import pm_license   # RM3030 : la licence fait partie de la naissance d'un dépôt
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


# ── GitHub (RM3016) ──────────────────────────────────────────────────────────────
# Adressage owner/repo, pas d'id numérique ; l'owner est une ORGANISATION ou un UTILISATEUR,
# et l'API de création n'est pas la même. Le jeton vient de GITHUB_TOKEN (.env utilisateur
# `~/.config/mmi-pm/.env` d'abord — identité par dev, RM2497 — sinon le .env d'instance).

def gh_owner(forge, token, owner):
    """'org' | 'user' — par lecture, jamais deviné (tripwire #14 : le chemin exact)."""
    st, data, raw = forge.api("GET", f"/orgs/{owner}", token)
    if st == 200 and isinstance(data, dict):
        return "org"
    st, data, raw = forge.api("GET", f"/users/{owner}", token)
    if st == 200 and isinstance(data, dict):
        return "user"
    die(f"owner GitHub '{owner}' introuvable (HTTP {st}) : {str(raw)[:200]}")


def gh_repo_exists(forge, token, full_path):
    st, data, raw = forge.api("GET", f"/repos/{full_path}", token)
    if st == 200 and isinstance(data, dict):
        return data
    if st == 404:
        return None
    die(f"lecture du dépôt GitHub (HTTP {st}) : {str(raw)[:200]}")


def gh_create(forge, token, owner, kind, name, args):
    fields = {"name": name, "private": args.visibility != "public", "auto_init": False,
              "has_wiki": False, "has_projects": False}
    if args.description:
        fields["description"] = args.description
    path = f"/orgs/{owner}/repos" if kind == "org" else "/user/repos"
    st, data, raw = forge.api("POST", path, token, fields=fields)
    if st not in (200, 201) or not isinstance(data, dict):
        die(f"création GitHub refusée (HTTP {st}) : {str(raw)[:300]}")
    return data


def gh_default_branch(forge, token, full_path, branch):
    """GitHub prend pour défaut la première branche poussée : on fixe la nôtre après le push."""
    st, data, raw = forge.api("PATCH", f"/repos/{full_path}", token, fields={"default_branch": branch})
    if st != 200:
        out.warn(f"branche par défaut non fixée (HTTP {st}) : {str(raw)[:200]}")


def gh_protect(forge, token, full_path, branch, dry):
    """Protection de `branch` : pas de push direct, une PR. Sur un dépôt PRIVÉ d'un plan
    gratuit GitHub la refuse (HTTP 403/404) : on le dit, le dépôt EST créé."""
    if dry:
        say(f"[dry] PUT /repos/{full_path}/branches/{branch}/protection")
        return True
    st, data, raw = forge.api("PUT", f"/repos/{full_path}/branches/{branch}/protection", token, fields={
        "required_status_checks": None, "enforce_admins": False,
        "required_pull_request_reviews": {"required_approving_review_count": 0},
        "restrictions": None, "allow_force_pushes": False, "allow_deletions": False})
    if st in (200, 201):
        out.info(f"  {branch} : protégée (PR obligatoire, pas de force-push)")
        return True
    out.warn(f"protection de {branch} refusée (HTTP {st}) — plan GitHub ou droits : {str(raw)[:160]}")
    return False


def check_push_source(local):
    """Valide `--push-from` AVANT toute création.

    Sinon un chemin erroné laisse derrière lui un projet vide sur la forge : l'échec
    arrive après le POST, et rien ne le nettoie.
    """
    local = Path(local).resolve()
    if not (local / "HEAD").is_file() and not (local / ".git").exists():
        die(f"--push-from : '{local}' n'est pas un dépôt git (ni bare, ni worktree).")
    return local


def ensure_license(local, license_opt, holder, dry, warn=say):
    """RM3030 : un dépôt naît avec sa licence. Choix = --license, sinon le `license:` du projet PM qui contient le dépôt,
    sinon la question en terminal, sinon `proprietary` (rien n'est publié). Écrit + committe LICENSE si le dépôt n'en a pas."""
    local = Path(local).resolve()
    if any((local / n).exists() for n in ("LICENSE", "LICENSE.md", "LICENSE.txt", "COPYING")):
        return None
    chosen = None
    if not license_opt:
        ov = pm_license.project_overview_from_workspace(local)
        chosen = pm_license.read_from_overview(ov) if ov else None
        if chosen:
            say(f"licence lue dans le projet PM : {chosen}")
    if not chosen:
        chosen = pm_license.choose(license_opt, warn=lambda m: warn("⚠ " + m))
    if dry:
        say(f"[dry] écrirait LICENSE ({chosen}) dans {local} et le committerait")
        return chosen
    written = pm_license.write_license(local, chosen, holder)
    if written:
        files = ["LICENSE"] + (["NOTICE"] if (local / "NOTICE").exists() else [])
        r = subprocess.run(["git", "-C", str(local), "add", "--"] + files, capture_output=True, text=True)
        if r.returncode == 0:
            r = subprocess.run(["git", "-C", str(local), "commit", "-q", "-m", f"chore: licence {chosen} (LICENSE)", "--"] + files, capture_output=True, text=True)
        if r.returncode != 0:
            die(f"LICENSE écrit mais non committé : {(r.stderr or r.stdout).strip()[:200]}")
        say(f"LICENSE ({chosen}) écrit et committé dans {local}")
    return chosen


def push_from(local, full_path, default_branch, dry, alias="gitlab", branches=None, remote="origin"):
    """Pousse un dépôt local existant. Remote en alias SSH canonique — jamais HTTPS.

    RM2328 : on ne convertit pas un remote en HTTPS. L'alias (`gitlab:`, `github:` — celui
    que le registre déclare pour l'instance) reste la forme stockée ; un `url.…insteadOf`
    global fait le repli token là où la clé manque. `branches` : celles à pousser (défaut :
    la branche par défaut) ; `remote` : son nom local (RM3016 : `github` pour ne pas
    remplacer `origin`).
    """
    local = check_push_source(local)
    url = f"{alias}:{full_path}.git"
    a_pousser = [b.strip() for b in (branches or [default_branch]) if b.strip()]
    if default_branch not in a_pousser:
        a_pousser.insert(0, default_branch)
    cmds = [["git", "-C", str(local), "remote", "remove", remote],
            ["git", "-C", str(local), "remote", "add", remote, url],
            ["git", "-C", str(local), "push", "-u", remote, *a_pousser, "--tags"]]
    if dry:
        for c in cmds[1:]:
            say("[dry] " + " ".join(c))
        return
    subprocess.run(cmds[0], capture_output=True, text=True)     # absent = très bien
    for c in cmds[1:]:
        r = subprocess.run(c, capture_output=True, text=True)
        if r.returncode != 0:
            die(f"`{' '.join(c)}` a échoué : {(r.stderr or r.stdout).strip()[:300]}")
    say(f"poussé depuis {local} → {url} ({', '.join(a_pousser)} + tags, remote « {remote} »)")


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
                    help="chemin complet du projet, groupe résolu par chemin EXACT (GitHub : owner/repo)")
    ap.add_argument("--forge", default="gitlab", choices=["gitlab", "github"],
                    help="la forge cible (RM3016) ; défaut : gitlab")
    ap.add_argument("--instance", default=None,
                    help="instance du registre providers (ex. github-public) ; défaut : celle du type")
    ap.add_argument("--branches", default=None, metavar="B1,B2",
                    help="branches à pousser avec --push-from (défaut : la branche par défaut)")
    ap.add_argument("--remote", default="origin",
                    help="nom local du remote posé par --push-from (défaut : origin)")
    ap.add_argument("--description", default="")
    ap.add_argument("--visibility", default="private",
                    choices=["private", "internal", "public"])
    ap.add_argument("--default-branch", default="main")
    ap.add_argument("--push-from", metavar="CHEMIN",
                    help="dépôt local (bare ou worktree) à pousser tel quel")
    ap.add_argument("--license", default=None, metavar="SPDX",
                    help="licence du code (MPL-2.0, Apache-2.0, MIT, LGPL-3.0, GPL-3.0, AGPL-3.0, proprietary) ; avec --push-from, "
                         "écrit LICENSE dans le dépôt s'il n'en a pas — sans l'option : le meta.yml du projet PM, sinon la question (TTY), sinon proprietary")
    ap.add_argument("--copyright", default=None, metavar="TITULAIRE", help="titulaire du copyright (défaut : PM_LICENSE_HOLDER ou iProspective)")
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
    alias = "gitlab" if args.forge == "gitlab" else "github"
    try:
        forge = get_forge(url=f"{alias}:{full_path}.git", forge=args.forge, instance=args.instance)
        token = forge.token("manager")
    except ForgeError as e:
        die(str(e))

    if args.push_from:                       # validé AVANT toute création
        check_push_source(args.push_from)
        ensure_license(args.push_from, args.license, args.copyright, args.dry_run)   # RM3030 : avant le push, dry-run compris
    branches = args.branches.split(",") if args.branches else None

    if args.forge == "github":
        return main_github(forge, token, group_path, name, full_path, args, alias, branches)

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
            push_from(args.push_from, full_path, args.default_branch, True, alias, branches, args.remote)
        if not args.no_protect:
            say("[dry] pm-protect --project-id <id-à-venir> --no-core")
        return

    proj = create_project(forge, token, name, group_id, args)
    pid, ppath = proj["id"], proj["path_with_namespace"]

    if args.push_from:
        push_from(args.push_from, ppath, args.default_branch, False, alias, branches, args.remote)
    if not args.no_protect:
        protect(pid, False)

    if args.porcelain:
        print(f"{pid} {ppath}")
    out.op("repo", extra=f"{ppath} (id {pid}, {args.visibility}, "
                         f"défaut {args.default_branch})")


def main_github(forge, token, owner, name, full_path, args, alias, branches):
    """Le chemin GitHub (RM3016) : owner résolu par lecture, refus si le dépôt existe, POST,
    push des branches choisies, branche par défaut fixée, protection si le plan le permet."""
    kind = gh_owner(forge, token, owner)
    if gh_repo_exists(forge, token, full_path):
        die(f"le dépôt GitHub '{full_path}' existe déjà — refus.",
            "pm-repo-new ne réécrit jamais un dépôt existant.")
    if args.dry_run:
        say(f"[dry] POST {'/orgs/' + owner + '/repos' if kind == 'org' else '/user/repos'}  name={name}  "
            f"private={args.visibility != 'public'}")
        if args.push_from:
            push_from(args.push_from, full_path, args.default_branch, True, alias, branches, args.remote)
            say(f"[dry] PATCH /repos/{full_path} default_branch={args.default_branch}")
        if not args.no_protect:
            gh_protect(forge, token, full_path, args.default_branch, True)
        return
    repo = gh_create(forge, token, owner, kind, name, args)
    ppath = repo.get("full_name") or full_path
    if args.push_from:
        push_from(args.push_from, ppath, args.default_branch, False, alias, branches, args.remote)
        gh_default_branch(forge, token, ppath, args.default_branch)
    if not args.no_protect:
        gh_protect(forge, token, ppath, args.default_branch, False)
    if args.porcelain:
        print(f"{repo.get('id', '-')} {ppath}")
    out.op("repo", extra=f"{ppath} sur GitHub ({args.visibility}, défaut {args.default_branch}) — {repo.get('html_url', '')}")


if __name__ == "__main__":
    main()
