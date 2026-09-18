#!/usr/bin/env python3
"""pm-mr — outillage Merge/Pull Request fiable (RM1871 ; forge-agnostique RM2498).

Sous-commandes :
  create <RMid> [--repo PATH] [--target BR] [--status STATUT] [--no-push]
      push la branche courante + crée (ou réutilise) la PR vers `--target`
      (défaut : `integration_branch`, sinon `dev`), pose les CF Redmine GIT
      Branche / GIT PR, option : passe le ticket à `--status` (note auto).
      Idempotent : PR déjà ouverte ⇒ renvoyée.
  merge <URL|iid> [--rm-id ID] [--repo PATH] [--squash]
      merge la PR. **Conserve la branche source** (règle NORMS). Idempotent.
  close <URL|iid> [--rm-id ID] [--repo PATH] [--expect-rm ID]
      ferme la PR SANS merger (PR ouverte par erreur, doublon, branche
      abandonnée). **Conserve la branche source.** Idempotent ; refuse une PR
      déjà mergée.
  get <URL|iid> [--rm-id ID] [--repo PATH]
      état (state + web_url + branches) de la PR.

DÉSIGNER une PR (RM2541) — `merge`, `close`, `get` :
  1. son **URL** : forme canonique, auto-portante (hôte → forge, chemin →
     projet, fin → iid). Aucun dépôt local requis, aucun cwd consulté ;
  2. `--rm-id <ticket>` : raccourci, si et seulement si le ticket porte UNE
     seule PR mémorisée (sinon refus qui liste les candidates) ;
  3. un **iid nu**, qui exige alors `--repo` EXPLICITE.
Un iid n'a de sens que rapporté à un dépôt. Ce dépôt venait du répertoire
courant, en silence : d'où une MR ouverte sur le mauvais projet (RM2522) et un
`merge` lancé depuis le dépôt de DONNÉES, échouant en 404 opaque (RM2537).
Sécurité : une URL dont l'hôte n'est pas une forge déclarée (GITLAB_URL /
GOGS_URL / GITHUB_URL) est refusée AVANT tout appel — un PAT ne part jamais
vers un hôte inconnu.

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
try:                                       # RM3095 : journal structuré, jamais bloquant
    import pm_log
    journal = pm_log.journal("pm-mr", "pm")
except ImportError:                        # pm_log absent (clone partiel) : on continue muet
    journal = None

from pm_paths import PMConfig  # charge aussi .env
from pm_output import out
from pm_forge import get_forge, get_forge_from_pr_url, ForgeError
from pm_task import get_task_provider  # seam TaskProvider (P1/RM2543)

# ── RM2541 : désigner une PR sans dépendre du répertoire courant ─────────────
# Une PR se désigne par son URL — auto-portante (hôte → forge, chemin → projet,
# fin → iid). Un iid NU n'a de sens que rapporté à un dépôt : jusqu'ici le cwd
# le fournissait en silence, et lancer `merge <iid>` depuis le mauvais dossier
# visait un autre projet (RM2522 : MR ouverte sur le mauvais projet ; RM2537 :
# merge lancé depuis le dépôt de DONNÉES → 404 opaque). Il l'exige désormais
# EXPLICITEMENT (`--repo`).


def _pr_urls_of_task(rm_id):
    """URL(s) de PR mémorisées dans le frontmatter d'un ticket (`git.mr_urls[]`,
    ou l'ancien scalaire `git.mr_url`). Commodité du raccourci `--rm-id` — pas
    une identité : un ticket porte 0, 1 ou N PR, et ça évolue."""
    import yaml
    md = PMConfig.load().find_task(int(rm_id))
    if not md:
        sys.exit(f"ERREUR : ticket RM{rm_id} introuvable en local.")
    m = re.match(r"^(---\n)(.*?)(\n---\n)", md.read_text(encoding="utf-8"), re.S)
    git = ((yaml.safe_load(m.group(2)) if m else None) or {}).get("git") or {}
    urls = git.get("mr_urls") or ([git["mr_url"]] if git.get("mr_url") else [])
    return [u for u in urls if u]


def _resolve_pr(args, role):
    """(forge, token, iid, origine) pour merge/get/close. Ordre : URL explicite,
    puis raccourci `--rm-id`, puis iid nu — qui EXIGE `--repo`."""
    target = getattr(args, "target_pr", None)
    if target and not str(target).isdigit():
        forge, iid = get_forge_from_pr_url(str(target))
        return forge, forge.token(role), iid, f"URL {target}"
    if getattr(args, "rm_id", None):
        urls = _pr_urls_of_task(args.rm_id)
        if not urls:
            sys.exit(f"ERREUR : aucune PR mémorisée sur RM{args.rm_id} "
                     f"(frontmatter git.mr_urls) — passe l'URL de la PR.")
        if len(urls) > 1:
            sys.exit(f"ERREUR : RM{args.rm_id} porte {len(urls)} PR — désigne-la par son URL :\n  "
                     + "\n  ".join(urls))
        forge, iid = get_forge_from_pr_url(urls[0])
        return forge, forge.token(role), iid, f"RM{args.rm_id} → {urls[0]}"
    if not target:
        sys.exit("ERREUR : indique l'URL de la PR (recommandé), un --rm-id, "
                 "ou un iid avec --repo explicite.")
    if not args.repo:
        sys.exit(f"ERREUR : iid nu ({target}) sans --repo : le dépôt cible serait déduit du "
                 f"répertoire courant, qui n'est pas une désignation fiable (RM2541). "
                 f"Passe l'URL de la PR, ou --repo <chemin du dépôt de code>.")
    forge = get_forge(args.repo)
    return forge, forge.token(role), int(target), f"--repo {args.repo}"


def current_branch(repo):
    return subprocess.run(["git", "-C", str(repo), "rev-parse", "--abbrev-ref", "HEAD"],
                          capture_output=True, text=True).stdout.strip()


def integration_branch(repo_path):
    """Branche d'intégration (défaut 'dev' ; raffinable via overview.md, RM2030)."""
    return "dev"


