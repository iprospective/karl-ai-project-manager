#!/usr/bin/env python3
"""pm-promote — promotion par lot intégration → branche protégée (RM2298).

⚠ **OUTIL DE TRANSITION (RM2440).** Depuis que les dépôts core acceptent le push
direct sur leur branche de prod (`pm-protect` pose push=Developer ; `pm_git`
pousse directement et rattrape les non-fast-forward), plus aucun commit de
données PM ne transite par `dev` : ce script n'a plus de rôle dans le flux
nominal. Il reste pour deux usages :
  - **résorber l'arriéré** hérité de l'ancien mécanisme (les commits déjà
    présents sur `dev` avant la bascule) ;
  - promouvoir un dépôt de **code** dont on veut merger l'intégration par MR.
Les branches `dev` des cores sont conservées (elles peuvent servir à dénouer un
merge ponctuel), mais elles ne reçoivent plus de trafic automatique.

Fonctionnement : MR `dev→main` créée (ou réutilisée si déjà ouverte) puis mergée
avec le PAT *manager* — les données PM ne passent pas par une revue humaine.
Idempotent ; ne touche JAMAIS l'arbre de travail local (pas de rebase/merge
local — invariant pm_git sur arbre partagé dirty).

Traçabilité (RM2809) : le lot est annoncé ticket par ticket AVANT le merge — donc
aussi en `--dry-run` —, puis chaque ticket reçoit une note portant le commit de
promotion et la branche cible. Un id sans ticket (auto-commit `pm-*`, MR sans
ticket) est ignoré sans bruit et n'interrompt jamais la promotion.

Usage :
    pm-promote.py [--repo PATH] [--source dev] [--target main]
                  [--title T] [--no-flush] [--dry-run]
                  [--no-annotate] [--advance]

--no-flush : ne pousse pas d'abord les commits locaux en attente vers --source.
--no-annotate : ne pose aucune note sur les tickets du lot.
--advance : applique `a_mep` → `en_mep` sur les tickets du lot (sinon proposé).
À lancer en fin de session ou périodiquement (cron) sur les repos de données PM.
"""
import argparse
import importlib.util
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

# Primitives forge (résolution projet RM2219, create/get/merge PR) via pm_forge
# (RM2498). La POLITIQUE de merge (_merge_with_policy : idempotence déjà-mergée,
# gardes d'état) est réutilisée de pm-mr.py (nom à tiret → import dynamique).
_spec = importlib.util.spec_from_file_location("pm_mr", HERE / "pm-mr.py")
pmmr = importlib.util.module_from_spec(_spec)
sys.modules["pm_mr"] = pmmr
_spec.loader.exec_module(pmmr)

import pm_forge
import pm_git
import pm_paths


def _git(repo, *a):
    return subprocess.run(["git", "-C", str(repo), *a], capture_output=True, text=True)


def origin_range(tgt, src):
    return f"origin/{tgt}..origin/{src}"


# RM2809 — deux façons dont un lot nomme ses tickets, et il faut les deux :
#   « RM2857 : … »                         → commit direct sur une branche de ticket
#   « Merge branch '2777-slug' into … »    → commit de merge, dont le sujet ne
#                                            porte PAS le RM<id>
# Sans la seconde, un lot passé par MR (le cas nominal) ressort vide.
_RM_IN_TEXT = re.compile(r"\bRM(\d{3,6})\b")
_MERGE_BRANCH = re.compile(r"(?:Merge (?:branch|remote-tracking branch) '(?:[^']*/)?)(\d{3,6})-")


def batch_ticket_ids(repo, tgt, count_from):
    """RM<id> présents dans le lot, dans l'ordre où git les rend (récent → ancien).

    Best-effort : un lot sans aucun ticket (auto-commits pm-*, MR sans ticket)
    rend une liste vide, ce qui n'est pas une anomalie.
    """
    p = _git(repo, "log", "--format=%s%n%b", f"origin/{tgt}..{count_from}")
    if p.returncode != 0:
        return []
    ids, seen = [], set()
    for rx in (_RM_IN_TEXT, _MERGE_BRANCH):
        for m in rx.finditer(p.stdout):
            i = int(m.group(1))
            if i not in seen:
                seen.add(i)
                ids.append(i)
    return ids


def _task_status(task_file):
    """Statut lu dans le frontmatter, ou None."""
    try:
        head = task_file.read_text(encoding="utf-8", errors="replace").split("---", 2)
    except OSError:
        return None
    if len(head) < 3:
        return None
    m = re.search(r"^status:\s*(\S+)\s*$", head[1], re.M)
    return m.group(1) if m else None


