#!/usr/bin/env python3
"""pm-mr — outillage Merge Request GitLab fiable (RM1871).

Sous-commandes :
  create <RMid> [--repo PATH] [--target BR] [--status STATUT] [--no-push]
      push la branche courante + crée (ou réutilise) la MR vers `--target`
      (défaut : `integration_branch` de l'overview, sinon `dev`), pose les CF
      Redmine GIT Branche (id 3) + GIT PR (id 4), option : passe le ticket à
      `--status` (note auto). Idempotent : MR déjà ouverte ⇒ renvoyée.
  merge <iid> [--repo PATH] [--squash]
      merge la MR `iid`. **Conserve la branche source** (remove_source_branch=false,
      règle NORMS). Idempotent : déjà mergée ⇒ signalé sans planter.
  get <iid> [--repo PATH]
      état (state + web_url + branches) de la MR.

Pourquoi ce script (vs `glab`) :
  - `glab` ne mappe pas un remote en **alias SSH** (`gitlab:…`) vers le host.
  - Apache iProspective **rejette les `%2F`** d'un chemin projet → 404 ⇒ on résout
    l'**ID NUMÉRIQUE** du projet via `GET /projects?search=…`.
  - L'API renvoie parfois un **corps vide** sur succès ⇒ on re-GET pour confirmer.
Tape l'API REST GitLab en direct (urllib + token lu de la config glab / .env).
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


# ── Auth / config GitLab ──────────────────────────────────────────────────────
def base_url():
    """URL GitLab depuis le `.env` du PM (GITLAB_URL). PMConfig.load() l'a chargé."""
    return (os.environ.get("GITLAB_URL") or f"https://{DEFAULT_HOST}").rstrip("/")


# Deux identités GitLab de karl, deux PAT distincts dans le `.env` (RM1871) :
#  - manager : casquette mainteneur/chef de projet — MERGE les MR, gère les projets ;
#  - worker  : casquette dev — push des branches, CRÉE des MR.
TOKEN_ENV = {"manager": "GITLAB_MANAGER_TOKEN", "worker": "GITLAB_WORKER_TOKEN"}


def token_for(role):
    """PAT de karl pour le rôle ('manager' | 'worker'), depuis le `.env` du PM."""
    var = TOKEN_ENV[role]
    tok = os.environ.get(var)
    if not tok:
        sys.exit(f"ERREUR : {var} absent du .env du PM (PAT karl-{role}, scope api).")
    return tok


def api(method, path, token, fields=None):
    """Requête REST. Retourne (status, parsed_json|None, raw). Jamais d'exception
    sur 4xx/5xx (on renvoie le status)."""
    url = path if path.startswith("http") else API_BASE + path
    data = urllib.parse.urlencode(fields, doseq=True).encode() if fields else None
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


# ── Résolution du projet (ID numérique, anti-%2F) ────────────────────────────
def repo_path_from_remote(repo, remote="origin"):
    """Chemin `owner/.../repo` déduit de l'URL du remote (alias SSH, ssh, https)."""
    import subprocess
    r = subprocess.run(["git", "-C", str(repo), "remote", "get-url", remote],
                       capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"ERREUR : remote '{remote}' introuvable dans {repo}")
    url = r.stdout.strip()
    if url.endswith(".git"):
        url = url[:-4]
    # alias SSH "gitlab:owner/...repo" | "git@host:owner/...repo" | "https://host/owner/...repo"
    if url.startswith("http"):
        path = urllib.parse.urlparse(url).path.lstrip("/")
    elif ":" in url:
        path = url.split(":", 1)[1]
    else:
        path = url
    return path.lstrip("/")


def resolve_project_id(token, repo_path):
    seg = repo_path.rstrip("/").split("/")[-1]
    status, data, raw = api("GET", f"/projects?search={urllib.parse.quote(seg)}&per_page=50&membership=true", token)
    if status != 200 or not isinstance(data, list):
        sys.exit(f"ERREUR résolution projet (HTTP {status}) : {raw[:200]}")
    for p in data:
        if p.get("path_with_namespace") == repo_path:
            return p["id"], p
    # fallback : match souple sur la fin du chemin
    for p in data:
        if str(p.get("path_with_namespace", "")).endswith(repo_path) or p.get("path") == seg:
            return p["id"], p
    sys.exit(f"ERREUR : projet '{repo_path}' introuvable (search '{seg}').")


def current_branch(repo):
    import subprocess
    return subprocess.run(["git", "-C", str(repo), "rev-parse", "--abbrev-ref", "HEAD"],
                          capture_output=True, text=True).stdout.strip()


def integration_branch(repo_path):
    """Branche d'intégration via overview.md du projet (défaut 'dev')."""
    return "dev"  # défaut robuste ; raffinable via overview.md (cf. RM2030)


# ── Commandes ────────────────────────────────────────────────────────────────
def cmd_get(args, token):
    pid, _ = resolve_project_id(token, repo_path_from_remote(args.repo))
    status, mr, raw = api("GET", f"/projects/{pid}/merge_requests/{args.iid}", token)
    if status != 200 or not mr:
        sys.exit(f"ERREUR get MR !{args.iid} (HTTP {status}) : {raw[:200]}")
    print(f"MR !{mr['iid']} [{mr['state']}] {mr['source_branch']} → {mr['target_branch']}")
    print(f"  {mr['web_url']}")