# ── Politique PM (indépendante de la forge) ──────────────────────────────────
# >>> branche_de_ticket — pure (testée par test_pm_mr_cf_branche.py)
def branche_de_ticket(rm_id, branch):
    """Vrai si `branch` est LA branche de travail du ticket (`<id>-<slug>`).

    RM2701 : le flux normal appelle `create` deux fois — la MR du ticket
    (`<id>-…` → `dev`), puis la MR de promotion (`dev` → `main`). La seconde
    écrasait « GIT Branche » par `dev`, qui ne désigne rien : toutes les
    livraisons y passent. Une valeur générique qu'on croit spécifique est pire
    qu'un champ vide. Même discernement que `_assert_mr_belongs_to`, qui sait
    déjà distinguer une branche de ticket d'une branche d'intégration."""
    return bool(re.match(r"^%s-" % re.escape(str(rm_id)), str(branch or "")))
# <<< branche_de_ticket


def _post_git_cf(rm_id, branch, pr_url):
    """Pose les CF Redmine GIT Branche + GIT PR, et VÉRIFIE (RM2219 : Redmine
    ignore silencieusement un CF non activé sur le tracker).

    RM2701 : « GIT Branche » n'est écrit que si la source EST la branche du
    ticket. « GIT PR » l'est toujours — l'URL d'une MR de promotion reste une
    information juste sur ce ticket."""
    try:
        import redmine_utils
        cfs = []
        champs = [("GIT PR", pr_url)]
        if branche_de_ticket(rm_id, branch):
            champs.insert(0, ("GIT Branche", branch))
        else:
            out.info(f"  · « GIT Branche » laissé tel quel : `{branch}` n'est pas la "
                     f"branche du ticket #{rm_id} (MR de promotion)")
        for name, val in champs:
            cid = redmine_utils.cf_id_by_name(name)
            if cid:
                cfs.append({"id": cid, "value": val})
        if cfs:
            redmine_utils.update_issue_fields(rm_id, custom_fields=cfs)
            issue = get_task_provider().fetch_issue(rm_id)
            present = {c.get("id"): c.get("value") for c in issue.get("custom_fields", [])}
            missing = [c["id"] for c in cfs if present.get(c["id"]) != c["value"]]
            if missing:
                out.warn(f"CF Redmine NON écrits (ids {missing}) — CF absents du "
                         f"tracker de #{rm_id} ? Poser le lien en note/manuel.")
            else:
                out.info(f"✓ CF Redmine posés et vérifiés (GIT Branche / GIT PR) sur #{rm_id}")
    except Exception as e:
        out.warn(f"CF Redmine non posés : {e}")