def annotate_tickets(ids, repo, tgt, sha, advance=False):
    """Pose sur chaque ticket du lot une note portant le commit de promotion.

    Rien de tout cela ne doit interrompre une promotion déjà faite : le code est
    entièrement best-effort. Un id sans ticket (auto-commit, MR sans ticket) est
    simplement ignoré.
    """
    try:
        cfg = pm_paths.PMConfig.load()
    except Exception as e:
        print(f"  ⚠ tickets non annotés (config PM illisible : {e})")
        return

    note = (f"Promu sur `{tgt}` par pm-promote — commit `{sha[:12]}` "
            f"(dépôt `{Path(repo).name}`).")
    done, skipped, advanced = [], [], []

    for rm_id in ids:
        try:
            f = cfg.find_task(rm_id)
        except Exception:
            f = None
        if not f:
            skipped.append(rm_id)
            continue

        # --no-commit : pm-promote peut tourner SUR le repo PM lui-même, et un
        # auto-commit ici créerait du travail local juste après la promotion.
        r = subprocess.run(
            [sys.executable, str(HERE / "pm-task-comment.py"), str(rm_id),
             "--note", note, "--no-commit"],
            capture_output=True, text=True)
        if r.returncode != 0:
            last = (r.stderr or r.stdout or "").strip().splitlines()
            print(f"  ⚠ RM{rm_id} : note non posée ({last[-1] if last else '?'})")
            continue
        done.append(rm_id)

        status = _task_status(f)
        if status != "a_mep":
            continue
        if not advance:
            advanced.append(rm_id)
            continue
        r = subprocess.run(
            [sys.executable, str(HERE / "pm-task-status-update.py"), str(rm_id),
             "en_mep", "--note", note],
            capture_output=True, text=True)
        if r.returncode != 0:
            last = (r.stderr or r.stdout or "").strip().splitlines()
            print(f"  ⚠ RM{rm_id} : a_mep → en_mep refusé ({last[-1] if last else '?'})")

    if done:
        print(f"✓ {len(done)} ticket(s) annoté(s) : " + ", ".join(f"RM{i}" for i in done))
    if skipped:
        print(f"  ({len(skipped)} id(s) sans ticket, ignoré(s) : "
              + ", ".join(f"RM{i}" for i in skipped) + ")")
    if advanced and not advance:
        print("  → à passer en_mep (relancer avec --advance) : "
              + ", ".join(f"RM{i}" for i in advanced))


