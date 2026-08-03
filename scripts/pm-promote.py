#!/usr/bin/env python3
"""pm-promote — promotion par lot intégration → branche protégée (RM2298).

Depuis la protection des branches (RM2030), l'auto-push des scripts pm-* replie
les commits sur la branche d'intégration (`dev`, cf. pm_git). Ce script promeut
le lot vers la branche protégée : MR `dev→main` créée (ou réutilisée si déjà
ouverte) puis mergée avec le PAT *manager* — les données PM ne passent pas par
une revue humaine. Idempotent ; ne touche JAMAIS l'arbre de travail local (pas
de rebase/merge local — invariant pm_git sur arbre partagé dirty).

Usage :
    pm-promote.py [--repo PATH] [--source dev] [--target main]
                  [--title T] [--no-flush] [--dry-run]

--no-flush : ne pousse pas d'abord les commits locaux en attente vers --source.
À lancer en fin de session ou périodiquement (cron) sur les repos de données PM.
"""
import argparse
import importlib.util
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


def _git(repo, *a):
    return subprocess.run(["git", "-C", str(repo), *a], capture_output=True, text=True)


def main():
    ap = argparse.ArgumentParser(description="Promotion par lot intégration → branche protégée (RM2298)")
    ap.add_argument("--repo", default=".", help="repo (défaut : cwd)")
    ap.add_argument("--source", default=None, help="branche d'intégration (défaut : git.integration_branch, dev)")
    ap.add_argument("--target", default="main", help="branche protégée cible (défaut : main)")
    ap.add_argument("--title", default=None)
    ap.add_argument("--no-flush", action="store_true", help="ne pousse pas d'abord les commits locaux vers --source")
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
    if not args.no_flush:
        p = _git(repo, "push", "origin", f"HEAD:{src}")
        if p.returncode == 0:
            print(f"✓ commits locaux poussés → {src}")
        else:
            last = (p.stderr or "").strip().splitlines()[-1] if (p.stderr or "").strip() else "?"
            print(f"  ⚠ flush local → {src} impossible ({last}) — promotion du lot déjà distant seulement")

    # 2. Delta réel à promouvoir (côté remote).
    _git(repo, "fetch", "origin")
    d = _git(repo, "rev-list", "--count", f"origin/{tgt}..origin/{src}")
    delta = int(d.stdout.strip() or 0) if d.returncode == 0 else -1
    if delta == 0:
        print(f"✓ rien à promouvoir ({tgt} contient déjà {src}).")
        return
    print(f"  {delta if delta >= 0 else '?'} commit(s) à promouvoir")
    if args.dry_run:
        print("  (dry-run : ni MR ni merge)")
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


if __name__ == "__main__":
    main()