def _record_pr_url(rm_id, pr_url):
    """Mémorise l'URL de la PR dans le frontmatter du ticket (`git.mr_urls[]`).

    RM2541 : `create` posait le CF Redmine « GIT PR » mais laissait `git.mr_url`
    à null côté MD — le PM ne savait donc pas quelle PR appartenait à quel
    ticket (rupture de parité MD↔Redmine). LISTE et non scalaire : un ticket
    porte parfois plusieurs PR (repos distincts, reprise après abandon).
    `git.mr_url` est tenu à jour pour l'existant (dernière PR en date)."""
    if not pr_url:
        return
    try:
        import yaml
        from datetime import datetime
        md = PMConfig.load().find_task(int(rm_id))
        if not md:
            out.warn(f"frontmatter git.mr_urls non écrit : RM{rm_id} introuvable en local.")
            return
        raw = md.read_text(encoding="utf-8")
        m = re.match(r"^(---\n)(.*?)(\n---\n)(.*)$", raw, re.S)
        if not m:
            out.warn(f"frontmatter git.mr_urls non écrit : pas de frontmatter dans {md.name}.")
            return
        fm = yaml.safe_load(m.group(2)) or {}
        git = fm.get("git") or {}
        urls = list(git.get("mr_urls") or [])
        if git.get("mr_url") and git["mr_url"] not in urls:
            urls.append(git["mr_url"])          # reprise de l'ancien scalaire
        if pr_url not in urls:
            urls.append(pr_url)
        git["mr_urls"], git["mr_url"] = urls, pr_url
        fm["git"] = git
        fm["updated"] = datetime.now().strftime("%Y-%m-%dT%H:%M")
        new_fm = yaml.safe_dump(fm, allow_unicode=True, sort_keys=False,
                                default_flow_style=False)
        md.write_text(f"{m.group(1)}{new_fm.rstrip()}{m.group(3)}{m.group(4)}",
                      encoding="utf-8")
        out.info(f"✓ frontmatter git.mr_urls ({len(urls)}) : {md.name}")
    except Exception as e:                       # jamais bloquant : la PR existe déjà
        out.warn(f"frontmatter git.mr_urls non écrit : {e}")


def _guard_expect_rm(pr, iid, expect_rm):
    """Garde RM2232 (tripwire #13 étendu) : la PR visée doit porter la branche du
    ticket annoncé, sinon un iid prédit ou mal recopié agirait sur la PR d'autrui.
    Les branches de flux (dev, preprod — promotions) sont admises."""
    if expect_rm is None:
        return
    if str(pr.source or "").startswith(f"{expect_rm}-") or pr.source in ("dev", "preprod"):
        return
    sys.exit(f"ERREUR : MR !{iid} porte la branche `{pr.source}` — pas celle de "
             f"RM{expect_rm}. Iid prédit/erroné (tripwire #13) ? Capture l'iid via "
             f"`pm-mr create --porcelain`, ou utilise `pm-mr create --merge` (atomique).")


def _hook_mr(iid, **kw):
    """RM2583 : reflet best-effort dans le worklog de session (jamais bloquant)."""
    try:
        from pm_session_hook import log_mr_to_session
        log_mr_to_session(iid, **kw)
    except Exception:
        pass


