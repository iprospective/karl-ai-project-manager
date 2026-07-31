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
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pm_paths import PMConfig  # charge aussi .env
from pm_output import out

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


def list_projects_paged(token):
    """Énumération paginée de /projects (membership). Nécessaire car le `?search=`
    GitLab a des FAUX NÉGATIFS silencieux (rate des projets existants — RM2219,
    cf. knowledge/gitlab/api.md)."""
    page, acc = 1, []
    while True:
        st, data, raw = api("GET", f"/projects?membership=true&simple=true"
                                   f"&per_page=100&page={page}", token)
        if st != 200 or not isinstance(data, list):
            sys.exit(f"ERREUR énumération projets (HTTP {st}) : {raw[:200]}")
        acc += data
        if len(data) < 100:
            return acc
        page += 1


def resolve_project_id(token, repo_path):
    """ID numérique par match EXACT de `path_with_namespace` — RM2219.

    JAMAIS de match souple : les basenames sont partagés entre clients
    (`infra-core` ×6, `*-core` généralisés RM1887) et l'ancien fallback
    `p.path == seg` a créé une MR sur le repo d'un AUTRE client. 0 ou >1 match
    exact = erreur explicite."""
    seg = repo_path.rstrip("/").split("/")[-1]
    # 1) search (rapide) — accepté UNIQUEMENT sur match exact du path complet
    st, data, _ = api("GET", f"/projects?search={urllib.parse.quote(seg)}"
                             f"&per_page=100&membership=true", token)
    cands = data if (st == 200 and isinstance(data, list)) else []
    exact = [p for p in cands if p.get("path_with_namespace") == repo_path]
    # 2) fallback fiable : énumération paginée complète (le search rate des projets)
    if not exact:
        cands = list_projects_paged(token)
        exact = [p for p in cands if p.get("path_with_namespace") == repo_path]
    if len(exact) == 1:
        return exact[0]["id"], exact[0]
    homonyms = sorted({p["path_with_namespace"] for p in cands if p.get("path") == seg})
    sys.exit(f"ERREUR : projet '{repo_path}' — {len(exact)} match exact "
             f"(attendu 1), pas de fallback basename (RM2219). "
             f"Homonymes '{seg}' visibles : {', '.join(homonyms) or 'aucun'}.")


def current_branch(repo):
    import subprocess
    return subprocess.run(["git", "-C", str(repo), "rev-parse", "--abbrev-ref", "HEAD"],
                          capture_output=True, text=True).stdout.strip()


def integration_branch(repo_path):
    """Branche d'intégration via overview.md du projet (défaut 'dev')."""
    return "dev"  # défaut robuste ; raffinable via overview.md (cf. RM2030)


# ── Commandes ────────────────────────────────────────────────────────────────
def cmd_merge(args, token):
    pid, proj = resolve_project_id(token, repo_path_from_remote(args.repo))
    out.info(f"→ projet {proj['path_with_namespace']} (id {pid})")
    merge_mr(pid, args.iid, token, squash=args.squash, expect_rm=args.expect_rm)


def cmd_get(args, token):
    pid, proj = resolve_project_id(token, repo_path_from_remote(args.repo))
    print(f"→ projet {proj['path_with_namespace']} (id {pid})")
    status, mr, raw = api("GET", f"/projects/{pid}/merge_requests/{args.iid}", token)
    if status != 200 or not mr:
        sys.exit(f"ERREUR get MR !{args.iid} (HTTP {status}) : {raw[:200]}")
    print(f"MR !{mr['iid']} [{mr['state']}] {mr['source_branch']} → {mr['target_branch']}"
          f" | {mr.get('detailed_merge_status')}"
          + (" | ⚠ sha:null (branche source absente)" if mr.get("sha") is None else ""))
    print(f"  {mr['web_url']}")


