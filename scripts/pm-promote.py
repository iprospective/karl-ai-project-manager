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
import urllib.parse
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

# pm-mr.py (nom à tiret) porte déjà l'auth GitLab, la résolution de projet par
# match EXACT de path_with_namespace (RM2219) et le merge idempotent — réutilisé.
_spec = importlib.util.spec_from_file_location("pm_mr", HERE / "pm-mr.py")
pmmr = importlib.util.module_from_spec(_spec)
sys.modules["pm_mr"] = pmmr
_spec.loader.exec_module(pmmr)
# API_BASE est une globale posée par le main() de pm-mr — requise par pmmr.api().
pmmr.API_BASE = pmmr.base_url() + "/api/v4"

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

    rp = pmmr.repo_path_from_remote(repo)
    token = pmmr.token_for("manager")
    pid, proj = pmmr.resolve_project_id(token, rp)
    print(f"→ projet {proj['path_with_namespace']} (id {pid}) : {src} → {tgt}")

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
    st, lst, _ = pmmr.api("GET", f"/projects/{pid}/merge_requests?source_branch={urllib.parse.quote(src)}"
                                 f"&target_branch={urllib.parse.quote(tgt)}&state=opened", token)
    mr = lst[0] if (st == 200 and isinstance(lst, list) and lst) else None
    if mr:
        print(f"↻ MR déjà ouverte : !{mr['iid']}")
    else:
        title = args.title or f"Promotion PM {src}→{tgt} (lot auto-push, {delta} commit(s))"
        st, mr, raw = pmmr.api("POST", f"/projects/{pid}/merge_requests", token, fields={
            "source_branch": src, "target_branch": tgt, "title": title,
            "description": "Promotion automatique du lot d'auto-commits pm-* (RM2298).",
            "remove_source_branch": "false",
        })
        if not mr:
            st2, lst2, _ = pmmr.api("GET", f"/projects/{pid}/merge_requests?source_branch={urllib.parse.quote(src)}"
                                           f"&target_branch={urllib.parse.quote(tgt)}&state=opened", token)
            mr = lst2[0] if (st2 == 200 and isinstance(lst2, list) and lst2) else None
        if not mr:
            sys.exit(f"ERREUR création MR (HTTP {st}) : {str(raw)[:200]}")
        print(f"✓ MR !{mr['iid']} créée")
    pmmr.merge_mr(pid, mr["iid"], token)


if __name__ == "__main__":
    main()