def _guard_questions(forge, project, pr, token, ids=None, local_repo=None, ignore=False):
    """RM3238 — pas de merge vers la prod (`main`/`master`) tant qu'un ticket de la MR a une
    question ouverte. Tickets : `ids` fourni (pm-promote, qui connaît son lot), sinon le préfixe
    de la branche source puis les commits de la MR (une promotion `dev→main` ne porte pas de
    préfixe). Dépôts de données PM exclus. Forge incapable de lister les commits ⇒ on le dit,
    on ne bloque pas sur de l'inconnu."""
    import pm_questions_gate as qg
    if not qg.is_prod_branch(pr.target) or qg.is_data_repo(project.path, local_repo):
        return
    if ids is None:
        ids = []
        bid = qg.id_from_branch(pr.source)
        if bid:
            ids.append(bid)
        msgs = forge.pr_commit_messages(project, pr.iid, token)
        if msgs is None and not bid:
            out.warn(f"MR !{pr.iid} → {pr.target} : tickets du lot inconnus (la forge ne liste pas "
                     f"les commits) — garde des questions non appliquée (RM3238)")
        for i in qg.ids_in_text("\n".join(msgs or [])):
            if i not in ids:
                ids.append(i)
    bm = qg.blocked(ids)
    if not bm:
        return
    if not ignore:
        sys.exit(qg.refusal(bm, f"merge de !{pr.iid} ({pr.source} → {pr.target})",
                            "--ignore-questions"))
    out.warn(f"merge de !{pr.iid} → {pr.target} malgré des questions ouvertes (--ignore-questions) :\n"
             + qg.describe(bm))
    if journal:
        journal.warn("merge prod malgré questions ouvertes", iid=pr.iid, target=pr.target,
                     tickets=",".join(f"RM{i}" for i in bm))


def _merge_with_policy(forge, project, iid, token, squash=False, expect_rm=None,
                       ignore_questions=False, ticket_ids=None, local_repo=None):
    """Merge le cœur d'une PR avec les gardes PM. `expect_rm` (RM2232, tripwire #13
    étendu) : refuse si la branche source n'est pas préfixée `<expect_rm>-`.
    RM3238 : vers la prod, refuse tant qu'un ticket de la MR a une question ouverte."""
    pr = forge.get_pr(project, iid, token)
    _guard_expect_rm(pr, iid, expect_rm)
    if pr.state == "opened":
        _guard_questions(forge, project, pr, token, ids=ticket_ids, local_repo=local_repo,
                         ignore=ignore_questions)
    if pr.state == "merged":
        # déjà mergée : le worklog peut l'ignorer encore, on le remet d'aplomb
        _hook_mr(iid, repo=project.path, source=pr.source, target=pr.target,
                 state="merged")
        out.op("merge", extra=f"!{iid} → {pr.target} "
                              f"(déjà mergée, branche {pr.source} conservée)")
        return
    if pr.state != "opened":
        sys.exit(f"ERREUR : MR !{iid} en état '{pr.state}' (pas 'opened').")
    forge.merge_pr(project, iid, token, squash=squash, keep_source=True)
    _hook_mr(iid, repo=project.path, source=pr.source, target=pr.target,
             state="merged")           # RM2583 : sort des « à merger »
    if journal:
        journal.info("MR mergée", iid=iid, src=pr.source, target=pr.target, repo=project.path)
    out.op("merge", extra=f"!{iid} → {pr.target} (branche {pr.source} conservée)")


def _resolved_project(forge, token, args):
    """Projet forge + trace de l'origine. Sur échec de résolution, le message dit
    QUOI on a cherché et D'OÙ vient la cible — sans ça, un `404 MR introuvable`
    laisse croire à un problème de droits alors qu'on interroge le mauvais dépôt."""
    origin = getattr(args, "_origin", "?")
    try:
        project = forge.resolve_project(token)
    except ForgeError as e:
        sys.exit(f"ERREUR forge : {e}\n  → dépôt visé : {forge.repo_path} "
                 f"(résolu depuis {origin})")
    out.info(f"→ projet {project.path} (id {project.id}) [depuis {origin}]")
    return project


# ── Commandes ────────────────────────────────────────────────────────────────
def cmd_merge(args, forge, token):
    project = _resolved_project(forge, token, args)
    _merge_with_policy(forge, project, args.iid, token,
                       squash=args.squash, expect_rm=args.expect_rm,
                       ignore_questions=args.ignore_questions, local_repo=args.repo)