def cmd_create(args, token):
    repo = args.repo
    rpath = repo_path_from_remote(repo)
    pid, _ = resolve_project_id(token, rpath)
    src = current_branch(repo)
    if src in ("HEAD", ""):
        sys.exit("ERREUR : HEAD détaché — pas de branche courante.")
    tgt = args.target or integration_branch(rpath)
    if src == tgt:
        sys.exit(f"ERREUR : branche courante == cible ({tgt}).")

    if not args.no_push:
        import subprocess
        p = subprocess.run(["git", "-C", str(repo), "push", "-u", "origin", src],
                           capture_output=True, text=True)
        if p.returncode != 0:
            sys.exit(f"ERREUR push : {(p.stderr or p.stdout).strip()}")
        print(f"✓ push {src} → origin")

    # Idempotence : MR ouverte déjà existante ?
    st, lst, _ = api("GET", f"/projects/{pid}/merge_requests?source_branch={urllib.parse.quote(src)}"
                            f"&target_branch={urllib.parse.quote(tgt)}&state=opened", token)
    mr = lst[0] if (st == 200 and isinstance(lst, list) and lst) else None
    if mr:
        print(f"↻ MR déjà ouverte : !{mr['iid']}")
    else:
        st, mr, raw = api("POST", f"/projects/{pid}/merge_requests", token, fields={
            "source_branch": src, "target_branch": tgt,
            "title": args.title or f"RM{args.rm_id} — {src}",
            "description": args.description or f"Ref RM{args.rm_id}.",
            "remove_source_branch": "false",
        })
        if not mr:  # corps vide / ambigu → re-GET pour confirmer
            st2, lst2, _ = api("GET", f"/projects/{pid}/merge_requests?source_branch={urllib.parse.quote(src)}"
                                      f"&target_branch={urllib.parse.quote(tgt)}&state=opened", token)
            mr = lst2[0] if (st2 == 200 and isinstance(lst2, list) and lst2) else None
        if not mr:
            sys.exit(f"ERREUR création MR (HTTP {st}) : {raw[:200]}")
        print(f"✓ MR !{mr['iid']} créée : {src} → {tgt}")
    print(f"  {mr['web_url']}")

    # CF Redmine GIT Branche (3) + GIT PR (4) + statut optionnel
    try:
        import redmine_utils
        cfs = []
        for name, val in (("GIT Branche", src), ("GIT PR", mr["web_url"])):
            cid = redmine_utils.cf_id_by_name(name)
            if cid:
                cfs.append({"id": cid, "value": val})
        if cfs:
            redmine_utils.update_issue_fields(args.rm_id, custom_fields=cfs)
            print(f"✓ CF Redmine posés (GIT Branche / GIT PR) sur #{args.rm_id}")
    except Exception as e:
        print(f"  ⚠ CF Redmine non posés : {e}", file=sys.stderr)

    if args.status:
        import subprocess
        scr = Path(__file__).resolve().parent / "pm-task-status-update.py"
        subprocess.run([sys.executable, str(scr), str(args.rm_id), args.status,
                        "--note", f"MR !{mr['iid']} ouverte vers {tgt} : {mr['web_url']}"],
                       check=False)


def cmd_merge(args, token):
    pid, _ = resolve_project_id(token, repo_path_from_remote(args.repo))
    base = f"/projects/{pid}/merge_requests/{args.iid}"
    st, mr, raw = api("GET", base, token)
    if st != 200 or not mr:
        sys.exit(f"ERREUR : MR !{args.iid} introuvable (HTTP {st}).")
    if mr["state"] == "merged":
        print(f"↻ MR !{args.iid} déjà mergée ({mr['source_branch']} → {mr['target_branch']}).")
        return
    if mr["state"] != "opened":
        sys.exit(f"ERREUR : MR !{args.iid} en état '{mr['state']}' (pas 'opened').")
    fields = {"should_remove_source_branch": "false"}  # CONSERVE la branche (NORMS)
    if args.squash:
        fields["squash"] = "true"
    st, res, raw = api("PUT", base + "/merge", token, fields=fields)
    state = res.get("state") if res else None
    if state != "merged":  # corps vide/ambigu → re-GET
        st2, mr2, _ = api("GET", base, token)
        state = mr2.get("state") if mr2 else None
    if state == "merged":
        print(f"✓ MR !{args.iid} mergée → {mr['target_branch']} (branche {mr['source_branch']} conservée).")
    else:
        sys.exit(f"ERREUR merge MR !{args.iid} (HTTP {st}, state={state}) : {raw[:200]}")


def main():
    PMConfig.load()  # charge .env (GITLAB_*, REDMINE_*, …)
    global API_BASE
    API_BASE = base_url() + "/api/v4"

    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    pc = sub.add_parser("create", help="push + crée/réutilise la MR + CF")
    pc.add_argument("rm_id", type=int)
    pc.add_argument("--repo", default=".", type=lambda s: Path(s).resolve())
    pc.add_argument("--target", help="branche cible (défaut : intégration / dev)")
    pc.add_argument("--title")
    pc.add_argument("--description")
    pc.add_argument("--status", help="passe le ticket à ce statut (note auto)")
    pc.add_argument("--no-push", action="store_true")

    pm = sub.add_parser("merge", help="merge une MR (conserve la branche)")
    pm.add_argument("iid", type=int)
    pm.add_argument("--repo", default=".", type=lambda s: Path(s).resolve())
    pm.add_argument("--squash", action="store_true")

    pg = sub.add_parser("get", help="état d'une MR")
    pg.add_argument("iid", type=int)
    pg.add_argument("--repo", default=".", type=lambda s: Path(s).resolve())

    args = ap.parse_args()
    # Token selon le rôle : worker (push/MR), manager (merge/gestion).
    role = {"create": "worker", "merge": "manager", "get": "worker"}[args.cmd]
    {"create": cmd_create, "merge": cmd_merge, "get": cmd_get}[args.cmd](args, token_for(role))


if __name__ == "__main__":
    main()
