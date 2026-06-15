#!/usr/bin/env python3
"""pm-corehist-backfill.py — réinjecte le VRAI historique git dans les repos -core.

La co-location (RM1946) a COPIÉ les fichiers .mmi-pm/.mmi-pm-client sans leur
historique git (les -core sont partis d'un commit « init »). L'historique complet
vit dans le repo ai-projects. Cet outil l'extrait (git-filter-repo, sous-arbre
renommé vers .mmi-pm[-client]/) et le **greffe sous l'état co-localisé actuel** de
chaque -core, puis force-push (--force-with-lease).

Sûr par construction : opère sur des clones temp d'ai-projects (jamais ai-projects
lui-même) ; dans le -core, n'utilise QUE `reset --soft` (HEAD bouge, l'arbre de
travail = la donnée vivante n'est JAMAIS touché) ; vérifie contenu + historique
avant de pousser ; refuse un -core sale.

DRY-RUN par défaut. `--execute` pour appliquer.

Usage :
  pm-corehist-backfill.py [--level project|client|all] [--only SLUG] [--execute]
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

AIPROJ = Path("/zfs/workspaces/ai/project-management/projects").resolve()
WORKSPACES = Path("/zfs/workspaces")
CLIENT_SUBDIRS = ["client", "memory", "projects_used"]
NO_PUSH = False


def git(repo, *args, check=True, capture=True):
    r = subprocess.run(["git", "-C", str(repo), *args],
                       text=True, capture_output=capture)
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} (rc={r.returncode}) : {r.stderr}")
    return r.stdout.strip() if capture else ""


def toplevel(path):
    try:
        return Path(git(path, "rev-parse", "--show-toplevel"))
    except RuntimeError:
        return None


def enumerate_projects():
    """Projets basculés : symlinks clients/<C>/projects/<P> → <ws>/.mmi-pm."""
    out = []
    base = AIPROJ / "clients"
    for client in sorted(base.iterdir()):
        pdir = client / "projects"
        if not pdir.is_dir():
            continue
        for link in sorted(pdir.iterdir()):
            if not link.is_symlink():
                continue  # pm-ai-agents (dossier réel) exclu naturellement
            target = link.resolve()  # <ws>/.mmi-pm
            repo = toplevel(target.parent)
            if repo is None:
                continue
            ai_rel = f"clients/{client.name}/projects/{link.name}"
            out.append({
                "label": f"{client.name}/{link.name}",
                "ai_paths": {ai_rel + "/": ".mmi-pm/"},
                "core": repo,
                "verify_file_glob": ".mmi-pm/tasks/RM*_*.md",
            })
    return out


def enumerate_clients():
    """Niveau client : symlinks clients/<C>/{client,memory,projects_used} →
    <client-ws>/.mmi-pm-client/{...}."""
    out = []
    base = AIPROJ / "clients"
    for client in sorted(base.iterdir()):
        subs = {}
        repo = None
        for sub in CLIENT_SUBDIRS:
            p = client / sub
            if p.is_symlink():
                target = p.resolve()  # <client-ws>/.mmi-pm-client/<sub>
                subs[f"clients/{client.name}/{sub}/"] = f".mmi-pm-client/{sub}/"
                if repo is None:
                    repo = toplevel(target.parent.parent)  # <client-ws>
        if subs and repo is not None:
            out.append({
                "label": f"{client.name} (client-level)",
                "ai_paths": subs,
                "core": repo,
                "verify_file_glob": ".mmi-pm-client/client/overview.md",
            })
    return out


def build_filtered_history(base_clone, ai_paths, workdir):
    """Clone base → filter-repo (garde + renomme les sous-arbres) → retourne le
    chemin du repo filtré + sa branche."""
    work = workdir / "hist"
    git(None if False else base_clone, "clone", "--no-local", "--quiet",
        str(base_clone), str(work))
    args = ["filter-repo", "--force"]
    for src, dst in ai_paths.items():
        args += ["--path", src, "--path-rename", f"{src}:{dst}"]
    git(work, *args)
    branch = git(work, "rev-parse", "--abbrev-ref", "HEAD")
    n = git(work, "rev-list", "--count", "HEAD")
    return work, branch, int(n)


def backfill_one(t, base_clone, dry):
    core = t["core"]
    label = t["label"]
    print(f"\n── {label}  → {core}")
    # garde : -core propre
    status = git(core, "status", "--porcelain")
    if status:
        print(f"   ✗  REFUS : -core a des changements non commités :\n{status}")
        return "dirty"
    # garde DUR : refuser un repo qui tracke autre chose que le PM (repo de
    # contenu/code, ex. calymix-core) — la greffe écraserait son historique réel.
    ALLOWED_TOP = {".mmi-pm", ".mmi-pm-client", ".gitignore"}
    top = set(git(core, "ls-tree", "--name-only", "HEAD").split("\n")) - {""}
    extra = top - ALLOWED_TOP
    if extra:
        print(f"   ✗  REFUS : -core riche en contenu (tracke aussi {sorted(extra)}) "
              f"— greffe d'historique inadaptée, à traiter à part")
        return "content_repo"
    old_head = git(core, "rev-parse", "HEAD")
    n_before = int(git(core, "rev-list", "--count", "HEAD"))

    with tempfile.TemporaryDirectory(prefix="corehist-") as td:
        wd = Path(td)
        hist, branch, n_hist = build_filtered_history(base_clone, t["ai_paths"], wd)
        print(f"   historique extrait : {n_hist} commit(s) (sous {list(t['ai_paths'].values())})")
        if n_hist == 0:
            print("   ⏭  aucun historique extrait — ignoré")
            return "empty"
        if dry:
            print(f"   [DRY-RUN] greffe {n_hist} commit(s) sous l'état actuel + "
                  f"force-push ; -core passerait de {n_before} → ~{n_hist + 1} commits")
            return "dry"

        # Greffe : HEAD → historique filtré (arbre de travail INTACT), puis commit
        # de l'état co-localisé courant par-dessus.
        git(core, "fetch", "--quiet", str(hist), branch)
        fetched = git(core, "rev-parse", "FETCH_HEAD")
        git(core, "reset", "--soft", fetched)
        git(core, "add", "-A")
        # commit même si l'index == arbre filtré (cas rare) : --allow-empty
        env_args = ["-c", "user.name=Mathieu Moulin",
                    "-c", "user.email=mathieu@iprospective.fr"]
        subprocess.run(["git", "-C", str(core), *env_args, "commit", "--allow-empty",
                        "-q", "-m",
                        "chore(coloc): greffe sur l'historique réel ai-projects (RM1949)\n\n"
                        "Réinjecte l'historique git du sous-arbre (extrait via\n"
                        "git-filter-repo) sous l'état co-localisé ; contenu inchangé."],
                       check=True)
    new_head = git(core, "rev-parse", "HEAD")
    n_after = int(git(core, "rev-list", "--count", "HEAD"))

    # ── VÉRIFS ──────────────────────────────────────────────────────────────
    if git(core, "status", "--porcelain"):
        print("   ✗  ÉCHEC : -core sale après greffe (arbre ≠ commit) — PAS de push")
        return "verify_fail"
    # le total doit refléter l'historique filtré + le commit de greffe
    # (idempotent : un re-run redonne le même total, ce n'est PAS un échec).
    if n_after < n_hist:
        print(f"   ✗  ÉCHEC : total {n_after} < historique attendu {n_hist} — PAS de push")
        return "verify_fail"
    # un fichier témoin DOIT avoir un historique multi-commits (preuve de greffe)
    sample = sorted(Path(core).glob(t["verify_file_glob"]))
    sample = [s for s in sample if not s.name.endswith(".log.md")]
    if sample:
        rel = str(sample[0].relative_to(core))
        nh = len(git(core, "log", "--oneline", "--", rel).splitlines())
        print(f"   vérif témoin {Path(rel).name} : {nh} commit(s) d'historique")
        if nh < 2 and n_hist >= 2:
            print("   ✗  ÉCHEC : témoin sans historique malgré extraction — PAS de push")
            return "verify_fail"
    print(f"   ✓  greffé : {n_before} → {n_after} commits (old {old_head[:8]} → {new_head[:8]})")

    # ── PUSH ────────────────────────────────────────────────────────────────
    if NO_PUSH:
        print("   ⏸  push différé (--no-push) — greffe locale en place")
        return "local_ok"
    try:
        git(core, "push", "--force-with-lease")
        print("   ✓  force-push OK")
        return "ok"
    except RuntimeError as e:
        print(f"   ⚠  greffe locale OK mais push KO : {e}")
        return "push_fail"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--level", choices=["project", "client", "all"], default="all")
    ap.add_argument("--only", default=None, help="ne traiter que ce label/slug (substring)")
    ap.add_argument("--execute", action="store_true")
    ap.add_argument("--no-push", action="store_true",
                    help="greffe locale seulement (push distant différé)")
    args = ap.parse_args()
    dry = not args.execute
    global NO_PUSH
    NO_PUSH = args.no_push

    targets = []
    if args.level in ("project", "all"):
        targets += enumerate_projects()
    if args.level in ("client", "all"):
        targets += enumerate_clients()
    if args.only:
        targets = [t for t in targets if args.only in t["label"] or args.only in str(t["core"])]

    print(f"== pm-corehist-backfill — {'DRY-RUN' if dry else 'EXECUTE'} — {len(targets)} repo(s) ==")
    if not targets:
        sys.exit("Aucune cible.")

    # clone de base d'ai-projects (indépendant), réutilisé pour chaque repo
    base_td = tempfile.mkdtemp(prefix="aiproj-base-")
    base_clone = Path(base_td) / "base"
    print(f"   clone base ai-projects → {base_clone}")
    git(AIPROJ, "clone", "--no-local", "--quiet", str(AIPROJ), str(base_clone))

    results = {}
    try:
        for t in targets:
            r = backfill_one(t, base_clone, dry)
            results.setdefault(r, []).append(t["label"])
    finally:
        shutil.rmtree(base_td, ignore_errors=True)

    print("\n== BILAN ==")
    for k in sorted(results):
        print(f"  {k:12} : {len(results[k])}  {results[k] if k!='ok' else ''}")
    if any(k in results for k in ("dirty", "verify_fail", "push_fail")):
        sys.exit(2)


if __name__ == "__main__":
    main()