def cmd_close(args, forge, token):
    """Ferme une PR sans la merger. Cas d'usage vécu (RM2522) : une MR ouverte
    depuis le mauvais répertoire courant, donc sur le mauvais projet — jusqu'ici
    il fallait un script jetable autour de `pm_forge.close_pr()`."""
    if not forge.capabilities.pull_request_api:
        sys.exit("ERREUR : cette forge n'a pas d'API PR (Gogs) — la fermeture est "
                 "un geste web humain.")
    project = _resolved_project(forge, token, args)
    pr = forge.get_pr(project, args.iid, token)
    _guard_expect_rm(pr, args.iid, args.expect_rm)
    if pr.state == "merged":
        sys.exit(f"ERREUR : MR !{args.iid} ({pr.source} → {pr.target}) est déjà MERGÉE — "
                 f"la fermer n'annulerait rien. Pour défaire un merge, révèrte-le par "
                 f"une branche dédiée.")
    if pr.state != "opened":
        # Idempotence : refermer une PR déjà fermée n'est pas une erreur.
        out.op("close", extra=f"!{args.iid} (déjà '{pr.state}', branche {pr.source} conservée)")
        return
    forge.close_pr(project, args.iid, token)
    _hook_mr(args.iid, repo=project.path, source=pr.source, target=pr.target,
             state="closed")
    out.op("close", extra=f"!{args.iid} {pr.source}→{pr.target} fermée "
                          f"(branche {pr.source} conservée)")


def cmd_get(args, forge, token):
    project = _resolved_project(forge, token, args)
    pr = forge.get_pr(project, args.iid, token)
    print(f"MR !{pr.iid} [{pr.state}] {pr.source} → {pr.target}"
          f" | {pr.raw.get('detailed_merge_status')}"
          + (" | ⚠ sha:null (branche source absente)" if pr.sha is None else ""))
    print(f"  {pr.web_url}")


def check_no_ticket_args(args):
    """Cohérence du mode sans ticket (RM2644) — refuse tôt et en nommant la cause.

    « Sans ticket » ne veut pas dire « sans MR » : la branche d'intégration reste
    protégée. Ce mode retire seulement ce qui n'a pas de sens faute de ticket — CF
    Redmine, `git.mr_urls` du frontmatter, transition de statut.
    """
    if not args.no_ticket:
        if args.rm_id is None:
            sys.exit("ERREUR : rm_id manquant. Un changement rattaché à un ticket passe "
                     "son id ; un changement qui n'en a pas (ajout au glossaire…) passe "
                     "`--no-ticket --title \"…\"`.")
        return
    if args.rm_id is not None:
        sys.exit(f"ERREUR : --no-ticket et un rm_id (RM{args.rm_id}) sont contradictoires. "
                 f"Choisis : la MR référence un ticket, ou elle n'en a pas.")
    if not args.title:
        sys.exit("ERREUR : --title est obligatoire avec --no-ticket — le titre par défaut "
                 "est `RM<id> — <branche>`, qui n'existe pas sans ticket.")
    if args.status:
        sys.exit("ERREUR : --status n'a pas de sens avec --no-ticket : il n'y a pas de "
                 "ticket à faire transiter.")


#: Les fichiers que TOUT LE MONDE touche : les signaler ferait crier l'avertissement à chaque MR, et
#: un signal qui se déclenche toujours cesse d'être lu. Ils sont d'ailleurs conçus pour l'ajout
#: parallèle — les conflits qu'ils produisent sont mécaniques, pas des collisions de raisonnement.
FICHIERS_PARTAGES = {"Changelog.md", "scripts/INDEX.md", "norms/NORMS.md", "norms/VERSION",
                     "norms/src/_frontmatter.txt", "norms/src/_full-body.md",
                     "deploy/karl-agent/cockpit/cockpit.css", "deploy/karl-agent/cockpit/src/core/endpoints.js"}