def cmd_create(args, token):
    # Mode --porcelain : géré par pm_output (out.configure) — ✓/info/⚠ partent
    # sur stderr, seul out.value(iid) écrit sur stdout.
    repo = args.repo
    rpath = repo_path_from_remote(repo)
    pid, proj = resolve_project_id(token, rpath)
    out.info(f"→ projet {proj['path_with_namespace']} (id {pid})")
    src = args.source or current_branch(repo)
    if src in ("HEAD", ""):
        sys.exit("ERREUR : HEAD détaché — pas de branche courante (ou --source vide).")
    # Garde anti-prédiction d'id (RM2224, tripwire #13) : une MR de ticket doit
    # partir d'une branche `<RMid>-…` du MÊME id. Une branche préfixée d'un autre
    # id = id deviné/erroné (incident RM2222 sur branche 2219-*) → refus.
    # Les branches non préfixées (dev, promotion) restent permises.
    m = re.match(r"^(\d+)-", src)
    if m and int(m.group(1)) != args.rm_id:
        sys.exit(f"ERREUR : la branche courante `{src}` porte l'id {m.group(1)} mais la MR "
                 f"est demandée pour RM{args.rm_id}. Id prédit/erroné (tripwire #13) ? "
                 f"Renomme la branche (`git branch -m {args.rm_id}-<slug>`) ou corrige le rm_id.")
    tgt = args.target or integration_branch(rpath)
    if src == tgt:
        sys.exit(f"ERREUR : branche courante == cible ({tgt}).")

    if not args.no_push:
        import subprocess
        p = subprocess.run(["git", "-C", str(repo), "push", "-u", "origin", src],
                           capture_output=True, text=True)
        if p.returncode != 0:
            sys.exit(f"ERREUR push : {(p.stderr or p.stdout).strip()}")
        out.info(f"✓ push {src} → origin")

    # Idempotence : MR ouverte déjà existante ?
    st, lst, _ = api("GET", f"/projects/{pid}/merge_requests?source_branch={urllib.parse.quote(src)}"
                            f"&target_branch={urllib.parse.quote(tgt)}&state=opened", token)
    mr = lst[0] if (st == 200 and isinstance(lst, list) and lst) else None
    if mr:
        out.info(f"↻ MR déjà ouverte : !{mr['iid']}")
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
        out.info(f"✓ MR !{mr['iid']} créée : {src} → {tgt}")
    out.op("mr", extra=f"!{mr['iid']} {src}→{tgt} {mr['web_url']}")
    if args.porcelain:
        out.value(mr["iid"])

    # Garde RM2219 : une MR saine référence le sha de sa branche source. `sha:null`
    # = branche absente de CE projet ⇒ MR créée au mauvais endroit → rollback.
    st, chk, _ = api("GET", f"/projects/{pid}/merge_requests/{mr['iid']}", token)
    if chk and chk.get("sha") is None:
        api("PUT", f"/projects/{pid}/merge_requests/{mr['iid']}", token,
            fields={"state_event": "close"})
        sys.exit(f"ERREUR : MR !{mr['iid']} sans sha — la branche `{src}` n'existe pas "
                 f"sur {proj['path_with_namespace']} (mauvaise résolution de projet ?). "
                 f"MR fermée (rollback).")

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
            # RM2219 : Redmine ignore SILENCIEUSEMENT un CF non activé sur le
            # tracker → relire et vérifier au lieu d'annoncer ✓ à l'aveugle.
            issue = redmine_utils.fetch_issue(args.rm_id)
            present = {c.get("id"): c.get("value")
                       for c in issue.get("custom_fields", [])}
            missing = [c["id"] for c in cfs if present.get(c["id"]) != c["value"]]
            if missing:
                out.warn(f"CF Redmine NON écrits (ids {missing}) — CF absents du "
                         f"tracker de #{args.rm_id} ? Poser le lien en note/manuel.")
            else:
                out.info(f"✓ CF Redmine posés et vérifiés (GIT Branche / GIT PR) sur #{args.rm_id}")
    except Exception as e:
        out.warn(f"CF Redmine non posés : {e}")

    if args.status:
        import subprocess
        scr = Path(__file__).resolve().parent / "pm-task-status-update.py"
        subprocess.run([sys.executable, str(scr), str(args.rm_id), args.status,
                        "--note", f"MR !{mr['iid']} ouverte vers {tgt} : {mr['web_url']}"],
                       check=False,
                       stdout=sys.stderr if getattr(args, "porcelain", False) else None)


    if getattr(args, "merge", False):
        # Atomique (RM2232) : merge immédiat de LA MR créée — l'iid ne sort pas d'ici ;
        # garde implicite : la branche source est celle du ticket par construction.
        # Le merge exige la casquette MANAGER (branches protégées, RM1871) — pas
        # le token worker du create.
        merge_mr(pid, mr["iid"], token_for("manager"),
                 expect_rm=args.rm_id if src.startswith(f"{args.rm_id}-") else None)

def wait_mergeable(base, iid, token, attempts=8, delay=2.0):
    """Attend la fin du calcul de mergeabilité GitLab (async : `preparing` →
    `checking` → `mergeable`). Sans ça, un `merge` lancé juste après `create`
    échoue en 422 'Branch cannot be merged' alors qu'il n'y a aucun conflit.
    Retourne le mr à jour (mergeable). Sort en erreur sur conflit, ou si toujours
    en calcul après le délai."""
    last = None
    for i in range(attempts):
        st, mr, _ = api("GET", base, token)
        if not mr:
            sys.exit(f"ERREUR : MR !{iid} introuvable pendant l'attente (HTTP {st}).")
        dms, ms = mr.get("detailed_merge_status"), mr.get("merge_status")
        last = dms or ms
        if dms == "mergeable" or (dms is None and ms == "can_be_merged"):
            return mr
        if dms in ("conflict", "broken_status") or ms == "cannot_be_merged":
            hint = " — conflit à résoudre."
            if mr.get("sha") is None:  # RM2219 : symptôme d'une MR au mauvais endroit
                hint = (" — `sha:null` : la branche source n'existe pas sur ce projet "
                        "(MR créée au mauvais endroit ? cf. RM2219).")
            sys.exit(f"ERREUR : MR !{iid} non mergeable ({last}){hint}")
        # transitoire (preparing / checking / unchecked / ci_still_running…) → on patiente
        if i < attempts - 1:
            time.sleep(delay)
    sys.exit(f"ERREUR : MR !{iid} toujours non mergeable après {attempts} tentatives "
             f"(dernier état : {last}).")