def main():
    ap = argparse.ArgumentParser(description="Promotion par lot intégration → branche protégée (RM2298)")
    ap.add_argument("--repo", default=".", help="repo (défaut : cwd)")
    ap.add_argument("--source", default=None, help="branche d'intégration (défaut : git.integration_branch, dev)")
    ap.add_argument("--target", default="main", help="branche protégée cible (défaut : main)")
    ap.add_argument("--title", default=None)
    ap.add_argument("--no-flush", action="store_true", help="ne pousse pas d'abord les commits locaux vers --source")
    ap.add_argument("--no-annotate", action="store_true",
                    help="ne pose pas de note de promotion sur les tickets du lot")
    ap.add_argument("--advance", action="store_true",
                    help="applique la transition a_mep → en_mep sur les tickets du lot "
                         "(sinon elle est seulement proposée)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    repo = pm_git.repo_root(Path(args.repo).resolve())
    if not repo:
        sys.exit(f"ERREUR : {args.repo} n'est pas dans un repo git.")
    src = args.source or pm_git.load_git_config()["integration_branch"]
    tgt = args.target
    if src == tgt:
        sys.exit(f"ERREUR : source == cible ({src}).")

    forge = pm_forge.get_forge(repo)
    if not forge.capabilities.pull_request_api:
        sys.exit("ERREUR : pm-promote nécessite une forge avec API PR (GitLab).")
    token = forge.token("manager")
    project = forge.resolve_project(token)
    print(f"→ projet {project.path} (id {project.id}) : {src} → {tgt}")

    # 1. Pousser les commits locaux en attente vers la branche d'intégration
    #    (repli pm_git déjà fait en temps normal — ceci rattrape les différés).
    #
    # RM2790 — en `--dry-run`, ce push doit rester une SIMULATION. Il s'exécutait
    # avant que `args.dry_run` ne soit testé (le test n'arrivait qu'à l'étape 2),
    # si bien qu'un `--dry-run` lancé pour *voir* le lot versait le travail local
    # dans l'intégration et court-circuitait la revue par MR (tripwire NORMS #3).
    # On garde le même chemin de code et on délègue à `git push --dry-run`, pour
    # qu'un refus (branche protégée, non-fast-forward) reste visible en simulation.
    flushed = False
    if not args.no_flush:
        p = _git(repo, "push", *(["--dry-run"] if args.dry_run else []),
                 "origin", f"HEAD:{src}")
        if p.returncode == 0:
            flushed = True
            if args.dry_run:
                print(f"  (dry-run) commits locaux seraient poussés → {src}")
            else:
                print(f"✓ commits locaux poussés → {src}")
        else:
            last = (p.stderr or "").strip().splitlines()[-1] if (p.stderr or "").strip() else "?"
            print(f"  ⚠ flush local → {src} impossible ({last}) — promotion du lot déjà distant seulement")

    # 2. Delta réel à promouvoir (côté remote).
    f = _git(repo, "fetch", "origin")
    if f.returncode != 0:
        last = (f.stderr or "").strip().splitlines()
        sys.exit(f"ERREUR : git fetch origin a échoué ({last[-1] if last else '?'}) — "
                 f"un comptage sur des refs périmées serait trompeur.")

    # RM2440 — un `rev-list` sur une ref inexistante échoue, ce qui affichait
    # « ? commit(s) » sans dire pourquoi. Or c'est le cas le plus fréquent : 44
    # des 66 cores n'ont tout simplement pas de branche `dev` distante. On
    # distingue donc « ref absente » (rien à faire, sortie normale) de « le
    # comptage a échoué » (anomalie à signaler).
    for ref in (f"origin/{src}", f"origin/{tgt}"):
        if _git(repo, "rev-parse", "--verify", "--quiet", ref).returncode != 0:
            which = "source" if ref.endswith(f"/{src}") else "cible"
            print(f"✓ rien à promouvoir : la branche {which} '{ref}' n'existe pas "
                  f"sur le remote.")
            return

    # RM2790 — en simulation, `origin/<src>` n'a pas bougé : compter le lot depuis
    # la ref distante sous-estimerait ce qui serait réellement promu. Quand un flush
    # aurait eu lieu, on compte donc depuis le HEAD local.
    count_from = "HEAD" if (args.dry_run and flushed) else f"origin/{src}"
    d = _git(repo, "rev-list", "--count", f"origin/{tgt}..{count_from}")
    if d.returncode != 0:
        last = (d.stderr or "").strip().splitlines()
        sys.exit(f"ERREUR : comptage {origin_range(tgt, src)} impossible "
                 f"({last[-1] if last else 'raison inconnue'}).")
    delta = int(d.stdout.strip() or 0)
    if delta == 0:
        print(f"✓ rien à promouvoir ({tgt} contient déjà {src}).")
        return
    print(f"  {delta} commit(s) à promouvoir")

    # RM2809 — annoncer le lot AVANT le merge : c'est la seule occasion de vérifier
    # ce qui part, et c'est aussi ce qui rend `--dry-run` réellement informatif.
    ids = batch_ticket_ids(repo, tgt, count_from)
    if ids:
        print("  tickets du lot : " + ", ".join(f"RM{i}" for i in ids))
    else:
        print("  aucun ticket identifié dans le lot")

    if args.dry_run:
        print("  (dry-run : ni MR ni merge, ni note sur les tickets)")
        return

    # 3. MR idempotente + merge (PAT manager).
    pr = forge.find_open_pr(project, src, tgt, token)
    if pr:
        print(f"↻ MR déjà ouverte : !{pr.iid}")
    else:
        title = args.title or f"Promotion PM {src}→{tgt} (lot auto-push, {delta} commit(s))"
        pr = forge.create_pr(project, src, tgt, title,
                             "Promotion automatique du lot d'auto-commits pm-* (RM2298).", token)
        print(f"✓ MR !{pr.iid} créée")
    pmmr._merge_with_policy(forge, project, pr.iid, token)

    # 4. Tracer la promotion sur les tickets du lot (RM2809). Best-effort : le
    #    merge est fait, plus rien ici ne doit faire échouer la commande.
    if ids and not args.no_annotate:
        _git(repo, "fetch", "origin", tgt)
        sha = _git(repo, "rev-parse", f"origin/{tgt}").stdout.strip() or "?"
        try:
            annotate_tickets(ids, repo, tgt, sha, advance=args.advance)
        except Exception as e:
            print(f"  ⚠ annotation des tickets interrompue ({e}) — la promotion, elle, est faite")


if __name__ == "__main__":
    main()