# >>> collisions — pure (testée par test_pm_mr_collisions.py)
def collisions(mes_fichiers, autres: dict, exclus=None) -> list:
    """[(branche, [fichiers communs])] — qui d'autre touche à ce que je touche. Pure. RM3157.

    Deux sessions ont corrigé le même défaut le même jour sans se voir (RM3142 et RM3143) : les
    TICKETS étaient différents — la garde de RM3086 ne pouvait rien dire — mais le CODE était
    commun. La seconde MR a été mergée par-dessus la première et a laissé `dev` mélangé.

    Git ne prévient pas : il ne voit un conflit que si les lignes se chevauchent exactement, et il
    le voit au merge, quand les deux raisonnements sont déjà écrits. Ici on regarde plus tôt et plus
    large : le même FICHIER suffit à mériter un coup d'œil.
    """
    exclus = FICHIERS_PARTAGES if exclus is None else exclus
    miens = {f for f in (mes_fichiers or []) if f not in exclus}
    out_ = []
    for branche, fichiers in sorted((autres or {}).items()):
        communs = sorted(miens & {f for f in (fichiers or []) if f not in exclus})
        if communs:
            out_.append((branche, communs))
    return out_
# <<< collisions


# >>> texte_collisions — pure
def texte_collisions(collisions_, ouvertes=None) -> str:
    """Le message, ou "" s'il n'y a rien à dire. Avertit, n'interdit pas : travailler à deux sur un
    fichier est parfois voulu, et un refus se contournerait — c'est un coup d'œil qu'on demande."""
    if not collisions_:
        return ""
    ouvertes = ouvertes or {}
    L = [f"⚠ {len(collisions_)} autre(s) branche(s) de ticket touchent les mêmes fichiers :"]
    for branche, communs in collisions_:
        mr = ouvertes.get(branche)
        # sans information sur la MR, on nomme la branche sans rien affirmer : prétendre « pas de MR »
        # sur la foi d'une absence de donnée enverrait chercher au mauvais endroit.
        L.append(f"  · {branche}" + (f" (MR !{mr})" if mr else ""))
        L.append("      " + ", ".join(communs[:6]) + (" …" if len(communs) > 6 else ""))
    L.append("  Regarde ces MR avant de merger : git ne signalera un conflit que si les lignes se")
    L.append("  chevauchent exactement, et la seconde mergée écrase le raisonnement de la première.")
    return "\n".join(L)
# <<< texte_collisions


def _fichiers_de(repo, base, branche):
    """Les fichiers que `branche` change par rapport à `base`. [] si on ne sait pas dire."""
    r = subprocess.run(["git", "-C", str(repo), "diff", "--name-only", f"{base}...{branche}"],
                       capture_output=True, text=True)
    return [x.strip() for x in r.stdout.splitlines() if x.strip()] if r.returncode == 0 else []


def avertir_collisions(repo, src, tgt, rm_id=None):
    """Dit si d'autres branches de ticket non mergées touchent les mêmes fichiers. Jamais bloquant."""
    try:
        base = f"origin/{tgt}"
        miens = _fichiers_de(repo, base, src)
        if not miens:
            return ""
        r = subprocess.run(["git", "-C", str(repo), "branch", "-r", "--no-merged", base,
                            "--format=%(refname:short)"], capture_output=True, text=True)
        if r.returncode != 0:
            return ""
        autres = {}
        for ref in r.stdout.splitlines():
            ref = ref.strip()
            nom = ref.split("origin/")[-1]
            if not re.match(r"^\d+-", nom) or nom == src:
                continue
            if rm_id and nom.startswith(f"{rm_id}-"):      # mes propres branches, même ticket
                continue
            autres[nom] = _fichiers_de(repo, base, ref)
        return texte_collisions(collisions(miens, autres))
    except Exception:      # noqa: BLE001 — un avertissement ne fait JAMAIS échouer une livraison
        return ""