def merge_mr(pid, iid, token, squash=False, expect_rm=None):
    """Merge le cœur d'une MR. `expect_rm` (RM2232, tripwire #13 étendu) : refuse
    si la branche source de la MR n'est pas préfixée `<expect_rm>-` — un iid
    prédit/erroné pointe presque toujours la MR d'une AUTRE session."""
    base = f"/projects/{pid}/merge_requests/{iid}"
    st, mr, raw = api("GET", base, token)
    if st != 200 or not mr:
        sys.exit(f"ERREUR : MR !{iid} introuvable (HTTP {st}).")
    if expect_rm is not None and not str(mr.get("source_branch", "")).startswith(f"{expect_rm}-") \
            and mr.get("source_branch") not in ("dev", "preprod"):
        sys.exit(f"ERREUR : MR !{iid} porte la branche `{mr.get('source_branch')}` — pas celle "
                 f"de RM{expect_rm}. Iid prédit/erroné (tripwire #13) ? Capture l'iid via "
                 f"`pm-mr create --porcelain`, ou utilise `pm-mr create --merge` (atomique).")
    if mr["state"] == "merged":
        out.op("merge", extra=f"!{iid} → {mr['target_branch']} "
                              f"(déjà mergée, branche {mr['source_branch']} conservée)")
        return
    if mr["state"] != "opened":
        sys.exit(f"ERREUR : MR !{iid} en état '{mr['state']}' (pas 'opened').")
    args = type("A", (), {"iid": iid, "squash": squash})
    mr = wait_mergeable(base, iid, token)  # attend la fin du calcul async GitLab
    fields = {"should_remove_source_branch": "false"}  # CONSERVE la branche (NORMS)
    if args.squash:
        fields["squash"] = "true"
    st, res, raw = api("PUT", base + "/merge", token, fields=fields)
    state = res.get("state") if res else None
    if state != "merged":  # corps vide/ambigu → re-GET
        st2, mr2, _ = api("GET", base, token)
        state = mr2.get("state") if mr2 else None
    if state == "merged":
        out.op("merge", extra=f"!{args.iid} → {mr['target_branch']} "
                              f"(branche {mr['source_branch']} conservée)")
    else:
        sys.exit(f"ERREUR merge MR !{args.iid} (HTTP {st}, state={state}) : {raw[:200]}")


def main():
    PMConfig.load()  # charge .env (GITLAB_*, REDMINE_*, …)
    global API_BASE
    API_BASE = base_url() + "/api/v4"

    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    out.add_args(ap)
    sub = ap.add_subparsers(dest="cmd", required=True)

    pc = sub.add_parser("create", help="push + crée/réutilise la MR + CF")
    pc.add_argument("rm_id", type=int)
    pc.add_argument("--repo", default=".", type=lambda s: Path(s).resolve())
    pc.add_argument("--source", help="branche source explicite (défaut : branche courante "
                                     "du --repo). Permet de créer la MR d'un ticket sans "
                                     "checkout de sa branche — ex. depuis le bare + --no-push "
                                     "(la branche est déjà sur origin). RM2355.")
    pc.add_argument("--target", help="branche cible (défaut : intégration / dev)")
    pc.add_argument("--title")
    pc.add_argument("--description")
    pc.add_argument("--status", help="passe le ticket à ce statut (note auto)")
    pc.add_argument("--no-push", action="store_true")
    pc.add_argument("--porcelain", action="store_true",
                    help="n'imprime que l'iid nu de la MR sur stdout (logs sur stderr) — "
                         "capture fiable, JAMAIS de prédiction d'iid (tripwire #13/RM2232)")
    pc.add_argument("--merge", action="store_true",
                    help="merge la MR créée dans la foulée (atomique : l'iid ne transite "
                         "pas par l'appelant ; garde expect-rm implicite)")

    pm = sub.add_parser("merge", help="merge une MR (conserve la branche)")
    pm.add_argument("iid", type=int)
    pm.add_argument("--repo", default=".", type=lambda s: Path(s).resolve())
    pm.add_argument("--squash", action="store_true")
    pm.add_argument("--expect-rm", type=int, default=None,
                    help="refuse si la branche source de la MR n'est pas préfixée <id>- "
                         "(protège d'un iid prédit/erroné — RM2232)")

    pg = sub.add_parser("get", help="état d'une MR")
    pg.add_argument("iid", type=int)
    pg.add_argument("--repo", default=".", type=lambda s: Path(s).resolve())

    args = ap.parse_args()
    out.configure(args)
    # Token selon le rôle : worker (push/MR), manager (merge/gestion).
    role = {"create": "worker", "merge": "manager", "get": "worker"}[args.cmd]
    {"create": cmd_create, "merge": cmd_merge, "get": cmd_get}[args.cmd](args, token_for(role))


if __name__ == "__main__":
    main()
