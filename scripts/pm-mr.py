#!/usr/bin/env python3
"""pm-mr — outillage Merge/Pull Request fiable (RM1871 ; forge-agnostique RM2498).

Sous-commandes :
  create <RMid> [--repo PATH] [--target BR] [--status STATUT] [--no-push]
      push la branche courante + crée (ou réutilise) la PR vers `--target`
      (défaut : `integration_branch`, sinon `dev`), pose les CF Redmine GIT
      Branche / GIT PR, option : passe le ticket à `--status` (note auto).
      Idempotent : PR déjà ouverte ⇒ renvoyée.
  merge <iid> [--repo PATH] [--squash]
      merge la PR `iid`. **Conserve la branche source** (règle NORMS). Idempotent.
  get <iid> [--repo PATH]
      état (state + web_url + branches) de la PR.

Depuis RM2498 (T2), les primitives forge (résolution projet, create/merge/get PR,
tokens, API) sont fournies par `pm_forge` : `GitlabForge` reproduit le comportement
historique ; `GogsForge` dégrade en flux « lien compare » (Gogs n'a pas d'API PR).
Ce script porte la POLITIQUE PM : garde tripwire #13, rollback sha:null (RM2219),
CF Redmine, transitions de statut.
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pm_paths import PMConfig  # charge aussi .env
from pm_output import out
from pm_forge import get_forge, ForgeError


def current_branch(repo):
    return subprocess.run(["git", "-C", str(repo), "rev-parse", "--abbrev-ref", "HEAD"],
                          capture_output=True, text=True).stdout.strip()


def integration_branch(repo_path):
    """Branche d'intégration (défaut 'dev' ; raffinable via overview.md, RM2030)."""
    return "dev"


# ── Politique PM (indépendante de la forge) ──────────────────────────────────
def _post_git_cf(rm_id, branch, pr_url):
    """Pose les CF Redmine GIT Branche + GIT PR, et VÉRIFIE (RM2219 : Redmine
    ignore silencieusement un CF non activé sur le tracker)."""
    try:
        import redmine_utils
        cfs = []
        for name, val in (("GIT Branche", branch), ("GIT PR", pr_url)):
            cid = redmine_utils.cf_id_by_name(name)
            if cid:
                cfs.append({"id": cid, "value": val})
        if cfs:
            redmine_utils.update_issue_fields(rm_id, custom_fields=cfs)
            issue = redmine_utils.fetch_issue(rm_id)
            present = {c.get("id"): c.get("value") for c in issue.get("custom_fields", [])}
            missing = [c["id"] for c in cfs if present.get(c["id"]) != c["value"]]
            if missing:
                out.warn(f"CF Redmine NON écrits (ids {missing}) — CF absents du "
                         f"tracker de #{rm_id} ? Poser le lien en note/manuel.")
            else:
                out.info(f"✓ CF Redmine posés et vérifiés (GIT Branche / GIT PR) sur #{rm_id}")
    except Exception as e:
        out.warn(f"CF Redmine non posés : {e}")


def _merge_with_policy(forge, project, iid, token, squash=False, expect_rm=None):
    """Merge le cœur d'une PR avec les gardes PM. `expect_rm` (RM2232, tripwire #13
    étendu) : refuse si la branche source n'est pas préfixée `<expect_rm>-`."""
    pr = forge.get_pr(project, iid, token)
    if expect_rm is not None and not str(pr.source or "").startswith(f"{expect_rm}-") \
            and pr.source not in ("dev", "preprod"):
        sys.exit(f"ERREUR : MR !{iid} porte la branche `{pr.source}` — pas celle de "
                 f"RM{expect_rm}. Iid prédit/erroné (tripwire #13) ? Capture l'iid via "
                 f"`pm-mr create --porcelain`, ou utilise `pm-mr create --merge` (atomique).")
    if pr.state == "merged":
        out.op("merge", extra=f"!{iid} → {pr.target} "
                              f"(déjà mergée, branche {pr.source} conservée)")
        return
    if pr.state != "opened":
        sys.exit(f"ERREUR : MR !{iid} en état '{pr.state}' (pas 'opened').")
    forge.merge_pr(project, iid, token, squash=squash, keep_source=True)
    out.op("merge", extra=f"!{iid} → {pr.target} (branche {pr.source} conservée)")


# ── Commandes ────────────────────────────────────────────────────────────────
def cmd_merge(args, forge, token):
    project = forge.resolve_project(token)
    out.info(f"→ projet {project.path} (id {project.id})")
    _merge_with_policy(forge, project, args.iid, token,
                       squash=args.squash, expect_rm=args.expect_rm)


def cmd_get(args, forge, token):
    project = forge.resolve_project(token)
    print(f"→ projet {project.path} (id {project.id})")
    pr = forge.get_pr(project, args.iid, token)
    print(f"MR !{pr.iid} [{pr.state}] {pr.source} → {pr.target}"
          f" | {pr.raw.get('detailed_merge_status')}"
          + (" | ⚠ sha:null (branche source absente)" if pr.sha is None else ""))
    print(f"  {pr.web_url}")