def cmd_create(args, forge, token):
    repo = args.repo
    check_no_ticket_args(args)
    project = forge.resolve_project(token)
    out.info(f"→ projet {project.path} (id {project.id})")
    src = args.source or current_branch(repo)
    if src in ("HEAD", ""):
        sys.exit("ERREUR : HEAD détaché — pas de branche courante (ou --source vide).")
    # Garde anti-prédiction d'id (RM2224, tripwire #13) : une PR de ticket part
    # d'une branche `<RMid>-…` du MÊME id. Branches non préfixées (dev, promotion) OK.
    m = re.match(r"^(\d+)-", src)
    if m and args.no_ticket:
        # Le garde s'inverse en mode sans ticket : une branche `<id>-…` trahit un ticket
        # oublié, pas un changement ticketless (RM2644).
        sys.exit(f"ERREUR : --no-ticket sur la branche `{src}`, qui porte l'id "
                 f"{m.group(1)}. Ticket oublié ? Passe `pm-mr create {m.group(1)}`, ou "
                 f"renomme la branche si le changement n'a vraiment pas de ticket.")
    if m and not args.no_ticket and int(m.group(1)) != args.rm_id:
        sys.exit(f"ERREUR : la branche courante `{src}` porte l'id {m.group(1)} mais la MR "
                 f"est demandée pour RM{args.rm_id}. Id prédit/erroné (tripwire #13) ? "
                 f"Renomme la branche (`git branch -m {args.rm_id}-<slug>`) ou corrige le rm_id.")
    tgt = args.target or integration_branch(project.path)
    if src == tgt:
        sys.exit(f"ERREUR : branche courante == cible ({tgt}).")

    # RM3157 : qui d'autre touche à ce que je touche ? C'est ICI que l'information existe (on connaît
    # enfin les fichiers) et qu'elle sert encore (on n'a pas mergé).
    mot = avertir_collisions(repo, src, tgt, rm_id=getattr(args, "rm_id", None))
    if mot:
        out.warn(mot)

    if not args.no_push:
        p = subprocess.run(["git", "-C", str(repo), "push", "-u", "origin", src],
                           capture_output=True, text=True)
        if p.returncode != 0:
            sys.exit(f"ERREUR push : {(p.stderr or p.stdout).strip()}")
        out.info(f"✓ push {src} → origin")

    caps = forge.capabilities
    if args.no_ticket:
        title = args.title                       # exigé par check_no_ticket_args
        desc = args.description or "Changement sans ticket (cf. NORMS governance)."
    else:
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
        # RM2583 : la session retient ce qu'elle a ouvert — sinon une MR se perd
        # jusqu'au prochain conflit, ou jusqu'à un core update incomplet.
        _hook_mr(pr.iid, url=pr.web_url, repo=project.path, source=src, target=tgt,
                 ref="sans ticket" if args.no_ticket else f"RM{args.rm_id}",
                 state="opened")
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

    if journal:
        journal.info("MR créée", iid=getattr(pr, "iid", None), src=src, target=tgt,
                     repo=project.path, rm=None if args.no_ticket else args.rm_id, url=pr.web_url)
    if not args.no_ticket:
        # Sans ticket, il n'y a ni CF Redmine à poser ni frontmatter où mémoriser l'URL.
        _post_git_cf(args.rm_id, src, pr.web_url)
        _record_pr_url(args.rm_id, pr.web_url)

    if args.status:
        scr = Path(__file__).resolve().parent / "pm-task-status-update.py"
        note = (f"MR !{pr.iid} ouverte vers {tgt} : {pr.web_url}" if pr.iid is not None
                else f"PR à ouvrir vers {tgt} : {pr.web_url}")
        subprocess.run([sys.executable, str(scr), str(args.rm_id), args.status, "--note", note],
                       check=False,
                       stdout=sys.stderr if getattr(args, "porcelain", False) else None)

    if getattr(args, "merge", False) and caps.pull_request_api:
        # Atomique (RM2232) : merge immédiat via la casquette MANAGER (branches protégées).
        # Sans ticket, la garde `expect_rm` n'a rien à vérifier (aucun id attendu).
        _merge_with_policy(forge, project, pr.iid, forge.token("manager"),
                           expect_rm=None if args.no_ticket else
                           (args.rm_id if src.startswith(f"{args.rm_id}-") else None),
                           ignore_questions=args.ignore_questions, local_repo=args.repo)


def main():
    PMConfig.load()  # charge .env (GITLAB_*, GOGS_*, REDMINE_*, …)

    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    out.add_args(ap)
    sub = ap.add_subparsers(dest="cmd", required=True)

    pc = sub.add_parser("create", help="push + crée/réutilise la PR + CF")
    pc.add_argument("rm_id", type=int, nargs="?",
                    help="ticket porté par la MR (omis avec --no-ticket)")
    pc.add_argument("--no-ticket", action="store_true",
                    help="MR sans ticket Redmine (ajout au glossaire, correction de "
                         "coquille… — cf. NORMS governance). Exige --title ; ne pose ni CF "
                         "ni frontmatter, refuse --status. La MR reste obligatoire : la "
                         "branche d'intégration est protégée.")
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
    pc.add_argument("--ignore-questions", action="store_true",
                    help="RM3238 : avec --merge vers main/master, passer outre les questions "
                         "non tranchées des tickets (tracé)")

    pm = sub.add_parser("merge", help="merge une PR (conserve la branche)")
    pm.add_argument("target_pr", nargs="?", metavar="URL|iid",
                    help="URL de la PR (recommandé : auto-portante) ou iid nu, "
                         "qui exige alors --repo explicite (RM2541)")
    pm.add_argument("--rm-id", type=int, help="raccourci : la PR mémorisée du ticket, "
                                              "si elle est unique (RM2541)")
    pm.add_argument("--repo", default=None, type=lambda s: Path(s).resolve())
    pm.add_argument("--squash", action="store_true")
    pm.add_argument("--expect-rm", type=int, default=None,
                    help="refuse si la branche source de la PR n'est pas préfixée <id>- "
                         "(protège d'un iid prédit/erroné — RM2232)")
    pm.add_argument("--ignore-questions", action="store_true",
                    help="RM3238 : merger vers main/master malgré des questions non tranchées "
                         "sur les tickets de la MR (tracé)")

    pcl = sub.add_parser("close", help="ferme une PR sans merger (conserve la branche)")
    pcl.add_argument("target_pr", nargs="?", metavar="URL|iid",
                     help="URL de la PR (recommandé) ou iid nu + --repo explicite")
    pcl.add_argument("--rm-id", type=int, help="raccourci : la PR mémorisée du ticket, "
                                               "si elle est unique (RM2541)")
    pcl.add_argument("--repo", default=None, type=lambda s: Path(s).resolve())
    pcl.add_argument("--expect-rm", type=int, default=None,
                     help="refuse si la branche source de la PR n'est pas préfixée <id>- "
                          "(protège d'un iid prédit/erroné — RM2232)")

    pg = sub.add_parser("get", help="état d'une PR")
    pg.add_argument("target_pr", nargs="?", metavar="URL|iid",
                    help="URL de la PR (recommandé) ou iid nu + --repo explicite")
    pg.add_argument("--rm-id", type=int, help="raccourci : la PR mémorisée du ticket, "
                                              "si elle est unique (RM2541)")
    pg.add_argument("--repo", default=None, type=lambda s: Path(s).resolve())

    args = ap.parse_args()
    out.configure(args)
    try:
        # Token selon le rôle : worker (push/PR), manager (merge/gestion).
        role = {"create": "worker", "merge": "manager",
                "close": "manager", "get": "worker"}[args.cmd]
        if args.cmd == "create":
            # `create` PRODUIT la PR : il lui faut le dépôt local (branche
            # courante, push) — le cwd y est une source légitime.
            forge = get_forge(args.repo)
            token = forge.token(role)
            args._origin = f"--repo {args.repo}"
        else:
            # RM2541 : URL > raccourci --rm-id > iid nu + --repo EXPLICITE.
            forge, token, args.iid, args._origin = _resolve_pr(args, role)
        {"create": cmd_create, "merge": cmd_merge,
         "close": cmd_close, "get": cmd_get}[args.cmd](args, forge, token)
    except ForgeError as e:
        sys.exit(f"ERREUR forge : {e}")


if __name__ == "__main__":
    main()