def cmd_create(args, forge, token):
    repo = args.repo
    project = forge.resolve_project(token)
    out.info(f"→ projet {project.path} (id {project.id})")
    src = args.source or current_branch(repo)
    if src in ("HEAD", ""):
        sys.exit("ERREUR : HEAD détaché — pas de branche courante (ou --source vide).")
    # Garde anti-prédiction d'id (RM2224, tripwire #13) : une PR de ticket part
    # d'une branche `<RMid>-…` du MÊME id. Branches non préfixées (dev, promotion) OK.
    m = re.match(r"^(\d+)-", src)
    if m and int(m.group(1)) != args.rm_id:
        sys.exit(f"ERREUR : la branche courante `{src}` porte l'id {m.group(1)} mais la MR "
                 f"est demandée pour RM{args.rm_id}. Id prédit/erroné (tripwire #13) ? "
                 f"Renomme la branche (`git branch -m {args.rm_id}-<slug>`) ou corrige le rm_id.")
    tgt = args.target or integration_branch(project.path)
    if src == tgt:
        sys.exit(f"ERREUR : branche courante == cible ({tgt}).")

    if not args.no_push:
        p = subprocess.run(["git", "-C", str(repo), "push", "-u", "origin", src],
                           capture_output=True, text=True)
        if p.returncode != 0:
            sys.exit(f"ERREUR push : {(p.stderr or p.stdout).strip()}")
        out.info(f"✓ push {src} → origin")

    caps = forge.capabilities
    title = args.title or f"RM{args.rm_id} — {src}"
    desc = args.description or f"Ref RM{args.rm_id}."

    if caps.pull_request_api:
        pr = forge.find_open_pr(project, src, tgt, token)
        if pr:
            out.info(f"↻ MR déjà ouverte : !{pr.iid}")
        else:
            pr = forge.create_pr(project, src, tgt, title, desc, token)
            out.info(f"✓ MR !{pr.iid} créée : {src} → {tgt}")
        out.op("mr", extra=f"!{pr.iid} {src}→{tgt} {pr.web_url}")
        if args.porcelain:
            out.value(pr.iid)
        # Garde RM2219 : une PR saine référence le sha de sa branche source.
        chk = forge.get_pr(project, pr.iid, token)
        if chk.sha is None:
            forge.close_pr(project, pr.iid, token)
            sys.exit(f"ERREUR : MR !{pr.iid} sans sha — la branche `{src}` n'existe pas "
                     f"sur {project.path} (mauvaise résolution de projet ?). MR fermée (rollback).")
    else:
        # Forge sans API PR (Gogs) → lien de création (compare) ; ouverture = geste web humain.
        pr = forge.create_pr(project, src, tgt, title, desc, token)
        out.info(f"→ PR à ouvrir (forge sans API PR) : {pr.web_url}")
        out.op("mr", extra=f"compare {src}→{tgt} {pr.web_url}")

    _post_git_cf(args.rm_id, src, pr.web_url)

    if args.status:
        scr = Path(__file__).resolve().parent / "pm-task-status-update.py"
        note = (f"MR !{pr.iid} ouverte vers {tgt} : {pr.web_url}" if pr.iid is not None
                else f"PR à ouvrir vers {tgt} : {pr.web_url}")
        subprocess.run([sys.executable, str(scr), str(args.rm_id), args.status, "--note", note],
                       check=False,
                       stdout=sys.stderr if getattr(args, "porcelain", False) else None)

    if getattr(args, "merge", False) and caps.pull_request_api:
        # Atomique (RM2232) : merge immédiat via la casquette MANAGER (branches protégées).
        _merge_with_policy(forge, project, pr.iid, forge.token("manager"),
                           expect_rm=args.rm_id if src.startswith(f"{args.rm_id}-") else None)


def main():
    PMConfig.load()  # charge .env (GITLAB_*, GOGS_*, REDMINE_*, …)

    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    out.add_args(ap)
    sub = ap.add_subparsers(dest="cmd", required=True)

    pc = sub.add_parser("create", help="push + crée/réutilise la PR + CF")
    pc.add_argument("rm_id", type=int)
    pc.add_argument("--repo", default=".", type=lambda s: Path(s).resolve())
    pc.add_argument("--source", help="branche source explicite (défaut : branche courante "
                                     "du --repo). RM2355.")
    pc.add_argument("--target", help="branche cible (défaut : intégration / dev)")
    pc.add_argument("--title")
    pc.add_argument("--description")
    pc.add_argument("--status", help="passe le ticket à ce statut (note auto)")
    pc.add_argument("--no-push", action="store_true")
    pc.add_argument("--porcelain", action="store_true",
                    help="n'imprime que l'iid nu de la PR sur stdout (logs sur stderr) — "
                         "capture fiable, JAMAIS de prédiction d'iid (tripwire #13/RM2232)")
    pc.add_argument("--merge", action="store_true",
                    help="merge la PR créée dans la foulée (atomique ; forge avec API PR)")

    pm = sub.add_parser("merge", help="merge une PR (conserve la branche)")
    pm.add_argument("iid", type=int)
    pm.add_argument("--repo", default=".", type=lambda s: Path(s).resolve())
    pm.add_argument("--squash", action="store_true")
    pm.add_argument("--expect-rm", type=int, default=None,
                    help="refuse si la branche source de la PR n'est pas préfixée <id>- "
                         "(protège d'un iid prédit/erroné — RM2232)")

    pg = sub.add_parser("get", help="état d'une PR")
    pg.add_argument("iid", type=int)
    pg.add_argument("--repo", default=".", type=lambda s: Path(s).resolve())

    args = ap.parse_args()
    out.configure(args)
    try:
        forge = get_forge(args.repo)
        # Token selon le rôle : worker (push/PR), manager (merge/gestion).
        role = {"create": "worker", "merge": "manager", "get": "worker"}[args.cmd]
        token = forge.token(role)
        {"create": cmd_create, "merge": cmd_merge, "get": cmd_get}[args.cmd](args, forge, token)
    except ForgeError as e:
        sys.exit(f"ERREUR forge : {e}")


if __name__ == "__main__":
    main()
